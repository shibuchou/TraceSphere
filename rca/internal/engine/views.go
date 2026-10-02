package engine

import (
	"context"
	"fmt"
	"sort"
	"strings"
	"time"

	"tracesphere/rca/internal/model"
	"tracesphere/rca/internal/source"
)

// ---------------------------------------------------------------------------
// 时间线 / 影响范围 / 子图
// ---------------------------------------------------------------------------

// BuildTimeline 按时间排序输出统一时间线（UI 按 layer 着色：应用/容器/虚拟机/云平台）。
func BuildTimeline(items []model.Evidence) []model.TimelineEntry {
	entries := make([]model.TimelineEntry, 0, len(items))
	for _, item := range items {
		entries = append(entries, model.TimelineEntry{
			ObservedAt:   item.ObservedAt,
			Layer:        item.Layer,
			Signal:       item.Signal,
			Severity:     item.Severity,
			ResourceID:   item.ResourceID,
			ResourceName: item.ResourceName,
			Description:  item.Description,
			EvidenceID:   item.EvidenceID,
			TaskID:       item.TaskID,
		})
	}
	sort.SliceStable(entries, func(i, j int) bool {
		return entries[i].ObservedAt.Before(entries[j].ObservedAt.Time)
	})
	return entries
}

// ComputeImpact 计算影响范围：沿资源图向上/向下各 2 跳，标出受影响的容器/服务/任务。
func ComputeImpact(idx *source.ResourceIndex, focus string, evidence []model.Evidence) model.Impact {
	impact := model.Impact{Counts: map[string]int{}}
	failedTasks := failedTaskSet(evidence)
	if focus != "" {
		if res, ok := idx.Get(focus); ok {
			impact.Focus = &model.ResourceRef{ResourceID: res.ResourceID, Kind: res.Kind, Name: res.Name}
		} else {
			impact.Focus = &model.ResourceRef{ResourceID: focus, Kind: model.KindOf(focus), Name: idx.Name(focus)}
		}
		impact.Scope = walkScope(idx, focus, 2)
	}
	// 关联任务（带 task_id 的失败证据即使不在图上也要列出）
	for taskID := range failedTasks {
		resourceID := "task:" + taskID
		found := false
		for _, entry := range impact.Scope {
			if entry.ResourceID == resourceID {
				found = true
				break
			}
		}
		if !found {
			impact.Scope = append(impact.Scope, model.ImpactScopeEntry{
				ResourceID: resourceID, Kind: "task", Name: taskID, Relation: "calls/失败证据", Depth: 1, Status: "failed",
			})
		}
	}
	for i := range impact.Scope {
		if _, ok := failedTasks[strings.TrimPrefix(impact.Scope[i].ResourceID, "task:")]; ok {
			impact.Scope[i].Status = "failed"
		}
	}
	for _, entry := range impact.Scope {
		impact.Counts[entry.Kind]++
	}
	sort.SliceStable(impact.Scope, func(i, j int) bool {
		if impact.Scope[i].Kind == impact.Scope[j].Kind {
			return impact.Scope[i].Name < impact.Scope[j].Name
		}
		return impact.Scope[i].Kind < impact.Scope[j].Kind
	})
	return impact
}

func failedTaskSet(evidence []model.Evidence) map[string]bool {
	out := map[string]bool{}
	for _, item := range evidence {
		if item.TaskID == "" {
			continue
		}
		if strings.EqualFold(item.Signal, "task.failed") || model.SeverityRank(item.Severity) >= 2 {
			out[item.TaskID] = true
		}
	}
	return out
}

func walkScope(idx *source.ResourceIndex, focus string, maxDepth int) []model.ImpactScopeEntry {
	type queueItem struct {
		id    string
		depth int
		rel   string
	}
	visited := map[string]bool{focus: true}
	queue := []queueItem{{id: focus, depth: 0}}
	var out []model.ImpactScopeEntry
	all := idx.All()
	edges := buildAdjacency(all, idx)
	for len(queue) > 0 {
		current := queue[0]
		queue = queue[1:]
		if current.depth >= maxDepth {
			continue
		}
		for _, next := range edges[current.id] {
			if visited[next.id] {
				continue
			}
			visited[next.id] = true
			queue = append(queue, queueItem{id: next.id, depth: current.depth + 1, rel: next.relation})
			res, ok := idx.Get(next.id)
			kind := model.KindOf(next.id)
			name := idx.Name(next.id)
			status := ""
			if ok {
				kind = res.Kind
				name = res.Name
				status = res.State
			}
			if kind == "host" || kind == "cluster" {
				continue
			}
			out = append(out, model.ImpactScopeEntry{
				ResourceID: next.id, Kind: kind, Name: name,
				Relation: next.relation, Depth: current.depth + 1, Status: status,
			})
		}
	}
	return out
}

