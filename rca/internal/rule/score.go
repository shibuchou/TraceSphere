package rule

import (
	"fmt"
	"math"
	"sort"
	"strings"
	"time"

	"tracesphere/rca/internal/model"
)

// Evidence Match 五维度上限（方案 §6.3）。
const (
	MaxRuleMatch      = 55.0
	MaxTemporal       = 15.0
	MaxAdjacency      = 10.0
	MaxSignalStrength = 10.0
	MaxIndependent    = 10.0

	// MatchNote 展示用文案：明确不是概率（方案 §6.3）。
	MatchNote = "Evidence Match 为规则证据命中评分（0–100），非概率"
)

// ClauseMatch 单条款的匹配结果。
type ClauseMatch struct {
	Index   int
	Clause  Clause
	Matched bool
	Items   []model.Evidence
	Detail  string
}

// Evaluation 一条规则对一组证据的完整评估结果。
type Evaluation struct {
	Rule          *Rule
	Matches       []ClauseMatch
	MatchedWeight float64
	Mandatory     float64
	Items         []model.Evidence
	Score         float64
	Breakdown     []model.ScoreDimension
	FocusResource string
	FocusName     string
}

// Adjacency 规则引擎需要的拓扑能力（由 source.ResourceIndex 实现）。
//
//	VMOf(resourceID)        资源所属 VM（CPU 争抢判"同 VM"）
//	Distance(from, to)      资源图最短跳数（0=同一资源，99=不可达）
type Adjacency interface {
	VMOf(resourceID string) string
	Distance(from, to string) int
}

// Evaluate 执行「证据匹配 + Evidence Match 评分」。
//
// adj 提供资源邻接度判定；为 nil 时退化为"同一资源才计分"。
func Evaluate(r *Rule, evidence []model.Evidence, adj Adjacency) Evaluation {
	sorted := append([]model.Evidence(nil), evidence...)
	sort.SliceStable(sorted, func(i, j int) bool {
		return sorted[i].ObservedAt.Before(sorted[j].ObservedAt.Time)
	})

	eval := Evaluation{Rule: r, Mandatory: r.MandatoryWeight()}
	seen := map[string]bool{}
	for i, clause := range r.Evidence {
		match := matchClause(i, clause, sorted)
		eval.Matches = append(eval.Matches, match)
		if !match.Matched {
			continue
		}
		eval.MatchedWeight += clause.Weight
		for _, item := range match.Items {
			key := item.EvidenceID
			if key == "" {
				key = item.Signal + "@" + item.ObservedAt.UTC().Format(time.RFC3339Nano) + "@" + item.ResourceID
			}
			if !seen[key] {
				seen[key] = true
				eval.Items = append(eval.Items, item)
			}
		}
	}
	sort.SliceStable(eval.Items, func(i, j int) bool {
		return eval.Items[i].ObservedAt.Before(eval.Items[j].ObservedAt.Time)
	})

	eval.FocusResource, eval.FocusName = focusOf(eval)
	eval.Score, eval.Breakdown = score(r, eval, adj)
	return eval
}

