// Package model 定义 C 侧（诊断/告警/展示）的统一数据模型。
//
// 字段与 `rca/docs/API.md`（W1 冻结契约）一一对应：证据 Evidence、诊断 Diagnosis、
// 评分明细 ScoreDimension、影响范围 Impact、时间线 TimelineEntry、拓扑 Graph 等。
package model

import (
	"encoding/json"
	"fmt"
	"strings"
	"time"
)

// ---------------------------------------------------------------------------
// 时间：容忍多种生产者格式（RFC3339 / RFC3339Nano / "+0000" / unix 秒 / 纳秒）
// ---------------------------------------------------------------------------

type TSTime struct{ time.Time }

func (t TSTime) MarshalJSON() ([]byte, error) {
	if t.Time.IsZero() {
		return []byte("null"), nil
	}
	return json.Marshal(t.UTC().Format(time.RFC3339))
}

func (t *TSTime) UnmarshalJSON(b []byte) error {
	var v any
	if err := json.Unmarshal(b, &v); err != nil {
		return err
	}
	parsed, err := ParseTimeAny(v)
	if err != nil {
		return err
	}
	t.Time = parsed
	return nil
}

var timeLayouts = []string{
	time.RFC3339Nano,
	time.RFC3339,
	"2006-01-02T15:04:05-0700",
	"2006-01-02T15:04:05.999999999-0700",
	"2006-01-02 15:04:05",
	"2006-01-02T15:04:05",
}

// ParseTimeAny 解析字符串 / 数字时间戳（秒、毫秒、微秒、纳秒自动识别）。
func ParseTimeAny(v any) (time.Time, error) {
	switch value := v.(type) {
	case nil:
		return time.Time{}, nil
	case time.Time:
		return value, nil
	case string:
		s := strings.TrimSpace(value)
		if s == "" {
			return time.Time{}, nil
		}
		for _, layout := range timeLayouts {
			if parsed, err := time.Parse(layout, s); err == nil {
				return parsed, nil
			}
		}
		return time.Time{}, fmt.Errorf("无法解析时间: %q", s)
	case float64:
		return fromUnix(float64(value)), nil
	case int64:
		return fromUnix(float64(value)), nil
	case json.Number:
		f, err := value.Float64()
		if err != nil {
			return time.Time{}, err
		}
		return fromUnix(f), nil
	default:
		return time.Time{}, fmt.Errorf("不支持的时间类型 %T", v)
	}
}

func fromUnix(v float64) time.Time {
	switch {
	case v > 1e18: // 纳秒
		return time.Unix(0, int64(v)).UTC()
	case v > 1e15: // 微秒
		return time.Unix(0, int64(v)*1000).UTC()
	case v > 1e12: // 毫秒
		return time.Unix(0, int64(v)*1e6).UTC()
	default: // 秒
		sec := int64(v)
		nsec := int64((v - float64(sec)) * 1e9)
		return time.Unix(sec, nsec).UTC()
	}
}

// ---------------------------------------------------------------------------
// 证据
// ---------------------------------------------------------------------------

// Evidence 是 C 侧统一证据条目（方案 §5.4 Evidence 语义 + 匹配所需的数值字段）。
type Evidence struct {
	EvidenceID     string         `json:"evidence_id"`
	Signal         string         `json:"signal"`
	Kind           string         `json:"kind"`
	Layer          string         `json:"layer"`
	ResourceID     string         `json:"resource_id,omitempty"`
	ResourceName   string         `json:"resource_name,omitempty"`
	CorrelationID  string         `json:"correlation_id,omitempty"`
	TaskID         string         `json:"task_id,omitempty"`
	ObservedAt     TSTime         `json:"observed_at"`
	Severity       string         `json:"severity,omitempty"`
	Description    string         `json:"description,omitempty"`
	Value          *float64       `json:"value,omitempty"`
	Baseline       *float64       `json:"baseline,omitempty"`
	Unit           string         `json:"unit,omitempty"`
	SourceEventIDs []string       `json:"source_event_ids,omitempty"`
	Origin         string         `json:"origin,omitempty"`
	Mode           string         `json:"mode,omitempty"`
	Payload        map[string]any `json:"payload,omitempty"`
}

// Attr 在 payload / payload.attributes 里查找字段（对齐 B 的 ingest._nested 语义）。
func (e Evidence) Attr(keys ...string) any {
	for _, key := range keys {
		if e.Payload == nil {
			break
		}
		if v, ok := e.Payload[key]; ok && v != nil {
			return v
		}
	}
	if attrs, ok := e.Payload["attributes"].(map[string]any); ok {
		for _, key := range keys {
			if v, ok := attrs[key]; ok && v != nil {
				return v
			}
		}
	}
	return nil
}