type neighbor struct {
	id       string
	relation string
}

// buildAdjacency 用资源表 + 边表构造邻接（边表缺省时用 vm_id 归属兜底）。
func buildAdjacency(resources []model.Resource, idx *source.ResourceIndex) map[string][]neighbor {
	adj := map[string][]neighbor{}
	for _, res := range resources {
		if res.VMID != "" {
			adj[res.VMID] = append(adj[res.VMID], neighbor{id: res.ResourceID, relation: "contains"})
			adj[res.ResourceID] = append(adj[res.ResourceID], neighbor{id: res.VMID, relation: "runs_on"})
		}
		if res.HostID != "" {
			adj[res.HostID] = append(adj[res.HostID], neighbor{id: res.ResourceID, relation: "contains"})
			adj[res.ResourceID] = append(adj[res.ResourceID], neighbor{id: res.HostID, relation: "runs_on"})
		}
	}
	for _, edge := range idx.EdgesSnapshot() {
		adj[edge.SrcID] = append(adj[edge.SrcID], neighbor{id: edge.DstID, relation: edge.Relation})
		adj[edge.DstID] = append(adj[edge.DstID], neighbor{id: edge.SrcID, relation: edge.Relation})
	}
	return adj
}

// BuildGraph 生成 G6 可用的资源子图（focus 为空时返回全图）。
func BuildGraph(idx *source.ResourceIndex, focus string, depth int) model.Graph {
	graph := model.Graph{}
	resources := idx.All()
	adjs := buildAdjacency(resources, idx)

	include := map[string]bool{}
	if focus == "" {
		for _, res := range resources {
			include[res.ResourceID] = true
			if len(include) >= 200 {
				break
			}
		}
	} else {
		include[focus] = true
		frontier := []string{focus}
		for d := 0; d < depth; d++ {
			var next []string
			for _, id := range frontier {
				for _, nb := range adjs[id] {
					if include[nb.id] {
						continue
					}
					include[nb.id] = true
					next = append(next, nb.id)
				}
			}
			frontier = next
		}
	}

	for _, res := range resources {
		if !include[res.ResourceID] {
			continue
		}
		graph.Nodes = append(graph.Nodes, model.GraphNode{
			ID:       res.ResourceID,
			Label:    displayName(res),
			Kind:     res.Kind,
			Status:   statusOfResource(res),
			Subtitle: subtitleOf(res),
		})
	}
	for _, edge := range idx.EdgesSnapshot() {
		if !include[edge.SrcID] || !include[edge.DstID] {
			continue
		}
		graph.Edges = append(graph.Edges, model.GraphEdge{
			ID:       edge.SrcID + "->" + edge.DstID + ":" + edge.Relation,
			Source:   edge.SrcID,
			Target:   edge.DstID,
			Relation: edge.Relation,
			Label:    edge.Relation,
		})
	}
	return graph
}

func displayName(res model.Resource) string {
	if res.Name != "" {
		return res.Name
	}
	return res.ResourceID
}

func subtitleOf(res model.Resource) string {
	switch res.Kind {
	case "vm":
		if res.Attributes != nil {
			if ips, ok := res.Attributes["ips"].([]any); ok && len(ips) > 0 {
				return fmt.Sprintf("%v", ips[0])
			}
			if ips, ok := res.Attributes["ips"].([]string); ok && len(ips) > 0 {
				return ips[0]
			}
		}
		return res.State
	case "container":
		if len(res.ContainerID) >= 12 {
			return res.ContainerID[:12]
		}
		return res.ContainerID
	case "task":
		if res.CorrelationID != "" {
			return "corr=" + res.CorrelationID
		}
	}
	return res.State
}

func statusOfResource(res model.Resource) string {
	state := strings.ToLower(res.State)
	switch state {
	case "failed", "error", "stopped", "exited", "dead":
		return "critical"
	case "warning", "degraded", "restarting":
		return "warning"
	case "running", "up", "active", "ok":
		return "healthy"
	}
	if res.State == "" {
		return "unknown"
	}
	return "healthy"
}

