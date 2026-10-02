// Package source 提供 C 侧的证据数据源适配器：
//
//	platform   —— 队友 B 的 TraceSphere Platform（/api/v1/context、/clusters、/resources）
//	prometheus —— VM 内 cAdvisor / llama.cpp 指标（真实链路，Provider 不可用时仍可出指标证据）
//	fixture    —— 本地回放（赛题要求的降级/回放模式）
//
// 三者产出同一个 model.Evidence 集合，Engine 与 UI 不感知来源差异（方案 §2.1）。
package source

import (
	"fmt"
	"sort"
	"strings"

	"tracesphere/rca/internal/model"
)

// Focus 诊断焦点：应用层锚点（correlation_id）或资源锚点（resource_id）。
type Focus struct {
	CorrelationID string `json:"correlation_id,omitempty"`
	ResourceID    string `json:"resource_id,omitempty"`
}

// SourceStatus 记录每个数据源的真实性状态，UI 必须展示（方案 §8 数据来源标注）。
type SourceStatus struct {
	Platform   string   `json:"platform"`
	Prometheus string   `json:"prometheus"`
	Fixture    string   `json:"fixture,omitempty"`
	Notes      []string `json:"notes,omitempty"`
}

// RawIncident 来自 B 的关联簇（关联 = B 的职责，诊断 = C 的职责，方案 §6.1）。
type RawIncident struct {
	ClusterID     string
	CorrelationID string
	ResourceID    string
	Rule          string
	Summary       string
	WindowStart   model.TSTime
	WindowEnd     model.TSTime
	Evidence      []model.Evidence
}

// Snapshot 一次取数的完整结果。
type Snapshot struct {
	Focus     Focus
	Window    model.Window
	Evidence  []model.Evidence
	Resources []model.Resource
	Edges     []model.Edge
	Series    []model.Series
	Incidents []RawIncident
	Sources   SourceStatus
}

// ResourceIndex 资源索引与图查询辅助。
type ResourceIndex struct {
	byID     map[string]model.Resource
	parent   map[string]string
	children map[string][]string
	edges    []model.Edge
}

func NewResourceIndex(resources []model.Resource, edges []model.Edge) *ResourceIndex {
	idx := &ResourceIndex{
		byID:     map[string]model.Resource{},
		parent:   map[string]string{},
		children: map[string][]string{},
		edges:    edges,
	}
	for _, r := range resources {
		idx.byID[r.ResourceID] = r
		if r.VMID != "" {
			idx.linkParent(r.ResourceID, r.VMID)
		}
		if r.HostID != "" {
			idx.linkParent(r.ResourceID, r.HostID)
		}
	}
	for _, e := range edges {
		// 关系方向：contains/provides/spawns 由 src 指向子资源；
		// runs_on/assigned_to/attached_to/uses/calls/over 由 src 指向其上层依赖。
		switch e.Relation {
		case "contains", "provides", "spawns", "has_volume":
			idx.linkParent(e.DstID, e.SrcID)
		case "runs_on", "assigned_to", "attached_to", "over":
			idx.linkParent(e.SrcID, e.DstID)
		}
	}
	return idx
}

func (r *ResourceIndex) linkParent(child, parent string) {
	if child == "" || parent == "" || child == parent {
		return
	}
	if _, ok := r.parent[child]; !ok {
		r.parent[child] = parent
	}
	for _, existing := range r.children[parent] {
		if existing == child {
			return
		}
	}
	r.children[parent] = append(r.children[parent], child)
}

// Neighbors 返回资源的一跳邻居（边的双向 + 归属关系）。
func (r *ResourceIndex) Neighbors(id string) []string {
	if r == nil || id == "" {
		return nil
	}
	seen := map[string]bool{}
	var out []string
	add := func(candidate string) {
		if candidate == "" || candidate == id || seen[candidate] {
			return
		}
		seen[candidate] = true
		out = append(out, candidate)
	}
	if parent := r.parent[id]; parent != "" {
		add(parent)
	}
	for _, child := range r.children[id] {
		add(child)
	}
	for _, edge := range r.edges {
		if edge.SrcID == id {
			add(edge.DstID)
		}
		if edge.DstID == id {
			add(edge.SrcID)
		}
	}
	return out
}

