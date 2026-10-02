package source

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"sort"
	"strconv"
	"strings"
	"time"

	"tracesphere/rca/internal/model"
)

// PlatformClient 访问队友 B 的 TraceSphere Platform（只读，方案 §6.1 边界）。
type PlatformClient struct {
	BaseURL string
	Token   string
	HTTP    *http.Client
}

func NewPlatformClient(baseURL, token string) *PlatformClient {
	return &PlatformClient{
		BaseURL: strings.TrimRight(baseURL, "/"),
		Token:   token,
		HTTP:    &http.Client{Timeout: 20 * time.Second},
	}
}

func (c *PlatformClient) do(ctx context.Context, method, path string, query url.Values, out any) error {
	endpoint := c.BaseURL + path
	if len(query) > 0 {
		endpoint += "?" + query.Encode()
	}
	req, err := http.NewRequestWithContext(ctx, method, endpoint, nil)
	if err != nil {
		return err
	}
	if c.Token != "" {
		req.Header.Set("Authorization", "Bearer "+c.Token)
	}
	resp, err := c.HTTP.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(io.LimitReader(resp.Body, 32<<20))
	if err != nil {
		return err
	}
	if resp.StatusCode >= 400 {
		return fmt.Errorf("platform %s %s -> HTTP %d: %s", method, path, resp.StatusCode, truncate(string(body), 200))
	}
	if out == nil {
		return nil
	}
	return json.Unmarshal(body, out)
}

// Health 探测 Platform 可用性（/api/v1/health 免 token）。
func (c *PlatformClient) Health(ctx context.Context) (map[string]any, error) {
	var payload map[string]any
	if err := c.do(ctx, http.MethodGet, "/api/v1/health", nil, &payload); err != nil {
		return nil, err
	}
	return payload, nil
}

// Meta 返回 Schema 字段 / 关系词表等（拓扑渲染用）。
func (c *PlatformClient) Meta(ctx context.Context) (map[string]any, error) {
	var payload map[string]any
	if err := c.do(ctx, http.MethodGet, "/api/v1/meta", nil, &payload); err != nil {
		return nil, err
	}
	return payload, nil
}

func (c *PlatformClient) Resources(ctx context.Context, limit int) ([]model.Resource, error) {
	query := url.Values{}
	query.Set("limit", strconv.Itoa(limit))
	var payload struct {
		Resources []model.Resource `json:"resources"`
	}
	if err := c.do(ctx, http.MethodGet, "/api/v1/resources", query, &payload); err != nil {
		return nil, err
	}
	return payload.Resources, nil
}

// Subgraph 取资源子图（nodes + edges），用于拓扑页与影响范围。
func (c *PlatformClient) Subgraph(ctx context.Context, resourceID string, depth int) ([]model.Resource, []model.Edge, error) {
	query := url.Values{}
	query.Set("depth", strconv.Itoa(depth))
	query.Set("direction", "both")
	var payload struct {
		Nodes []model.Resource `json:"nodes"`
		Edges []model.Edge     `json:"edges"`
	}
	path := "/api/v1/resources/" + url.PathEscape(resourceID) + "/graph"
	if err := c.do(ctx, http.MethodGet, path, query, &payload); err != nil {
		return nil, nil, err
	}
	return payload.Nodes, payload.Edges, nil
}

type contextResponse struct {
	CorrelationID string           `json:"correlation_id"`
	ResourceID    string           `json:"resource_id"`
	Window        windowPayload    `json:"window"`
	Events        []PlatformEvent  `json:"events"`
	Evidence      []EvidenceRow    `json:"evidence"`
	Clusters      []ClusterRow     `json:"clusters"`
	Resources     []model.Resource `json:"resources"`
	Graph         *graphPayload    `json:"graph"`
}

type windowPayload struct {
	From    model.TSTime `json:"from"`
	To      model.TSTime `json:"to"`
	Seconds float64      `json:"seconds"`
}

type graphPayload struct {
	Nodes []model.Resource `json:"nodes"`
	Edges []model.Edge     `json:"edges"`
}

