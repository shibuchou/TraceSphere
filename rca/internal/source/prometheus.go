package source

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"tracesphere/rca/internal/model"
)

// PrometheusClient 查询 VM 内 Prometheus（cAdvisor / llama.cpp 指标）。
//
// 为什么 C 也要直接读 Prometheus：关联簇只覆盖"事件"，而规则里的
// `memory.current_ratio` / `cpu.cfs.throttled_periods` / 重启计数是**指标型证据**，
// 原生存放在 Prometheus（方案 §2.1 三条管道，指标不做物理归集）。
type PrometheusClient struct {
	BaseURL string
	HTTP    *http.Client
}

func NewPrometheusClient(baseURL string) *PrometheusClient {
	return &PrometheusClient{
		BaseURL: strings.TrimRight(baseURL, "/"),
		HTTP:    &http.Client{Timeout: 20 * time.Second},
	}
}

type promSample struct {
	Labels map[string]string
	Value  float64
	At     time.Time
}

type promSeries struct {
	Labels map[string]string
	Points []model.Point
}

func (c *PrometheusClient) api(ctx context.Context, path string, query url.Values, out any) error {
	endpoint := c.BaseURL + path
	if len(query) > 0 {
		endpoint += "?" + query.Encode()
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return err
	}
	resp, err := c.HTTP.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(io.LimitReader(resp.Body, 16<<20))
	if err != nil {
		return err
	}
	if resp.StatusCode >= 400 {
		return fmt.Errorf("prometheus %s -> HTTP %d", path, resp.StatusCode)
	}
	if out == nil {
		return nil
	}
	return json.Unmarshal(body, out)
}

// Healthy 探测 Prometheus 可用性（/-/healthy）。
func (c *PrometheusClient) Healthy(ctx context.Context) bool {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.BaseURL+"/-/healthy", nil)
	if err != nil {
		return false
	}
	resp, err := c.HTTP.Do(req)
	if err != nil {
		return false
	}
	defer resp.Body.Close()
	io.Copy(io.Discard, io.LimitReader(resp.Body, 1024))
	return resp.StatusCode == 200
}

func (c *PrometheusClient) instant(ctx context.Context, expr string, at time.Time) ([]promSample, error) {
	query := url.Values{}
	query.Set("query", expr)
	if !at.IsZero() {
		query.Set("time", strconv.FormatInt(at.Unix(), 10))
	}
	var payload struct {
		Status string `json:"status"`
		Data   struct {
			Result []struct {
				Metric map[string]string `json:"metric"`
				Value  []any             `json:"value"`
			} `json:"result"`
		} `json:"data"`
	}
	if err := c.api(ctx, "/api/v1/query", query, &payload); err != nil {
		return nil, err
	}
	var out []promSample
	for _, item := range payload.Data.Result {
		value, at, ok := parsePromPair(item.Value)
		if !ok {
			continue
		}
		out = append(out, promSample{Labels: item.Metric, Value: value, At: at})
	}
	return out, nil
}

func (c *PrometheusClient) rng(ctx context.Context, expr string, from, to time.Time, step time.Duration) ([]promSeries, error) {
	query := url.Values{}
	query.Set("query", expr)
	query.Set("start", strconv.FormatInt(from.Unix(), 10))
	query.Set("end", strconv.FormatInt(to.Unix(), 10))
	query.Set("step", strconv.Itoa(int(step.Seconds())))
	var payload struct {
		Status string `json:"status"`
		Data   struct {
			Result []struct {
				Metric map[string]string `json:"metric"`
				Values [][]any           `json:"values"`
			} `json:"result"`
		} `json:"data"`
	}
	if err := c.api(ctx, "/api/v1/query_range", query, &payload); err != nil {
		return nil, err
	}
	var out []promSeries
	for _, item := range payload.Data.Result {
		series := promSeries{Labels: item.Metric}
		for _, pair := range item.Values {
			value, at, ok := parsePromPair(pair)
			if !ok {
				continue
			}
			series.Points = append(series.Points, model.Point{float64(at.Unix()), value})
		}
		if len(series.Points) > 0 {
			out = append(out, series)
		}
	}
	return out, nil
}

