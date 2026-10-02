// Package render 负责 CLI 的文本渲染（无需第三方依赖，CJK 宽度对齐）。
package render

import (
	"fmt"
	"sort"
	"strings"

	"tracesphere/rca/internal/model"
)

// Diagnose 渲染一次诊断结果（tracesphere diagnose）。
func Diagnose(res model.DiagnoseResult) string {
	var b strings.Builder
	b.WriteString("TraceSphere 诊断（成员 C / RCA Rule Engine + Evidence Match）\n")
	b.WriteString(fmt.Sprintf("时间窗：%s ~ %s（%.0fs）\n",
		res.Window.From.UTC().Format("2006-01-02T15:04:05Z"),
		res.Window.To.UTC().Format("2006-01-02T15:04:05Z"),
		res.Window.Seconds))
	b.WriteString(fmt.Sprintf("数据源：platform=%v prometheus=%v fixture=%v ｜ 证据 %v 条\n",
		res.Sources["platform"], res.Sources["prometheus"], res.Sources["fixture"], res.Sources["evidence_count"]))
	if notes, ok := res.Sources["notes"].([]string); ok && len(notes) > 0 {
		b.WriteString("说明：" + strings.Join(notes, "；") + "\n")
	}
	if cid, ok := res.Focus["correlation_id"]; ok && cid != "" {
		b.WriteString(fmt.Sprintf("关联锚点：correlation_id=%v\n", cid))
	}
	if rid, ok := res.Focus["resource_id"]; ok && rid != "" {
		b.WriteString(fmt.Sprintf("聚焦资源：%v\n", rid))
	}
	b.WriteString("\n")

	if len(res.Diagnoses) == 0 {
		b.WriteString("未匹配到任何规则（证据不足）。\n")
		b.WriteString("提示：确认采样窗口内是否有 task.failed / oom_kill / PSI 等信号，或使用 --scenario 回放 fixture。\n")
		return b.String()
	}

	b.WriteString(fmt.Sprintf("根因候选 Top-%d\n", len(res.Diagnoses)))
	for i, d := range res.Diagnoses {
		b.WriteString(strings.Repeat("═", 78) + "\n")
		b.WriteString(fmt.Sprintf("[%d] %s\n", i+1, d.Title))
		b.WriteString(fmt.Sprintf("    Evidence Match: %.0f/100 ｜ 规则 %s v%d ｜ 严重度 %s\n",
			d.MatchScore, d.Rule, d.RuleVersion, d.Severity))
		b.WriteString(fmt.Sprintf("    根因：%s\n", d.RootCause))
		b.WriteString(fmt.Sprintf("          %s\n", d.RootCauseLabel))
		b.WriteString("    评分明细：\n")
		for _, dim := range d.ScoreBreakdown {
			b.WriteString(fmt.Sprintf("      · %-12s %5.1f/%-5.0f %s\n", dim.Label, dim.Score, dim.Max, dim.Detail))
		}
		b.WriteString(fmt.Sprintf("    证据（%d 条，可溯源）：\n", len(d.Evidence)))
		for _, item := range d.Evidence {
			value := ""
			if item.Value != nil {
				value = fmt.Sprintf(" value=%.3g%s", *item.Value, unitSuffix(item.Unit))
			}
			b.WriteString(fmt.Sprintf("      %-14s %-26s %-10s %-16s %s%s\n",
				shortID(item.EvidenceID), item.Signal, item.Kind, item.ResourceName,
				item.ObservedAt.UTC().Format("15:04:05"), value))
		}
		if len(d.Suggestions) > 0 {
			b.WriteString("    处置建议：\n")
			for index, s := range d.Suggestions {
				b.WriteString(fmt.Sprintf("      %d) %s\n", index+1, s.Title))
				if s.Basis != "" {
					b.WriteString(fmt.Sprintf("         依据：%s\n", s.Basis))
				}
				if s.Detail != "" {
					b.WriteString(fmt.Sprintf("         操作：%s\n", s.Detail))
				}
				if s.Risk != "" {
					b.WriteString(fmt.Sprintf("         风险：%s\n", s.Risk))
				}
			}
		}
		if len(d.Alternatives) > 0 {
			var alts []string
			for _, alt := range d.Alternatives {
				alts = append(alts, fmt.Sprintf("%s(%.0f)", alt.Title, alt.MatchScore))
			}
			b.WriteString("    备选候选：" + strings.Join(alts, "、") + "\n")
		}
	}
	b.WriteString(strings.Repeat("═", 78) + "\n")
	b.WriteString(fmt.Sprintf("影响范围：%d 个资源（%s）\n", len(res.Impact.Scope), formatCounts(res.Impact.Counts)))
	for _, entry := range res.Impact.Scope {
		status := entry.Status
		if status == "" {
			status = "-"
		}
		b.WriteString(fmt.Sprintf("  · %-10s %-34s %-8s depth=%d\n", entry.Kind, entry.Name, status, entry.Depth))
	}
	b.WriteString("\n注：Evidence Match 为规则证据命中评分（0–100），非概率。\n")
	return b.String()
}