// ---------------------------------------------------------------------------
// 视图：拓扑 / 健康 / 告警
// ---------------------------------------------------------------------------

// Topology 生成拓扑页数据（Host Combo → VM Combo → Container / Service / Task）。
func (e *Engine) Topology(ctx context.Context, focusID string, windowSeconds float64) model.Topology {
	window := e.Window(windowSeconds, time.Time{}, time.Time{})
	snap := e.Gather(ctx, source.Focus{ResourceID: focusID}, window)
	idx := source.NewResourceIndex(snap.Resources, snap.Edges)

	severityByResource := map[string]string{}
	incidentsByResource := map[string]int{}
	for _, item := range snap.Evidence {
		if item.ResourceID == "" {
			continue
		}
		severityByResource[item.ResourceID] = model.MaxSeverity(severityByResource[item.ResourceID], item.Severity)
	}
	for _, incident := range snap.Incidents {
		if incident.ResourceID != "" {
			incidentsByResource[incident.ResourceID]++
		}
	}

	tp := model.Topology{
		GeneratedAt: model.TSTime{Time: time.Now().UTC()},
		Source: map[string]any{
			"platform": snap.Sources.Platform, "prometheus": snap.Sources.Prometheus,
			"fixture": snap.Sources.Fixture, "notes": snap.Sources.Notes,
		},
		Legend: []model.Legend{
			{Kind: "host", Label: "宿主机"}, {Kind: "vm", Label: "虚拟机"},
			{Kind: "container", Label: "容器"}, {Kind: "service", Label: "AI 服务"},
			{Kind: "task", Label: "Agent 任务"}, {Kind: "process", Label: "进程"},
		},
	}

	comboSeen := map[string]bool{}
	resources := idx.All()
	for _, res := range resources {
		if res.Kind != "host" && res.Kind != "vm" {
			continue
		}
		comboID := "combo:" + res.Kind + ":" + shortID(res.ResourceID)
		if comboSeen[comboID] {
			continue
		}
		comboSeen[comboID] = true
		combo := model.Combo{ID: comboID, Label: displayName(res), Kind: res.Kind}
		if res.Kind == "vm" {
			hostID := res.HostID
			if hostID == "" {
				if host := findHostOf(idx, res.ResourceID); host != "" {
					hostID = host
				}
			}
			if hostID != "" {
				combo.Parent = "combo:host:" + shortID(hostID)
			}
		}
		tp.Combos = append(tp.Combos, combo)
	}
	// 没有 host 资源时（fixture 精简场景），保证 combo 树完整
	hasHostCombo := false
	for _, combo := range tp.Combos {
		if combo.Kind == "host" {
			hasHostCombo = true
		}
	}
	if !hasHostCombo {
		tp.Combos = append([]model.Combo{{ID: "combo:host:unknown", Label: "宿主机（未注册）", Kind: "host"}}, tp.Combos...)
		for i := range tp.Combos {
			if tp.Combos[i].Kind == "vm" && tp.Combos[i].Parent == "" {
				tp.Combos[i].Parent = "combo:host:unknown"
			}
		}
	}

	for _, res := range resources {
		node := model.GraphNode{
			ID:       res.ResourceID,
			Label:    displayName(res),
			Kind:     res.Kind,
			Subtitle: subtitleOf(res),
			Status:   statusOfResource(res),
			Combo:    comboOf(idx, res),
			Incident: incidentsByResource[res.ResourceID],
		}
		if sev := severityByResource[res.ResourceID]; sev != "" {
			node.Status = statusFromSeverity(sev)
			if model.SeverityRank(sev) >= 2 {
				node.Badges = append(node.Badges, strings.ToUpper(sev))
			}
		}
		tp.Nodes = append(tp.Nodes, node)
	}
	for _, edge := range snap.Edges {
		tp.Edges = append(tp.Edges, model.GraphEdge{
			ID:     edge.SrcID + "->" + edge.DstID + ":" + edge.Relation,
			Source: edge.SrcID, Target: edge.DstID,
			Relation: edge.Relation, Label: edge.Relation,
		})
	}
	sort.SliceStable(tp.Nodes, func(i, j int) bool {
		if tp.Nodes[i].Kind == tp.Nodes[j].Kind {
			return tp.Nodes[i].Label < tp.Nodes[j].Label
		}
		return kindRank(tp.Nodes[i].Kind) < kindRank(tp.Nodes[j].Kind)
	})
	return tp
}