// matchClause 判断单条证据条款是否命中。
func matchClause(index int, clause Clause, evidence []model.Evidence) ClauseMatch {
	match := ClauseMatch{Index: index, Clause: clause}
	signals := candidateSignals(clause)

	var candidates []model.Evidence
	for _, item := range evidence {
		if !signalMatches(item.Signal, signals) {
			continue
		}
		if clause.Kind != "" && !strings.EqualFold(item.Kind, clause.Kind) {
			continue
		}
		if len(clause.KindAny) > 0 && !containsFold(clause.KindAny, item.Kind) {
			continue
		}
		if clause.Layer != "" && !strings.EqualFold(item.Layer, clause.Layer) {
			continue
		}
		candidates = append(candidates, item)
	}
	if len(candidates) == 0 {
		match.Detail = fmt.Sprintf("未命中：窗口内无 %s 证据", strings.Join(signals, "/"))
		return match
	}

	// 谓词过滤：status / match_any / require_attribute
	var filtered []model.Evidence
	for _, item := range candidates {
		if clause.Status != "" {
			status := strings.ToLower(fmt.Sprintf("%v", item.Attr("status")))
			if status != strings.ToLower(clause.Status) {
				continue
			}
		}
		if len(clause.MatchAny) > 0 && !containsAnyFold(clause.MatchAny, item.Text()) {
			continue
		}
		if clause.RequireAttribute != "" && item.Attr(clause.RequireAttribute) == nil {
			continue
		}
		filtered = append(filtered, item)
	}
	if len(filtered) == 0 {
		match.Detail = fmt.Sprintf("未命中：%d 条 %s 证据不满足附加条件（status/match/attribute）",
			len(candidates), strings.Join(signals, "/"))
		return match
	}

	// 计数型证据：要求窗口内增量 > 0
	if clause.RequireIncrease {
		positive, quantified := 0, 0
		var total float64
		for _, item := range filtered {
			if item.Value != nil {
				quantified++
				total += *item.Value
				if *item.Value > 0 {
					positive++
				}
			}
		}
		switch {
		case quantified > 0 && positive == 0:
			match.Detail = fmt.Sprintf("未命中：%s 增量合计 %.0f（≤ 0）", strings.Join(signals, "/"), total)
			return match
		case quantified == 0:
			match.Detail = fmt.Sprintf("命中：出现 %d 条 %s 证据（增量未量化，按出现计）",
				len(filtered), strings.Join(signals, "/"))
		default:
			match.Detail = fmt.Sprintf("命中：%s 增量合计 %.0f（%d 次）", strings.Join(signals, "/"), total, positive)
		}
		match.Matched = true
		match.Items = filtered
		return match
	}

	// 指标型证据：阈值比较（取窗口内峰值）
	if clause.Metric != "" && clause.Op != "" {
		peak := math.Inf(-1)
		var peakItem model.Evidence
		quantified := false
		for _, item := range filtered {
			if item.Value == nil {
				continue
			}
			quantified = true
			if *item.Value > peak {
				peak = *item.Value
				peakItem = item
			}
		}
		if !quantified {
			match.Detail = fmt.Sprintf("未命中：%s 无量化数值", clause.Metric)
			return match
		}
		if !compare(peak, clause.Op, clause.Value) {
			match.Detail = fmt.Sprintf("未命中：%s 峰值 %.3f 不满足 %s %.3f", clause.Metric, peak, clause.Op, clause.Value)
			return match
		}
		match.Matched = true
		match.Items = []model.Evidence{peakItem}
		match.Detail = fmt.Sprintf("命中：%s 峰值 %.3f %s %.3f", clause.Metric, peak, clause.Op, clause.Value)
		return match
	}

	match.Matched = true
	match.Items = filtered
	match.Detail = fmt.Sprintf("命中：%d 条 %s 证据", len(filtered), matchedSignalNames(filtered, signals))
	return match
}

// matchedSignalNames 展示实际命中的信号名（signal_any 场景下比条款首项更准确）。
func matchedSignalNames(items []model.Evidence, fallback []string) string {
	seen := map[string]bool{}
	var names []string
	for _, item := range items {
		if item.Signal == "" || seen[item.Signal] {
			continue
		}
		seen[item.Signal] = true
		names = append(names, item.Signal)
		if len(names) >= 3 {
			break
		}
	}
	if len(names) == 0 {
		return strings.Join(fallback, "/")
	}
	return strings.Join(names, "/")
}

