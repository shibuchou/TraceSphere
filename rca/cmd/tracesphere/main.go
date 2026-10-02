// tracesphere —— TraceSphere 诊断侧 CLI（成员 C，方案 §6.5）。
//
//	tracesphere serve    [--config c.json] [--listen :8010]
//	tracesphere topo     [--focus <resource_id>] [--window 15m]
//	tracesphere health   [--window 15m]
//	tracesphere alerts   [--window 15m] [--severity critical] [--rule container_oom]
//	tracesphere diagnose [--correlation-id X | --resource-id Y | --scenario case1-oom]
//	tracesphere rules
//
// 所有查询命令都支持 --json 输出原始结构（便于脚本与演示取证）。
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"syscall"
	"time"

	"tracesphere/rca/internal/api"
	"tracesphere/rca/internal/config"
	"tracesphere/rca/internal/engine"
	"tracesphere/rca/internal/render"
	"tracesphere/rca/internal/source"
)

const version = "0.1.0"

func main() {
	if len(os.Args) < 2 {
		usage()
		os.Exit(2)
	}
	switch os.Args[1] {
	case "serve":
		cmdServe(os.Args[2:])
	case "diagnose", "diagnosis", "rca":
		cmdDiagnose(os.Args[2:])
	case "topo", "topology":
		cmdTopo(os.Args[2:])
	case "health":
		cmdHealth(os.Args[2:])
	case "alerts", "incidents":
		cmdAlerts(os.Args[2:])
	case "rules":
		cmdRules(os.Args[2:])
	case "capture":
		cmdCapture(os.Args[2:])
	case "version", "-v", "--version":
		fmt.Printf("tracesphere %s (TraceSphere RCA / Evidence Match)\n", version)
	case "help", "-h", "--help":
		usage()
	default:
		fmt.Fprintf(os.Stderr, "未知子命令：%s\n\n", os.Args[1])
		usage()
		os.Exit(2)
	}
}

func usage() {
	fmt.Print(`tracesphere —— TraceSphere 诊断侧 CLI（成员 C）

用法：
  tracesphere serve    [--config rca.json] [--listen :8010]
  tracesphere topo     [--focus <resource_id>] [--window 15m] [--json]
  tracesphere health   [--window 15m] [--json]
  tracesphere alerts   [--window 15m] [--severity critical|major] [--rule container_oom] [--json]
  tracesphere diagnose (--correlation-id X | --resource-id Y | --scenario case1-oom) [--window 15m] [--top 3] [--json]
  tracesphere rules    [--json]

常用环境变量：
  TRACESPHERE_PLATFORM_URL      默认 http://127.0.0.1:8000
  TRACESPHERE_PROMETHEUS_URL    默认 http://127.0.0.1:9090
  TRACESPHERE_RCA_FIXTURE=1     强制使用 fixture 回放（降级演示）
  TRACESPHERE_RCA_SCENARIO      fixture 场景名（case1-oom / case2-cpu / case3-tool-failure）
`)
}

// ---------------------------------------------------------------------------
// serve
// ---------------------------------------------------------------------------

func cmdServe(args []string) {
	fs := flag.NewFlagSet("serve", flag.ExitOnError)
	configPath := fs.String("config", "", "配置文件路径（JSON）")
	listen := fs.String("listen", "", "监听地址，如 :8010")
	consoleDir := fs.String("console", "", "console dist 目录（静态托管前端）")
	fixture := fs.Bool("fixture", false, "强制 fixture 回放模式")
	scenario := fs.String("scenario", "", "fixture 场景名")
	_ = fs.Parse(args)

	cfg := mustConfig(*configPath)
	if *listen != "" {
		cfg.Listen = *listen
	}
	if *consoleDir != "" {
		cfg.ConsoleDir = *consoleDir
	}
	if *fixture {
		cfg.Sources.Fixture.Enabled = true
		cfg.Sources.Platform.Enabled = false
		cfg.Sources.Prometheus.Enabled = false
	}
	if *scenario != "" {
		cfg.Sources.Fixture.Scenario = *scenario
	}

	eng, err := engine.New(cfg)
	if err != nil {
		fatal(err)
	}
	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()
	if err := api.Serve(ctx, eng, cfg.Listen); err != nil {
		fatal(err)
	}
}

// ---------------------------------------------------------------------------
// diagnose
// ---------------------------------------------------------------------------

