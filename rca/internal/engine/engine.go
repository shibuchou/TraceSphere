// Package engine 是诊断侧编排层：
//
//	取数（platform + prometheus + fixture）→ 规则匹配（Evidence Match）→
//	根因候选 Top-N → 影响范围 / 时间线 / 子图 → 供 CLI 与 Web Console 使用。
package engine

import (
	"context"
	"fmt"
	"sort"
	"strings"
	"sync"
	"time"

	"tracesphere/rca/internal/config"
	"tracesphere/rca/internal/model"
	"tracesphere/rca/internal/rule"
	"tracesphere/rca/internal/source"
)

// Engine 诊断引擎。
type Engine struct {
	cfg      *config.Config
	rules    []*rule.Rule
	platform *source.PlatformClient
	prom     *source.PrometheusClient
	fixtures map[string]*source.Snapshot

	mu            sync.Mutex
	incidentCache map[string]source.RawIncident
	lastGathered  time.Time
}

// New 按配置装配引擎；规则加载失败视为致命错误（配置驱动是硬约束）。
func New(cfg *config.Config) (*Engine, error) {
	rules, err := rule.LoadDir(cfg.RulesDir)
	if err != nil {
		return nil, err
	}
	e := &Engine{cfg: cfg, rules: rules, incidentCache: map[string]source.RawIncident{}}
	if cfg.Sources.Platform.Enabled {
		e.platform = source.NewPlatformClient(cfg.Sources.Platform.BaseURL, cfg.Sources.Platform.Token)
	}
	if cfg.Sources.Prometheus.Enabled {
		e.prom = source.NewPrometheusClient(cfg.Sources.Prometheus.BaseURL)
	}
	// fixture 场景总是尝试加载：即使当前以真实数据源运行，也允许按需回放
	// （`diagnose --scenario` / POST /diagnose {"scenario":...} 需要它；
	//  只有 cfg.Sources.Fixture.Enabled 时才会把 fixture 证据并入实时取数。）
	if e.cfg.Sources.Fixture.Enabled || (e.platform == nil && e.prom == nil) {
		e.cfg.Sources.Fixture.Enabled = true
	}
	if fixtures, err := source.LoadFixtureDir(cfg.Sources.Fixture.Dir); err == nil {
		e.fixtures = fixtures
	}
	return e, nil
}

func (e *Engine) Config() *config.Config { return e.cfg }

func (e *Engine) Rules() []*rule.Rule { return e.rules }

// Window 由窗口秒数生成时间窗（未指定时用配置默认值）。
func (e *Engine) Window(seconds float64, from, to time.Time) model.Window {
	if seconds <= 0 {
		seconds = e.cfg.WindowSeconds
	}
	if to.IsZero() {
		to = time.Now().UTC()
	}
	if from.IsZero() {
		from = to.Add(-time.Duration(seconds) * time.Second)
	}
	return model.Window{From: model.TSTime{Time: from.UTC()}, To: model.TSTime{Time: to.UTC()}, Seconds: to.Sub(from).Seconds()}
}