func comboOf(idx *source.ResourceIndex, res model.Resource) string {
	switch res.Kind {
	case "host":
		return "combo:host:" + shortID(res.ResourceID)
	case "vm":
		return "combo:vm:" + shortID(res.ResourceID)
	}
	vm := res.VMID
	if vm == "" {
		vm = idx.VMOf(res.ResourceID)
	}
	if vm != "" {
		return "combo:vm:" + shortID(vm)
	}
	if host := findHostOf(idx, res.ResourceID); host != "" {
		return "combo:host:" + shortID(host)
	}
	return "combo:host:unknown"
}

func findHostOf(idx *source.ResourceIndex, resourceID string) string {
	seen := map[string]bool{}
	current := resourceID
	for i := 0; i < 8 && current != "" && !seen[current]; i++ {
		seen[current] = true
		res, ok := idx.Get(current)
		if !ok {
			return ""
		}
		if res.Kind == "host" {
			return res.ResourceID
		}
		if res.HostID != "" {
			return res.HostID
		}
		current = idx.ParentOf(current)
	}
	return ""
}

func kindRank(kind string) int {
	switch kind {
	case "host":
		return 0
	case "vm":
		return 1
	case "container":
		return 2
	case "service":
		return 3
	case "task":
		return 4
	case "process":
		return 5
	default:
		return 6
	}
}

func statusFromSeverity(sev string) string {
	switch model.Severity(sev) {
	case "critical":
		return "critical"
	case "major":
		return "critical"
	case "warning":
		return "warning"
	default:
		return "healthy"
	}
}

func shortID(id string) string {
	if idx := strings.Index(id, ":"); idx >= 0 {
		id = id[idx+1:]
	}
	if len(id) > 12 {
		return id[:12]
	}
	return id
}

// Overview 生成健康页数据。
func (e *Engine) Overview(ctx context.Context, windowSeconds float64) model.Overview {
	window := e.Window(windowSeconds, time.Time{}, time.Time{})
	snap := e.Gather(ctx, source.Focus{}, window)
	idx := source.NewResourceIndex(snap.Resources, snap.Edges)

	overview := model.Overview{
		GeneratedAt: model.TSTime{Time: time.Now().UTC()},
		Source: map[string]any{
			"platform": snap.Sources.Platform, "prometheus": snap.Sources.Prometheus,
			"fixture": snap.Sources.Fixture, "notes": snap.Sources.Notes,
		},
		Window:   snap.Window,
		Timeline: BuildTimeline(snap.Evidence),
	}

	byResource := map[string][]model.Evidence{}
	for _, item := range snap.Evidence {
		byResource[item.ResourceID] = append(byResource[item.ResourceID], item)
	}

	for _, res := range idx.All() {
		switch res.Kind {
		case "vm", "container", "service":
		default:
			continue
		}
		card := model.WorkloadCard{
			ResourceID: res.ResourceID, Name: displayName(res), Kind: res.Kind,
			WorkloadType: workloadType(res), Status: statusOfResource(res), HealthScore: 100,
		}
		if res.VMID != "" {
			card.Parent = &model.ResourceRef{ResourceID: res.VMID, Kind: "vm", Name: idx.Name(res.VMID)}
		}
		items := byResource[res.ResourceID]
		signals := map[string]*model.SignalCount{}
		worst := ""
		for _, item := range items {
			worst = model.MaxSeverity(worst, item.Severity)
			key := item.Signal + "|" + item.Layer
			entry, ok := signals[key]
			if !ok {
				entry = &model.SignalCount{Signal: item.Signal, Layer: item.Layer, Severity: item.Severity, LastAt: item.ObservedAt}
				signals[key] = entry
			}
			entry.Count++
			if item.ObservedAt.After(entry.LastAt.Time) {
				entry.LastAt = item.ObservedAt
			}
			entry.Severity = model.MaxSeverity(entry.Severity, item.Severity)
			if item.ObservedAt.After(card.LastEventAt.Time) {
				card.LastEventAt = item.ObservedAt
			}
			if strings.EqualFold(item.Signal, "task.failed") {
				card.TaskFailures++
			}
		}
		for _, entry := range signals {
			card.Signals = append(card.Signals, *entry)
		}
		sort.SliceStable(card.Signals, func(i, j int) bool {
			if card.Signals[i].Severity == card.Signals[j].Severity {
				return card.Signals[i].Signal < card.Signals[j].Signal
			}
			return model.SeverityRank(card.Signals[i].Severity) > model.SeverityRank(card.Signals[j].Severity)
		})
		card.HealthScore = healthScore(card.Signals, card.TaskFailures)
		card.Status = statusFromScore(card.HealthScore, worst)
		card.Metrics = metricsFor(snap.Series, res.ResourceID, idx.Name(res.ResourceID))
		overview.Workloads = append(overview.Workloads, card)
	}
	sort.SliceStable(overview.Workloads, func(i, j int) bool {
		if overview.Workloads[i].HealthScore == overview.Workloads[j].HealthScore {
			return overview.Workloads[i].Name < overview.Workloads[j].Name
		}
		return overview.Workloads[i].HealthScore < overview.Workloads[j].HealthScore
	})

	overview.Summary = model.Summary{
		Resources:   len(overview.Workloads),
		TasksTotal:  len(idx.OfKind("task")),
		Incidents:   len(snap.Incidents),
		OpenAlerts:  countAlerts(snap.Evidence),
		TasksFailed: countTaskFailures(snap.Evidence),
	}
	for _, card := range overview.Workloads {
		switch card.Status {
		case "critical":
			overview.Summary.Critical++
		case "warning":
			overview.Summary.Warning++
		default:
			overview.Summary.Healthy++
		}
	}
	return overview
}

