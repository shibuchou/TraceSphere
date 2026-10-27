# TraceSphere Solution Overview

> Full-stack observability for containerized and agent workloads inside ZSvirt virtual machines
> Shanghai Open Source Software Application Innovation Competition · Built on ZSvirt

[中文](../方案说明.md) | English

This document corresponds to delivery requirement §3.a: architecture, deployment boundaries, data model, collection methods, resource correlation, alerting strategy, event correlation and diagnosis flow, and ZSvirt integration with permission and security design.

---

## 1. Design goals

TraceSphere uses three organizing ideas: **VM as the boundary, workload as the object, and event correlation as the core**. It brings metrics, logs, events, and alert evidence into one traceable chain and answers one operational question:

**When an agent task fails, is the cause the application, the container, the VM, the GPU, or the host?**

Three hard constraints:

1. **Explainable** — every diagnosis returns root-cause candidates, impact scope, and evidence IDs. The score is an evidence-match score, not a probability.
2. **Low intrusion** — the VM-side probe is a single binary managed by systemd, degrades automatically when a collector is unavailable, and can be uninstalled with one command.
3. **Reproducible** — real exercise data can be captured as fixtures for replay. Environments without a GPU or eBPF have explicit degraded paths.

## 2. Overall architecture

![TraceSphere layered architecture](../diagrams/architecture-layers.svg)

The platform/diagnosis boundary is deliberate:

- **Platform** owns ZSvirt synchronization, the resource graph, event normalization, correlation clusters, and evidence storage.
- **RCA** reads platform context (`/context`) plus Prometheus metrics and applies YAML rules. It does not collect or correlate on its own.
- Adding a diagnosis rule means adding a YAML file; the engine code does not change.

## 3. Deployment boundaries and minimum environment

| Component | Deployment location | Description |
|---|---|---|
| platform (Python 3.10+, no third-party dependencies) | Host or management node (systemd `tracesphere-platform`, port 8000) | Read-only ZSvirt sync, event ingestion, correlation |
| RCA + Console (Go 1.22+ / static build) | Same host (systemd `tracesphere-rca`, port 8010) | Rule-based diagnosis and Console hosting |
| vm-agent (single Go binary) | Business VM (systemd `tracesphere-vm-agent`) | eBPF / PSI / cgroup / OOM journal collection |
| Sample workload (Docker Compose) | Business VM | llama.cpp + agent-service + tool-service + Toxiproxy + Prometheus + cAdvisor (+ mock-dcgm) |

Minimum environment: a Linux x86_64 KVM host and one ZSvirt-managed business VM (4 vCPU / 4 GiB or more).

Degraded paths:

- No GPU: Mock DCGM provides simulated GPU memory signals.
- No eBPF: the probe falls back to PSI, cgroup, and journal collection.

## 4. Data model

### 4.1 Schema v1 event (frozen)

```text
schema_version / origin / mode / observed_at / ingested_at / type / event_type /
resource_id / correlation_id / trace_id / task_id / severity / source / cluster_id / payload
```

Three input shapes are accepted:

1. **AppEvent** — application events with `event_type / task_id / correlation_id / service / timestamp / status / attributes`.
2. **Full Schema v1 event** — stored according to the field whitelist.
3. **Loose vm-agent event** — any JSON with `event_type`; unknown fields are preserved under `payload`.

`origin ∈ {zsvirt, ebpf, cgroup, cadvisor, app, fluentbit, gpu}` and `mode ∈ {real, mock}`.

### 4.2 Resource model and relation vocabulary

Resource IDs follow `<kind>:<key>`:

```text
host: / vm: / container: / process: / service: / task: / gpu: / cluster: /
zone: / network: / datastore: / volume: / image: / offering:
```

Relation vocabulary (queryable via `GET /api/v1/meta`):

```text
contains / assigned_to / attached_to / uses / has_volume / over /
provides / runs_on / calls / spawns
```

Typical chains:

```text
host -contains-> vm -contains-> container -runs_on-> service -runs_on-> task
gpu -assigned_to-> vm
```

The GPU edge is also present in the Mock DCGM degraded mode.

### 4.3 Evidence item