// Distance 返回资源图中两点的最短跳数（超过 4 跳返回 99，视为不相关）。
//
// 用途：Evidence Match 的"资源邻接度"维度（方案 §6.3）——同一容器/服务上下文得高分，
// 跨主机得低分。fixture 精简场景没有边时由 VM 归属兜底。
func (r *ResourceIndex) Distance(from, to string) int {
	if from == "" || to == "" {
		return 99
	}
	if from == to {
		return 0
	}
	visited := map[string]int{from: 0}
	queue := []string{from}
	for len(queue) > 0 {
		current := queue[0]
		queue = queue[1:]
		depth := visited[current]
		if depth >= 4 {
			continue
		}
		for _, next := range r.Neighbors(current) {
			if _, ok := visited[next]; ok {
				continue
			}
			if next == to {
				return depth + 1
			}
			visited[next] = depth + 1
			queue = append(queue, next)
		}
	}
	// 没有图信息时：同一 VM 视为可关联（返回 3）
	vmFrom, vmTo := r.VMOf(from), r.VMOf(to)
	if vmFrom != "" && vmFrom == vmTo {
		return 3
	}
	return 99
}

func (r *ResourceIndex) Get(id string) (model.Resource, bool) {
	if r == nil {
		return model.Resource{}, false
	}
	res, ok := r.byID[id]
	return res, ok
}

func (r *ResourceIndex) Name(id string) string {
	if res, ok := r.Get(id); ok && res.Name != "" {
		return res.Name
	}
	return id
}

// OfKind 返回指定 kind 的资源（按名称排序，保证输出稳定）。
func (r *ResourceIndex) OfKind(kind string) []model.Resource {
	var out []model.Resource
	for _, res := range r.byID {
		if res.Kind == kind {
			out = append(out, res)
		}
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Name < out[j].Name })
	return out
}

func (r *ResourceIndex) All() []model.Resource {
	out := make([]model.Resource, 0, len(r.byID))
	for _, res := range r.byID {
		out = append(out, res)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].ResourceID < out[j].ResourceID })
	return out
}

// ParentOf 返回资源的上游（contains / runs_on / provides / assigned_to / over / spawns）。
func (r *ResourceIndex) ParentOf(id string) string {
	if r == nil {
		return ""
	}
	return r.parent[id]
}

// EdgesSnapshot 返回资源图的边（副本，避免调用方修改内部状态）。
func (r *ResourceIndex) EdgesSnapshot() []model.Edge {
	if r == nil {
		return nil
	}
	out := make([]model.Edge, len(r.edges))
	copy(out, r.edges)
	return out
}

// VMOf 沿资源图向上找所属 VM（CPU 争抢规则需要"同 VM"判定，方案 §5.2）。
func (r *ResourceIndex) VMOf(resourceID string) string {
	if r == nil || resourceID == "" {
		return ""
	}
	seen := map[string]bool{}
	current := resourceID
	for i := 0; i < 8 && current != "" && !seen[current]; i++ {
		seen[current] = true
		res, ok := r.byID[current]
		if ok {
			if res.Kind == "vm" {
				return res.ResourceID
			}
			if res.VMID != "" {
				return res.VMID
			}
		}
		current = r.parent[current]
	}
	return ""
}

// Layer 判定证据所属层级（时间线按层着色：应用/容器/虚拟机/云平台）。
func (r *ResourceIndex) Layer(origin, resourceID string) string {
	switch origin {
	case "app", "fluentbit":
		return "application"
	case "zsvirt":
		return "zsvirt"
	}
	if res, ok := r.Get(resourceID); ok {
		switch res.Kind {
		case "container", "service", "task", "process":
			return "container"
		case "vm":
			return "vm"
		case "gpu":
			// GPU 为 VM 侧加速资源（无 GPU 降级模式下为模拟资源），归入虚拟机层
			return "vm"
		case "host", "cluster", "zone", "datacenter":
			return "zsvirt"
		}
	}
	switch model.KindOf(resourceID) {
	case "container", "service", "task", "process":
		return "container"
	case "vm":
		return "vm"
	case "gpu":
		return "vm"
	case "host", "cluster":
		return "zsvirt"
	}
	switch origin {
	case "cgroup", "cadvisor":
		return "container"
	case "ebpf":
		return "vm"
	}
	return "application"
}

// KindForOrigin 证据类别（对齐 B 的 evidence.kind 词表）。
func KindForOrigin(origin string) string {
	switch origin {
	case "zsvirt":
		return "zsvirt"
	case "ebpf":
		return "ebpf"
	case "cgroup":
		return "cgroup"
	case "cadvisor":
		return "metric"
	case "app":
		return "app_event"
	case "fluentbit":
		return "log"
	case "platform":
		return "topology"
	case "prometheus":
		return "metric"
	case "gpu":
		return "metric"
	default:
		return "other"
	}
}