func workloadType(res model.Resource) string {
	if res.Labels != nil {
		if v, ok := res.Labels["com.tracesphere.workload.type"]; ok {
			return v
		}
	}
	name := strings.ToLower(res.Name)
	switch {
	case strings.Contains(name, "llama") || strings.Contains(name, "inference"):
		return "inference"
	case strings.Contains(name, "tool"):
		return "tool"
	case strings.Contains(name, "agent"):
		return "agent"
	case strings.Contains(name, "stress") || strings.Contains(name, "victim"):
		return "fault-injection"
	}
	return ""
}

func healthScore(signals []model.SignalCount, taskFailures int) float64 {
	score := 100.0
	for _, signal := range signals {
		switch model.Severity(signal.Severity) {
		case "critical":
			score -= 45
		case "major":
			score -= 22
		case "warning":
			score -= 8
		}
	}
	score -= float64(taskFailures) * 6
	if score < 0 {
		score = 0
	}
	if score > 100 {
		score = 100
	}
	return score
}

func statusFromScore(score float64, worst string) string {
	switch {
	case model.SeverityRank(worst) >= 2 || score < 60:
		return "critical"
	case model.SeverityRank(worst) == 1 || score < 85:
		return "warning"
	default:
		return "healthy"
	}
}

func countAlerts(evidence []model.Evidence) int {
	count := 0
	for _, item := range evidence {
		if model.SeverityRank(item.Severity) >= 2 {
			count++
		}
	}
	return count
}

func countTaskFailures(evidence []model.Evidence) int {
	tasks := map[string]bool{}
	for _, item := range evidence {
		if strings.EqualFold(item.Signal, "task.failed") && item.TaskID != "" {
			tasks[item.TaskID] = true
		}
	}
	return len(tasks)
}

func metricsFor(series []model.Series, resourceID, name string) []model.Metric {
	var out []model.Metric
	for _, s := range series {
		if !strings.Contains(s.Label, name) {
			continue
		}
		if len(s.Points) == 0 {
			continue
		}
		last := s.Points[len(s.Points)-1][1]
		status := "info"
		for _, threshold := range s.Thresholds {
			if last >= threshold.Value {
				status = "critical"
			}
		}
		trend := "flat"
		if len(s.Points) > 1 {
			first := s.Points[0][1]
			switch {
			case last > first*1.1:
				trend = "up"
			case last < first*0.9:
				trend = "down"
			}
		}
		out = append(out, model.Metric{
			Name: s.Name, Label: s.Label, Value: last, Unit: s.Unit, Status: status, Trend: trend,
		})
	}
	sort.SliceStable(out, func(i, j int) bool { return out[i].Name < out[j].Name })
	return out
}