// Gather 组装一次诊断所需的全部证据。
//
// 任何单一数据源失败都不会中断：降级信息进入 Sources/Notes，UI 明确展示真实/回放状态。
func (e *Engine) Gather(ctx context.Context, focus source.Focus, window model.Window) *source.Snapshot {
	snap := &source.Snapshot{
		Focus:  focus,
		Window: window,
		Sources: source.SourceStatus{
			Platform:   "off",
			Prometheus: "off",
			Fixture:    "off",
		},
	}
	if from := window.From.Time; !from.IsZero() {
		snap.Focus = focus
	}

	// ---- 1) fixture 基线（仅显式回放模式并入：--fixture / TRACESPHERE_RCA_FIXTURE）----
	// 实时模式下 fixture 只作为降级后备（见 3.5），不再无条件混入真实诊断（API.md §6）。
	if e.fixtures != nil && e.cfg.Sources.Fixture.Enabled {
		e.mergeFixtureBaseline(snap, window)
	}

	// ---- 2) platform（B 的平台：资源图 + 事件/证据 + 关联簇）----
	if e.platform != nil {
		var problems []string
		if _, err := e.platform.Health(ctx); err != nil {
			problems = append(problems, "health: "+err.Error())
		}
		if resources, err := e.platform.Resources(ctx, 2000); err == nil {
			snap.Resources = mergeResources(snap.Resources, resources)
		} else {
			problems = append(problems, "resources: "+err.Error())
		}

		if focus.CorrelationID != "" || focus.ResourceID != "" {
			if ctxSnap, err := e.platform.Context(ctx, focus, window.From.Time, window.To.Time); err == nil {
				snap.Evidence = append(snap.Evidence, ctxSnap.Evidence...)
				snap.Resources = mergeResources(snap.Resources, ctxSnap.Resources)
				snap.Edges = mergeEdges(snap.Edges, ctxSnap.Edges)
				if len(ctxSnap.Incidents) > 0 {
					snap.Incidents = ctxSnap.Incidents
				}
				if ctxSnap.Window.From.Time.Before(snap.Window.From.Time) {
					snap.Window = ctxSnap.Window
				}
			} else {
				problems = append(problems, "context: "+err.Error())
			}
			// 系统层证据补全：B 的关联簇以 correlation_id 为锚点，而 OOM/PSI/节流等
			// 系统层信号不带 correlation_id（方案 §5.3）。这里按"同一 VM 子树 + 时间窗"
			// 把窗口内的系统证据并入本次诊断（W2 可由 B 的关联引擎在簇内直接扩展）。
			if extra := e.widenSystemEvidence(ctx, snap, window); extra > 0 {
				snap.Sources.Notes = append(snap.Sources.Notes,
					fmt.Sprintf("已按资源拓扑+时间窗补入 %d 条系统层原始证据（correlation_id 锚点之外，合并后参与匹配）", extra))
			}
		} else {
			idxPlaceholder := source.NewResourceIndex(snap.Resources, snap.Edges)
			if events, err := e.platform.EventsWindow(ctx, window.From.Time, window.To.Time, 2000); err == nil {
				for _, ev := range events {
					snap.Evidence = append(snap.Evidence, source.EventToEvidence(ev, idxPlaceholder)...)
				}
			} else {
				problems = append(problems, "events: "+err.Error())
			}
			if items, err := e.platform.EvidenceWindow(ctx, window.From.Time, window.To.Time, 2000); err == nil {
				snap.Evidence = append(snap.Evidence, items...)
			} else {
				problems = append(problems, "evidence: "+err.Error())
			}
		}

		if incidents, err := e.loadClusters(ctx, 40); err == nil {
			if len(incidents) > 0 {
				snap.Incidents = mergeIncidents(snap.Incidents, incidents)
			}
		} else {
			problems = append(problems, "clusters: "+err.Error())
		}

		if len(problems) == 0 {
			snap.Sources.Platform = "real"
		} else {
			snap.Sources.Platform = "degraded"
			snap.Sources.Notes = append(snap.Sources.Notes, problems...)
		}
	}

	// ---- 3) prometheus（指标型证据：内存/限流/重启/CPU）----
	snap.Edges = source.EnrichEdges(snap.Resources, snap.Edges)
	if e.prom != nil {
		idx := source.NewResourceIndex(snap.Resources, snap.Edges)
		if e.prom.Healthy(ctx) {
			evidence, series, names, notes := e.prom.Collect(ctx, idx, window)
			snap.Evidence = append(snap.Evidence, evidence...)
			snap.Series = append(snap.Series, series...)
			// 用 cAdvisor 里的真实容器名回填资源名（B 的 ingest 用哈希占位名）
			for i := range snap.Resources {
				if display, ok := names[snap.Resources[i].ResourceID]; ok && display != "" {
					snap.Resources[i].Name = display
				}
			}
			snap.Sources.Prometheus = "real"
			snap.Sources.Notes = append(snap.Sources.Notes, notes...)
		} else {
			snap.Sources.Prometheus = "degraded"
			snap.Sources.Notes = append(snap.Sources.Notes,
				fmt.Sprintf("Prometheus %s 不可达，指标型证据缺失（规则评分会体现）", e.cfg.Sources.Prometheus.BaseURL))
		}
	}

	// ---- 3.5) 降级后备：真实源不可用时并入 fixture 回放（API.md §6）----
	//   platform 不可用 → prometheus + fixture；全不可用 → 仅 fixture。
	if e.fixtures != nil && !e.cfg.Sources.Fixture.Enabled && snap.Sources.Platform != "real" {
		if e.mergeFixtureBaseline(snap, window) {
			snap.Sources.Notes = append(snap.Sources.Notes,
				"platform 不可用，已按降级规则并入 fixture 回放证据（API.md §6）")
		}
	}

	// ---- 4) 归一化：计数器转增量、推理延迟 P95、同类证据合并、去重排序 ----
	snap.Evidence = source.NormalizeCounters(snap.Evidence)
	snap.Evidence = source.AddLatencyP95(snap.Evidence)
	snap.Evidence = source.Condense(snap.Evidence)
	snap.Evidence = source.DedupEvidence(snap.Evidence)
	snap.Resources = mergeResources(snap.Resources, nil)
	snap.Edges = mergeEdges(snap.Edges, nil)

	e.mu.Lock()
	e.lastGathered = time.Now().UTC()
	e.mu.Unlock()
	return snap
}