// Text 返回用于 match_any 关键字匹配的文本（描述 + 常见字段）。
func (e Evidence) Text() string {
	var b strings.Builder
	b.WriteString(e.Description)
	for _, key := range []string{"reason", "error", "message", "status", "detail"} {
		if v := e.Attr(key); v != nil {
			b.WriteString(" ")
			b.WriteString(fmt.Sprintf("%v", v))
		}
	}
	return b.String()
}

// ---------------------------------------------------------------------------
// 诊断
// ---------------------------------------------------------------------------

// ScoreDimension 是 Evidence Match 的单个维度明细（方案 §6.3 五维度）。
type ScoreDimension struct {
	Dimension string  `json:"dimension"`
	Label     string  `json:"label"`
	Score     float64 `json:"score"`
	Max       float64 `json:"max"`
	Detail    string  `json:"detail"`
}

// Suggestion 处置建议：依据 + 操作 + 风险（方案 §6.4）。
type Suggestion struct {
	Action string `json:"action"`
	Title  string `json:"title"`
	Basis  string `json:"basis"`
	Detail string `json:"detail"`
	Risk   string `json:"risk"`
}

// Alternative 备选根因候选。
type Alternative struct {
	Rule        string  `json:"rule"`
	Title       string  `json:"title"`
	RootCause   string  `json:"root_cause"`
	MatchScore  float64 `json:"match_score"`
	EvidenceCnt int     `json:"evidence_count"`
}

// ImpactScopeEntry 影响范围内的单个资源。
type ImpactScopeEntry struct {
	ResourceID string `json:"resource_id"`
	Kind       string `json:"kind"`
	Name       string `json:"name"`
	Relation   string `json:"relation,omitempty"`
	Depth      int    `json:"depth"`
	Status     string `json:"status,omitempty"`
}

// Impact 影响范围（方案 §7 每个 Case 都要给出"影响谁"）。
type Impact struct {
	Focus  *ResourceRef       `json:"focus,omitempty"`
	Counts map[string]int     `json:"counts"`
	Scope  []ImpactScopeEntry `json:"scope"`
}

// ResourceRef 资源引用（ID + 名称 + 类型）。
type ResourceRef struct {
	ResourceID string `json:"resource_id"`
	Kind       string `json:"kind"`
	Name       string `json:"name"`
}

// TimelineEntry 时间线条目（按层着色展示）。
type TimelineEntry struct {
	ObservedAt   TSTime `json:"observed_at"`
	Layer        string `json:"layer"`
	Signal       string `json:"signal"`
	Severity     string `json:"severity,omitempty"`
	ResourceID   string `json:"resource_id,omitempty"`
	ResourceName string `json:"resource_name,omitempty"`
	Description  string `json:"description"`
	EvidenceID   string `json:"evidence_id,omitempty"`
	IncidentID   string `json:"incident_id,omitempty"`
	TaskID       string `json:"task_id,omitempty"`
}

// Diagnosis 根因诊断结果（方案 §6.3：根因候选 + 证据 + 评分明细 + 处置建议）。
type Diagnosis struct {
	DiagnosisID    string           `json:"diagnosis_id"`
	Rule           string           `json:"rule"`
	RuleVersion    int              `json:"rule_version"`
	Title          string           `json:"title"`
	RootCause      string           `json:"root_cause"`
	RootCauseLabel string           `json:"root_cause_label"`
	Severity       string           `json:"severity"`
	MatchScore     float64          `json:"match_score"`
	MatchNote      string           `json:"match_note"`
	ScoreBreakdown []ScoreDimension `json:"score_breakdown"`
	EvidenceIDs    []string         `json:"evidence_ids"`
	Evidence       []Evidence       `json:"evidence"`
	Suggestions    []Suggestion     `json:"suggestions"`
	Alternatives   []Alternative    `json:"alternatives"`
	Window         Window           `json:"window"`
	CorrelationID  string           `json:"correlation_id,omitempty"`
	FocusResource  string           `json:"focus_resource,omitempty"`
}

// Window 时间窗。
type Window struct {
	From    TSTime  `json:"from"`
	To      TSTime  `json:"to"`
	Seconds float64 `json:"seconds,omitempty"`
}

// ---------------------------------------------------------------------------
// 资源与拓扑
// ---------------------------------------------------------------------------

