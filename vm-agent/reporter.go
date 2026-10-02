// reporter: vm-agent 直报器 —— 把事件批量 POST 到平台 /api/v1/events（替换临时 event-bridge）
//
// 设计（方案 §3.2 / API.md §1）：
//   - 本地 stdout 日志始终保留（证据文件 / 故障排查的完整来源）
//   - 上报失败写入本地 spool 文件并后台重试（断网/平台重启不丢数据，上限 200 批）
//   - eBPF 事件按 PID 解析 container_id 并附 VM uuid（跨层关联，identity.go）
//   - 环境变量：VMAGENT_PLATFORM_URL（为空则关闭上报）、VMAGENT_TOKEN、
//     VMAGENT_VM_UUID（给 VM 级证据挂 resource_id）、VMAGENT_REPORT_PROCESS=1（默认关）、
//     VMAGENT_SPOOL_DIR（重试队列目录，默认 /var/lib/tracesphere/vm-agent/spool）
package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"sync/atomic"
	"time"
)

const spoolMaxFiles = 200

type reporter struct {
	endpoint string
	token    string
	ch       chan map[string]interface{}
	client   *http.Client
	spoolDir string
	sent     uint64
	failed   uint64
	dropped  uint64
	retried  uint64
}

var rep *reporter

// initReporter 按环境变量初始化；未配置平台地址时返回 nil（仅本地日志模式）。
func initReporter() *reporter {
	base := os.Getenv("VMAGENT_PLATFORM_URL")
	if base == "" {
		return nil
	}
	r := &reporter{
		endpoint: base + "/api/v1/events",
		token:    os.Getenv("VMAGENT_TOKEN"),
		ch:       make(chan map[string]interface{}, 2048),
		client:   &http.Client{Timeout: 8 * time.Second},
		spoolDir: ensureSpoolDir(),
	}
	go r.loop()
	if r.spoolDir != "" {
		go r.retryLoop()
		log.Printf("reporter enabled: %s (spool=%s)", r.endpoint, r.spoolDir)
	} else {
		log.Printf("reporter enabled: %s (spool disabled)", r.endpoint)
	}
	return r
}

func ensureSpoolDir() string {
	dir := os.Getenv("VMAGENT_SPOOL_DIR")
	if dir == "" {
		dir = "/var/lib/tracesphere/vm-agent/spool"
		if err := os.MkdirAll(dir, 0o755); err != nil {
			dir = filepath.Join(os.TempDir(), "tracesphere-vm-agent-spool")
		}
	}
	if err := os.MkdirAll(dir, 0o755); err != nil {
		log.Printf("WARN spool 目录不可用（%v），失败批次将只保留日志", err)
		return ""
	}
	return dir
}

// submit 非阻塞投递；缓冲满时丢弃（本地日志仍是完整证据源）。
func (r *reporter) submit(event map[string]interface{}) {
	if r == nil {
		return
	}
	select {
	case r.ch <- event:
	default:
		atomic.AddUint64(&r.dropped, 1)
	}
}

func (r *reporter) send(payload []byte) error {
	req, err := http.NewRequest("POST", r.endpoint, bytes.NewReader(payload))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	if r.token != "" {
		req.Header.Set("Authorization", "Bearer "+r.token)
	}
	resp, err := r.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		return fmt.Errorf("HTTP %d", resp.StatusCode)
	}
	return nil
}

// spool 把失败批次落盘，供后台重试（断网/平台重启场景不丢证据）。
func (r *reporter) spool(payload []byte) {
	if r.spoolDir == "" {
		return
	}
	name := filepath.Join(r.spoolDir, fmt.Sprintf("%019d.json", time.Now().UnixNano()))
	if err := os.WriteFile(name, payload, 0o640); err != nil {
		log.Printf("WARN spool 写入失败: %v", err)
		return
	}
	entries, err := filepath.Glob(filepath.Join(r.spoolDir, "*.json"))
	if err != nil || len(entries) <= spoolMaxFiles {
		return
	}
	sort.Strings(entries)
	for _, old := range entries[:len(entries)-spoolMaxFiles] {
		_ = os.Remove(old)
	}
}

func (r *reporter) retryLoop() {
	ticker := time.NewTicker(30 * time.Second)
	for range ticker.C {
		entries, err := filepath.Glob(filepath.Join(r.spoolDir, "*.json"))
		if err != nil || len(entries) == 0 {
			continue
		}
		sort.Strings(entries)
		for i, path := range entries {
			if i >= 50 {
				break
			}
			payload, err := os.ReadFile(path)
			if err != nil {
				continue
			}
			if err := r.send(payload); err != nil {
				break // 平台仍不可用：保留剩余批次，下一轮再试
			}
			_ = os.Remove(path)
			atomic.AddUint64(&r.retried, 1)
		}
	}
}

func (r *reporter) loop() {
	ticker := time.NewTicker(2 * time.Second)
	batch := make([]map[string]interface{}, 0, 128)
	flush := func() {
		if len(batch) == 0 {
			return
		}
		count := len(batch)
		payload, err := json.Marshal(map[string]interface{}{"events": batch})
		batch = batch[:0]
		if err != nil {
			return
		}
		if err := r.send(payload); err != nil {
			atomic.AddUint64(&r.failed, uint64(count))
			r.spool(payload)
			log.Printf("WARN 上报失败（%v），已写入重试队列（%d 条）", err, count)
			return
		}
		atomic.AddUint64(&r.sent, uint64(count))
	}
	for {
		select {
		case ev := <-r.ch:
			batch = append(batch, ev)
			if len(batch) >= 128 {
				flush()
			}
		case <-ticker.C:
			flush()
		}
	}
}

// reportEnabledProcess 是否上报高频进程事件（默认关闭，避免事件量过大）。
func reportEnabledProcess() bool {
	return os.Getenv("VMAGENT_REPORT_PROCESS") == "1"
}

// mappedEBPFEvent 把 eBPF 原始事件映射为平台契约事件（与 API.md §1 信号表一致）。
//
// 跨层关联：按 PID 解析 container_id（identity.go），并附 VM uuid，
// 平台 ingest 会把事件挂到对应容器资源（12 位短 ID 自动前缀归一）。
func mappedEBPFEvent(origin string, ev event) (map[string]interface{}, bool) {
	base := map[string]interface{}{
		"mode":        "real",
		"observed_at": time.Now().UTC().Format(time.RFC3339),
		"source":      "vm-agent",
		"attributes":  map[string]interface{}{"pid": ev.PID, "comm": commString(ev.Comm)},
	}
	if id := containerForPID(ev.PID); id != "" {
		base["container_id"] = id
	}
	if vm := os.Getenv("VMAGENT_VM_UUID"); vm != "" {
		base["vm_uuid"] = vm
	}
	switch origin {
	case "oom":
		base["event_type"] = "oom.ebpf"
		base["origin"] = "ebpf"
		base["severity"] = "critical"
	case "tcp":
		base["event_type"] = "tcp.retransmit"
		base["origin"] = "ebpf"
		base["severity"] = "warning"
	case "process":
		if !reportEnabledProcess() {
			return nil, false
		}
		if ev.Kind == kindExec {
			base["event_type"] = "process.exec"
		} else {
			base["event_type"] = "process.exit"
		}
		base["origin"] = "ebpf"
		base["severity"] = "info"
	default:
		return nil, false
	}
	return base, true
}