// mergeFixtureBaseline 把 fixture 基线并入快照（显式回放与降级后备共用）。
// 返回是否实际并入。fixture 目录为空/场景不存在时返回 false 并记录说明。
func (e *Engine) mergeFixtureBaseline(snap *source.Snapshot, window model.Window) bool {
	if e.fixtures == nil {
		return false
	}
	scenario := e.cfg.Sources.Fixture.Scenario
	entry, ok := e.fixtures[scenario]
	if !ok {
		for _, candidate := range e.fixtures {
			entry = candidate
			break
		}
	}
	if entry == nil {
		snap.Sources.Notes = append(snap.Sources.Notes, "fixture 目录为空，回放不可用")
		return false
	}
	snap.Resources = append(snap.Resources, entry.Resources...)
	snap.Edges = append(snap.Edges, entry.Edges...)
	snap.Series = append(snap.Series, entry.Series...)
	snap.Evidence = append(snap.Evidence, entry.Evidence...)
	snap.Incidents = append(snap.Incidents, entry.Incidents...)
	replayOnly := !e.cfg.Sources.Platform.Enabled && !e.cfg.Sources.Prometheus.Enabled
	if replayOnly || entry.Window.From.Time.After(window.From.Time) {
		snap.Window = entry.Window
	}
	snap.Sources.Fixture = "mock"
	snap.Sources.Notes = append(snap.Sources.Notes,
		fmt.Sprintf("fixture 回放场景 %s（%s）", scenario, entry.Sources.Notes))
	return true
}

// widenSystemEvidence 把窗口内的系统层证据并入当前诊断。
//
// 关联原则（方案 §5.3 / §5.6）：系统层事件不带 correlation_id，靠
// resource_id + 时间窗 + 资源图拓扑完成关联。这里取"与本焦点同属一个 VM 子树"
// 的窗口证据，避免把无关 VM 的信号混进证据链。
func (e *Engine) widenSystemEvidence(ctx context.Context, snap *source.Snapshot, window model.Window) int {
	if e.platform == nil {
		return 0
	}
	events, err := e.platform.EventsWindow(ctx, window.From.Time, window.To.Time, 2000)
	if err != nil {
		return 0
	}
	idx := source.NewResourceIndex(snap.Resources, source.EnrichEdges(snap.Resources, snap.Edges))

	// 焦点 VM：优先用 focus resource，其次用已在簇里的应用层证据反查
	focusVM := idx.VMOf(snap.Focus.ResourceID)
	if focusVM == "" {
		for _, item := range snap.Evidence {
			if item.CorrelationID != "" && item.ResourceID != "" {
				if vm := idx.VMOf(item.ResourceID); vm != "" {
					focusVM = vm
					break
				}
			}
		}
	}

	existing := map[string]bool{}
	for _, item := range snap.Evidence {
		existing[item.Signal+"|"+item.ResourceID+"|"+item.ObservedAt.UTC().Format(time.RFC3339)] = true
	}
	added := 0
	for _, ev := range events {
		items := source.EventToEvidence(ev, idx)
		for _, item := range items {
			if item.ResourceID != "" && focusVM != "" {
				if vm := idx.VMOf(item.ResourceID); vm != "" && vm != focusVM {
					continue // 无关 VM 的信号
				}
			}
			if item.Layer == "zsvirt" {
				continue // 云平台告警由告警页展示，不并入应用层根因证据
			}
			key := item.Signal + "|" + item.ResourceID + "|" + item.ObservedAt.UTC().Format(time.RFC3339)
			if existing[key] {
				continue
			}
			existing[key] = true
			snap.Evidence = append(snap.Evidence, item)
			added++
		}
	}
	return added
}