// Resource 资源实体（对齐 B 的 resources 表主要字段 + 展示字段）。
type Resource struct {
	ResourceID    string            `json:"resource_id"`
	Kind          string            `json:"kind"`
	Name          string            `json:"name"`
	ClusterID     string            `json:"cluster_id,omitempty"`
	VMID          string            `json:"vm_id,omitempty"`
	HostID        string            `json:"host_id,omitempty"`
	ContainerID   string            `json:"container_id,omitempty"`
	CorrelationID string            `json:"correlation_id,omitempty"`
	State         string            `json:"state,omitempty"`
	Origin        string            `json:"origin,omitempty"`
	Mode          string            `json:"mode,omitempty"`
	Labels        map[string]string `json:"labels,omitempty"`
	Attributes    map[string]any    `json:"attributes,omitempty"`
	ObservedAt    TSTime            `json:"observed_at,omitempty"`
	// 展示扩展（由 C 侧健康评估填充）
	Status      string  `json:"status,omitempty"`
	Subtitle    string  `json:"subtitle,omitempty"`
	HealthScore float64 `json:"health_score,omitempty"`
	WorkloadTyp string  `json:"workload_type,omitempty"`
}

// Edge 资源关系边（关系词表见 B 的 domain.REL_*）。
type Edge struct {
	SrcID    string `json:"src_id"`
	DstID    string `json:"dst_id"`
	Relation string `json:"relation"`
	Origin   string `json:"origin,omitempty"`
	Mode     string `json:"mode,omitempty"`
}

// Graph 资源子图（G6 直接可用）。
type Graph struct {
	Nodes []GraphNode `json:"nodes"`
	Edges []GraphEdge `json:"edges"`
}

type GraphNode struct {
	ID       string   `json:"id"`
	Label    string   `json:"label"`
	Kind     string   `json:"kind"`
	Combo    string   `json:"combo,omitempty"`
	Status   string   `json:"status"`
	Subtitle string   `json:"subtitle,omitempty"`
	Badges   []string `json:"badges,omitempty"`
	Incident int      `json:"incident_count"`
	Metrics  []Metric `json:"metrics,omitempty"`
}

type GraphEdge struct {
	ID       string `json:"id"`
	Source   string `json:"source"`
	Target   string `json:"target"`
	Relation string `json:"relation"`
	Label    string `json:"label,omitempty"`
}

type Combo struct {
	ID     string `json:"id"`
	Label  string `json:"label"`
	Kind   string `json:"kind"`
	Parent string `json:"parent,omitempty"`
}

type Legend struct {
	Kind  string `json:"kind"`
	Label string `json:"label"`
}

// Topology 拓扑页响应（API.md §4.1）。
type Topology struct {
	GeneratedAt TSTime         `json:"generated_at"`
	Source      map[string]any `json:"source"`
	Combos      []Combo        `json:"combos"`
	Nodes       []GraphNode    `json:"nodes"`
	Edges       []GraphEdge    `json:"edges"`
	Legend      []Legend       `json:"legend"`
}

// ---------------------------------------------------------------------------
// 健康 / 告警 / 曲线
// ---------------------------------------------------------------------------

type Metric struct {
	Name   string  `json:"name"`
	Label  string  `json:"label,omitempty"`
	Value  float64 `json:"value"`
	Unit   string  `json:"unit,omitempty"`
	Status string  `json:"status,omitempty"`
	Trend  string  `json:"trend,omitempty"`
}

type SignalCount struct {
	Signal   string `json:"signal"`
	Layer    string `json:"layer"`
	Count    int    `json:"count"`
	LastAt   TSTime `json:"last_at"`
	Severity string `json:"severity,omitempty"`
}

type WorkloadCard struct {
	ResourceID   string        `json:"resource_id"`
	Name         string        `json:"name"`
	Kind         string        `json:"kind"`
	WorkloadType string        `json:"workload_type,omitempty"`
	Status       string        `json:"status"`
	HealthScore  float64       `json:"health_score"`
	Parent       *ResourceRef  `json:"parent,omitempty"`
	LastEventAt  TSTime        `json:"last_event_at,omitempty"`
	TaskFailures int           `json:"task_failures"`
	Signals      []SignalCount `json:"signals"`
	Metrics      []Metric      `json:"metrics"`
}

type Summary struct {
	Resources   int `json:"resources"`
	Healthy     int `json:"healthy"`
	Warning     int `json:"warning"`
	Critical    int `json:"critical"`
	TasksTotal  int `json:"tasks_total"`
	TasksFailed int `json:"tasks_failed"`
	Incidents   int `json:"incidents"`
	OpenAlerts  int `json:"open_alerts"`
}

