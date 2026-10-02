package source

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"tracesphere/rca/internal/model"
)

// FixtureFile 是回放场景文件（赛题要求的降级/回放材料，方案 §2.4 P0）。
//
// 一个场景 = 一次故障演练的完整证据快照：资源图 + 证据 + 指标曲线 + 关联簇。
// 结构与 platform 的 API 响应同源，便于"真实数据 → fixture"一键落盘。
type FixtureFile struct {
	Scenario    string            `json:"scenario"`
	Description string            `json:"description"`
	Mode        string            `json:"mode"`
	Window      model.Window      `json:"window"`
	Focus       Focus             `json:"focus"`
	Resources   []model.Resource  `json:"resources"`
	Edges       []model.Edge      `json:"edges"`
	Evidence    []model.Evidence  `json:"evidence"`
	Series      []model.Series    `json:"series"`
	Incidents   []FixtureIncident `json:"incidents"`
	Meta        map[string]any    `json:"meta"`
}

// FixtureIncident 关联簇（证据用 ID 引用，保持 fixture 可读）。
type FixtureIncident struct {
	ClusterID     string       `json:"cluster_id"`
	CorrelationID string       `json:"correlation_id"`
	ResourceID    string       `json:"resource_id"`
	Rule          string       `json:"rule"`
	Summary       string       `json:"summary"`
	WindowStart   model.TSTime `json:"window_start"`
	WindowEnd     model.TSTime `json:"window_end"`
	EvidenceIDs   []string     `json:"evidence_ids"`
}

// LoadFixture 读取单个场景文件。
func LoadFixture(path string) (*Snapshot, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var file FixtureFile
	if err := json.Unmarshal(raw, &file); err != nil {
		return nil, fmt.Errorf("解析 fixture %s 失败: %w", path, err)
	}
	mode := file.Mode
	if mode == "" {
		mode = "mock"
	}
	for i := range file.Evidence {
		if file.Evidence[i].Mode == "" {
			file.Evidence[i].Mode = mode
		}
	}
	idx := NewResourceIndex(file.Resources, file.Edges)
	// 补全证据里的资源名与层级
	for i := range file.Evidence {
		if file.Evidence[i].ResourceName == "" {
			file.Evidence[i].ResourceName = idx.Name(file.Evidence[i].ResourceID)
		}
		if file.Evidence[i].Layer == "" {
			file.Evidence[i].Layer = idx.Layer(file.Evidence[i].Origin, file.Evidence[i].ResourceID)
		}
	}

	byID := map[string][]model.Evidence{}
	for _, item := range file.Evidence {
		byID[item.EvidenceID] = append(byID[item.EvidenceID], item)
	}
	var incidents []RawIncident
	for _, raw := range file.Incidents {
		var items []model.Evidence
		for _, id := range raw.EvidenceIDs {
			items = append(items, byID[id]...)
		}
		if len(items) == 0 {
			items = file.Evidence
		}
		incidents = append(incidents, RawIncident{
			ClusterID: raw.ClusterID, CorrelationID: raw.CorrelationID, ResourceID: raw.ResourceID,
			Rule: raw.Rule, Summary: raw.Summary,
			WindowStart: raw.WindowStart, WindowEnd: raw.WindowEnd, Evidence: items,
		})
	}

	return &Snapshot{
		Focus:     file.Focus,
		Window:    file.Window,
		Evidence:  DedupEvidence(file.Evidence),
		Resources: file.Resources,
		Edges:     EnrichEdges(file.Resources, file.Edges),
		Series:    file.Series,
		Incidents: incidents,
		Sources:   SourceStatus{Platform: "mock", Prometheus: "mock", Fixture: "mock", Notes: []string{"fixture 回放：" + file.Scenario}},
	}, nil
}

// SaveFixture 把一次真实快照落盘为回放 fixture（真实 → 回放的取证路径）。
//
// 赛题要求可复现：演示现场若 ZSvirt/VM 不可用，可直接用这些真实抓取的文件回放。
func SaveFixture(path string, snap *Snapshot, scenario, description string) error {
	file := FixtureFile{
		Scenario:    scenario,
		Description: description,
		Mode:        "real",
		Window:      snap.Window,
		Focus:       snap.Focus,
		Resources:   snap.Resources,
		Edges:       snap.Edges,
		Evidence:    snap.Evidence,
		Series:      snap.Series,
		Meta: map[string]any{
			"captured_at": time.Now().UTC().Format(time.RFC3339),
			"sources":     snap.Sources,
			"note":        "由 tracesphere capture 从真实环境（platform + Prometheus）抓取",
		},
	}
	byID := map[string]bool{}
	for _, item := range snap.Evidence {
		byID[item.EvidenceID] = true
	}
	for _, incident := range snap.Incidents {
		fixtureIncident := FixtureIncident{
			ClusterID: incident.ClusterID, CorrelationID: incident.CorrelationID,
			ResourceID: incident.ResourceID, Rule: incident.Rule, Summary: incident.Summary,
			WindowStart: incident.WindowStart, WindowEnd: incident.WindowEnd,
		}
		for _, item := range incident.Evidence {
			if byID[item.EvidenceID] {
				fixtureIncident.EvidenceIDs = append(fixtureIncident.EvidenceIDs, item.EvidenceID)
			}
		}
		file.Incidents = append(file.Incidents, fixtureIncident)
	}
	raw, err := json.MarshalIndent(file, "", "  ")
	if err != nil {
		return err
	}
	raw = append(raw, '\n')
	return os.WriteFile(path, raw, 0o644)
}

// LoadFixtureDir 读取目录下全部场景（scenario -> snapshot）。
func LoadFixtureDir(dir string) (map[string]*Snapshot, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	out := map[string]*Snapshot{}
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".json") {
			continue
		}
		snap, err := LoadFixture(filepath.Join(dir, entry.Name()))
		if err != nil {
			return nil, err
		}
		key := strings.TrimSuffix(entry.Name(), ".json")
		out[key] = snap
	}
	if len(out) == 0 {
		return nil, fmt.Errorf("目录 %s 下没有 fixture", dir)
	}
	return out, nil
}

// Scenarios 返回目录下的场景名（排序）。
func Scenarios(dir string) []string {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil
	}
	var names []string
	for _, entry := range entries {
		if !entry.IsDir() && strings.HasSuffix(entry.Name(), ".json") {
			names = append(names, strings.TrimSuffix(entry.Name(), ".json"))
		}
	}
	sort.Strings(names)
	return names
}