// loadClusters 拉取关联簇及其证据（B 的关联结果 = C 的"告警/事件"）。
func (e *Engine) loadClusters(ctx context.Context, limit int) ([]source.RawIncident, error) {
	rows, err := e.platform.Clusters(ctx, limit)
	if err != nil {
		return nil, err
	}
	var out []source.RawIncident
	for _, row := range rows {
		incident, evidence, err := e.platform.ClusterDetail(ctx, row.ClusterID)
		if err != nil {
			// 拿不到明细也保留簇摘要，避免告警列表空窗
			incident = &source.RawIncident{
				ClusterID: row.ClusterID, CorrelationID: row.CorrelationID, ResourceID: row.ResourceID,
				Rule: row.Rule, Summary: row.Summary, WindowStart: row.WindowStart, WindowEnd: row.WindowEnd,
			}
		}
		incident.Evidence = evidence
		out = append(out, *incident)
	}
	return out, nil
}

// Diagnose 对快照执行全部规则匹配，返回根因候选 Top-N（方案 §6.3）。
func (e *Engine) Diagnose(snap *source.Snapshot, topN int) model.DiagnoseResult {
	if topN <= 0 {
		topN = e.cfg.TopN
	}
	idx := source.NewResourceIndex(snap.Resources, snap.Edges)
	diagnoses := e.evaluate(snap.Evidence, idx, snap.Window, snap.Focus.CorrelationID)

	focus := snap.Focus.ResourceID
	for _, d := range diagnoses {
		if focus == "" && d.FocusResource != "" {
			focus = d.FocusResource
			break
		}
	}
	if focus == "" && len(snap.Incidents) > 0 {
		focus = snap.Incidents[0].ResourceID
	}

	top := diagnoses
	if len(top) > topN {
		top = top[:topN]
	}
	// 备选候选写入每条诊断
	for i := range top {
		for _, other := range diagnoses {
			if other.Rule == top[i].Rule {
				continue
			}
			top[i].Alternatives = append(top[i].Alternatives, model.Alternative{
				Rule: other.Rule, Title: other.Title, RootCause: other.RootCause,
				MatchScore: other.MatchScore, EvidenceCnt: len(other.Evidence),
			})
			if len(top[i].Alternatives) >= 3 {
				break
			}
		}
	}

	focusRef := ""
	if focus != "" {
		focusRef = focus
	}
	return model.DiagnoseResult{
		Window: snap.Window,
		Focus:  map[string]any{"correlation_id": snap.Focus.CorrelationID, "resource_id": focusRef},
		Sources: map[string]any{
			"platform": snap.Sources.Platform, "prometheus": snap.Sources.Prometheus,
			"fixture": snap.Sources.Fixture, "evidence_count": len(snap.Evidence),
			"notes": snap.Sources.Notes,
		},
		Diagnoses: top,
		Evidence:  snap.Evidence,
		Timeline:  BuildTimeline(snap.Evidence),
		Impact:    ComputeImpact(idx, focus, snap.Evidence),
		Graph:     BuildGraph(idx, focus, 2),
	}
}

// evaluate 对证据集执行规则匹配并按分数排序。
func (e *Engine) evaluate(evidence []model.Evidence, idx *source.ResourceIndex, window model.Window, correlationID string) []model.Diagnosis {
	var out []model.Diagnosis
	for _, r := range e.rules {
		eval := rule.Evaluate(r, evidence, idx)
		if len(eval.Items) == 0 || eval.MatchedWeight == 0 {
			continue
		}
		if eval.Score < e.cfg.MinScore {
			continue
		}
		out = append(out, buildDiagnosis(r, eval, window, correlationID))
	}
	sort.SliceStable(out, func(i, j int) bool {
		if out[i].MatchScore == out[j].MatchScore {
			return len(out[i].Evidence) > len(out[j].Evidence)
		}
		return out[i].MatchScore > out[j].MatchScore
	})
	return out
}