func cmdDiagnose(args []string) {
	fs := flag.NewFlagSet("diagnose", flag.ExitOnError)
	configPath := fs.String("config", "", "配置文件路径")
	correlationID := fs.String("correlation-id", "", "应用层关联锚点（Agent 任务）")
	resourceID := fs.String("resource-id", "", "资源锚点（如 container:xxxx / vm:xxxx）")
	scenario := fs.String("scenario", "", "fixture 场景回放（case1-oom / case2-cpu / case3-tool-failure）")
	window := fs.String("window", "", "时间窗（如 15m / 300s / 1h），默认取配置值")
	from := fs.String("from", "", "起始时间 RFC3339（可选）")
	to := fs.String("to", "", "结束时间 RFC3339（可选）")
	topN := fs.Int("top", 0, "根因候选数量（默认配置值）")
	asJSON := fs.Bool("json", false, "输出原始 JSON")
	_ = fs.Parse(args)

	if *correlationID == "" && *resourceID == "" && *scenario == "" {
		fatal(fmt.Errorf("必须指定 --correlation-id / --resource-id / --scenario 之一"))
	}
	cfg := mustConfig(*configPath)
	if *scenario != "" {
		cfg.Sources.Fixture.Enabled = true
		cfg.Sources.Fixture.Scenario = *scenario
	}
	eng, err := engine.New(cfg)
	if err != nil {
		fatal(err)
	}
	seconds := cfg.WindowSeconds
	if *window != "" {
		seconds = parseDuration(*window)
	}
	result := eng.Run(context.Background(), engine.DiagnoseRequest{
		CorrelationID: *correlationID,
		ResourceID:    *resourceID,
		WindowSeconds: seconds,
		From:          parseTimeFlag(*from),
		To:            parseTimeFlag(*to),
		TopN:          *topN,
		Scenario:      *scenario,
	})
	if *asJSON {
		printJSON(result)
		return
	}
	fmt.Print(render.Diagnose(result))
}

// ---------------------------------------------------------------------------
// topo / health / alerts / rules
// ---------------------------------------------------------------------------

func cmdTopo(args []string) {
	fs := flag.NewFlagSet("topo", flag.ExitOnError)
	configPath := fs.String("config", "", "配置文件路径")
	focus := fs.String("focus", "", "聚焦资源 ID")
	window := fs.String("window", "", "时间窗（如 15m）")
	fixture := fs.Bool("fixture", false, "只使用 fixture 回放（等价降级模式）")
	scenario := fs.String("scenario", "", "fixture 场景名")
	asJSON := fs.Bool("json", false, "输出原始 JSON")
	_ = fs.Parse(args)
	cfg := mustConfig(*configPath)
	applyFixtureFlags(cfg, *fixture, *scenario)
	eng, err := engine.New(cfg)
	if err != nil {
		fatal(err)
	}
	seconds := pickWindow(cfg, *window)
	tp := eng.Topology(context.Background(), *focus, seconds)
	if *asJSON {
		printJSON(tp)
		return
	}
	fmt.Print(render.Topology(tp))
}

func cmdHealth(args []string) {
	fs := flag.NewFlagSet("health", flag.ExitOnError)
	configPath := fs.String("config", "", "配置文件路径")
	window := fs.String("window", "", "时间窗（如 15m）")
	fixture := fs.Bool("fixture", false, "只使用 fixture 回放（等价降级模式）")
	scenario := fs.String("scenario", "", "fixture 场景名")
	asJSON := fs.Bool("json", false, "输出原始 JSON")
	_ = fs.Parse(args)
	cfg := mustConfig(*configPath)
	applyFixtureFlags(cfg, *fixture, *scenario)
	eng, err := engine.New(cfg)
	if err != nil {
		fatal(err)
	}
	seconds := pickWindow(cfg, *window)
	overview := eng.Overview(context.Background(), seconds)
	if *asJSON {
		printJSON(overview)
		return
	}
	fmt.Print(render.Overview(overview))
}

func cmdAlerts(args []string) {
	fs := flag.NewFlagSet("alerts", flag.ExitOnError)
	configPath := fs.String("config", "", "配置文件路径")
	window := fs.String("window", "", "时间窗（如 15m）")
	severity := fs.String("severity", "", "按严重度过滤：critical|major|warning|info")
	ruleFilter := fs.String("rule", "", "按规则过滤：container_oom|cpu_contention|tool_failure")
	limit := fs.Int("limit", 100, "最多返回条数")
	fixture := fs.Bool("fixture", false, "只使用 fixture 回放（等价降级模式）")
	scenario := fs.String("scenario", "", "fixture 场景名")
	asJSON := fs.Bool("json", false, "输出原始 JSON")
	_ = fs.Parse(args)
	cfg := mustConfig(*configPath)
	applyFixtureFlags(cfg, *fixture, *scenario)
	eng, err := engine.New(cfg)
	if err != nil {
		fatal(err)
	}
	seconds := pickWindow(cfg, *window)
	list := eng.Incidents(context.Background(), seconds, *severity, *ruleFilter, *limit)
	if *asJSON {
		printJSON(list)
		return
	}
	fmt.Print(render.Incidents(list))
}