// Incidents 生成告警/事件列表（B 的关联簇 + C 的 Top-1 诊断摘要）。
func (e *Engine) Incidents(ctx context.Context, windowSeconds float64, severity, ruleFilter string, limit int) model.IncidentList {
	window := e.Window(windowSeconds, time.Time{}, time.Time{})
	snap := e.Gather(ctx, source.Focus{}, window)
	idx := source.NewResourceIndex(snap.Resources, snap.Edges)

	raw := snap.Incidents
	if len(raw) == 0 {
		raw = synthesizeIncidents(snap.Evidence)
	}

	list := model.IncidentList{GeneratedAt: model.TSTime{Time: time.Now().UTC()}}
	for _, incident := range raw {
		evidence := incident.Evidence
		if len(evidence) == 0 {
			evidence = filterEvidence(snap.Evidence, incident)
		}
		id := incident.ClusterID
		if id == "" {
			id = syntheticIncidentID(incident)
		}
		e.mu.Lock()
		e.incidentCache[id] = source.RawIncident{
			ClusterID: id, CorrelationID: incident.CorrelationID, ResourceID: incident.ResourceID,
			Rule: incident.Rule, Summary: incident.Summary,
			WindowStart: incident.WindowStart, WindowEnd: incident.WindowEnd, Evidence: evidence,
		}
		e.mu.Unlock()

		item := model.Incident{
			IncidentID: id, CorrelationID: incident.CorrelationID, Status: "open",
			Source: "correlation_cluster", ClusterID: incident.ClusterID,
			EvidenceCount: len(evidence),
			FirstSeenAt:   incident.WindowStart,
			LastSeenAt:    incident.WindowEnd,
			Summary:       incident.Summary,
			Severity:      "info",
			Title:         "未匹配已知规则（证据不足）",
			Rule:          "",
			AffectedTasks: countTaskFailures(evidence),
		}
		if len(evidence) > 0 {
			item.FirstSeenAt = evidence[0].ObservedAt
			item.LastSeenAt = evidence[len(evidence)-1].ObservedAt
		}
		if item.LastSeenAt.IsZero() {
			item.LastSeenAt = incident.WindowEnd
		}
		if item.FirstSeenAt.IsZero() {
			item.FirstSeenAt = incident.WindowStart
		}

		diagnoses := e.evaluate(evidence, idx, window, incident.CorrelationID)
		if len(diagnoses) > 0 {
			top := diagnoses[0]
			item.Title = top.Title
			item.Rule = top.Rule
			item.Severity = top.Severity
			item.MatchScore = top.MatchScore
			item.RootCauseLabel = top.RootCauseLabel
		} else if len(evidence) > 0 {
			worst := ""
			for _, ev := range evidence {
				worst = model.MaxSeverity(worst, ev.Severity)
			}
			item.Severity = model.Severity(worst)
		}
		focus := incident.ResourceID
		if focus == "" && len(evidence) > 0 {
			focus = evidence[0].ResourceID
		}
		if focus != "" {
			item.FocusResource = &model.ResourceRef{ResourceID: focus, Kind: model.KindOf(focus), Name: idx.Name(focus)}
		}
		if item.Summary == "" && item.FocusResource != nil {
			item.Summary = fmt.Sprintf("%s 相关 %d 条证据", item.FocusResource.Name, len(evidence))
		}
		if limit > 0 && len(list.Incidents) >= limit {
			break
		}
		if ruleFilter != "" && !strings.EqualFold(item.Rule, ruleFilter) {
			continue
		}
		if severity != "" && !strings.EqualFold(item.Severity, severity) {
			continue
		}
		list.Incidents = append(list.Incidents, item)
	}
	sort.SliceStable(list.Incidents, func(i, j int) bool {
		return list.Incidents[i].LastSeenAt.After(list.Incidents[j].LastSeenAt.Time)
	})
	list.Count = len(list.Incidents)
	return list
}

