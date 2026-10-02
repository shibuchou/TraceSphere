package source

import (
	"fmt"
	"math"
	"sort"
	"strings"
	"time"

	"tracesphere/rca/internal/model"
)

// PlatformEvent 对齐 B 的 events 表行（`platform/tsplatform/schema.py` SCHEMA_FIELDS + 平台扩展列）。
type PlatformEvent struct {
	EventID       string         `json:"event_id"`
	SchemaVersion string         `json:"schema_version"`
	Origin        string         `json:"origin"`
	Mode          string         `json:"mode"`
	ObservedAt    model.TSTime   `json:"observed_at"`
	IngestedAt    model.TSTime   `json:"ingested_at"`
	Type          string         `json:"type"`
	EventType     string         `json:"event_type"`
	ResourceID    string         `json:"resource_id"`
	CorrelationID string         `json:"correlation_id"`
	TraceID       string         `json:"trace_id"`
	TaskID        string         `json:"task_id"`
	Severity      string         `json:"severity"`
	Source        string         `json:"source"`
	ClusterID     string         `json:"cluster_id"`
	Payload       map[string]any `json:"payload"`
}

// EventToEvidence 把 B 的事件归一化为 C 的证据条目。
//
// 兼容三种入库格式（平台 README §事件入库支持的三种格式）：
//  1. AppEvent（task.* / tool.* / inference.*，带 correlation_id）
//  2. Schema v1 完整事件
//  3. vm-agent 松散事件（eBPF 事件 + 每 5s 的 PSI/cgroup 指标行）
func EventToEvidence(ev PlatformEvent, idx *ResourceIndex) []model.Evidence {
	origin := ev.Origin
	if origin == "" {
		origin = "app"
	}
	layer := idx.Layer(origin, ev.ResourceID)
	kind := KindForOrigin(origin)
	severity := model.Severity(ev.Severity)
	if ev.Severity == "" {
		severity = severityFromStatus(ev.Payload)
	}
	signal := strings.TrimSpace(ev.EventType)

	base := model.Evidence{
		EvidenceID:     evidenceID("evt", ev.EventID),
		Signal:         signal,
		Kind:           kind,
		Layer:          layer,
		ResourceID:     ev.ResourceID,
		ResourceName:   idx.Name(ev.ResourceID),
		CorrelationID:  ev.CorrelationID,
		TaskID:         ev.TaskID,
		ObservedAt:     ev.ObservedAt,
		Severity:       severity,
		Description:    describe(ev, idx),
		SourceEventIDs: compact([]string{ev.EventID}),
		Origin:         origin,
		Mode:           ev.Mode,
		Payload:        ev.Payload,
	}

	// vm-agent 的 PSI / cgroup 指标行：一条事件里可能带多个信号
	if signals := metricSignalsFromPayload(ev.Payload); len(signals) > 0 {
		out := make([]model.Evidence, 0, len(signals)+1)
		for _, item := range signals {
			item.EvidenceID = evidenceID("m", ev.EventID+"|"+item.Signal)
			item.Layer = layer
			item.ResourceID = ev.ResourceID
			item.ResourceName = idx.Name(ev.ResourceID)
			item.CorrelationID = ev.CorrelationID
			item.ObservedAt = ev.ObservedAt
			item.Origin = origin
			item.Mode = ev.Mode
			if item.Kind == "" {
				item.Kind = KindForOrigin(origin)
			}
			out = append(out, item)
		}
		if len(base.Payload) > 0 && base.Signal != "" && base.Signal != "unknown" {
			out = append(out, base)
		}
		return out
	}

	if base.Signal == "" || base.Signal == "unknown" {
		base.Signal = fallbackSignal(ev)
	}
	for _, key := range []string{"value", "delta", "duration_ms"} {
		if v := numeric(ev.Payload[key]); v != nil {
			base.Value = v
			switch key {
			case "duration_ms":
				base.Unit = "ms"
			default:
				base.Unit = "count"
			}
			break
		}
	}
	if v := numeric(ev.Payload["latency_ms"]); v != nil {
		base.Value = v
		base.Unit = "ms"
	}
	return []model.Evidence{base}
}

func describe(ev PlatformEvent, idx *ResourceIndex) string {
	parts := []string{ev.EventType}
	if ev.Origin != "" {
		parts[0] = fmt.Sprintf("%s [%s]", ev.EventType, ev.Origin)
	}
	if ev.ResourceID != "" {
		parts = append(parts, "on "+idx.Name(ev.ResourceID))
	}
	if status := text(ev.Payload["status"]); status != "" {
		parts = append(parts, "status="+status)
	}
	for _, key := range []string{"reason", "error", "answer"} {
		if v := text(ev.Payload[key]); v != "" {
			parts = append(parts, fmt.Sprintf("%s=%s", key, truncate(v, 160)))
			break
		}
	}
	if ev.Severity != "" {
		parts = append(parts, "severity="+ev.Severity)
	}
	return strings.Join(parts, " ")
}