// cmdCapture 把一次真实取数落盘为回放 fixture（真实 → 回放，赛题可复现要求）。
func cmdCapture(args []string) {
	fs := flag.NewFlagSet("capture", flag.ExitOnError)
	configPath := fs.String("config", "", "配置文件路径")
	scenario := fs.String("scenario", "", "场景名（输出文件名，如 case1-oom）")
	correlationID := fs.String("correlation-id", "", "应用层关联锚点")
	resourceID := fs.String("resource-id", "", "资源锚点")
	window := fs.String("window", "15m", "时间窗（如 15m）")
	outDir := fs.String("out", "fixtures", "输出目录")
	description := fs.String("description", "", "场景说明")
	_ = fs.Parse(args)

	if *scenario == "" {
		fatal(fmt.Errorf("必须指定 --scenario（输出文件名）"))
	}
	if *correlationID == "" && *resourceID == "" {
		fatal(fmt.Errorf("必须指定 --correlation-id 或 --resource-id"))
	}
	cfg := mustConfig(*configPath)
	eng, err := engine.New(cfg)
	if err != nil {
		fatal(err)
	}
	seconds := parseDuration(*window)
	snap := eng.Gather(context.Background(), source.Focus{
		CorrelationID: *correlationID, ResourceID: *resourceID,
	}, eng.Window(seconds, time.Time{}, time.Time{}))

	if err := os.MkdirAll(*outDir, 0o755); err != nil {
		fatal(err)
	}
	path := filepath.Join(*outDir, *scenario+".json")
	note := *description
	if note == "" {
		note = fmt.Sprintf("真实环境抓取：platform=%s prometheus=%s，证据 %d 条",
			snap.Sources.Platform, snap.Sources.Prometheus, len(snap.Evidence))
	}
	if err := source.SaveFixture(path, snap, *scenario, note); err != nil {
		fatal(err)
	}
	fmt.Printf("已写出 fixture：%s（资源 %d，边 %d，证据 %d，曲线 %d，簇 %d）\n",
		path, len(snap.Resources), len(snap.Edges), len(snap.Evidence), len(snap.Series), len(snap.Incidents))
}

func cmdRules(args []string) {
	fs := flag.NewFlagSet("rules", flag.ExitOnError)
	configPath := fs.String("config", "", "配置文件路径")
	asJSON := fs.Bool("json", false, "输出原始 JSON")
	_ = fs.Parse(args)
	cfg := mustConfig(*configPath)
	eng, err := engine.New(cfg)
	if err != nil {
		fatal(err)
	}
	infos := eng.RuleInfos()
	if *asJSON {
		printJSON(map[string]any{"rules": infos})
		return
	}
	fmt.Print(render.Rules(infos))
}

// ---------------------------------------------------------------------------
// 工具
// ---------------------------------------------------------------------------

func mustConfig(path string) *config.Config {
	cfg, err := config.Load(path)
	if err != nil {
		fatal(err)
	}
	return cfg
}

// applyFixtureFlags 处理 --fixture / --scenario：
//   - --fixture：只走回放（关掉真实数据源），用于无网络/演示确定性；
//   - --scenario：仅切换场景名，真实数据源仍参与（fixture 作为补充）。
func applyFixtureFlags(cfg *config.Config, fixtureOnly bool, scenario string) {
	if fixtureOnly {
		cfg.Sources.Fixture.Enabled = true
		cfg.Sources.Platform.Enabled = false
		cfg.Sources.Prometheus.Enabled = false
	}
	if scenario != "" {
		cfg.Sources.Fixture.Enabled = true
		cfg.Sources.Fixture.Scenario = scenario
	}
}

func pickWindow(cfg *config.Config, raw string) float64 {
	if raw == "" {
		return cfg.WindowSeconds
	}
	return parseDuration(raw)
}

// parseDuration 支持 Go 风格（15m）与纯秒数（300）。
func parseDuration(raw string) float64 {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return 0
	}
	if seconds, err := time.ParseDuration(raw); err == nil {
		return seconds.Seconds()
	}
	var plain float64
	if _, err := fmt.Sscanf(raw, "%g", &plain); err == nil && plain > 0 {
		return plain
	}
	fatal(fmt.Errorf("无法解析时间窗 %q（示例：15m / 300s / 1h）", raw))
	return 0
}

func parseTimeFlag(raw string) time.Time {
	if raw == "" {
		return time.Time{}
	}
	for _, layout := range []string{time.RFC3339, "2006-01-02T15:04:05", "2006-01-02 15:04:05"} {
		if parsed, err := time.Parse(layout, raw); err == nil {
			return parsed
		}
	}
	fatal(fmt.Errorf("无法解析时间 %q（RFC3339：2026-09-20T08:25:00Z）", raw))
	return time.Time{}
}

func printJSON(payload any) {
	encoder := json.NewEncoder(os.Stdout)
	encoder.SetIndent("", "  ")
	encoder.SetEscapeHTML(false)
	if err := encoder.Encode(payload); err != nil {
		fatal(err)
	}
}

func fatal(err error) {
	fmt.Fprintln(os.Stderr, "错误："+err.Error())
	os.Exit(1)
}