// IncidentDetail 生成告警详情页数据。
func (e *Engine) IncidentDetail(ctx context.Context, incidentID string) (model.IncidentDetail, error) {
	window := e.Window(0, time.Time{}, time.Time{})

	e.mu.Lock()
	cached, ok := e.incidentCache[incidentID]
	e.mu.Unlock()

	var (
		incident source.RawIncident
		snap     *source.Snapshot
	)
	if ok && len(cached.Evidence) > 0 {
		incident = cached
		snap = e.Gather(ctx, source.Focus{CorrelationID: cached.CorrelationID, ResourceID: cached.ResourceID}, window)
	} else if e.platform != nil {
		if found, _, err := e.platform.ClusterDetail(ctx, incidentID); err == nil && found != nil {
			incident = *found
		}
		snap = e.Gather(ctx, source.Focus{CorrelationID: incident.CorrelationID, ResourceID: incident.ResourceID}, window)
	}
	if snap == nil {
		snap = e.Gather(ctx, source.Focus{}, window)
	}
	if len(incident.Evidence) == 0 {
		for _, candidate := range snap.Incidents {
			if candidate.ClusterID == incidentID {
				incident = candidate
				break
			}
		}
	}
	evidence := incident.Evidence
	if len(evidence) == 0 {
		evidence = filterEvidence(snap.Evidence, incident)
	}
	if len(evidence) == 0 {
		evidence = snap.Evidence
	}

	idx := source.NewResourceIndex(snap.Resources, snap.Edges)
	focus := incident.ResourceID
	if focus == "" && len(evidence) > 0 {
		focus = evidence[0].ResourceID
	}
	diagnoses := e.evaluate(evidence, idx, window, incident.CorrelationID)

	detail := model.IncidentDetail{
		Window:     snap.Window,
		Candidates: diagnoses,
		Evidence:   evidence,
		Timeline:   BuildTimeline(evidence),
		Impact:     ComputeImpact(idx, focus, evidence),
		Graph:      BuildGraph(idx, focus, 2),
	}
	incidentRow := model.Incident{
		IncidentID: incidentID, CorrelationID: incident.CorrelationID, ClusterID: incident.ClusterID,
		Status: "open", Source: "correlation_cluster", EvidenceCount: len(evidence),
		AffectedTasks: countTaskFailures(evidence), Summary: incident.Summary,
		FirstSeenAt: incident.WindowStart, LastSeenAt: incident.WindowEnd,
		Severity: "info", Title: "未匹配已知规则（证据不足）",
	}
	if len(evidence) > 0 {
		incidentRow.FirstSeenAt = evidence[0].ObservedAt
		incidentRow.LastSeenAt = evidence[len(evidence)-1].ObservedAt
	}
	if focus != "" {
		incidentRow.FocusResource = &model.ResourceRef{ResourceID: focus, Kind: model.KindOf(focus), Name: idx.Name(focus)}
	}
	if len(diagnoses) > 0 {
		top := diagnoses[0]
		detail.Diagnosis = &top
		incidentRow.Title = top.Title
		incidentRow.Rule = top.Rule
		incidentRow.Severity = top.Severity
		incidentRow.MatchScore = top.MatchScore
		incidentRow.RootCauseLabel = top.RootCauseLabel
	}
	detail.Incident = incidentRow
	return detail, nil
}

// DiagnoseRequest 诊断请求（HTTP 与 CLI 共用）。
type DiagnoseRequest struct {
	CorrelationID string
	ResourceID    string
	WindowSeconds float64
	From          time.Time
	To            time.Time
	TopN          int
	Scenario      string
}

// Run 执行一次诊断。
func (e *Engine) Run(ctx context.Context, req DiagnoseRequest) model.DiagnoseResult {
	if req.Scenario != "" && e.fixtures != nil {
		if snap, ok := e.fixtures[req.Scenario]; ok {
			copied := *snap
			copied.Focus = source.Focus{CorrelationID: req.CorrelationID, ResourceID: req.ResourceID}
			return e.Diagnose(&copied, req.TopN)
		}
	}
	window := e.Window(req.WindowSeconds, req.From, req.To)
	snap := e.Gather(ctx, source.Focus{CorrelationID: req.CorrelationID, ResourceID: req.ResourceID}, window)
	return e.Diagnose(snap, req.TopN)
}

// Series 返回 ECharts 曲线数据（按资源与指标名过滤）。
func (e *Engine) Series(ctx context.Context, resourceID string, metrics []string, windowSeconds float64) model.SeriesResponse {
	window := e.Window(windowSeconds, time.Time{}, time.Time{})
	snap := e.Gather(ctx, source.Focus{ResourceID: resourceID}, window)
	idx := source.NewResourceIndex(snap.Resources, snap.Edges)
	name := idx.Name(resourceID)

	wanted := map[string]bool{}
	for _, metric := range metrics {
		wanted[metric] = true
	}
	resp := model.SeriesResponse{ResourceID: resourceID, Window: snap.Window}
	for _, series := range snap.Series {
		if len(wanted) > 0 && !wanted[series.Name] {
			continue
		}
		if resourceID != "" && name != "" && !strings.Contains(series.Label, name) && !wanted[series.Name] {
			continue
		}
		resp.Series = append(resp.Series, series)
	}
	sort.SliceStable(resp.Series, func(i, j int) bool { return resp.Series[i].Name < resp.Series[j].Name })
	return resp
}