func buildDiagnosis(r *rule.Rule, eval rule.Evaluation, window model.Window, correlationID string) model.Diagnosis {
	ids := make([]string, 0, len(eval.Items))
	for _, item := range eval.Items {
		if item.EvidenceID != "" {
			ids = append(ids, item.EvidenceID)
		}
	}
	if correlationID == "" {
		for _, item := range eval.Items {
			if item.CorrelationID != "" {
				correlationID = item.CorrelationID
				break
			}
		}
	}
	suggestions := make([]model.Suggestion, 0, len(r.Result.Suggestions))
	for _, s := range r.Result.Suggestions {
		suggestions = append(suggestions, model.Suggestion{
			Action: s.Action, Title: s.Title, Basis: s.Basis, Detail: s.Detail, Risk: s.Risk,
		})
	}
	return model.Diagnosis{
		DiagnosisID:    fmt.Sprintf("diag-%s-%s", window.To.UTC().Format("20060102T150405Z"), r.ID),
		Rule:           r.ID,
		RuleVersion:    r.Version,
		Title:          r.Title,
		RootCause:      r.Result.RootCause,
		RootCauseLabel: r.Result.Label,
		Severity:       model.Severity(r.Severity),
		MatchScore:     eval.Score,
		MatchNote:      rule.MatchNote,
		ScoreBreakdown: eval.Breakdown,
		EvidenceIDs:    ids,
		Evidence:       eval.Items,
		Suggestions:    suggestions,
		Window:         window,
		CorrelationID:  correlationID,
		FocusResource:  eval.FocusResource,
	}
}

// ---------------------------------------------------------------------------
// 合并工具
// ---------------------------------------------------------------------------

func mergeResources(base, extra []model.Resource) []model.Resource {
	index := map[string]int{}
	for i, item := range base {
		index[item.ResourceID] = i
	}
	for _, item := range extra {
		if item.ResourceID == "" {
			continue
		}
		if pos, ok := index[item.ResourceID]; ok {
			merged := base[pos]
			if merged.Name == "" || (item.Name != "" && len(item.Name) > len(merged.Name)) {
				if item.Name != "" {
					merged.Name = item.Name
				}
			}
			if merged.Kind == "" {
				merged.Kind = item.Kind
			}
			if merged.ContainerID == "" {
				merged.ContainerID = item.ContainerID
			}
			if merged.VMID == "" {
				merged.VMID = item.VMID
			}
			if merged.HostID == "" {
				merged.HostID = item.HostID
			}
			if merged.ClusterID == "" {
				merged.ClusterID = item.ClusterID
			}
			if merged.State == "" {
				merged.State = item.State
			}
			if item.Attributes != nil {
				if merged.Attributes == nil {
					merged.Attributes = map[string]any{}
				}
				for k, v := range item.Attributes {
					merged.Attributes[k] = v
				}
			}
			base[pos] = merged
			continue
		}
		index[item.ResourceID] = len(base)
		base = append(base, item)
	}
	sort.SliceStable(base, func(i, j int) bool { return base[i].ResourceID < base[j].ResourceID })
	return base
}

func mergeEdges(base, extra []model.Edge) []model.Edge {
	seen := map[string]bool{}
	var out []model.Edge
	for _, item := range append(append([]model.Edge{}, base...), extra...) {
		if item.SrcID == "" || item.DstID == "" {
			continue
		}
		rel := item.Relation
		if rel == "" {
			rel = "related_to"
		}
		key := item.SrcID + "|" + item.DstID + "|" + rel
		if seen[key] {
			continue
		}
		seen[key] = true
		item.Relation = rel
		out = append(out, item)
	}
	sort.SliceStable(out, func(i, j int) bool {
		if out[i].SrcID == out[j].SrcID {
			return out[i].DstID < out[j].DstID
		}
		return out[i].SrcID < out[j].SrcID
	})
	return out
}

func mergeIncidents(base, extra []source.RawIncident) []source.RawIncident {
	seen := map[string]bool{}
	var out []source.RawIncident
	for _, item := range append(append([]source.RawIncident{}, base...), extra...) {
		key := item.ClusterID
		if key == "" {
			key = item.CorrelationID + "|" + item.ResourceID
		}
		if seen[key] {
			continue
		}
		seen[key] = true
		out = append(out, item)
	}
	sort.SliceStable(out, func(i, j int) bool {
		return out[i].WindowEnd.After(out[j].WindowEnd.Time)
	})
	return out
}

// LayerRank 时间线分层排序（应用层在最后展示"表现"，系统层在前"起因"）。
func LayerRank(layer string) int {
	switch layer {
	case "zsvirt":
		return 0
	case "vm":
		return 1
	case "container":
		return 2
	case "application":
		return 3
	default:
		return 4
	}
}

func shortResource(id string) string {
	if id == "" {
		return "-"
	}
	return strings.TrimSpace(id)
}
