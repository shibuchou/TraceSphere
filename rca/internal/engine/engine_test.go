package engine

import (
	"context"
	"path/filepath"
	"testing"

	"tracesphere/rca/internal/config"
	"tracesphere/rca/internal/model"
	"tracesphere/rca/internal/source"
)

// fixture 模式下的端到端回归：三个 Case 的 Top-1 根因必须正确、评分合理、证据可溯源。
//
// 这是"配置驱动 + 证据匹配"的验收测试：回放真实演练证据，断言规则引擎的输出。
func TestFixtureScenariosTopDiagnosis(t *testing.T) {
	// 阈值为"真实抓取 fixture"的实测下界（2026-09-25 安全基线版四场景验收后的基线，
	// 实测 Top-1 评分：Case1 99 / Case2 85 / Case3 67 / Case4 89，Top-1 规则全对）。
	// 评分由证据驱动：真实演练中缺哪条证据就在评分明细里显示缺哪条，因此低于满分。
	cases := []struct {
		scenario  string
		wantRule  string
		minScore  float64
		wantLayer string
	}{
		{"case1-oom", "container_oom", 85, "container"},
		{"case2-cpu", "cpu_contention", 75, "vm"},
		{"case3-tool-failure", "tool_failure", 60, "application"},
		{"case4-gpu-mock", "gpu_memory_exhaustion", 80, "vm"},
	}
	for _, tc := range cases {
		t.Run(tc.scenario, func(t *testing.T) {
			eng := fixtureEngine(t, tc.scenario)
			result := eng.Run(context.Background(), DiagnoseRequest{Scenario: tc.scenario, TopN: 3})
			if len(result.Diagnoses) == 0 {
				t.Fatalf("场景 %s 未产出任何根因候选", tc.scenario)
			}
			top := result.Diagnoses[0]
			if top.Rule != tc.wantRule {
				t.Fatalf("Top-1 规则 = %s，期望 %s", top.Rule, tc.wantRule)
			}
			if top.MatchScore < tc.minScore {
				t.Fatalf("Top-1 评分 = %.1f，期望 >= %.1f", top.MatchScore, tc.minScore)
			}
			if len(top.EvidenceIDs) == 0 {
				t.Fatal("诊断结论必须携带证据 ID（方案 §5.4 可追溯要求）")
			}
			if len(top.ScoreBreakdown) != 5 {
				t.Fatalf("Evidence Match 必须输出五个维度，实际 %d", len(top.ScoreBreakdown))
			}
			if len(top.Suggestions) == 0 {
				t.Fatal("诊断必须给出处置建议（依据 + 操作 + 风险）")
			}
			for _, suggestion := range top.Suggestions {
				if suggestion.Basis == "" || suggestion.Detail == "" || suggestion.Risk == "" {
					t.Fatalf("处置建议缺少 basis/detail/risk：%+v", suggestion)
				}
			}
			if len(result.Impact.Scope) == 0 {
				t.Fatal("必须给出影响范围")
			}
			if len(result.Timeline) == 0 {
				t.Fatal("必须给出证据时间线")
			}
			if result.Sources["fixture"] != "mock" {
				t.Fatalf("回放模式必须标注数据来源为 mock，实际 %v", result.Sources["fixture"])
			}
			labels := map[string]bool{}
			for _, dim := range top.ScoreBreakdown {
				labels[dim.Dimension] = true
			}
			for _, want := range []string{"rule_match", "temporal_precedence", "resource_adjacency", "signal_strength", "independent_evidence"} {
				if !labels[want] {
					t.Fatalf("缺少评分维度 %s", want)
				}
			}
			if !hasLayer(result.Timeline, tc.wantLayer) {
				t.Fatalf("时间线缺少 %s 层证据", tc.wantLayer)
			}
		})
	}
}

// 无证据时不得凭规则硬报根因（避免"三个 if/else 硬编码"的评审质疑）。
func TestNoEvidenceMeansNoDiagnosis(t *testing.T) {
	cfg := testConfig(t, "case1-oom")
	eng, err := New(cfg)
	if err != nil {
		t.Fatal(err)
	}
	snap := &source.Snapshot{Window: model.Window{}}
	result := eng.Diagnose(snap, 3)
	if len(result.Diagnoses) != 0 {
		t.Fatalf("空证据不应产出诊断，实际 %d 条", len(result.Diagnoses))
	}
}

// 规则库必须能被解析与校验（配置驱动是硬约束：新增 YAML 即生效）。
func TestRulesLoad(t *testing.T) {
	cfg := testConfig(t, "case1-oom")
	eng, err := New(cfg)
	if err != nil {
		t.Fatal(err)
	}
	if len(eng.Rules()) != 4 {
		t.Fatalf("期望 4 条规则，实际 %d", len(eng.Rules()))
	}
	seen := map[string]bool{}
	for _, r := range eng.Rules() {
		seen[r.ID] = true
		if r.MandatoryWeight() <= 0 {
			t.Fatalf("规则 %s 的必选权重和必须为正", r.ID)
		}
		if r.Result.RootCause == "" || len(r.Result.Suggestions) == 0 {
			t.Fatalf("规则 %s 缺少根因或处置建议", r.ID)
		}
	}
	for _, want := range []string{"container_oom", "cpu_contention", "tool_failure"} {
		if !seen[want] {
			t.Fatalf("规则库缺少 %s", want)
		}
	}
}

// ---------------------------------------------------------------------------

func fixtureEngine(t *testing.T, scenario string) *Engine {
	t.Helper()
	eng, err := New(testConfig(t, scenario))
	if err != nil {
		t.Fatal(err)
	}
	return eng
}

func testConfig(t *testing.T, scenario string) *config.Config {
	t.Helper()
	cfg := config.Default()
	cfg.RulesDir = filepath.Join("..", "..", "rules")
	cfg.Sources.Platform.Enabled = false
	cfg.Sources.Prometheus.Enabled = false
	cfg.Sources.Fixture = config.FixtureSource{
		Enabled:  true,
		Dir:      filepath.Join("..", "..", "fixtures"),
		Scenario: scenario,
	}
	cfg.MinScore = 20
	cfg.TopN = 3
	return cfg
}

func hasLayer(entries []model.TimelineEntry, layer string) bool {
	for _, entry := range entries {
		if entry.Layer == layer {
			return true
		}
	}
	return false
}
