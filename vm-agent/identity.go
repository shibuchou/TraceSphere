// identity.go: eBPF 事件的进程 → 容器身份映射（跨层关联的关键一环）。
//
// 背景：eBPF 事件只带 PID/comm；若不上报 container_id，平台侧会生成孤立事件，
// 无法与容器 cgroup 证据/Agent 任务证据关联（方案 §5.2 资源关联）。
// 这里在事件上报时按 /proc/<pid>/cgroup 解析容器 ID（带 60s 缓存），
// 平台 ingest 会把 12 位短 ID 前缀归一到 64 位容器资源。
package main

import (
	"os"
	"regexp"
	"strconv"
	"sync"
	"time"
)

var containerIDPatterns = []*regexp.Regexp{
	// systemd scope：/system.slice/docker-<id>.scope、cri-containerd-<id>.scope
	regexp.MustCompile(`(?:docker-|cri-containerd-|containerd-)([0-9a-f]{12,64})\.scope`),
	// cgroupfs / containerd：.../docker/<id>、.../containerd/<id>
	regexp.MustCompile(`/(?:docker|containerd)/([0-9a-f]{12,64})(?:/|$)`),
	// 兜底：任意 64 位 hex 段（Docker cgroupfs、k8s pod 子 cgroup 等）
	regexp.MustCompile(`(?:^|/)([0-9a-f]{64})(?:/|$)`),
}

type identEntry struct {
	containerID string
	ts          time.Time
}

var identCache = struct {
	mu sync.Mutex
	m  map[uint32]identEntry
}{m: map[uint32]identEntry{}}

// containerForPID 解析 PID 所属容器 ID（失败返回空串）；结果缓存 60s。
func containerForPID(pid uint32) string {
	if pid == 0 {
		return ""
	}
	identCache.mu.Lock()
	if e, ok := identCache.m[pid]; ok && time.Since(e.ts) < 60*time.Second {
		identCache.mu.Unlock()
		return e.containerID
	}
	identCache.mu.Unlock()

	id := readContainerID(pid)

	identCache.mu.Lock()
	if len(identCache.m) > 4096 {
		identCache.m = map[uint32]identEntry{}
	}
	identCache.m[pid] = identEntry{containerID: id, ts: time.Now()}
	identCache.mu.Unlock()
	return id
}

func readContainerID(pid uint32) string {
	raw, err := os.ReadFile("/proc/" + strconv.FormatUint(uint64(pid), 10) + "/cgroup")
	if err != nil {
		return ""
	}
	text := string(raw)
	for _, re := range containerIDPatterns {
		if m := re.FindStringSubmatch(text); len(m) > 1 {
			return m[1]
		}
	}
	return ""
}
