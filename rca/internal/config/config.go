// Package config 定义 C 侧诊断服务的配置（JSON 文件 + 环境变量覆盖）。
package config

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

type PlatformSource struct {
	Enabled bool   `json:"enabled"`
	BaseURL string `json:"base_url"`
	Token   string `json:"token"`
}

type PrometheusSource struct {
	Enabled bool   `json:"enabled"`
	BaseURL string `json:"base_url"`
}

type FixtureSource struct {
	Enabled  bool   `json:"enabled"`
	Dir      string `json:"dir"`
	Scenario string `json:"scenario"`
}

type Sources struct {
	Platform   PlatformSource   `json:"platform"`
	Prometheus PrometheusSource `json:"prometheus"`
	Fixture    FixtureSource    `json:"fixture"`
}

type Config struct {
	Listen        string   `json:"listen"`
	RulesDir      string   `json:"rules_dir"`
	ConsoleDir    string   `json:"console_dir"`
	FixtureDir    string   `json:"fixture_dir"`
	MinScore      float64  `json:"min_score"`
	TopN          int      `json:"top_n"`
	WindowSeconds float64  `json:"window_seconds"`
	CORSOrigins   []string `json:"cors_origins"`
	// SilenceFile 记录人工静默/确认状态的 JSON 文件（告警运营最小实现）
	SilenceFile string  `json:"silence_file"`
	// AuthToken 设置后，/api/*（/health 除外）需要 Bearer Token（最小鉴权，TRACESPHERE_RCA_TOKEN）
	AuthToken string `json:"auth_token"`
	// RateLimitPerMin 写接口（POST）每客户端 IP 每分钟限流；0 = 关闭
	RateLimitPerMin int     `json:"rate_limit_per_min"`
	Sources         Sources `json:"sources"`
	Path            string  `json:"-"`
}

// Default 返回可直接运行的默认配置（真实环境默认值来自交接文档 §2.4）。
func Default() *Config {
	cfg := &Config{
		Listen:        ":8010",
		RulesDir:      "rules",
		FixtureDir:    "fixtures",
		MinScore:      20,
		TopN:          3,
		WindowSeconds: 900,
		CORSOrigins:   []string{"http://127.0.0.1:5173", "http://localhost:5173"},
		SilenceFile:   "data/silenced.json",
		RateLimitPerMin: 600,
	}
	cfg.Sources.Platform = PlatformSource{Enabled: true, BaseURL: "http://127.0.0.1:8000"}
	cfg.Sources.Prometheus = PrometheusSource{Enabled: true, BaseURL: "http://127.0.0.1:9090"}
	cfg.Sources.Fixture = FixtureSource{Enabled: false, Dir: "fixtures", Scenario: "case1-oom"}
	return cfg
}

// Load 读取配置文件；不存在时返回默认值。
func Load(path string) (*Config, error) {
	cfg := Default()
	if path != "" {
		raw, err := os.ReadFile(path)
		if err != nil {
			if !os.IsNotExist(err) {
				return nil, err
			}
		} else if err := json.Unmarshal(raw, cfg); err != nil {
			return nil, err
		}
	}
	cfg.Path = path
	cfg.applyEnv()
	cfg.resolvePaths()
	return cfg, nil
}

func (c *Config) applyEnv() {
	if v := os.Getenv("TRACESPHERE_RCA_LISTEN"); v != "" {
		c.Listen = v
	}
	if v := os.Getenv("TRACESPHERE_PLATFORM_URL"); v != "" {
		c.Sources.Platform.BaseURL = v
	}
	if v := os.Getenv("TRACESPHERE_PLATFORM_TOKEN"); v != "" {
		c.Sources.Platform.Token = v
	}
	if v := os.Getenv("TRACESPHERE_PROMETHEUS_URL"); v != "" {
		c.Sources.Prometheus.BaseURL = v
	}
	if v := os.Getenv("TRACESPHERE_RCA_FIXTURE"); v != "" {
		c.Sources.Fixture.Enabled = v != "0" && !strings.EqualFold(v, "false")
	}
	if v := os.Getenv("TRACESPHERE_RCA_SCENARIO"); v != "" {
		c.Sources.Fixture.Scenario = v
	}
	if v := os.Getenv("TRACESPHERE_RCA_RULES"); v != "" {
		c.RulesDir = v
	}
	if v := os.Getenv("TRACESPHERE_RCA_CONSOLE"); v != "" {
		c.ConsoleDir = v
	}
	if v := os.Getenv("TRACESPHERE_RCA_SILENCE_FILE"); v != "" {
		c.SilenceFile = v
	}
	if v := os.Getenv("TRACESPHERE_RCA_TOKEN"); v != "" {
		c.AuthToken = v
	}
	if v := os.Getenv("TRACESPHERE_RCA_RATE_LIMIT"); v != "" {
		if parsed, err := strconv.Atoi(v); err == nil {
			c.RateLimitPerMin = parsed
		}
	}
	if v := os.Getenv("TRACESPHERE_RCA_CORS"); v != "" {
		parts := []string{}
		for _, item := range strings.Split(v, ",") {
			if trimmed := strings.TrimSpace(item); trimmed != "" {
				parts = append(parts, trimmed)
			}
		}
		c.CORSOrigins = parts
	}
	if v := os.Getenv("TRACESPHERE_RCA_MIN_SCORE"); v != "" {
		if parsed, err := strconv.ParseFloat(v, 64); err == nil {
			c.MinScore = parsed
		}
	}
	if v := os.Getenv("TRACESPHERE_RCA_DISABLE_PLATFORM"); v == "1" {
		c.Sources.Platform.Enabled = false
	}
	if v := os.Getenv("TRACESPHERE_RCA_DISABLE_PROMETHEUS"); v == "1" {
		c.Sources.Prometheus.Enabled = false
	}
}

// resolvePaths 把相对路径按配置文件所在目录解析，便于从任意目录启动。
func (c *Config) resolvePaths() {
	base := "."
	if c.Path != "" {
		base = filepath.Dir(c.Path)
	} else if wd, err := os.Getwd(); err == nil {
		base = wd
	}
	abs := func(p string) string {
		if p == "" || filepath.IsAbs(p) {
			return p
		}
		return filepath.Join(base, p)
	}
	c.RulesDir = abs(c.RulesDir)
	c.FixtureDir = abs(c.FixtureDir)
	c.Sources.Fixture.Dir = abs(c.Sources.Fixture.Dir)
	if c.SilenceFile != "" {
		c.SilenceFile = abs(c.SilenceFile)
	}
	if c.ConsoleDir != "" {
		c.ConsoleDir = abs(c.ConsoleDir)
	}
}
