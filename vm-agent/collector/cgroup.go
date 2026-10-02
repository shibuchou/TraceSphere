// Package collector 采集 cgroup v2 与 PSI 指标（无需特权）。
package collector

import (
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

// Sample 为单个 cgroup 的关键资源快照。
type Sample struct {
	CgroupPath    string `json:"cgroup"`
	MemoryCurrent uint64 `json:"memory_current"`
	MemoryMax     uint64 `json:"memory_max"`
	OOMKills      uint64 `json:"oom_kills"`
	NRThrottled   uint64 `json:"nr_throttled"`
	ThrottledUsec uint64 `json:"throttled_usec"`
}

// ReadCgroup 读取 cgroup v2 目录下的 memory / cpu.stat 关键字段。
func ReadCgroup(path string) (Sample, error) {
	s := Sample{CgroupPath: path}

	if v, err := readUint(filepath.Join(path, "memory.current")); err == nil {
		s.MemoryCurrent = v
	} else {
		return s, fmt.Errorf("memory.current: %w", err)
	}
	if v, err := readUint(filepath.Join(path, "memory.max")); err == nil {
		s.MemoryMax = v
	}
	if v, err := readUint(filepath.Join(path, "cpu.stat"), "nr_throttled"); err == nil {
		s.NRThrottled = v
	}
	if v, err := readUint(filepath.Join(path, "cpu.stat"), "throttled_usec"); err == nil {
		s.ThrottledUsec = v
	}
	if v, err := readUint(filepath.Join(path, "memory.events"), "oom_kill"); err == nil {
		s.OOMKills = v
	}
	return s, nil
}

func readUint(file string, keys ...string) (uint64, error) {
	b, err := os.ReadFile(file)
	if err != nil {
		return 0, err
	}
	if len(keys) == 0 {
		return parseUint(strings.TrimSpace(string(b)))
	}
	for _, line := range strings.Split(string(b), "\n") {
		fields := strings.Fields(line)
		if len(fields) == 2 && fields[0] == keys[0] {
			return parseUint(fields[1])
		}
	}
	return 0, fmt.Errorf("key %q not found in %s", keys[0], file)
}

func parseUint(s string) (uint64, error) {
	if s == "max" {
		return ^uint64(0), nil
	}
	return strconv.ParseUint(s, 10, 64)
}