```text
evidence_id / signal / kind / layer / resource_id / observed_at / severity /
value / unit / description / source_event_ids / payload
```

- `signal` is a normalized signal name such as `memory.events.oom_kill`, `psi_cpu_some_avg10`, `gpu.memory_used_ratio`, `tool.result`, or `task.failed`.
- Counter signals are merged by window delta (evidence only when Δ > 0); gauge signals take the window peak. Raw sampling rows are not promoted to evidence.
- Every evidence item keeps `source_event_ids` so it can be traced back to the original event.

## 5. Collection methods

| Signal | Collector | Path | Frequency |
|---|---|---|---|
| ZSvirt resources / alarms | platform | Read-only REST sync (login + inventory), configurable interval (`ZSVIRT_SYNC_INTERVAL`) | Startup + configurable interval (120 s in the tested deployment) |
| Container cgroup (memory / CPU / throttling) | vm-agent | cgroup v2 direct read (per container) | 15 s |
| PSI (CPU / memory / IO pressure) | vm-agent | `/proc/pressure/*` | 5 s |
| Process exec/exit, TCP retransmit | vm-agent | eBPF tracepoints, degrade on failure | Real time |
| Kernel OOM | vm-agent | journal pattern match → structured event | 10 s poll |
| Agent task / tool / inference | agent-service | AppEvent direct report with `correlation_id` / `task_id` | Real time |
| Container metrics (Prometheus side) | cAdvisor | Prometheus scrape → RCA adapter | 5 s |
| GPU memory (degraded) | mock-dcgm | Simulated DCGM metrics: direct report + `/metrics` | 15 s |

All VM-side events are posted directly to platform `/api/v1/events`; there is no bridge process. Probe overhead is measured in `docs/evidence/`.

## 6. Resource correlation logic

1. **Resource synchronization mapping** — ZSvirt inventory is mapped to the domain model (Host / VM / Cluster / Zone / Network / Volume / Image / Alarm), preserving `origin/mode` and labels.
2. **Identity completion at ingest** — 12-character container short IDs are prefix-normalized to the full 64-character container ID. The `VM --contains--> Container` edge is created from `vm_uuid` in the event.
3. **Application-layer attribution first** — an AppEvent carrying container / service / task identity is attached to the most specific entity (container > service > task > vm), preventing task evidence from being rolled up and polluting the VM.
4. **GPU layer** — `Host --contains--> GPU --assigned_to--> VM`. In a real environment this can come from the ZSvirt GPU inventory or a DCGM exporter; in degraded mode it is registered by `mock_gpu` configuration.
5. **Correlation keys** — `resource_id` is the primary key; `correlation_id` / `task_id` connect the application layer. Cross-layer tracing uses the resource graph; RCA impact scope is calculated by depth.
6. **eBPF event identity** — vm-agent resolves `/proc/<pid>/cgroup` to a container ID (60 s cache) and attaches `vm_uuid`, so kernel events (OOM / retransmit / process) land on a concrete container rather than an isolated resource.
7. **Extension point (roadmap)** — process-layer events are written only to the local log by default (`VMAGENT_REPORT_PROCESS=1` enables reporting to avoid topology noise). Tenant/project dimensions depend on ZSvirt exposing tenant fields and do not affect the current four-layer correlation.

## 7. Event correlation and diagnosis flow

![Event correlation and diagnosis flow](../diagrams/correlation-diagnosis-flow.svg)

The correlation engine uses:

```text
events
→ time window (default ±5 s)
→ resource identity (cgroup / cAdvisor / eBPF)
→ correlation_id (application anchor)
→ resource-graph topology (1-hop neighbours of the focus resource)
→ cluster (idempotent cluster_key = hash of event-ID set)
→ evidence (signal / kind / description / source event IDs)
```

**No evidence, no diagnosis.** An empty evidence set produces zero root-cause candidates; the engine does not emit a hard-coded guess.

## 8. Alerting strategy

