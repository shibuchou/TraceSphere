// Package api 暴露诊断服务的 HTTP 接口（供 Web Console 与外部调用）。
// 契约见 rca/docs/API.md §4。
package api

import (
	"context"
	"crypto/subtle"
	"encoding/json"
	"fmt"
	"log"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"

	"tracesphere/rca/internal/config"
	"tracesphere/rca/internal/engine"
	"tracesphere/rca/internal/model"
)

// Server 诊断服务。
type Server struct {
	engine  *engine.Engine
	cfg     *config.Config
	silence *SilenceState
	limiter *rateLimiter
}

func New(e *engine.Engine) *Server {
	return &Server{
		engine:  e,
		cfg:     e.Config(),
		silence: NewSilenceState(e.Config().SilenceFile),
		limiter: newRateLimiter(e.Config().RateLimitPerMin),
	}
}

// rateLimiter：POST 接口的最小令牌限流（按客户端 IP 的滑动窗口）。
type rateLimiter struct {
	mu     sync.Mutex
	limit  int
	window time.Duration
	hits   map[string][]time.Time
}

func newRateLimiter(perMinute int) *rateLimiter {
	return &rateLimiter{limit: perMinute, window: time.Minute, hits: map[string][]time.Time{}}
}

func (l *rateLimiter) allow(key string) bool {
	if l == nil || l.limit <= 0 {
		return true
	}
	l.mu.Lock()
	defer l.mu.Unlock()
	now := time.Now()
	kept := l.hits[key][:0]
	for _, t := range l.hits[key] {
		if now.Sub(t) < l.window {
			kept = append(kept, t)
		}
	}
	if len(kept) >= l.limit {
		l.hits[key] = kept
		return false
	}
	l.hits[key] = append(kept, now)
	return true
}

// SilenceState 记录人工静默/确认/恢复的告警状态（告警运营最小实现，赛题 §2）。
//
// 采用 JSON 文件持久化（默认 ``data/silenced.json``，可用
// ``TRACESPHERE_RCA_SILENCE_FILE`` 覆盖）；语义：
//   - silenced     静默（不再打扰，保留在列表中并标记）
//   - acknowledged 已确认（运维接单）
//   - resolved     已处理
//   - 空           恢复 open
type SilenceState struct {
	mu     sync.Mutex
	path   string
	status map[string]string
}

func NewSilenceState(path string) *SilenceState {
	state := &SilenceState{path: path, status: map[string]string{}}
	_ = state.load()
	return state
}

func (s *SilenceState) load() error {
	if s == nil || s.path == "" {
		return nil
	}
	raw, err := os.ReadFile(s.path)
	if err != nil {
		return err
	}
	return json.Unmarshal(raw, &s.status)
}