// EnrichEdges 补全资源图的归属边（VM → Container/Service/Task）。
//
// 背景（联调发现的接口缺口，见开工交接 §已知问题）：
// B 的 event ingest 从事件惰性创建 container/service/task 资源，但**不写 vm_id**，
// 因此 platform 侧资源图里没有 VM→Container 边。C 侧按以下顺序兜底：
//  1. 资源属性里的 vm_id / vm_uuid / configured_vm_uuid（最可靠）；
//  2. 单 VM 环境（当前演示环境只有一台业务 VM）下，把未归属的容器/服务/任务挂到该 VM；
//  3. host 同理。
//
// 这些边标记 origin=platform-inferred，演示时可明确区分"来自 ZSvirt 的真实边"与"C 侧推断边"。
func EnrichEdges(resources []model.Resource, edges []model.Edge) []model.Edge {
	exists := map[string]bool{}
	for _, edge := range edges {
		exists[edge.SrcID+"|"+edge.DstID+"|"+edge.Relation] = true
	}
	var vms, hosts []model.Resource
	for _, res := range resources {
		switch res.Kind {
		case "vm":
			vms = append(vms, res)
		case "host":
			hosts = append(hosts, res)
		}
	}
	add := func(src, dst string) {
		if src == "" || dst == "" || src == dst {
			return
		}
		key := src + "|" + dst + "|contains"
		if exists[key] {
			return
		}
		exists[key] = true
		edges = append(edges, model.Edge{SrcID: src, DstID: dst, Relation: "contains", Origin: "platform-inferred", Mode: "real"})
	}

	for _, res := range resources {
		switch res.Kind {
		case "container", "service", "task", "process":
		default:
			continue
		}
		vmID := attributeString(res, "vm_id", "vm_uuid", "configured_vm_uuid")
		if vmID != "" && !strings.HasPrefix(vmID, "vm:") {
			vmID = "vm:" + vmID
		}
		if vmID == "" && len(vms) == 1 {
			vmID = vms[0].ResourceID
		}
		if vmID != "" {
			add(vmID, res.ResourceID)
		}
		hostID := attributeString(res, "host_id", "host_uuid")
		if hostID == "" && res.VMID != "" {
			for _, vm := range vms {
				if vm.ResourceID == res.VMID && vm.HostID != "" {
					hostID = vm.HostID
				}
			}
		}
		if hostID == "" && len(hosts) == 1 {
			hostID = hosts[0].ResourceID
		}
		if hostID != "" {
			add(hostID, res.ResourceID)
		}
	}
	return edges
}

func attributeString(res model.Resource, keys ...string) string {
	for _, key := range keys {
		value, ok := res.Attributes[key]
		if !ok || value == nil {
			continue
		}
		switch typed := value.(type) {
		case string:
			if typed != "" {
				return typed
			}
		default:
			text := fmt.Sprintf("%v", value)
			if text != "" && text != "<nil>" {
				return text
			}
		}
	}
	if res.VMID != "" {
		for _, key := range keys {
			if key == "vm_id" {
				return res.VMID
			}
		}
	}
	return ""
}

// LooksLikeID 判断资源名是否是"哈希式"占位名（B 的 ingest 用 container_id 前 12 位当名字）。
func LooksLikeID(name string) bool {
	if len(name) < 12 {
		return false
	}
	if len(name) > 12 {
		return false
	}
	for _, r := range name {
		if !((r >= '0' && r <= '9') || (r >= 'a' && r <= 'f')) {
			return false
		}
	}
	return true
}

// DedupEvidence 按 evidence_id（无 ID 时按 signal+时间+资源）去重并排序。
func DedupEvidence(items []model.Evidence) []model.Evidence {
	seen := map[string]bool{}
	out := make([]model.Evidence, 0, len(items))
	for _, item := range items {
		key := item.EvidenceID
		if key == "" {
			key = strings.Join([]string{item.Signal, item.ResourceID, item.ObservedAt.UTC().Format("2006-01-02T15:04:05.999999999")}, "|")
		}
		if seen[key] {
			continue
		}
		seen[key] = true
		out = append(out, item)
	}
	sort.SliceStable(out, func(i, j int) bool {
		return out[i].ObservedAt.Before(out[j].ObservedAt.Time)
	})
	return out
}