func fallbackSignal(ev PlatformEvent) string {
	if ev.Source != "" {
		return ev.Source + ".event"
	}
	return "unknown"
}

// metricSignalsFromPayload 从 vm-agent 指标行/ cgroup 样本里提取信号（一条事件 → 多条证据）。
func metricSignalsFromPayload(payload map[string]any) []model.Evidence {
	if len(payload) == 0 {
		return nil
	}
	var out []model.Evidence
	for _, key := range []string{"psi_cpu_some_avg10", "psi_cpu_full_avg10", "psi_mem_some_avg10", "psi_mem_full_avg10", "psi_io_some_avg10", "psi_io_full_avg10"} {
		if v := numeric(payload[key]); v != nil {
			out = append(out, model.Evidence{
				Signal: key, Value: v, Unit: "percent",
				Severity:    psiSeverity(key, *v),
				Description: fmt.Sprintf("%s=%.2f", key, *v),
			})
		}
	}
	// Mock DCGM（无 GPU 降级的模拟显存指标，赛题 §4）：一条 gpu.metric 事件 → 显存占用率证据
	if v := numeric(payload["gpu_memory_used_ratio"]); v != nil {
		ratio := *v
		desc := fmt.Sprintf("GPU 显存占用率=%.1f%%", ratio*100)
		if used := numeric(payload["gpu_memory_used_bytes"]); used != nil {
			if total := numeric(payload["gpu_memory_total_bytes"]); total != nil && *total > 0 {
				desc = fmt.Sprintf("GPU 显存占用=%.2f/%.2f GiB（%.1f%%）", *used/(1<<30), *total/(1<<30), ratio*100)
			}
		}
		out = append(out, model.Evidence{
			Signal: "gpu.memory_used_ratio", Value: &ratio, Unit: "ratio",
			Severity: ratioSeverity(ratio), Description: desc,
			Payload: map[string]any{
				"gpu_memory_used_bytes":  deref(numeric(payload["gpu_memory_used_bytes"])),
				"gpu_memory_total_bytes": deref(numeric(payload["gpu_memory_total_bytes"])),
			},
		})
	}
	if cgroup, ok := payload["cgroup"].(map[string]any); ok && len(cgroup) > 0 {
		current := numeric(cgroup["memory_current"])
		limit := numeric(cgroup["memory_max"])
		if current != nil {
			ratio := 0.0
			desc := fmt.Sprintf("memory.current=%.0f", *current)
			if limit != nil && *limit > 0 && *limit < 1e15 {
				ratio = *current / *limit
				desc = fmt.Sprintf("memory.current/max=%.3f（%.0f/%.0f）", ratio, *current, *limit)
			}
			out = append(out, model.Evidence{
				Signal: "memory.current_ratio", Value: &ratio, Unit: "ratio",
				Severity: ratioSeverity(ratio), Description: desc,
				Payload: map[string]any{"memory_current": *current, "memory_max": deref(limit)},
			})
		}
		if v := numeric(cgroup["oom_kills"]); v != nil {
			out = append(out, model.Evidence{
				Signal: "memory.events.oom_kill", Value: v, Unit: "cumulative_count",
				Severity: "critical", Description: fmt.Sprintf("memory.events.oom_kill=%d（累计）", int64(*v)),
				Payload: map[string]any{"cumulative": true},
			})
		}
		if v := numeric(cgroup["nr_throttled"]); v != nil {
			out = append(out, model.Evidence{
				Signal: "cpu.stat.nr_throttled", Value: v, Unit: "cumulative_count",
				Severity: "warning", Description: fmt.Sprintf("cpu.stat.nr_throttled=%d（累计）", int64(*v)),
				Payload: map[string]any{"cumulative": true},
			})
		}
		if v := numeric(cgroup["throttled_usec"]); v != nil {
			out = append(out, model.Evidence{
				Signal: "cpu.stat.throttled_usec", Value: v, Unit: "cumulative_count",
				Severity: "warning", Description: fmt.Sprintf("cpu.stat.throttled_usec=%d（累计）", int64(*v)),
				Payload: map[string]any{"cumulative": true},
			})
		}
	}
	return out
}