func (s *SilenceState) persistLocked() error {
	if s.path == "" {
		return nil
	}
	if err := os.MkdirAll(filepath.Dir(s.path), 0o755); err != nil {
		return err
	}
	raw, err := json.MarshalIndent(s.status, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(s.path, raw, 0o644)
}

// Set 更新状态；status 为空表示恢复 open。
func (s *SilenceState) Set(id, status string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if status == "" {
		delete(s.status, id)
	} else {
		s.status[id] = status
	}
	return s.persistLocked()
}

func (s *SilenceState) Get(id string) string {
	if s == nil {
		return ""
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.status[id]
}

func (s *SilenceState) applyList(list *model.IncidentList) {
	if s == nil || list == nil {
		return
	}
	for i := range list.Incidents {
		if status := s.Get(list.Incidents[i].IncidentID); status != "" {
			list.Incidents[i].Status = status
		}
	}
}

// Handler 组装路由（含 CORS 与 console 静态托管）。
func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /api/v1/health", s.handleHealth)
	mux.HandleFunc("GET /api/v1/meta", s.handleMeta)
	mux.HandleFunc("GET /api/v1/rules", s.handleRules)
	mux.HandleFunc("GET /api/v1/topology", s.handleTopology)
	mux.HandleFunc("GET /api/v1/overview", s.handleOverview)
	mux.HandleFunc("GET /api/v1/incidents", s.handleIncidents)
	mux.HandleFunc("GET /api/v1/incidents/{id}", s.handleIncidentDetail)
	mux.HandleFunc("POST /api/v1/incidents/{id}/status", s.handleIncidentStatus)
	mux.HandleFunc("POST /api/v1/diagnose", s.handleDiagnose)
	mux.HandleFunc("GET /api/v1/diagnose", s.handleDiagnose)
	mux.HandleFunc("GET /api/v1/metrics/series", s.handleSeries)
	mux.HandleFunc("GET /api/v1/context", s.handleContext)

	if s.cfg.ConsoleDir != "" {
		if info, err := os.Stat(s.cfg.ConsoleDir); err == nil && info.IsDir() {
			mux.Handle("/", spaHandler(s.cfg.ConsoleDir))
		}
	}
	var handler http.Handler = cors(mux, s.cfg.CORSOrigins)
	handler = s.rateLimit(handler)
	handler = s.authenticate(handler)
	return handler
}

// authenticate：配置 TRACESPHERE_RCA_TOKEN 后，/api/*（/health 除外）需要 Bearer Token。
func (s *Server) authenticate(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		token := strings.TrimSpace(s.cfg.AuthToken)
		if token == "" || r.Method == http.MethodOptions ||
			!strings.HasPrefix(r.URL.Path, "/api/") || r.URL.Path == "/api/v1/health" {
			next.ServeHTTP(w, r)
			return
		}
		header := r.Header.Get("Authorization")
		supplied := strings.TrimSpace(r.Header.Get("X-API-Token"))
		if len(header) > 7 && strings.EqualFold(header[:7], "bearer ") {
			supplied = strings.TrimSpace(header[7:])
		}
		if subtle.ConstantTimeCompare([]byte(supplied), []byte(token)) != 1 {
			writeError(w, http.StatusUnauthorized, fmt.Errorf("missing or invalid API token"))
			return
		}
		next.ServeHTTP(w, r)
	})
}

// rateLimit：仅对写接口（POST /api/*）做最小限流。
func (s *Server) rateLimit(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodPost && strings.HasPrefix(r.URL.Path, "/api/") {
			host, _, err := net.SplitHostPort(r.RemoteAddr)
			if err != nil {
				host = r.RemoteAddr
			}
			if !s.limiter.allow(host) {
				writeError(w, http.StatusTooManyRequests, fmt.Errorf("rate limit exceeded (per-minute POST quota)"))
				return
			}
		}
		next.ServeHTTP(w, r)
	})
}

// Serve 启动 HTTP 服务。
func Serve(ctx context.Context, e *engine.Engine, listen string) error {
	server := &http.Server{Addr: listen, Handler: New(e).Handler(), ReadHeaderTimeout: 10 * time.Second}
	go func() {
		<-ctx.Done()
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = server.Shutdown(shutdownCtx)
	}()
	log.Printf("TraceSphere RCA 诊断服务监听 http://0.0.0.0%s（规则 %d 条，平台 %s，Prometheus %s）",
		listen, len(e.Rules()), e.Config().Sources.Platform.BaseURL, e.Config().Sources.Prometheus.BaseURL)
	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		return err
	}
	return nil
}

// ---------------------------------------------------------------------------
// handlers
// ---------------------------------------------------------------------------

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, s.engine.Health(r.Context()))
}

func (s *Server) handleMeta(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{
		"service":        "tracesphere-rca",
		"schema_version": "v1",
		"endpoints": []string{
			"GET /api/v1/health", "GET /api/v1/meta", "GET /api/v1/rules",
			"GET /api/v1/topology", "GET /api/v1/overview", "GET /api/v1/incidents",
			"GET /api/v1/incidents/{id}", "POST /api/v1/incidents/{id}/status",
			"POST /api/v1/diagnose", "GET /api/v1/metrics/series",
		},
		"notes":            "Evidence Match 为规则证据命中评分（0–100），非概率",
		"config":           s.cfg,
		"score_dimensions": []string{"rule_match", "temporal_precedence", "resource_adjacency", "signal_strength", "independent_evidence"},
	})
}

func (s *Server) handleRules(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{"rules": s.engine.RuleInfos()})
}