// Topology 渲染资源拓扑（tree 形式，CLI `tracesphere topo`）。
func Topology(tp model.Topology) string {
	var b strings.Builder
	b.WriteString("TraceSphere 资源拓扑（Host → VM → Container / Service / Task）\n")
	b.WriteString(fmt.Sprintf("数据源：%v\n\n", tp.Source))

	children := map[string][]model.GraphNode{}
	inTopology := map[string]bool{}
	for _, node := range tp.Nodes {
		inTopology[node.ID] = true
	}
	parentOf := map[string]string{}
	for _, edge := range tp.Edges {
		if !inTopology[edge.Source] || !inTopology[edge.Target] {
			continue
		}
		switch edge.Relation {
		case "contains", "provides", "spawns", "has_volume":
			parentOf[edge.Target] = edge.Source
		case "runs_on", "assigned_to", "attached_to", "over":
			parentOf[edge.Source] = edge.Target
		}
	}
	var roots []model.GraphNode
	for _, node := range tp.Nodes {
		parent := parentOf[node.ID]
		if parent == "" {
			roots = append(roots, node)
			continue
		}
		children[parent] = append(children[parent], node)
	}
	sort.SliceStable(roots, func(i, j int) bool { return kindRank(roots[i].Kind) < kindRank(roots[j].Kind) })
	if len(roots) == 0 {
		b.WriteString("（拓扑为空：请确认 platform 已同步资源，或使用 fixture 回放）\n")
		return b.String()
	}
	for _, root := range roots {
		renderNode(&b, root, children, "", true)
	}
	return b.String()
}

func renderNode(b *strings.Builder, node model.GraphNode, children map[string][]model.GraphNode, prefix string, last bool) {
	branch := "├─ "
	nextPrefix := prefix + "│  "
	if last {
		branch = "└─ "
		nextPrefix = prefix + "   "
	}
	badge := ""
	if len(node.Badges) > 0 {
		badge = " [" + strings.Join(node.Badges, ",") + "]"
	}
	status := node.Status
	if node.Incident > 0 {
		status += fmt.Sprintf(" 告警x%d", node.Incident)
	}
	b.WriteString(fmt.Sprintf("%s%s%-12s %-28s %s%s\n", prefix, branch, node.Kind, node.Label, status, badge))
	kids := children[node.ID]
	sort.SliceStable(kids, func(i, j int) bool { return kindRank(kids[i].Kind) < kindRank(kids[j].Kind) })
	for i, child := range kids {
		renderNode(b, child, children, nextPrefix, i == len(kids)-1)
	}
}

// Overview 渲染健康页文本视图（CLI `tracesphere health`）。
func Overview(ov model.Overview) string {
	var b strings.Builder
	b.WriteString("TraceSphere 工作负载健康总览\n")
	b.WriteString(fmt.Sprintf("时间窗：%s ~ %s（%.0fs）\n",
		ov.Window.From.UTC().Format("2006-01-02T15:04:05Z"),
		ov.Window.To.UTC().Format("2006-01-02T15:04:05Z"), ov.Window.Seconds))
	b.WriteString(fmt.Sprintf("数据源：%v\n\n", ov.Source))
	b.WriteString(fmt.Sprintf("资源 %d（健康 %d / 警告 %d / 严重 %d）｜任务 %d（失败 %d）｜关联簇 %d｜高优信号 %d\n\n",
		ov.Summary.Resources, ov.Summary.Healthy, ov.Summary.Warning, ov.Summary.Critical,
		ov.Summary.TasksTotal, ov.Summary.TasksFailed, ov.Summary.Incidents, ov.Summary.OpenAlerts))

	rows := [][]string{{"状态", "类型", "名称", "健康分", "失败任务", "关键信号"}}
	for _, card := range ov.Workloads {
		signals := []string{}
		for _, signal := range card.Signals {
			if model.SeverityRank(signal.Severity) >= 1 {
				signals = append(signals, fmt.Sprintf("%s x%d", signal.Signal, signal.Count))
			}
		}
		rows = append(rows, []string{
			card.Status, card.Kind, card.Name, fmt.Sprintf("%.0f", card.HealthScore),
			fmt.Sprintf("%d", card.TaskFailures), strings.Join(signals, ", "),
		})
	}
	b.WriteString(Table(rows))
	if len(ov.Timeline) > 0 {
		b.WriteString("\n事件时间线（最近 20 条）\n")
		start := 0
		if len(ov.Timeline) > 20 {
			start = len(ov.Timeline) - 20
		}
		for _, entry := range ov.Timeline[start:] {
			b.WriteString(fmt.Sprintf("  %s  %-11s %-26s %s\n",
				entry.ObservedAt.UTC().Format("15:04:05"), entry.Layer, entry.Signal,
				truncate(entry.Description, 70)))
		}
	}
	return b.String()
}

