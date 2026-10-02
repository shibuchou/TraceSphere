// containers.go: 逐容器 cgroup v2 采样（memory.current/max、oom_kill、cpu.stat）
//
// 为什么需要：RCA 的 container_oom / cpu_contention 规则依赖
//   - memory.current_ratio（current/max）与 container.restart 的容器级证据；
//   - cpu.stat.nr_throttled 的容器级互证。
// 原 event-bridge 的 collect_container_cgroups 已下线（P0-2 直报），这里在 vm-agent 内补齐，
// 保持与平台证据契约（rca/docs/API.md §1 / §5）一致。
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"strings"
	"time"

	"tracesphere/vm-agent/collector"
)

func startContainerCgroupLoop() {
	ticker := time.NewTicker(15 * time.Second)
	for range ticker.C {
		pollContainerCgroups()
	}
}

type containerRef struct {
	id   string
	name string
}

func listRunningContainers() []containerRef {
	out, err := exec.Command("docker", "ps", "--no-trunc", "--format", "{{.ID}}\t{{.Names}}").Output()
	if err != nil {
		return nil
	}
	var refs []containerRef
	for _, line := range strings.Split(strings.TrimSpace(string(out)), "\n") {
		parts := strings.SplitN(line, "\t", 2)
		if len(parts) != 2 || parts[0] == "" {
			continue
		}
		refs = append(refs, containerRef{id: parts[0], name: parts[1]})
	}
	return refs
}

func pollContainerCgroups() {
	for _, ref := range listRunningContainers() {
		cgPath := "/sys/fs/cgroup/system.slice/docker-" + ref.id + ".scope"
		sample, err := collector.ReadCgroup(cgPath)
		if err != nil {
			continue
		}
		ratio := 0.0
		if sample.MemoryMax > 0 && sample.MemoryMax < (1<<62) {
			ratio = float64(sample.MemoryCurrent) / float64(sample.MemoryMax)
		}
		severity := "info"
		if ratio > 0.9 {
			severity = "warning"
		}
		observed := time.Now().UTC().Format(time.RFC3339)
		cgroupName := strings.TrimPrefix(cgPath, "/sys/fs/cgroup")

		// 本地证据文件（stdout → systemd 追加日志）
		local := map[string]interface{}{
			"origin":         "cgroup",
			"type":           "metric",
			"wall":           observed,
			"container_id":   ref.id,
			"name":           ref.name,
			"memory_current": sample.MemoryCurrent,
			"memory_max":     sample.MemoryMax,
			"oom_kills":      sample.OOMKills,
			"nr_throttled":   sample.NRThrottled,
			"throttled_usec": sample.ThrottledUsec,
		}
		if b, err := json.Marshal(local); err == nil {
			fmt.Println(string(b))
		}

		// 直报平台（与 API.md §1 的 cgroup.metric 契约一致；C 侧据此计算
		// memory.current_ratio / nr_throttled 等容器级证据）
		event := map[string]interface{}{
			"event_type":   "cgroup.metric",
			"origin":       "cgroup",
			"mode":         "real",
			"observed_at":  observed,
			"severity":     severity,
			"source":       "vm-agent",
			"container_id": ref.id,
			"attributes":   map[string]interface{}{"name": ref.name, "runtime": "docker"},
			"payload": map[string]interface{}{
				"cgroup":         cgroupName,
				"memory_current": sample.MemoryCurrent,
				"memory_max":     sample.MemoryMax,
				"oom_kills":      sample.OOMKills,
				"nr_throttled":   sample.NRThrottled,
				"throttled_usec": sample.ThrottledUsec,
			},
		}
		if vmUUID := os.Getenv("VMAGENT_VM_UUID"); vmUUID != "" {
			event["vm_uuid"] = vmUUID
		}
		rep.submit(event)
	}
}