func (s *Server) handleTopology(w http.ResponseWriter, r *http.Request) {
	focus := r.URL.Query().Get("focus_id")
	window := queryFloat(r, "window_seconds", s.cfg.WindowSeconds)
	writeJSON(w, http.StatusOK, s.engine.Topology(r.Context(), focus, window))
}

func (s *Server) handleOverview(w http.ResponseWriter, r *http.Request) {
	window := queryFloat(r, "window_seconds", s.cfg.WindowSeconds)
	writeJSON(w, http.StatusOK, s.engine.Overview(r.Context(), window))
}

func (s *Server) handleIncidents(w http.ResponseWriter, r *http.Request) {
	window := queryFloat(r, "window_seconds", s.cfg.WindowSeconds)
	severity := r.URL.Query().Get("severity")
	ruleFilter := r.URL.Query().Get("rule")
	limit := queryInt(r, "limit", 100)
	list := s.engine.Incidents(r.Context(), window, severity, ruleFilter, limit)
	s.silence.applyList(&list)
	writeJSON(w, http.StatusOK, list)
}

func (s *Server) handleIncidentDetail(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	detail, err := s.engine.IncidentDetail(r.Context(), id)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err)
		return
	}
	if status := s.silence.Get(id); status != "" {
		detail.Incident.Status = status
	}
	writeJSON(w, http.StatusOK, detail)
}

type incidentStatusBody struct {
	Action string `json:"action"`
}

// handleIncidentStatus 更新告警运营状态（静默 / 确认 / 已处理 / 恢复）。
func (s *Server) handleIncidentStatus(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	var body incidentStatusBody
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, fmt.Errorf("请求体必须是 JSON：%w", err))
		return
	}
	action := strings.ToLower(strings.TrimSpace(body.Action))
	statusByAction := map[string]string{
		"silence":     "silenced",
		"acknowledge": "acknowledged",
		"resolve":     "resolved",
		"open":        "",
		"unsilence":   "",
	}
	status, ok := statusByAction[action]
	if !ok {
		writeError(w, http.StatusBadRequest, fmt.Errorf("action 必须是 silence / acknowledge / resolve / open"))
		return
	}
	if err := s.silence.Set(id, status); err != nil {
		writeError(w, http.StatusInternalServerError, fmt.Errorf("持久化状态失败：%w", err))
		return
	}
	if status == "" {
		status = "open"
	}
	writeJSON(w, http.StatusOK, map[string]any{"incident_id": id, "status": status})
}

type diagnoseBody struct {
	CorrelationID string  `json:"correlation_id"`
	ResourceID    string  `json:"resource_id"`
	WindowSeconds float64 `json:"window_seconds"`
	From          string  `json:"from"`
	To            string  `json:"to"`
	TopN          int     `json:"top_n"`
	Scenario      string  `json:"scenario"`
}

func (s *Server) handleDiagnose(w http.ResponseWriter, r *http.Request) {
	req := diagnoseBody{WindowSeconds: s.cfg.WindowSeconds, TopN: s.cfg.TopN}
	if r.Method == http.MethodPost {
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			writeError(w, http.StatusBadRequest, fmt.Errorf("请求体必须是 JSON：%w", err))
			return
		}
	} else {
		req.CorrelationID = r.URL.Query().Get("correlation_id")
		req.ResourceID = r.URL.Query().Get("resource_id")
		req.Scenario = r.URL.Query().Get("scenario")
		if v := r.URL.Query().Get("window_seconds"); v != "" {
			req.WindowSeconds = queryFloat(r, "window_seconds", s.cfg.WindowSeconds)
		}
	}
	if req.CorrelationID == "" && req.ResourceID == "" && req.Scenario == "" {
		writeError(w, http.StatusBadRequest, fmt.Errorf("必须提供 correlation_id / resource_id / scenario 之一"))
		return
	}
	result := s.engine.Run(r.Context(), engine.DiagnoseRequest{
		CorrelationID: req.CorrelationID,
		ResourceID:    req.ResourceID,
		WindowSeconds: req.WindowSeconds,
		From:          parseTime(req.From),
		To:            parseTime(req.To),
		TopN:          req.TopN,
		Scenario:      req.Scenario,
	})
	writeJSON(w, http.StatusOK, result)
}