// EvidenceRow 对齐 B 的 evidence 行。
type EvidenceRow struct {
	EvidenceID     string         `json:"evidence_id"`
	ClusterID      string         `json:"cluster_id"`
	Kind           string         `json:"kind"`
	Signal         string         `json:"signal"`
	Description    string         `json:"description"`
	ResourceID     string         `json:"resource_id"`
	CorrelationID  string         `json:"correlation_id"`
	TaskID         string         `json:"task_id"`
	ObservedAt     model.TSTime   `json:"observed_at"`
	SourceEventIDs []string       `json:"source_event_ids"`
	Payload        map[string]any `json:"payload"`
	Origin         string         `json:"origin"`
	Mode           string         `json:"mode"`
	DedupKey       string         `json:"dedup_key"`
}

// ClusterRow 对齐 B 的 clusters 行。
type ClusterRow struct {
	ClusterID     string       `json:"cluster_id"`
	ClusterKey    string       `json:"cluster_key"`
	CorrelationID string       `json:"correlation_id"`
	ResourceID    string       `json:"resource_id"`
	Rule          string       `json:"rule"`
	WindowStart   model.TSTime `json:"window_start"`
	WindowEnd     model.TSTime `json:"window_end"`
	Status        string       `json:"status"`
	Summary       string       `json:"summary"`
	EventIDs      []string     `json:"event_ids"`
	EvidenceIDs   []string     `json:"evidence_ids"`
	EventCount    int          `json:"event_count"`
	EvidenceCount int          `json:"evidence_count"`
}

// Context 拉取 RCA 聚合输入（B 专为 C 提供的端点，platform README §HTTP API 契约）。
func (c *PlatformClient) Context(ctx context.Context, focus Focus, from, to time.Time) (*Snapshot, error) {
	query := url.Values{}
	if focus.CorrelationID != "" {
		query.Set("correlation_id", focus.CorrelationID)
	}
	if focus.ResourceID != "" {
		query.Set("resource_id", focus.ResourceID)
	}
	if !from.IsZero() {
		query.Set("from", from.UTC().Format(time.RFC3339))
	}
	if !to.IsZero() {
		query.Set("to", to.UTC().Format(time.RFC3339))
	}
	var payload contextResponse
	if err := c.do(ctx, http.MethodGet, "/api/v1/context", query, &payload); err != nil {
		return nil, err
	}

	resources := payload.Resources
	var edges []model.Edge
	if payload.Graph != nil {
		edges = payload.Graph.Edges
		for _, node := range payload.Graph.Nodes {
			resources = append(resources, node)
		}
		resources = dedupResources(resources)
	}
	idx := NewResourceIndex(resources, edges)

	snap := &Snapshot{
		Focus:     focus,
		Resources: resources,
		Edges:     edges,
		Window: model.Window{
			From:    payload.Window.From,
			To:      payload.Window.To,
			Seconds: payload.Window.Seconds,
		},
	}
	if snap.Window.Seconds == 0 && !snap.Window.From.Time.IsZero() && !snap.Window.To.Time.IsZero() {
		snap.Window.Seconds = snap.Window.To.Time.Sub(snap.Window.From.Time).Seconds()
	}
	for _, row := range payload.Evidence {
		snap.Evidence = append(snap.Evidence, EvidenceRowToEvidence(row, idx)...)
	}
	// 未生成 evidence 的原始事件（例如 W1 阶段 A 尚未接入 AppEvent ingest）也参与匹配
	seen := evidenceKeys(snap.Evidence)
	for _, ev := range payload.Events {
		for _, item := range EventToEvidence(ev, idx) {
			key := evidenceKey(item)
			if seen[key] {
				continue
			}
			seen[key] = true
			snap.Evidence = append(snap.Evidence, item)
		}
	}
	for _, row := range payload.Clusters {
		snap.Incidents = append(snap.Incidents, RawIncident{
			ClusterID: row.ClusterID, CorrelationID: row.CorrelationID, ResourceID: row.ResourceID,
			Rule: row.Rule, Summary: row.Summary,
			WindowStart: row.WindowStart, WindowEnd: row.WindowEnd,
		})
	}
	return snap, nil
}