// NormalizeCounters 把累计计数器样本转成窗口内增量证据（只保留 Δ>0 的条目）。
//
// 规则里的 `require_increase: true` 语义是"窗口内出现增量"，因此这里先做差。
func NormalizeCounters(items []model.Evidence) []model.Evidence {
	type key struct{ signal, resource string }
	groups := map[key][]model.Evidence{}
	var out []model.Evidence
	for _, item := range items {
		cumulative, _ := item.Payload["cumulative"].(bool)
		if !cumulative || item.Value == nil {
			out = append(out, item)
			continue
		}
		k := key{item.Signal, item.ResourceID}
		groups[k] = append(groups[k], item)
	}
	for k, group := range groups {
		sort.SliceStable(group, func(i, j int) bool {
			return group[i].ObservedAt.Before(group[j].ObservedAt.Time)
		})
		var prev *float64
		for _, item := range group {
			value := *item.Value
			delta := value
			if prev != nil {
				delta = value - *prev
			}
			v := value
			prev = &v
			if delta <= 0 {
				continue
			}
			deltaCopy := delta
			item.Value = &deltaCopy
			item.Unit = "count"
			item.Signal = k.signal
			item.Description = fmt.Sprintf("%s Δ=%.0f（%s）", k.signal, delta, item.ObservedAt.UTC().Format(time.RFC3339))
			delete(item.Payload, "cumulative")
			out = append(out, item)
		}
	}
	return out
}

// AddLatencyP95 由 `inference.result` 的 duration_ms 计算窗口内 P95 延迟证据。
//
// llama.cpp 的 /metrics 未暴露延迟直方图（只有 tokens 计数），因此推理延迟采用
// agent-service AppEvent 的实测 duration_ms（真实、可复现，方案 §7 Case2 验收口径）。
func AddLatencyP95(items []model.Evidence) []model.Evidence {
	type key struct{ resource string }
	groups := map[key][]float64{}
	meta := map[key]model.Evidence{}
	for _, item := range items {
		if !strings.EqualFold(item.Signal, "inference.result") || item.Value == nil {
			continue
		}
		k := key{item.ResourceID}
		groups[k] = append(groups[k], *item.Value)
		if _, ok := meta[k]; !ok {
			meta[k] = item
		}
	}
	out := items
	for k, values := range groups {
		if len(values) == 0 {
			continue
		}
		p95 := percentile(values, 95)
		base := meta[k]
		base.EvidenceID = evidenceID("agg", base.ResourceID+"|p95")
		base.Signal = "llama_latency_p95_ms"
		base.Value = &p95
		base.Unit = "ms"
		base.Kind = "app_event"
		base.Severity = latencySeverity(p95)
		base.Description = fmt.Sprintf("推理延迟 P95=%.0f ms（%d 次推理请求）", p95, len(values))
		out = append(out, base)
	}
	return out
}

// 计数型（窗口内取增量合计）与指标型（窗口内取峰值）信号分类。
var (
	counterSignals = map[string]bool{
		"memory.events.oom_kill":    true,
		"cpu.stat.nr_throttled":     true,
		"cpu.stat.throttled_usec":   true,
		"container.restart":         true,
		"cpu.cfs.throttled_periods": true,
	}
	gaugeSignals = map[string]bool{
		"memory.current_ratio":  true,
		"container.cpu_pct":     true,
		"llama_latency_p95_ms":  true,
		"llamacpp.tokens_per_s": true,
		"gpu.memory_used_ratio": true,
	}
	// 基础设施噪声信号：不作为证据（容器发现、进程 exec/exit、原始 cgroup 采样行——
	// 后者的有效内容已抽取为 psi_* / memory.current_ratio / memory.events.oom_kill 等信号；
	// gpu.metric 采样行的有效内容同理已抽取为 gpu.memory_used_ratio）
	noisySignals = map[string]bool{
		"container.discovered": true,
		"process.exec":         true,
		"process.exit":         true,
		"cgroup.metric":        true,
		"gpu.metric":           true,
	}
)