// score 计算五个维度并归一化到 0–100。
func score(r *Rule, eval Evaluation, adj Adjacency) (float64, []model.ScoreDimension) {
	var breakdown []model.ScoreDimension

	// 1) Rule Match
	ruleMatch := 0.0
	if eval.Mandatory > 0 {
		ratio := math.Min(1.0, eval.MatchedWeight/eval.Mandatory)
		ruleMatch = ratio * MaxRuleMatch
	}
	hit, total := 0, 0
	var hitNames []string
	for _, m := range eval.Matches {
		total++
		if m.Matched {
			hit++
			hitNames = append(hitNames, clauseName(m.Clause))
		}
	}
	ruleDetail := fmt.Sprintf("%d/%d 条命中", hit, total)
	if len(hitNames) > 0 {
		ruleDetail += "：" + strings.Join(hitNames, "、")
	}
	breakdown = append(breakdown, model.ScoreDimension{
		Dimension: "rule_match", Label: "规则证据命中",
		Score: round1(ruleMatch), Max: MaxRuleMatch, Detail: ruleDetail,
	})

	// 2) Temporal Precedence（规则未定义 after 约束时该维度不适用：Max=0，不参与归一化）
	var temporal model.ScoreDimension
	temporal = model.ScoreDimension{
		Dimension: "temporal_precedence", Label: "时间优先性", Max: 0,
		Detail: "规则未定义 after 时序约束，该维度不适用（不参与归一化）",
	}
	constraints, satisfied := 0, 0
	var temporalDetails []string
	for _, m := range eval.Matches {
		if m.Clause.After == "" || !m.Matched {
			continue
		}
		constraints++
		cause := findMatch(eval.Matches, m.Clause.After)
		if cause == nil || !cause.Matched {
			temporalDetails = append(temporalDetails, fmt.Sprintf("%s 的前序证据 %s 缺失", clauseName(m.Clause), m.Clause.After))
			continue
		}
		effectAt := earliest(m.Items)
		causeAt := earliest(cause.Items)
		if effectAt.IsZero() || causeAt.IsZero() {
			continue
		}
		delta := effectAt.Sub(causeAt)
		if delta >= 0 {
			satisfied++
			temporalDetails = append(temporalDetails, fmt.Sprintf("%s 晚于 %s %.1fs",
				clauseName(m.Clause), m.Clause.After, delta.Seconds()))
		} else {
			temporalDetails = append(temporalDetails, fmt.Sprintf("%s 早于 %s %.1fs（时序不符）",
				clauseName(m.Clause), m.Clause.After, -delta.Seconds()))
		}
	}
	if constraints > 0 {
		temporal.Max = MaxTemporal
		temporal.Score = round1(float64(satisfied) / float64(constraints) * MaxTemporal)
		temporal.Detail = strings.Join(temporalDetails, "；")
	}
	breakdown = append(breakdown, temporal)

	// 3) Resource Adjacency（资源图距离加权：同一资源 > 同一容器上下文 > 同 VM > 跨主机）
	adjacency := model.ScoreDimension{
		Dimension: "resource_adjacency", Label: "资源邻接度", Max: MaxAdjacency,
		Detail: "无匹配证据，无法判定邻接关系",
	}
	if len(eval.Items) > 0 {
		total := float64(len(eval.Items))
		weightSum := 0.0
		sameResource, nearOneHop, sameVM, far := 0, 0, 0, 0
		for _, item := range eval.Items {
			distance := 99
			switch {
			case item.ResourceID != "" && item.ResourceID == eval.FocusResource:
				distance = 0
			case adj != nil:
				distance = adj.Distance(eval.FocusResource, item.ResourceID)
			}
			switch {
			case distance == 0:
				sameResource++
				weightSum += 1.0
			case distance == 1:
				nearOneHop++
				weightSum += 0.9
			case distance <= 3:
				sameVM++
				weightSum += 0.7
			default:
				far++
				weightSum += 0.2
			}
		}
		adjacency.Score = round1(MaxAdjacency * weightSum / total)
		var parts []string
		if sameResource > 0 {
			parts = append(parts, fmt.Sprintf("%d 条同属 %s", sameResource, eval.FocusResource))
		}
		if nearOneHop > 0 {
			parts = append(parts, fmt.Sprintf("%d 条一跳邻接（同容器/服务上下文）", nearOneHop))
		}
		if sameVM > 0 {
			parts = append(parts, fmt.Sprintf("%d 条同 VM 内可关联（服务/任务链）", sameVM))
		}
		if far > 0 {
			parts = append(parts, fmt.Sprintf("%d 条与聚焦资源无拓扑关联", far))
		}
		adjacency.Detail = strings.Join(parts, "；")
		if r.Correlation.SameResource && far > 0 {
			adjacency.Score = 0
			adjacency.Detail += "（规则要求 same_resource，存在无关资源证据）"
		}
	}
	breakdown = append(breakdown, adjacency)

	// 4) Signal Strength
	strength := 0.0
	strengthDetail := "无匹配证据"
	if len(eval.Items) > 0 {
		primary := eval.Items[len(eval.Items)-1]
		if focus := primaryOf(eval); focus != nil {
			primary = *focus
		}
		base := severityBase(primary.Severity)
		bonus := math.Min(3, float64(len(eval.Items)-1))
		strength = math.Min(MaxSignalStrength, base+bonus)
		strengthDetail = fmt.Sprintf("主证据 %s severity=%s（基础 %.0f）+ 额外证据 %d 条（+%.0f）",
			primary.Signal, model.Severity(primary.Severity), base, len(eval.Items)-1, bonus)
	}
	breakdown = append(breakdown, model.ScoreDimension{
		Dimension: "signal_strength", Label: "信号强度",
		Score: round1(strength), Max: MaxSignalStrength, Detail: strengthDetail,
	})

	// 5) Independent Evidence Count
	kinds := map[string]bool{}
	for _, item := range eval.Items {
		if item.Kind != "" {
			kinds[item.Kind] = true
		}
	}
	independent := 0.0
	switch {
	case len(kinds) >= 3:
		independent = MaxIndependent
	case len(kinds) == 2:
		independent = 5
	case len(kinds) == 1:
		independent = 2
	}
	var kindNames []string
	for kind := range kinds {
		kindNames = append(kindNames, kind)
	}
	sort.Strings(kindNames)
	breakdown = append(breakdown, model.ScoreDimension{
		Dimension: "independent_evidence", Label: "独立证据数",
		Score: independent, Max: MaxIndependent,
		Detail: fmt.Sprintf("覆盖 %d 类证据来源：%s", len(kinds), strings.Join(kindNames, " / ")),
	})

	raw := ruleMatch + temporal.Score + adjacency.Score + strength + independent
	applicable := r.ApplicableMax()
	if applicable <= 0 {
		return 0, breakdown
	}
	return round1(math.Min(100, raw/applicable*100)), breakdown
}

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

