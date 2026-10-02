// vm-agent: TraceSphere VM 内轻量探针
// 采集：eBPF 内核事件（进程生命周期 / OOM / TCP 重传） + cgroup v2 / PSI 指标
// 输出：结构化 JSON 事件（stdout），由 systemd 追加写入日志文件，供平台侧 Event Ingest 采集。
// 容错：eBPF 加载/attach 失败时自动进入降级模式（仅 PSI/cgroup 轮询采集），保持同一事件 Schema。
package main

import (
	"bytes"
	"encoding/binary"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/cilium/ebpf"
	"github.com/cilium/ebpf/link"
	"github.com/cilium/ebpf/ringbuf"
	"github.com/cilium/ebpf/rlimit"

	"tracesphere/vm-agent/collector"
)

const (
	kindExec       = 1
	kindExit       = 2
	kindOOMKill    = 3
	kindRetransmit = 4
)

// event 与 bpf/*.bpf.c 中的 struct event 二进制布局一致
type event struct {
	TS   uint64
	PID  uint32
	Kind uint32
	Comm [16]int8
}

func main() {
	rep = initReporter()

	cleanup, attached, failed := setupProbes()
	defer cleanup()
	if len(failed) > 0 {
		log.Printf("WARN 部分 eBPF 探针不可用：%s", strings.Join(failed, "; "))
	}
	degraded := len(attached) == 0

	go startMetricLoop()
	go startJournalOOMPoll()
	go startContainerCgroupLoop()

	if degraded {
		log.Printf("vm-agent started in DEGRADED mode: PSI/cgroup metrics only")
	} else {
		log.Printf("vm-agent started: eBPF probes attached (%s)", strings.Join(attached, ", "))
	}

	sig := make(chan os.Signal, 1)
	signal.Notify(sig, syscall.SIGINT, syscall.SIGTERM)
	<-sig
	log.Println("vm-agent shutting down")
}

// setupProbes 逐项加载/挂载 eBPF 探针：单个失败只跳过该项（逐能力降级），
// 全部失败时 attached 为空，调用方进入仅 PSI/cgroup 的全降级模式。
func setupProbes() (cleanup func(), attached []string, failed []string) {
	cleanups := []func(){}
	cleanup = func() {
		for i := len(cleanups) - 1; i >= 0; i-- {
			cleanups[i]()
		}
	}
	if err := rlimit.RemoveMemlock(); err != nil {
		failed = append(failed, "memlock: "+err.Error())
		return cleanup, attached, failed
	}

	var pObj processObjects
	if err := loadProcessObjects(&pObj, nil); err != nil {
		failed = append(failed, "load process: "+err.Error())
	} else {
		if l, err := link.Tracepoint("sched", "sched_process_exec", pObj.HandleExec, nil); err != nil {
			failed = append(failed, "attach exec: "+err.Error())
		} else {
			cleanups = append(cleanups, func() { l.Close() })
			attached = append(attached, "sched_process_exec")
		}
		if l, err := link.Tracepoint("sched", "sched_process_exit", pObj.HandleExit, nil); err != nil {
			failed = append(failed, "attach exit: "+err.Error())
		} else {
			cleanups = append(cleanups, func() { l.Close() })
			attached = append(attached, "sched_process_exit")
		}
		go readEvents("process", pObj.Events)
		cleanups = append(cleanups, func() { pObj.Close() })
	}

	var oObj oomObjects
	if err := loadOomObjects(&oObj, nil); err != nil {
		failed = append(failed, "load oom: "+err.Error())
	} else {
		if l, err := link.Tracepoint("oom", "mark_victim", oObj.HandleOom, nil); err != nil {
			failed = append(failed, "attach oom: "+err.Error())
		} else {
			cleanups = append(cleanups, func() { l.Close() })
			attached = append(attached, "oom:mark_victim")
		}
		go readEvents("oom", oObj.Events)
		cleanups = append(cleanups, func() { oObj.Close() })
	}

	var tObj tcpObjects
	if err := loadTcpObjects(&tObj, nil); err != nil {
		failed = append(failed, "load tcp: "+err.Error())
	} else {
		if l, err := link.Tracepoint("tcp", "tcp_retransmit_skb", tObj.HandleRetransmit, nil); err != nil {
			failed = append(failed, "attach tcp: "+err.Error())
		} else {
			cleanups = append(cleanups, func() { l.Close() })
			attached = append(attached, "tcp:tcp_retransmit_skb")
		}
		go readEvents("tcp", tObj.Events)
		cleanups = append(cleanups, func() { tObj.Close() })
	}

	return cleanup, attached, failed
}

