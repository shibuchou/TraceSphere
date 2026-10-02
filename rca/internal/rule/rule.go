// Package rule 实现配置驱动的 RCA 规则加载与 Evidence Match 匹配/评分。
//
// 设计约束（方案 §6.3）：RCA 不允许写成三个巨大的 if/else。
// 证据匹配、关联条件、输出结论全部由 rules/*.yaml 驱动，引擎本身通用；
// 新增规则 = 新增 YAML，不改引擎代码。
package rule

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"gopkg.in/yaml.v3"
)

// Clause 是单条证据条款（事件型 / 指标型 / 多信号型）。
type Clause struct {
	Signal    string   `yaml:"signal" json:"signal,omitempty"`
	SignalAny []string `yaml:"signal_any" json:"signal_any,omitempty"`
	Metric    string   `yaml:"metric" json:"metric,omitempty"`

	Kind    string   `yaml:"kind" json:"kind,omitempty"`
	KindAny []string `yaml:"kind_any" json:"kind_any,omitempty"`
	Layer   string   `yaml:"layer" json:"layer,omitempty"`

	Weight          float64 `yaml:"weight" json:"weight"`
	Optional        bool    `yaml:"optional" json:"optional,omitempty"`
	RequireIncrease bool    `yaml:"require_increase" json:"require_increase,omitempty"`

	Status           string   `yaml:"status" json:"status,omitempty"`
	MatchAny         []string `yaml:"match_any" json:"match_any,omitempty"`
	RequireAttribute string   `yaml:"require_attribute" json:"require_attribute,omitempty"`

	Op    string  `yaml:"op" json:"op,omitempty"`
	Value float64 `yaml:"value" json:"value,omitempty"`

	After       string `yaml:"after" json:"after,omitempty"`
	Description string `yaml:"description" json:"description,omitempty"`
}

// Correlation 关联约束（由 B 的关联簇满足 / C 侧校验）。
type Correlation struct {
	SameResource         bool     `yaml:"same_resource" json:"same_resource"`
	SameVM               bool     `yaml:"same_vm" json:"same_vm,omitempty"`
	TimeWindow           string   `yaml:"time_window" json:"time_window,omitempty"`
	RequireCorrelationID bool     `yaml:"require_correlation_id" json:"require_correlation_id,omitempty"`
	LinkViaGraph         []string `yaml:"link_via_graph" json:"link_via_graph,omitempty"`
}

// Suggestion 处置建议（依据 + 操作 + 风险）。
type Suggestion struct {
	Action string `yaml:"action" json:"action"`
	Title  string `yaml:"title" json:"title"`
	Basis  string `yaml:"basis" json:"basis,omitempty"`
	Detail string `yaml:"detail" json:"detail,omitempty"`
	Risk   string `yaml:"risk" json:"risk,omitempty"`
}

// Result 规则结论（根因 + 解释 + 处置建议）。
type Result struct {
	RootCause   string       `yaml:"root_cause" json:"root_cause"`
	Label       string       `yaml:"label" json:"label"`
	Suggestions []Suggestion `yaml:"suggestions" json:"suggestions"`
}

// Rule 是一条完整规则（四段结构：rule / evidence / correlation / result）。
type Rule struct {
	ID          string      `yaml:"rule" json:"rule"`
	Version     int         `yaml:"version" json:"version"`
	Title       string      `yaml:"title" json:"title"`
	Description string      `yaml:"description" json:"description,omitempty"`
	Severity    string      `yaml:"severity" json:"severity"`
	Evidence    []Clause    `yaml:"evidence" json:"evidence"`
	Correlation Correlation `yaml:"correlation" json:"correlation"`
	Result      Result      `yaml:"result" json:"result"`

	// SourcePath / SourceText 供 /api/v1/rules 展示"配置驱动、可扩展"。
	SourcePath string `yaml:"-" json:"source_path,omitempty"`
	SourceText string `yaml:"-" json:"source_text,omitempty"`
}

// MandatoryWeight 返回非可选条款权重之和（rule_match 的分母）。
func (r *Rule) MandatoryWeight() float64 {
	var sum float64
	for _, clause := range r.Evidence {
		if !clause.Optional {
			sum += clause.Weight
		}
	}
	return sum
}

// HasTemporalConstraints 是否定义了 `after` 时序约束。
func (r *Rule) HasTemporalConstraints() bool {
	for _, clause := range r.Evidence {
		if strings.TrimSpace(clause.After) != "" {
			return true
		}
	}
	return false
}

// ApplicableMax 返回该规则可得的 Evidence Match 上限（无时序约束时不足 100）。
func (r *Rule) ApplicableMax() float64 {
	max := 55.0
	if r.HasTemporalConstraints() {
		max += 15
	}
	return max + 10 + 10 + 10
}

// Validate 检查规则自身的一致性（权重、信号、结论齐备）。
func (r *Rule) Validate() error {
	if r.ID == "" {
		return fmt.Errorf("规则缺少 rule 字段")
	}
	if len(r.Evidence) == 0 {
		return fmt.Errorf("规则 %s 未定义 evidence 条款", r.ID)
	}
	for i, clause := range r.Evidence {
		if clause.Signal == "" && clause.Metric == "" && len(clause.SignalAny) == 0 {
			return fmt.Errorf("规则 %s 第 %d 条条款缺少 signal / metric / signal_any", r.ID, i+1)
		}
		if clause.Weight <= 0 {
			return fmt.Errorf("规则 %s 第 %d 条条款 weight 必须为正", r.ID, i+1)
		}
		if clause.Op != "" && clause.Metric == "" {
			return fmt.Errorf("规则 %s 第 %d 条条款使用了 op 但未指定 metric", r.ID, i+1)
		}
	}
	if r.Result.RootCause == "" {
		return fmt.Errorf("规则 %s 缺少 result.root_cause", r.ID)
	}
	return nil
}

// LoadFile 从单个 YAML 文件加载规则。
func LoadFile(path string) (*Rule, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var r Rule
	if err := yaml.Unmarshal(raw, &r); err != nil {
		return nil, fmt.Errorf("解析 %s 失败: %w", path, err)
	}
	if err := r.Validate(); err != nil {
		return nil, fmt.Errorf("%s: %w", path, err)
	}
	r.SourcePath = path
	r.SourceText = string(raw)
	if r.Version == 0 {
		r.Version = 1
	}
	if r.Severity == "" {
		r.Severity = "major"
	}
	return &r, nil
}

// LoadDir 加载目录下全部 *.yaml / *.yml 规则，按 rule ID 排序。
func LoadDir(dir string) ([]*Rule, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	var rules []*Rule
	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}
		name := entry.Name()
		if !strings.HasSuffix(name, ".yaml") && !strings.HasSuffix(name, ".yml") {
			continue
		}
		r, err := LoadFile(filepath.Join(dir, name))
		if err != nil {
			return nil, err
		}
		rules = append(rules, r)
	}
	if len(rules) == 0 {
		return nil, fmt.Errorf("目录 %s 下未找到规则文件", dir)
	}
	sort.Slice(rules, func(i, j int) bool { return rules[i].ID < rules[j].ID })
	return rules, nil
}