// Condense 合并同类证据，保证证据链可读（评审要求"证据链清晰、可追溯"）。
//
//   - 计数型信号：按资源合并为一条，value = 窗口内增量合计（附采样命中次数）；
//   - 指标型信号（含 PSI）：按资源保留窗口内峰值；
//   - 零值计数与基础设施噪声（container.discovered / process.*）直接丢弃。
//
// 合并不丢信息：source_event_ids 与 payload.samples 都保留。
func Condense(items []model.Evidence) []model.Evidence {
	type key struct{ signal, resource string }
	counters := map[key][]model.Evidence{}
	gauges := map[key]model.Evidence{}
	var out []model.Evidence

	for _, item := range items {
		signal := strings.ToLower(item.Signal)
		if noisySignals[signal] {
			continue
		}
		if counterSignals[signal] {
			if item.Value != nil && *item.Value <= 0 {
				continue
			}
			k := key{item.Signal, item.ResourceID}
			counters[k] = append(counters[k], item)
			continue
		}
		if gaugeSignals[signal] || strings.HasPrefix(signal, "psi_") {
			if item.Value == nil {
				continue
			}
			k := key{item.Signal, item.ResourceID}
			if existing, ok := gauges[k]; !ok || *existing.Value < *item.Value {
				gauges[k] = item
			}
			continue
		}
		out = append(out, item)
	}

	for k, group := range counters {
		merged := group[0]
		total := 0.0
		quantified := false
		var ids []string
		for _, item := range group {
			if item.Value != nil {
				total += *item.Value
				quantified = true
			}
			ids = append(ids, item.SourceEventIDs...)
			if item.ObservedAt.Before(merged.ObservedAt.Time) {
				merged.ObservedAt = item.ObservedAt
			}
			merged.Severity = model.MaxSeverity(merged.Severity, item.Severity)
		}
		merged.SourceEventIDs = ids
		if quantified {
			value := total
			merged.Value = &value
			merged.Description = fmt.Sprintf("%s 窗口内合计 Δ=%.0f（%d 次采样命中）", k.signal, total, len(group))
		} else {
			// 离散事件（如内核 OOM 日志 / docker OOMKilled）：无数值，保留出现即证据的语义
			merged.Value = nil
			merged.Description = fmt.Sprintf("%s 窗口内出现 %d 次（离散事件，无数值）", k.signal, len(group))
		}
		if merged.Payload == nil {
			merged.Payload = map[string]any{}
		}
		merged.Payload["samples"] = len(group)
		out = append(out, merged)
	}
	for _, item := range gauges {
		if item.Value == nil {
			continue
		}
		value := *item.Value
		item.Description = fmt.Sprintf("%s（窗口峰值 %.4g%s）", item.Signal, value, unitSuffix(item.Unit))
		out = append(out, item)
	}
	return out
}

func unitSuffix(unit string) string {
	if unit == "" {
		return ""
	}
	return " " + unit
}

func percentile(values []float64, p float64) float64 {
	if len(values) == 0 {
		return 0
	}
	sorted := append([]float64(nil), values...)
	sort.Float64s(sorted)
	if len(sorted) == 1 {
		return sorted[0]
	}
	rank := (p / 100) * float64(len(sorted)-1)
	lower := int(math.Floor(rank))
	upper := int(math.Ceil(rank))
	if lower == upper {
		return sorted[lower]
	}
	weight := rank - float64(lower)
	return sorted[lower]*(1-weight) + sorted[upper]*weight
}

// ---------------------------------------------------------------------------
// 小工具
// ---------------------------------------------------------------------------

func evidenceID(prefix, seed string) string {
	if seed == "" {
		return ""
	}
	sum := 0
	for _, b := range []byte(seed) {
		sum = (sum*131 + int(b)) % 1000000007
	}
	return fmt.Sprintf("%s-%08x", prefix, uint32(sum))
}

func severityFromStatus(payload map[string]any) string {
	status := strings.ToLower(text(payload["status"]))
	switch status {
	case "error", "failed", "failure", "timeout", "timed_out":
		return "major"
	case "warning", "degraded":
		return "warning"
	default:
		return "info"
	}
}

func psiSeverity(signal string, value float64) string {
	switch {
	case strings.Contains(signal, "mem") && value > 10:
		return "major"
	case value > 20:
		return "major"
	case value > 5:
		return "warning"
	default:
		return "info"
	}
}

func ratioSeverity(ratio float64) string {
	switch {
	case ratio >= 0.95:
		return "critical"
	case ratio >= 0.8:
		return "warning"
	default:
		return "info"
	}
}

func latencySeverity(ms float64) string {
	switch {
	case ms >= 30000:
		return "critical"
	case ms >= 3000:
		return "major"
	case ms >= 1000:
		return "warning"
	default:
		return "info"
	}
}

func numeric(v any) *float64 {
	switch value := v.(type) {
	case nil:
		return nil
	case float64:
		return &value
	case float32:
		f := float64(value)
		return &f
	case int:
		f := float64(value)
		return &f
	case int64:
		f := float64(value)
		return &f
	case uint64:
		f := float64(value)
		return &f
	case string:
		var f float64
		if _, err := fmt.Sscanf(strings.TrimSpace(value), "%g", &f); err == nil {
			return &f
		}
		return nil
	default:
		return nil
	}
}

func deref(v *float64) float64 {
	if v == nil {
		return 0
	}
	return *v
}

func text(v any) string {
	switch value := v.(type) {
	case nil:
		return ""
	case string:
		return value
	default:
		return fmt.Sprintf("%v", value)
	}
}

func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "…"
}

func compact(items []string) []string {
	var out []string
	for _, item := range items {
		if strings.TrimSpace(item) != "" {
			out = append(out, item)
		}
	}
	return out
}