func readEvents(origin string, m *ebpf.Map) {
	rd, err := ringbuf.NewReader(m)
	if err != nil {
		log.Fatalf("ringbuf %s: %v", origin, err)
	}
	defer rd.Close()

	for {
		rec, err := rd.Read()
		if err != nil {
			if errors.Is(err, ringbuf.ErrClosed) {
				return
			}
			log.Printf("read ringbuf %s: %v", origin, err)
			continue
		}

		var ev event
		if err := binary.Read(bytes.NewReader(rec.RawSample), binary.LittleEndian, &ev); err != nil {
			log.Printf("decode event %s: %v", origin, err)
			continue
		}

		out, err := json.Marshal(map[string]interface{}{
			"origin": origin,
			"ts":     ev.TS,
			"wall":   time.Now().UTC().Format(time.RFC3339),
			"pid":    ev.PID,
			"kind":   ev.Kind,
			"comm":   commString(ev.Comm),
		})
		if err != nil {
			continue
		}
		fmt.Println(string(out))

		if mapped, ok := mappedEBPFEvent(origin, ev); ok {
			rep.submit(mapped)
		}
	}
}

func commString(b [16]int8) string {
	n := 0
	for n < len(b) && b[n] != 0 {
		n++
	}
	buf := make([]byte, n)
	for i := 0; i < n; i++ {
		buf[i] = byte(b[i])
	}
	return string(buf)
}

// startMetricLoop 每 5s 输出一次 PSI / cgroup 指标（JSON 行）
// 环境变量 VMAGENT_CGROUP 可指定额外采集的 cgroup v2 路径（如某容器的 docker scope）
func startMetricLoop() {
	cgroupPath := os.Getenv("VMAGENT_CGROUP")
	ticker := time.NewTicker(5 * time.Second)
	for range ticker.C {
		m := map[string]interface{}{
			"origin": "cgroup",
			"type":   "metric",
			"ts":     uint64(time.Now().UnixNano()),
		}
		if p, err := collector.ReadPSI("cpu"); err == nil {
			m["psi_cpu_some_avg10"] = p.SomeAvg10
			m["psi_cpu_full_avg10"] = p.FullAvg10
		}
		if p, err := collector.ReadPSI("memory"); err == nil {
			m["psi_mem_some_avg10"] = p.SomeAvg10
			m["psi_mem_full_avg10"] = p.FullAvg10
		}
		if p, err := collector.ReadPSI("io"); err == nil {
			m["psi_io_some_avg10"] = p.SomeAvg10
		}
		if cgroupPath != "" {
			if s, err := collector.ReadCgroup(cgroupPath); err == nil {
				m["cgroup"] = s
			}
		}
		if b, err := json.Marshal(m); err == nil {
			fmt.Println(string(b))
		}
		// 直报平台（cgroup.metric；resource_id 指向 VM，供 RCA 的 PSI 证据匹配）
		report := map[string]interface{}{
			"event_type":  "cgroup.metric",
			"origin":      "cgroup",
			"mode":        "real",
			"observed_at": time.Now().UTC().Format(time.RFC3339),
			"source":      "vm-agent",
			"severity":    "info",
		}
		if vmUUID := os.Getenv("VMAGENT_VM_UUID"); vmUUID != "" {
			report["resource_id"] = "vm:" + vmUUID
		}
		for k, v := range m {
			if k == "origin" || k == "type" || k == "ts" {
				continue
			}
			report[k] = v
		}
		if cpu, ok := m["psi_cpu_some_avg10"].(float64); ok && cpu > 5 {
			report["severity"] = "warning"
		}
		rep.submit(report)
	}
}