// Incidents 渲染告警列表（CLI `tracesphere alerts`）。
func Incidents(list model.IncidentList) string {
	var b strings.Builder
	b.WriteString(fmt.Sprintf("TraceSphere 告警/事件列表（%d 条）\n\n", list.Count))
	rows := [][]string{{"严重度", "规则", "标题", "匹配分", "影响任务", "最近时间", "焦点资源"}}
	for _, item := range list.Incidents {
		focus := "-"
		if item.FocusResource != nil {
			focus = item.FocusResource.Name
		}
		rows = append(rows, []string{
			item.Severity, emptyDash(item.Rule), item.Title,
			fmt.Sprintf("%.0f", item.MatchScore), fmt.Sprintf("%d", item.AffectedTasks),
			item.LastSeenAt.UTC().Format("01-02 15:04:05"), focus,
		})
	}
	b.WriteString(Table(rows))
	b.WriteString("\n提示：tracesphere diagnose --resource-id <资源> 查看某个告警的证据链与处置建议。\n")
	return b.String()
}

// Rules 渲染规则清单。
func Rules(infos []model.RuleInfo) string {
	var b strings.Builder
	b.WriteString(fmt.Sprintf("TraceSphere RCA 规则库（%d 条，配置驱动，新增 YAML 即生效）\n\n", len(infos)))
	rows := [][]string{{"规则 ID", "版本", "标题", "严重度", "条款数", "权重和"}}
	for _, info := range infos {
		rows = append(rows, []string{
			info.Rule, fmt.Sprintf("v%d", info.Version), info.Title,
			info.Severity, fmt.Sprintf("%d", info.Clauses), fmt.Sprintf("%.0f", info.Weights),
		})
	}
	b.WriteString(Table(rows))
	return b.String()
}

// Table 渲染等宽表格（CJK 字符按 2 列宽计算）。
func Table(rows [][]string) string {
	if len(rows) == 0 {
		return ""
	}
	widths := make([]int, len(rows[0]))
	for _, row := range rows {
		for i, cell := range row {
			if i >= len(widths) {
				continue
			}
			if w := displayWidth(cell); w > widths[i] {
				widths[i] = w
			}
		}
	}
	var b strings.Builder
	for index, row := range rows {
		b.WriteString("  ")
		for i, cell := range row {
			if i >= len(widths) {
				break
			}
			b.WriteString(cell)
			b.WriteString(strings.Repeat(" ", widths[i]-displayWidth(cell)+2))
		}
		b.WriteString("\n")
		if index == 0 {
			total := 0
			for _, w := range widths {
				total += w + 2
			}
			b.WriteString("  " + strings.Repeat("─", total) + "\n")
		}
	}
	return b.String()
}

func displayWidth(s string) int {
	width := 0
	for _, r := range s {
		if r >= 0x1100 && (r <= 0x115F || (r >= 0x2E80 && r <= 0xA4CF) || (r >= 0xAC00 && r <= 0xD7A3) ||
			(r >= 0xF900 && r <= 0xFAFF) || (r >= 0xFE30 && r <= 0xFE6F) || (r >= 0xFF00 && r <= 0xFF60) ||
			(r >= 0xFFE0 && r <= 0xFFE6) || (r >= 0x20000 && r <= 0x3FFFD)) {
			width += 2
			continue
		}
		width++
	}
	return width
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

func formatCounts(counts map[string]int) string {
	if len(counts) == 0 {
		return "无下游资源"
	}
	keys := make([]string, 0, len(counts))
	for key := range counts {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	parts := make([]string, 0, len(keys))
	for _, key := range keys {
		parts = append(parts, fmt.Sprintf("%s %d", key, counts[key]))
	}
	return strings.Join(parts, ", ")
}

func unitSuffix(unit string) string {
	if unit == "" {
		return ""
	}
	return " " + unit
}

func shortID(id string) string {
	if len(id) <= 14 {
		return id
	}
	return id[:14]
}

func emptyDash(s string) string {
	if s == "" {
		return "-"
	}
	return s
}

func truncate(s string, n int) string {
	runes := []rune(s)
	if len(runes) <= n {
		return s
	}
	return string(runes[:n]) + "…"
}