func parsePromPair(pair []any) (float64, time.Time, bool) {
	if len(pair) != 2 {
		return 0, time.Time{}, false
	}
	ts, ok := pair[0].(float64)
	if !ok {
		return 0, time.Time{}, false
	}
	raw, ok := pair[1].(string)
	if !ok {
		return 0, time.Time{}, false
	}
	value, err := strconv.ParseFloat(raw, 64)
	if err != nil || math.IsNaN(value) {
		return 0, time.Time{}, false
	}
	return value, time.Unix(int64(ts), 0).UTC(), true
}

// Collect 拉取窗口内的容器指标证据与曲线。
//
// 返回 (证据, 曲线序列, 容器展示名映射(resource_id -> docker name), 告警/说明)。
func (c *PrometheusClient) Collect(ctx context.Context, idx *ResourceIndex, window model.Window) ([]model.Evidence, []model.Series, map[string]string, []string) {
	var (
		evidence []model.Evidence
		series   []model.Series
		notes    []string
	)
	names := map[string]string{}
	from, to := window.From.Time, window.To.Time
	if from.IsZero() || to.IsZero() || !to.After(from) {
		to = time.Now().UTC()
		from = to.Add(-15 * time.Minute)
	}
	seconds := int(to.Sub(from).Seconds())
	if seconds < 60 {
		seconds = 60
	}
	rangeSel := fmt.Sprintf("[%ds]", seconds)
	step := time.Duration(seconds/60) * time.Second
	if step < 5*time.Second {
		step = 5 * time.Second
	}

	containers := idx.OfKind("container")
	if len(containers) == 0 {
		notes = append(notes, "资源清单为空，跳过容器指标采集")
		return nil, nil, names, notes
	}
	for _, container := range containers {
		resourceName := container.Name
		selector, display := c.resolveContainer(ctx, resourceName, container.ContainerID)
		if selector == "" {
			notes = append(notes, fmt.Sprintf("容器 %s 在 Prometheus 中无匹配序列", resourceName))
			continue
		}
		if display == "" {
			display = resourceName
		}
		if display != "" {
			names[container.ResourceID] = display
		}
		name := display
		resourceID := container.ResourceID
		// 1) 内存使用率（working_set / limit）
		usedSeries, _ := c.rng(ctx, "container_memory_working_set_bytes{"+selector+"}", from, to, step)
		limitSeries, _ := c.rng(ctx, "container_spec_memory_limit_bytes{"+selector+"}", from, to, step)
		ratioPoints, peakRatio, peakAt := ratioSeries(usedSeries, limitSeries)
		if len(ratioPoints) > 0 {
			series = append(series, model.Series{
				Name: "memory.current_ratio", Label: name + " 内存使用率", Unit: "ratio",
				Points:     ratioPoints,
				Thresholds: []model.Threshold{{Value: 0.95, Label: "memory limit", Color: "#ff4d4f"}},
			})
			value := peakRatio
			evidence = append(evidence, model.Evidence{
				EvidenceID:   evidenceID("prom", resourceID+"|mem_ratio|"+peakAt.UTC().Format(time.RFC3339)),
				Signal:       "memory.current_ratio",
				Kind:         "metric",
				Layer:        "container",
				ResourceID:   resourceID,
				ResourceName: name,
				ObservedAt:   model.TSTime{Time: peakAt},
				Severity:     ratioSeverity(value),
				Description:  fmt.Sprintf("内存使用率峰值 %.3f（working_set/limit，来源 Prometheus/cAdvisor）", value),
				Value:        &value,
				Unit:         "ratio",
				Origin:       "cadvisor",
				Mode:         "real",
			})
		}
		if len(usedSeries) > 0 {
			series = append(series, model.Series{
				Name: "container_memory_working_set_bytes", Label: name + " working_set", Unit: "bytes",
				Points: usedSeries[0].Points,
			})
		}

		// 2) OOM 计数增量
		if samples, err := c.instant(ctx, "increase(container_oom_events_total{"+selector+"}"+rangeSel+")", to); err == nil {
			for _, sample := range samples {
				if sample.Value <= 0 {
					continue
				}
				value := sample.Value
				evidence = append(evidence, model.Evidence{
					EvidenceID:   evidenceID("prom", resourceID+"|oom|"+sample.At.UTC().Format(time.RFC3339)),
					Signal:       "memory.events.oom_kill",
					Kind:         "cgroup",
					Layer:        "container",
					ResourceID:   resourceID,
					ResourceName: name,
					ObservedAt:   model.TSTime{Time: to},
					Severity:     "critical",
					Description:  fmt.Sprintf("memory.events.oom_kill Δ=%.0f（cAdvisor container_oom_events_total）", value),
					Value:        &value,
					Unit:         "count",
					Origin:       "cadvisor",
					Mode:         "real",
				})
			}
		}

		// 3) 容器重启
		if samples, err := c.instant(ctx, "changes(container_start_time_seconds{"+selector+"}"+rangeSel+")", to); err == nil {
			for _, sample := range samples {
				if sample.Value <= 0 {
					continue
				}
				value := sample.Value
				evidence = append(evidence, model.Evidence{
					EvidenceID:   evidenceID("prom", resourceID+"|restart|"+sample.At.UTC().Format(time.RFC3339)),
					Signal:       "container.restart",
					Kind:         "metric",
					Layer:        "container",
					ResourceID:   resourceID,
					ResourceName: name,
					ObservedAt:   model.TSTime{Time: to},
					Severity:     "warning",
					Description:  fmt.Sprintf("容器重启 %.0f 次（container_start_time_seconds 变化）", value),
					Value:        &value,
					Unit:         "count",
					Origin:       "cadvisor",
					Mode:         "real",
				})
			}
		}

		// 4) CPU 限流周期增量 + CPU 使用率
		if samples, err := c.instant(ctx, "increase(container_cpu_cfs_throttled_periods_total{"+selector+"}"+rangeSel+")", to); err == nil {
			for _, sample := range samples {
				if sample.Value <= 0 {
					continue
				}
				value := sample.Value
				evidence = append(evidence, model.Evidence{
					EvidenceID:   evidenceID("prom", resourceID+"|throttle|"+sample.At.UTC().Format(time.RFC3339)),
					Signal:       "cpu.cfs.throttled_periods",
					Kind:         "metric",
					Layer:        "container",
					ResourceID:   resourceID,
					ResourceName: name,
					ObservedAt:   model.TSTime{Time: to},
					Severity:     "warning",
					Description:  fmt.Sprintf("CPU 限流周期 Δ=%.0f（container_cpu_cfs_throttled_periods_total）", value),
					Value:        &value,
					Unit:         "count",
					Origin:       "cadvisor",
					Mode:         "real",
				})
			}
		}
		if cpuSeries, err := c.rng(ctx, "rate(container_cpu_usage_seconds_total{"+selector+"}"+rangeSel+") * 100", from, to, step); err == nil && len(cpuSeries) > 0 {
			series = append(series, model.Series{
				Name: "container_cpu_pct", Label: name + " CPU 使用率", Unit: "percent",
				Points: cpuSeries[0].Points,
			})
			points := cpuSeries[0].Points
			last := points[len(points)-1][1]
			severity := "info"
			if last >= 80 {
				severity = "warning"
			}
			value := last
			at := time.Unix(int64(points[len(points)-1][0]), 0).UTC()
			evidence = append(evidence, model.Evidence{
				EvidenceID:   evidenceID("prom", resourceID+"|cpu|"+at.Format(time.RFC3339)),
				Signal:       "container.cpu_pct",
				Kind:         "metric",
				Layer:        "container",
				ResourceID:   resourceID,
				ResourceName: name,
				ObservedAt:   model.TSTime{Time: at},
				Severity:     severity,
				Description:  fmt.Sprintf("CPU 使用率 %.1f%%（基线与阈值见 rules/cpu.yaml）", value),
				Value:        &value,
				Unit:         "percent",
				Origin:       "cadvisor",
				Mode:         "real",
			})
		}
	}

	// 5) llama.cpp 推理吞吐（辅助证据）
	if samples, err := c.instant(ctx, "rate(llamacpp:tokens_predicted_total[5m])", to); err == nil {
		for _, sample := range samples {
			value := sample.Value
			evidence = append(evidence, model.Evidence{
				EvidenceID:   evidenceID("prom", "llamacpp|"+sample.At.UTC().Format(time.RFC3339)),
				Signal:       "llamacpp.tokens_per_s",
				Kind:         "metric",
				Layer:        "container",
				ResourceID:   vmResourceOf(idx),
				ResourceName: "llama-server",
				ObservedAt:   model.TSTime{Time: to},
				Severity:     "info",
				Description:  fmt.Sprintf("llama.cpp 推理吞吐 %.2f tokens/s", value),
				Value:        &value,
				Unit:         "tokens_per_s",
				Origin:       "cadvisor",
				Mode:         "real",
			})
		}
	}
	return evidence, series, names, notes
}