func (s *Server) handleSeries(w http.ResponseWriter, r *http.Request) {
	resourceID := r.URL.Query().Get("resource_id")
	metrics := []string{}
	if raw := r.URL.Query().Get("metrics"); raw != "" {
		for _, item := range strings.Split(raw, ",") {
			if trimmed := strings.TrimSpace(item); trimmed != "" {
				metrics = append(metrics, trimmed)
			}
		}
	}
	window := queryFloat(r, "window_seconds", s.cfg.WindowSeconds)
	writeJSON(w, http.StatusOK, s.engine.Series(r.Context(), resourceID, metrics, window))
}

func (s *Server) handleContext(w http.ResponseWriter, r *http.Request) {
	req := engine.DiagnoseRequest{
		CorrelationID: r.URL.Query().Get("correlation_id"),
		ResourceID:    r.URL.Query().Get("resource_id"),
		WindowSeconds: queryFloat(r, "window_seconds", s.cfg.WindowSeconds),
	}
	result := s.engine.Run(r.Context(), req)
	writeJSON(w, http.StatusOK, result)
}

// ---------------------------------------------------------------------------
// plumbing
// ---------------------------------------------------------------------------

func writeJSON(w http.ResponseWriter, status int, payload any) {
	body, err := json.MarshalIndent(payload, "", "  ")
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_, _ = w.Write(body)
}

func writeError(w http.ResponseWriter, status int, err error) {
	writeJSON(w, status, map[string]any{"error": map[string]any{"message": err.Error()}})
}

func queryFloat(r *http.Request, name string, fallback float64) float64 {
	raw := r.URL.Query().Get(name)
	if raw == "" {
		return fallback
	}
	value, err := strconv.ParseFloat(raw, 64)
	if err != nil || value <= 0 {
		return fallback
	}
	return value
}

func queryInt(r *http.Request, name string, fallback int) int {
	raw := r.URL.Query().Get(name)
	if raw == "" {
		return fallback
	}
	value, err := strconv.Atoi(raw)
	if err != nil || value <= 0 {
		return fallback
	}
	return value
}

func parseTime(raw string) time.Time {
	if raw == "" {
		return time.Time{}
	}
	if parsed, err := time.Parse(time.RFC3339, raw); err == nil {
		return parsed
	}
	return time.Time{}
}

// cors 按配置的来源白名单下发 CORS 头（默认仅本地 dev 源；"*" 表示放开）。
func cors(next http.Handler, origins []string) http.Handler {
	allowAll := false
	allowed := map[string]bool{}
	for _, o := range origins {
		if o == "*" {
			allowAll = true
		}
		allowed[o] = true
	}
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		origin := r.Header.Get("Origin")
		switch {
		case allowAll:
			w.Header().Set("Access-Control-Allow-Origin", "*")
		case origin != "" && allowed[origin]:
			w.Header().Set("Access-Control-Allow-Origin", origin)
			w.Header().Add("Vary", "Origin")
		}
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization, X-API-Token")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}

// spaHandler 托管构建好的 console（dist），未知路径回退 index.html（前端路由）。
func spaHandler(dir string) http.Handler {
	fileServer := http.FileServer(http.Dir(dir))
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		path := filepath.Join(dir, filepath.Clean(r.URL.Path))
		if info, err := os.Stat(path); err == nil && !info.IsDir() {
			if filepath.Base(path) == "index.html" {
				setNoCache(w)
			}
			fileServer.ServeHTTP(w, r)
			return
		}
		index := filepath.Join(dir, "index.html")
		if _, err := os.Stat(index); err != nil {
			http.NotFound(w, r)
			return
		}
		setNoCache(w)
		http.ServeFile(w, r, index)
	})
}

// HTML shell must be revalidated so browsers receive the newest content-hashed asset names after deployment.
func setNoCache(w http.ResponseWriter) {
	w.Header().Set("Cache-Control", "no-cache, no-store, must-revalidate")
	w.Header().Set("Pragma", "no-cache")
	w.Header().Set("Expires", "0")
}