// RuleInfos 规则清单（诊断页展示"配置驱动、可扩展"）。
func (e *Engine) RuleInfos() []model.RuleInfo {
	out := make([]model.RuleInfo, 0, len(e.rules))
	for _, r := range e.rules {
		out = append(out, model.RuleInfo{
			Rule: r.ID, Version: r.Version, Title: r.Title, Description: r.Description,
			Severity: model.Severity(r.Severity), Clauses: len(r.Evidence),
			Weights: r.MandatoryWeight(), Source: r.SourcePath,
		})
	}
	return out
}

// Health 服务健康 + 各数据源状态。
func (e *Engine) Health(ctx context.Context) map[string]any {
	status := map[string]any{
		"status":         "ok",
		"schema_version": "v1",
		"rules":          len(e.rules),
		"time":           time.Now().UTC().Format(time.RFC3339),
	}
	platformStatus := "off"
	if e.platform != nil {
		if _, err := e.platform.Health(ctx); err == nil {
			platformStatus = "real"
		} else {
			platformStatus = "degraded"
			status["platform_error"] = err.Error()
		}
	}
	promStatus := "off"
	if e.prom != nil {
		if e.prom.Healthy(ctx) {
			promStatus = "real"
		} else {
			promStatus = "degraded"
		}
	}
	fixtureStatus := "off"
	var scenarios []string
	if e.fixtures != nil {
		for name := range e.fixtures {
			scenarios = append(scenarios, name)
		}
		sort.Strings(scenarios)
		switch {
		case e.cfg.Sources.Fixture.Enabled:
			fixtureStatus = "mock" // 显式回放模式（--fixture / TRACESPHERE_RCA_FIXTURE）
		case platformStatus != "real":
			fixtureStatus = "mock" // 降级：真实源不可用，回放证据将参与诊断（API.md §6）
		default:
			fixtureStatus = "off" // 已加载但实时模式下不参与
		}
	}
	status["sources"] = map[string]any{
		"platform": platformStatus, "prometheus": promStatus, "fixture": fixtureStatus,
		"fixture_scenarios": scenarios,
	}
	return status
}

// ---------------------------------------------------------------------------
// 内部工具
// ---------------------------------------------------------------------------

func synthesizeIncidents(evidence []model.Evidence) []source.RawIncident {
	groups := map[string][]model.Evidence{}
	order := []string{}
	for _, item := range evidence {
		key := item.CorrelationID
		if key == "" {
			key = item.ResourceID
		}
		if key == "" {
			continue
		}
		if _, ok := groups[key]; !ok {
			order = append(order, key)
		}
		groups[key] = append(groups[key], item)
	}
	var out []source.RawIncident
	for _, key := range order {
		items := groups[key]
		incident := source.RawIncident{Evidence: items}
		if len(items) > 0 {
			incident.CorrelationID = items[0].CorrelationID
			incident.ResourceID = items[0].ResourceID
			incident.WindowStart = items[0].ObservedAt
			incident.WindowEnd = items[len(items)-1].ObservedAt
			incident.Summary = fmt.Sprintf("%d 条证据（C 侧按 %s 聚合）", len(items), key)
		}
		out = append(out, incident)
	}
	return out
}

func syntheticIncidentID(incident source.RawIncident) string {
	key := incident.CorrelationID
	if key == "" {
		key = incident.ResourceID
	}
	if key == "" {
		key = "unknown"
	}
	return "inc-" + strings.ReplaceAll(key, ":", "-")
}

func filterEvidence(evidence []model.Evidence, incident source.RawIncident) []model.Evidence {
	var out []model.Evidence
	for _, item := range evidence {
		if incident.CorrelationID != "" && item.CorrelationID == incident.CorrelationID {
			out = append(out, item)
			continue
		}
		if incident.ResourceID != "" && item.ResourceID == incident.ResourceID {
			out = append(out, item)
		}
	}
	return out
}
