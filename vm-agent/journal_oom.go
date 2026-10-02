// journal_oom.go: 内核 OOM 日志轮询（Case 1 主判据来源）
//
// 为什么需要它（方案 §7 Case1）：
//   - cAdvisor v0.49.1 的 container_oom_events_total 在本环境恒为 0；
//   - 容器自身 cgroup 的 memory.events.oom_kill 在容器重启后归零；
//   - 只有内核 OOM 记录同时给出**容器归属**（oom_memcg=/system.slice/docker-<id>.scope）、
//     被杀进程与精确时间。vm-agent 以 root 运行（systemd），直接轮询 journalctl -k 解析。
//
// 事件同时写 stdout（本地证据文件）并直报平台（event_type=memory.events.oom_kill）。
package main

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
	"os/exec"
	"regexp"
	"strings"
	"time"
)

var (
	oomMemcgRe = regexp.MustCompile(`oom_memcg=/system\.slice/docker-([0-9a-f]{64})\.scope`)
	oomPidRe   = regexp.MustCompile(`\bpid=(\d+)`)
	oomTaskRe  = regexp.MustCompile(`\btask=([^,\s]+)`)
	// journalOOMStart：进程启动时刻；早于该时刻的内核 OOM 只标记去重、不上报，
	// 避免重启后把历史 OOM 回放成新事件（污染新建立基线/其他场景的诊断）。
	journalOOMStart = time.Now()
)

type journalEntry struct {
	Message          interface{} `json:"MESSAGE"`
	RealtimeTimestamp string    `json:"__REALTIME_TIMESTAMP"`
}

func startJournalOOMPoll() {
	journalOOMStart = time.Now()
	seen := map[string]time.Time{}
	ticker := time.NewTicker(15 * time.Second)
	for range ticker.C {
		pollKernelOOM(seen)
		// 清理 30 分钟前的去重记录
		cutoff := time.Now().Add(-30 * time.Minute)
		for key, at := range seen {
			if at.Before(cutoff) {
				delete(seen, key)
			}
		}
	}
}

func pollKernelOOM(seen map[string]time.Time) {
	out, err := exec.Command("journalctl", "-k", "-o", "json", "--since", "-90s", "--no-pager").Output()
	if err != nil {
		return
	}
	for _, line := range strings.Split(string(out), "\n") {
		line = strings.TrimSpace(line)
		if !strings.HasPrefix(line, "{") {
			continue
		}
		var entry journalEntry
		if err := json.Unmarshal([]byte(line), &entry); err != nil {
			continue
		}
		message := ""
		switch v := entry.Message.(type) {
		case string:
			message = v
		case []interface{}:
			parts := make([]string, 0, len(v))
			for _, part := range v {
				parts = append(parts, fmt.Sprintf("%v", part))
			}
			message = strings.Join(parts, " ")
		default:
			continue
		}
		if !strings.Contains(message, "oom_memcg=") {
			continue
		}
		match := oomMemcgRe.FindStringSubmatch(message)
		if match == nil {
			continue
		}
		containerID := match[1]
		pid := "0"
		if m := oomPidRe.FindStringSubmatch(message); m != nil {
			pid = m[1]
		}
		task := ""
		if m := oomTaskRe.FindStringSubmatch(message); m != nil {
			task = m[1]
		}
		key := containerID + ":" + pid
		if _, ok := seen[key]; ok {
			continue
		}

		observed := time.Now().UTC()
		if entry.RealtimeTimestamp != "" {
			var micros int64
			if _, err := fmt.Sscanf(entry.RealtimeTimestamp, "%d", &micros); err == nil && micros > 0 {
				observed = time.Unix(0, micros*1000).UTC()
			}
		}
		// 历史 OOM（进程启动前）：只标记去重，不上报，避免重启回放污染基线
		if observed.Before(journalOOMStart) {
			seen[key] = time.Now()
			continue
		}
		seen[key] = time.Now()

		observedStr := observed.Format(time.RFC3339)

		// 本地证据文件（stdout → systemd 追加日志）
		local := map[string]interface{}{
			"origin":      "journal",
			"type":        "event",
			"wall":        observedStr,
			"event_type":  "memory.events.oom_kill",
			"container_id": containerID,
			"severity":    "critical",
			"pid":         pid,
			"comm":        task,
		}
		if b, err := json.Marshal(local); err == nil {
			fmt.Println(string(b))
		}
		log.Printf("kernel OOM: container=%s pid=%s task=%s", containerID[:12], pid, task)

		// 直报平台（容器归属 + 精确时间 + 被杀进程）
		report := map[string]interface{}{
			"event_type":   "memory.events.oom_kill",
			"origin":       "cgroup",
			"mode":         "real",
			"observed_at":  observedStr,
			"severity":     "critical",
			"source":       "kernel",
			"value":        1,
			"container_id": containerID,
			"attributes": map[string]interface{}{
				"pid": pid, "comm": task, "memcg": "docker-" + containerID[:12] + ".scope",
			},
			"payload": map[string]interface{}{
				"delta":    1,
				"unit":     "count",
				"task":     task,
				"pid":      pid,
				"memcg":    "docker-" + containerID[:12] + ".scope",
				"evidence": "kernel oom-kill log (vm-agent journal poll)",
			},
		}
		if vmUUID := os.Getenv("VMAGENT_VM_UUID"); vmUUID != "" {
			report["vm_uuid"] = vmUUID
		}
		rep.submit(report)
	}
}