// Overview 健康页响应（API.md §4.2）。
type Overview struct {
	GeneratedAt TSTime          `json:"generated_at"`
	Source      map[string]any  `json:"source"`
	Window      Window          `json:"window"`
	Summary     Summary         `json:"summary"`
	Workloads   []WorkloadCard  `json:"workloads"`
	Timeline    []TimelineEntry `json:"timeline"`
}

// Incident 告警/事件条目（一个关联簇 + Top-1 诊断摘要）。
type Incident struct {
	IncidentID     string       `json:"incident_id"`
	CorrelationID  string       `json:"correlation_id,omitempty"`
	Title          string       `json:"title"`
	Rule           string       `json:"rule"`
	Severity       string       `json:"severity"`
	Status         string       `json:"status"`
	MatchScore     float64      `json:"match_score"`
	FirstSeenAt    TSTime       `json:"first_seen_at"`
	LastSeenAt     TSTime       `json:"last_seen_at"`
	FocusResource  *ResourceRef `json:"focus_resource,omitempty"`
	EvidenceCount  int          `json:"evidence_count"`
	AffectedTasks  int          `json:"affected_tasks"`
	Summary        string       `json:"summary"`
	Source         string       `json:"source"`
	ClusterID      string       `json:"cluster_id,omitempty"`
	RootCauseLabel string       `json:"root_cause_label,omitempty"`
}

type IncidentList struct {
	GeneratedAt TSTime     `json:"generated_at"`
	Count       int        `json:"count"`
	Incidents   []Incident `json:"incidents"`
}

// IncidentDetail 告警详情页响应（API.md §4.4）。
type IncidentDetail struct {
	Incident   Incident        `json:"incident"`
	Window     Window          `json:"window"`
	Diagnosis  *Diagnosis      `json:"diagnosis,omitempty"`
	Candidates []Diagnosis     `json:"candidates"`
	Evidence   []Evidence      `json:"evidence"`
	Timeline   []TimelineEntry `json:"timeline"`
	Impact     Impact          `json:"impact"`
	Graph      Graph           `json:"graph"`
}

// DiagnoseResult 诊断接口响应（API.md §4.5）。
type DiagnoseResult struct {
	Window    Window          `json:"window"`
	Focus     map[string]any  `json:"focus"`
	Sources   map[string]any  `json:"sources"`
	Diagnoses []Diagnosis     `json:"diagnoses"`
	Evidence  []Evidence      `json:"evidence"`
	Timeline  []TimelineEntry `json:"timeline"`
	Impact    Impact          `json:"impact"`
	Graph     Graph           `json:"graph"`
}

type Point [2]float64

type Threshold struct {
	Value float64 `json:"value"`
	Label string  `json:"label"`
	Color string  `json:"color,omitempty"`
}

type Series struct {
	Name       string      `json:"name"`
	Label      string      `json:"label"`
	Unit       string      `json:"unit"`
	Points     []Point     `json:"points"`
	Thresholds []Threshold `json:"thresholds"`
}

type SeriesResponse struct {
	ResourceID string   `json:"resource_id"`
	Window     Window   `json:"window"`
	Series     []Series `json:"series"`
}

// RuleInfo 规则清单条目（诊断页"可扩展"展示）。
type RuleInfo struct {
	Rule        string  `json:"rule"`
	Version     int     `json:"version"`
	Title       string  `json:"title"`
	Description string  `json:"description"`
	Severity    string  `json:"severity"`
	Clauses     int     `json:"clauses"`
	Weights     float64 `json:"mandatory_weight"`
	Source      string  `json:"source"`
}

// ---------------------------------------------------------------------------
// 小工具
// ---------------------------------------------------------------------------

// Severity 归一化（方案 §5.4：info | warning | major | critical）。
func Severity(sev string) string {
	switch strings.ToLower(strings.TrimSpace(sev)) {
	case "critical", "fatal", "emergency", "alert":
		return "critical"
	case "major", "error", "failed", "failure", "timeout", "timed_out":
		return "major"
	case "warning", "warn", "degraded":
		return "warning"
	default:
		return "info"
	}
}

// SeverityRank 越大越严重（用于聚合与排序）。
func SeverityRank(sev string) int {
	switch Severity(sev) {
	case "critical":
		return 3
	case "major":
		return 2
	case "warning":
		return 1
	default:
		return 0
	}
}

// MaxSeverity 返回更严重的一方。
func MaxSeverity(a, b string) string {
	if SeverityRank(a) >= SeverityRank(b) {
		return Severity(a)
	}
	return Severity(b)
}

// KindOf 从 resource_id（`<kind>:<key>`）解析类型。
func KindOf(resourceID string) string {
	if idx := strings.Index(resourceID, ":"); idx > 0 {
		return resourceID[:idx]
	}
	return ""
}