- **Severity** — `info / warning / major / critical`, declared by rule YAML; the incident takes the maximum evidence severity.
- **Aggregation** — multiple events from one correlation cluster become one incident, showing evidence count, affected task count, and Top-1 score.
- **Deduplication** — events carry a `dedup_key`; repeated events do not add score.
- **Thresholds and baselines** — thresholds live in the rule YAML (e.g. PSI > 5%, GPU memory ratio > 90%); environment changes are handled by editing the rule.
- **Operations** — `open → acknowledged → resolved`, plus `silenced` and restore. State is persisted by RCA through `POST /api/v1/incidents/{id}/status` (JSON file) and is available from the Console.
- **Boundary** — **Alertmanager is not deployed.** The platform provides in-house correlation-cluster aggregation and a minimal incident workflow. Alertmanager-style grouping, inhibition, and notification channels are out of scope; a production deployment can forward incidents to one.

## 9. ZSvirt integration and permission / security design

| Item | Design |
|---|---|
| Integration API | `accounts/login` (SHA-512 password) + read-only inventory queries (hosts / vm-instances / zwatch alarms, paths configurable) |
| Permission | One account is used for read-only queries; the code does not call write APIs. Read-only access is a code-discipline guarantee, **not** a restricted-account guarantee. |
| Credentials | `ZSVIRT_PASSWORD` environment variable (`/etc/tracesphere/platform.env`, mode 600); never in the repository or logs |
| Access control | Platform API `TRACESPHERE_API_TOKEN` (non-loopback binding is refused without a token; direct-report/registration links carry Bearer); RCA `TRACESPHERE_RCA_TOKEN`; write endpoints are rate-limited per IP per minute (default 600); workload control planes bind to loopback by default (`PROM_BIND` for cross-host Prometheus reads) |
| Failure handling | Automatic re-login on 401/403; login or network failure keeps existing data and marks `degraded` (visible in health) |
| Data-plane security | Ingest field whitelist; no business text such as questions/answers (only lengths and metadata); kernel logs are pattern-matched for OOM only; platform API supports a static token |
| Submission sanitization | `tools/sanitize-for-submission.sh` excludes internal documents, replaces internal identifiers, runs a residue scan, and includes a sanitized copy of `docs/evidence` |

## 10. Degradation and reproducibility

- **Fixture replay** — `tracesphere diagnose --scenario <case>` and `TRACESPHERE_RCA_FIXTURE=1` replay the full Console. Fixtures are captured from real exercises and reproduce the Top-1 result and score for the captured scenarios.
- **No GPU** — Mock DCGM (`TRACESPHERE_MOCK_GPU=1` + the `mock-dcgm` container) reproduces Case 4.
- **No eBPF** — the probe automatically falls back to PSI / cgroup / journal.
- **One-command acceptance** — `tools/acceptance.sh` runs injection → collection → correlation → diagnosis → fixture capture for all four scenarios.

## 11. Scenarios and verification results (real environment, 2026-09-30)

| Scenario | Injection | Top-1 conclusion | Evidence Match | Data source |
|---|---|---|---|---|
| Case 1 container OOM | tool-service memory limit 8 MB | Container memory exhausted | 99/100 | platform=real, prometheus=real, fixture=off |
| Case 2 CPU contention | cpu-stress + tightened llama CPU quota | CPU resource contention | 85/100 | platform=real, prometheus=real, fixture=off |
| Case 3 tool call failure | Toxiproxy tool proxy disabled | Agent tool call failure | 67/100 | platform=real, prometheus=real, fixture=off |
| Case 4 GPU memory exhaustion (degraded) | Mock DCGM `exhaust` | GPU memory exhaustion | 89/100 | Mock DCGM (mock) |

Evidence boundaries for these results:

- Case 3 evidence in this run was **application events only** (`tool.result`, `task.failed`). There was no transport-layer or kernel evidence; the result should not be described as proof of a network transport anomaly.
- Case 2 had no `llama_latency_p95_ms` evidence in this run; "inference latency increased" is not a measured conclusion for this run.
- Case 4 uses Mock DCGM. Its metric names are `ts_gpu_*`; they are semantically compatible with a real DCGM exporter but are not real DCGM metric names. No real GPU validation was performed.
- Evidence Match is a rule-evidence hit score (0–100), not a probability or a general accuracy rate.

Original reports: `docs/evidence/acceptance-2026-09-21/` (the directory name is a historical batch name; the reports' time window is 2026-09-30). Evidence-chain examples: `docs/evidence/case*-chain.md`.