// EvidenceWindow 拉取全局时间窗内的证据（健康页 / 告警列表页用，无 focus）。
func (c *PlatformClient) EvidenceWindow(ctx context.Context, from, to time.Time, limit int) ([]model.Evidence, error) {
	query := url.Values{}
	query.Set("from", from.UTC().Format(time.RFC3339))
	query.Set("to", to.UTC().Format(time.RFC3339))
	query.Set("limit", strconv.Itoa(limit))
	var payload struct {
		Evidence []EvidenceRow `json:"evidence"`
	}
	if err := c.do(ctx, http.MethodGet, "/api/v1/evidence", query, &payload); err != nil {
		return nil, err
	}
	idx := &ResourceIndex{}
	var out []model.Evidence
	for _, row := range payload.Evidence {
		out = append(out, EvidenceRowToEvidence(row, idx)...)
	}
	return out, nil
}

// EventsWindow 拉取全局时间窗内的事件并归一化为证据。
func (c *PlatformClient) EventsWindow(ctx context.Context, from, to time.Time, limit int) ([]PlatformEvent, error) {
	query := url.Values{}
	query.Set("from", from.UTC().Format(time.RFC3339))
	query.Set("to", to.UTC().Format(time.RFC3339))
	query.Set("limit", strconv.Itoa(limit))
	query.Set("order", "asc")
	var payload struct {
		Events []PlatformEvent `json:"events"`
	}
	if err := c.do(ctx, http.MethodGet, "/api/v1/events", query, &payload); err != nil {
		return nil, err
	}
	return payload.Events, nil
}

// Clusters 列出关联簇（告警列表页的数据来源）。
func (c *PlatformClient) Clusters(ctx context.Context, limit int) ([]ClusterRow, error) {
	query := url.Values{}
	query.Set("limit", strconv.Itoa(limit))
	var payload struct {
		Clusters []ClusterRow `json:"clusters"`
	}
	if err := c.do(ctx, http.MethodGet, "/api/v1/clusters", query, &payload); err != nil {
		return nil, err
	}
	sort.SliceStable(payload.Clusters, func(i, j int) bool {
		return payload.Clusters[i].WindowStart.After(payload.Clusters[j].WindowStart.Time)
	})
	return payload.Clusters, nil
}

// ClusterDetail 取单个簇（含证据与源事件）——一个簇就是一条"告警/事件"。
func (c *PlatformClient) ClusterDetail(ctx context.Context, clusterID string) (*RawIncident, []model.Evidence, error) {
	var payload struct {
		Cluster  ClusterRow      `json:"cluster"`
		Evidence []EvidenceRow   `json:"evidence"`
		Events   []PlatformEvent `json:"events"`
	}
	path := "/api/v1/clusters/" + url.PathEscape(clusterID)
	if err := c.do(ctx, http.MethodGet, path, nil, &payload); err != nil {
		return nil, nil, err
	}
	idx := &ResourceIndex{}
	var items []model.Evidence
	for _, row := range payload.Evidence {
		items = append(items, EvidenceRowToEvidence(row, idx)...)
	}
	seen := evidenceKeys(items)
	for _, ev := range payload.Events {
		for _, item := range EventToEvidence(ev, idx) {
			key := evidenceKey(item)
			if seen[key] {
				continue
			}
			seen[key] = true
			items = append(items, item)
		}
	}
	incident := &RawIncident{
		ClusterID: payload.Cluster.ClusterID, CorrelationID: payload.Cluster.CorrelationID,
		ResourceID: payload.Cluster.ResourceID, Rule: payload.Cluster.Rule,
		Summary:     payload.Cluster.Summary,
		WindowStart: payload.Cluster.WindowStart, WindowEnd: payload.Cluster.WindowEnd,
		Evidence: items,
	}
	return incident, items, nil
}