func candidateSignals(clause Clause) []string {
	var signals []string
	if clause.Signal != "" {
		signals = append(signals, clause.Signal)
	}
	if clause.Metric != "" {
		signals = append(signals, clause.Metric)
	}
	signals = append(signals, clause.SignalAny...)
	return signals
}

func clauseName(clause Clause) string {
	if clause.Signal != "" {
		return clause.Signal
	}
	if clause.Metric != "" {
		return clause.Metric
	}
	if len(clause.SignalAny) > 0 {
		return clause.SignalAny[0]
	}
	return "unknown"
}

func signalMatches(signal string, candidates []string) bool {
	for _, candidate := range candidates {
		if strings.EqualFold(signal, candidate) {
			return true
		}
	}
	return false
}

func containsFold(list []string, value string) bool {
	for _, item := range list {
		if strings.EqualFold(item, value) {
			return true
		}
	}
	return false
}

func containsAnyFold(needles []string, haystack string) bool {
	lower := strings.ToLower(haystack)
	for _, needle := range needles {
		if strings.Contains(lower, strings.ToLower(needle)) {
			return true
		}
	}
	return false
}

func compare(value float64, op string, threshold float64) bool {
	switch strings.TrimSpace(op) {
	case ">":
		return value > threshold
	case ">=":
		return value >= threshold
	case "<":
		return value < threshold
	case "<=":
		return value <= threshold
	case "==", "=":
		return value == threshold
	case "!=":
		return value != threshold
	case "increase_gt":
		return value > threshold
	default:
		return false
	}
}

func earliest(items []model.Evidence) time.Time {
	var out time.Time
	for _, item := range items {
		if item.ObservedAt.IsZero() {
			continue
		}
		if out.IsZero() || item.ObservedAt.Before(out) {
			out = item.ObservedAt.Time
		}
	}
	return out
}

func findMatch(matches []ClauseMatch, signal string) *ClauseMatch {
	for i := range matches {
		if strings.EqualFold(clauseName(matches[i].Clause), signal) {
			return &matches[i]
		}
	}
	return nil
}

// focusOf 取权重最高且命中条款的首条证据作为聚焦资源。
func focusOf(eval Evaluation) (string, string) {
	bestWeight := -1.0
	var focus model.Evidence
	for _, m := range eval.Matches {
		if !m.Matched || len(m.Items) == 0 {
			continue
		}
		if m.Clause.Weight > bestWeight {
			bestWeight = m.Clause.Weight
			focus = m.Items[0]
		}
	}
	return focus.ResourceID, focus.ResourceName
}

// primaryOf 返回权重最高命中条款的首条证据。
func primaryOf(eval Evaluation) *model.Evidence {
	bestWeight := -1.0
	var focus *model.Evidence
	for _, m := range eval.Matches {
		if !m.Matched || len(m.Items) == 0 {
			continue
		}
		if m.Clause.Weight > bestWeight {
			bestWeight = m.Clause.Weight
			item := m.Items[0]
			focus = &item
		}
	}
	return focus
}

func severityBase(sev string) float64 {
	switch model.Severity(sev) {
	case "critical":
		return 7
	case "major":
		return 5
	case "warning":
		return 3
	case "info":
		return 1
	default:
		return 0
	}
}

func round1(v float64) float64 { return math.Round(v*10) / 10 }

// FormatScore 便于 CLI/日志输出 "92/100"。
func FormatScore(v float64, max float64) string {
	return fmt.Sprintf("%.0f/%.0f", v, max)
}