// resolveContainer 解析容器在 Prometheus 中的标签选择器，并顺带取回真实容器名。
//
// 为什么需要：B 的事件 ingest 用 container_id 前 12 位当资源名（哈希占位），
// 而 cAdvisor 指标里带真实 docker name（name 标签）。这里用真实名字回填，
// 使拓扑/证据展示可读（C 侧不与上游耦合，缺失时不影响功能）。
func (c *PrometheusClient) resolveContainer(ctx context.Context, name, containerID string) (string, string) {
	if name != "" && !LooksLikeID(name) {
		selector := fmt.Sprintf("name=%q", name)
		if samples, err := c.instant(ctx, "container_last_seen{"+selector+"}", time.Time{}); err == nil && len(samples) > 0 {
			return selector, name
		}
	}
	if containerID == "" {
		return "", ""
	}
	short := containerID
	if len(short) > 12 {
		short = short[:12]
	}
	selector := fmt.Sprintf("id=~%q", ".*"+short+".*")
	samples, err := c.instant(ctx, "container_last_seen{"+selector+"}", time.Time{})
	if err != nil || len(samples) == 0 {
		return "", ""
	}
	display := samples[0].Labels["name"]
	if display == "" {
		display = name
	}
	return selector, display
}

func ratioSeries(used, limit []promSeries) ([]model.Point, float64, time.Time) {
	if len(used) == 0 || len(limit) == 0 {
		return nil, 0, time.Time{}
	}
	limits := map[float64]float64{}
	for _, point := range limit[0].Points {
		limits[point[0]] = point[1]
	}
	var (
		points   []model.Point
		peak     float64
		peakAt   time.Time
		hasPoint bool
	)
	for _, point := range used[0].Points {
		cap, ok := limits[point[0]]
		if !ok || cap <= 0 || cap > 1e15 {
			continue
		}
		ratio := point[1] / cap
		points = append(points, model.Point{point[0], round3(ratio)})
		hasPoint = true
		at := time.Unix(int64(point[0]), 0).UTC()
		if ratio > peak {
			peak = ratio
			peakAt = at
		}
	}
	if !hasPoint {
		return nil, 0, time.Time{}
	}
	return points, peak, peakAt
}

func vmResourceOf(idx *ResourceIndex) string {
	vms := idx.OfKind("vm")
	if len(vms) > 0 {
		return vms[0].ResourceID
	}
	return ""
}

func round3(v float64) float64 { return math.Round(v*1000) / 1000 }