// Correlate 触发一次平台侧关联（C 主动扫描窗口时使用，方案 §5.6）。
func (c *PlatformClient) Correlate(ctx context.Context, from, to time.Time, resourceID, correlationID string, windowSeconds float64) error {
	body := map[string]any{
		"from": from.UTC().Format(time.RFC3339),
		"to":   to.UTC().Format(time.RFC3339),
	}
	if resourceID != "" {
		body["resource_id"] = resourceID
	}
	if correlationID != "" {
		body["correlation_id"] = correlationID
	}
	if windowSeconds > 0 {
		body["window_seconds"] = windowSeconds
	}
	raw, err := json.Marshal(body)
	if err != nil {
		return err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.BaseURL+"/api/v1/correlate", strings.NewReader(string(raw)))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	if c.Token != "" {
		req.Header.Set("Authorization", "Bearer "+c.Token)
	}
	resp, err := c.HTTP.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 4096))
		return fmt.Errorf("correlate -> HTTP %d: %s", resp.StatusCode, truncate(string(body), 200))
	}
	return nil
}

// EvidenceRowToEvidence 把平台证据行转成 C 的证据模型。
func EvidenceRowToEvidence(row EvidenceRow, idx *ResourceIndex) []model.Evidence {
	payload := row.Payload
	inner, _ := payload["event_payload"].(map[string]any)
	if len(inner) == 0 {
		inner = payload
	}
	severity := model.Severity(text(payload["severity"]))
	if text(payload["severity"]) == "" {
		severity = severityFromStatus(inner)
	}
	kind := row.Kind
	if kind == "" || kind == "other" {
		kind = KindForOrigin(row.Origin)
	}
	resourceName := ""
	if idx != nil {
		resourceName = idx.Name(row.ResourceID)
	}
	base := model.Evidence{
		EvidenceID:     row.EvidenceID,
		Signal:         row.Signal,
		Kind:           kind,
		Layer:          layerOf(idx, row.Origin, row.ResourceID),
		ResourceID:     row.ResourceID,
		ResourceName:   resourceName,
		CorrelationID:  row.CorrelationID,
		TaskID:         row.TaskID,
		ObservedAt:     row.ObservedAt,
		Severity:       severity,
		Description:    row.Description,
		SourceEventIDs: row.SourceEventIDs,
		Origin:         row.Origin,
		Mode:           row.Mode,
		Payload:        inner,
	}
	if v := numeric(inner["duration_ms"]); v != nil {
		base.Value = v
		base.Unit = "ms"
	} else if v := numeric(inner["value"]); v != nil {
		base.Value = v
		base.Unit = "count"
	} else if v := numeric(inner["delta"]); v != nil {
		base.Value = v
		base.Unit = "count"
	}
	// 指标型证据：payload 里可能带 psi_* / cgroup / gpu 样本
	if signals := metricSignalsFromPayload(inner); len(signals) > 0 {
		out := make([]model.Evidence, 0, len(signals)+1)
		for _, item := range signals {
			item.EvidenceID = evidenceID("ev", row.EvidenceID+"|"+item.Signal)
			item.ResourceID = row.ResourceID
			item.ResourceName = resourceName
			item.CorrelationID = row.CorrelationID
			item.ObservedAt = row.ObservedAt
			item.Origin = row.Origin
			item.Mode = row.Mode
			if item.Kind == "" {
				item.Kind = KindForOrigin(row.Origin)
			}
			out = append(out, item)
		}
		if base.Signal != "" {
			out = append(out, base)
		}
		return out
	}
	return []model.Evidence{base}
}

func layerOf(idx *ResourceIndex, origin, resourceID string) string {
	if idx == nil {
		idx = &ResourceIndex{}
	}
	return idx.Layer(origin, resourceID)
}

func evidenceKey(item model.Evidence) string {
	return strings.Join([]string{
		strings.ToLower(item.Signal),
		item.ResourceID,
		item.TaskID,
		item.ObservedAt.UTC().Truncate(time.Second).Format(time.RFC3339),
	}, "|")
}

func evidenceKeys(items []model.Evidence) map[string]bool {
	out := map[string]bool{}
	for _, item := range items {
		out[evidenceKey(item)] = true
	}
	return out
}

func dedupResources(items []model.Resource) []model.Resource {
	seen := map[string]bool{}
	var out []model.Resource
	for _, item := range items {
		if item.ResourceID == "" || seen[item.ResourceID] {
			continue
		}
		seen[item.ResourceID] = true
		out = append(out, item)
	}
	return out
}
