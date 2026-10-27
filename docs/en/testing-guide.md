# TraceSphere Testing Guide

> A full-stack observability platform for containers and agent workloads inside ZSvirt virtual machines
> Shanghai Open Source Software Application Innovation Competition (上海开源软件应用创新大赛) · Based on the ZSvirt virtualization platform
> Document version: v1.0 (2026-10-27) | Code: tracesphere repository main branch

[中文](../测试文档.md) | English

---

## 1. About this document

### 1.1 Purpose

This document describes TraceSphere's test scope, test environment, test methods, test cases, execution records, defects and known limitations. Test conclusions follow the raw reports stored in [`docs/evidence/`](../evidence/); this document cites only results that have already been written to disk, and does not present design goals as measured conclusions.

### 1.2 Test targets

| Module | Code | Test focus |
|---|---|---|
| platform | `platform/` | event normalization, identity completion, resource graph, correlation clusters, evidence, HTTP API, ZSvirt REST Provider |
| rca | `rca/` | rule loading, evidence matching, Evidence Match scoring, diagnosis API, CLI, fixture replay |
| console | `console/` | type contracts, fixture consistency, CSS module references, the four pages and their interactions |
| vm-agent | `vm-agent/` | eBPF / PSI / cgroup / OOM log collection, degradation, reporting and spool |
| workload | `workload/` | sample agent pipeline, four fault injections, Prometheus scraping, Mock DCGM |
| Deployment and operations | `deploy/`, `tools/` | systemd services, one-click start/stop, acceptance, reset, sanitization |

### 1.3 References

- [Solution overview](solution-overview.md): data model, collection methods, correlation logic, incident strategy, degradation requirements;
- [RCA API contract](../../rca/docs/API.md): rule structure, evidence model, five-dimension scoring, HTTP API;
- [Platform API reference](../../platform/README.md): the `/api/v1` contract;
- [Deployment guide](deployment-guide.md): environment, configuration and verification steps;
- `rca/internal/engine/engine_test.go`: Top-1 regression thresholds;
- [`docs/evidence/`](../evidence/): four-scenario acceptance, evidence chains, probe overhead, real-environment run records.

### 1.4 Test data source markers

Every diagnosis response carries `source` / `sources`:

| Marker | Meaning |
|---|---|
| `real` | Real data source (ZSvirt / Prometheus / vm-agent / AppEvent) |
| `degraded` | Data source availability is reduced; some evidence is missing |
| `mock` | Fixture replay or simulated Mock DCGM data |
| `off` | Not enabled |

Test conclusions must record the data source marker at the same time. Live drill results with `fixture=off` and replay results with `fixture=mock` are counted separately.

---

## 2. Quality goals and entry criteria

### 2.1 Functional goals

| ID | Goal | Acceptance criterion |
|---|---|---|
| G-01 | Top-1 hit on four controlled faults | Case1 `container_oom`, Case2 `cpu_contention`, Case3 `tool_failure`, Case4 `gpu_memory_exhaustion` |
| G-02 | Explainable diagnosis | each diagnosis outputs 5 scoring dimensions, evidence IDs, impact scope, and remediation advice (basis / action / risk) |
| G-03 | Traceable evidence | every evidence item has an `evidence_id` and `source_event_ids`; the diagnosis cites evidence IDs |
| G-04 | No diagnosis without evidence | empty evidence returns 0 candidates; no hard reporting based on rules alone |
| G-05 | Real / replay distinguishable | page badge and footer show the data source; api-mode failures do not degrade silently |
| G-06 | Usable under degradation | Mock DCGM when there is no GPU; PSI/cgroup retained when eBPF is unavailable; fixture replay when the platform is unavailable |
| G-07 | Security baseline | token, rate limiting, field whitelist, loopback-only control-plane binding, credentials not written to the database |
| G-08 | Low intrusion | vm-agent idle CPU < 2%, RSS < 100 MiB (design target) |
| G-09 | Reproducible | the four-scenario fixtures can be replayed without a cloud environment, with results consistent with the live run |

### 2.2 Entry criteria

The following must be met before release / submission:

1. all 50 `platform` unit tests pass;
2. `go test ./...` for `rca` passes, and the four scenarios' Top-1 is not below the regression thresholds;
3. `console`'s `npm run verify` passes and `npm run build` succeeds;
4. `tools/acceptance.sh` produces reports for the four scenarios with correct Top-1;
5. the security baseline check passes (see §9);
6. the submission package sanitization and residue scan result is `clean`.

### 2.3 Regression thresholds

Current thresholds in `rca/internal/engine/engine_test.go`:

| Scenario | Expected Top-1 rule | Score floor | Expected timeline layer |
|---|---|---:|---|
| case1-oom | `container_oom` | 85 | container |
| case2-cpu | `cpu_contention` | 75 | vm |
| case3-tool-failure | `tool_failure` | 60 | application |
| case4-gpu-mock | `gpu_memory_exhaustion` | 80 | vm |

The thresholds are the measured floor of fixtures captured from the real environment, not a full-score requirement. The most recent measured values are 99 / 85 / 67 / 89, all above the thresholds.

---

## 3. Test environment

### 3.1 Environment topology

| Role | Configuration | Notes |
|---|---|---|
| KVM host | 20 vCPU / 30 GiB / 176 GiB available disk, nested virtualization enabled | physical machine hosting the platform and the ZSvirt management node |
| ZSvirt management node | 12 vCPU / 16 GiB, ZSvirt v1.0.0 | provides UI on 443 and REST on 8080 |
| Business VM `workload-vm` | 4 vCPU / 4 GiB / 40 GiB, Ubuntu 24.04, kernel 6.8 | vm-agent + Docker Compose |
| Platform side | Python 3.10+ / Go 1.22+ / Node 22 | platform on 8000, RCA + Console on 8010 |
| GPU | none | Case4 uses the Mock DCGM degradation path |

### 3.2 Version record

| Component | Version |
|---|---|
| ZSvirt | v1.0.0 (x86_64 qcow2) |
| Ubuntu | 24.04 LTS |
| Linux kernel | 6.8 (business VM); the measured eBPF environment was recorded as 7.0.0-31-generic |
| Go | 1.25 (vm-agent); 1.22 (rca) |
| Node | 22 |
| Python | 3.10+ (platform, zero third-party dependencies) |
| Prometheus | v2.53.0 (image digest pinned) |
| cAdvisor | v0.49.1 |
| llama.cpp server | image digest pinned |
| Toxiproxy | latest (image digest pinned) |
| cilium/ebpf | v0.22.0 |
| SQLite | 3.x (bundled with Python) |

### 3.3 Test data

| Data | Location | Purpose |
|---|---|---|
| Four-scenario real fixtures | `rca/fixtures/case{1,2,3,4}*.json` | RCA offline replay and regression |
| Frontend fixtures | `console/src/mocks/*.json` | Console fixture mode |
| Four-scenario acceptance reports | [`docs/evidence/acceptance-2026-09-21/`](../evidence/acceptance-2026-09-21/) | Results from real data sources |
| Evidence chain examples | `../evidence/case{1,2,3}-chain.md` | Raw events and the correlation process |
| Real-environment run record | [`docs/evidence/rca-real-run.md`](../evidence/rca-real-run.md) | Real-environment acceptance from an earlier batch |
| Probe overhead report | [`docs/evidence/vm-agent-overhead.md`](../evidence/vm-agent-overhead.md) | Performance testing |
| Mock DCGM | `workload/mock/gpu_exporter.py` | Fallback when there is no GPU |

> `acceptance-2026-09-21/` is a historical directory name; the time window of the four reports inside is 2026-09-30. When citing them, use the timestamps and data source markers inside the reports.

---

## 4. Test strategy

### 4.1 Layers

| Layer | Object | Method | Execution |
|---|---|---|---|
| L1 unit tests | platform's schema / store / ingest / correlate / REST provider / mock GPU | Python `unittest`, temporary SQLite and fake providers | automated |
| L1 unit tests | RCA rule loading, scoring, fixture diagnosis | Go `testing`, fixture replay | automated |
| L2 contract tests | three event formats, evidence signal naming, API response fields | unit tests + fixture validation | automated |
| L2 frontend contracts | type definitions consistent with `API.md`, fixture fields complete | `tsc --noEmit` + `check-fixtures` + `check-css` | automated |
| L3 integration tests | ZSvirt REST → platform → resource graph → events → correlation → evidence | real environment / fixture | automated + manual |
| L4 end-to-end acceptance | injection → collection → ingestion → correlation → RCA → Console | `tools/acceptance.sh` + page checks | semi-automated |
| L5 security tests | token, rate limiting, binding, field whitelist, privacy | curl + code review + configuration checks | manual |
| L6 performance tests | vm-agent overhead | `measure-overhead.sh` sampling | manual |
| L7 degradation tests | no GPU / no eBPF / platform unavailable / fixture | disable data sources or switch scenarios | manual |
| L8 UI tests | four pages, filters, status operations, error states | manual browser checks | manual |

### 4.2 Test judgments

- **Top-1 correct**: the rule ID matches the expectation;
- **Score reasonable**: not below the regression threshold, and `score_breakdown` contains all five dimensions;
- **Evidence traceable**: `evidence_ids` is non-empty, and every evidence item can be found in the response;
- **Impact scope non-empty**: `impact.scope` contains at least one resource;
- **Timeline non-empty**: contains at least evidence at the expected layer;
- **Source correct**: live drill uses `fixture=off`; replay uses `fixture=mock`;
- **No diagnosis without evidence**: an empty snapshot returns 0 candidates.

### 4.3 Test tools

| Tool | Purpose |
|---|---|
| `python -m unittest` | platform unit tests |
| `go test ./...` | RCA rules and scenario regression |
| `npm run verify` | Console type, fixture and CSS checks |
| `npm run build` | Console production build |
| `tools/demo-up.sh` | start/stop platform / RCA / vm-agent |
| `tools/acceptance.sh` | one-click four-scenario acceptance |
| `tools/reset-platform.sh` | reset the platform database |
| `tools/evidence-chain.sh` | evidence chain assembly |
| `workload/faults/*.sh` | OOM / CPU / tool fault injection |
| `workload/mock/gpu_exporter.py` | Mock DCGM memory injection |
| `vm-agent/deploy/measure-overhead.sh` | probe overhead sampling |

---

## 5. Unit and interface tests

### 5.1 platform (50 tests)

Command:

```bash
cd platform
python -m unittest discover -s tests -t . -v
```

Last run: 2026-10-27, `Ran 50 tests ... OK`.

| Test file | Cases | Coverage |
|---|---:|---|
| `test_api.py` | 6 | health / meta, resources and graph, agent registration, event → correlation → evidence → context, error codes, health open but API requires a token |
| `test_correlate.py` | 3 | Case1 application-layer and system-layer events in the same cluster, correlation idempotency, resource-window clustering without a correlation_id |
| `test_fixture_mapper.py` | 6 | fixture snapshot mode and counts, VM resources, edges, scenario coverage, tolerance for missing sets, retention of the alarm list |
| `test_ingest.py` | 5 | AppEvent identity and edges, dedup, cgroup resource preservation, ZSvirt alarm target resolution, batch summary |
| `test_mock_gpu.py` | 3 | off by default, resource and edge registration, enabling via environment variable |
| `test_rest_provider.py` | 5 | password sha512, pagination and OAuth headers, re-login on 401, error codes, partial collection failure |
| `test_store.py` | 6 | resource upsert merge, lookup by UUID, edges and subgraph, event dedup and query, evidence and clusters, agent update |
| `test_util_schema.py` | 12 | RFC3339 / offset / ZStack time / epoch milliseconds, sha512, AppEvent, Schema v1, loose events, alarm mapping, non-object rejection, severity mapping |
| `test_zsvirt_events.py` | 4 | only active alarms become events, all alarms retained, ZWatch event shape, synchronous ingestion and dedup |

Coverage conclusions:

- all three Schema v1 input formats (AppEvent / full event / loose event) have test cases;
- container short-ID prefix normalization, the VM→Container edge, and application-layer attribution priority are covered;
- correlation idempotency, evidence dedup, and cluster aggregation are covered;
- ZSvirt login with sha512, OAuth, 401 re-login, and pagination are covered;
- Mock GPU resources and the `Host→GPU→VM` edges are covered;
- the API token and the health exemption are covered.

### 5.2 rca (3 test functions + 4 sub-scenarios)

Command:

```bash
cd rca
go test ./...
```

| Test | Assertions |
|---|---|
| `TestFixtureScenariosTopDiagnosis` | executed for each of the four scenarios: Top-1 rule correct, score ≥ threshold, evidence IDs non-empty, all 5 scoring dimensions present, three-part remediation advice non-empty, impact scope non-empty, timeline non-empty, `fixture=mock`, timeline contains the expected layer |
| `TestNoEvidenceMeansNoDiagnosis` | an empty evidence snapshot returns 0 candidates |
| `TestRulesLoad` | 4 YAML rules load, required weights sum > 0, root cause and advice non-empty, includes `container_oom` / `cpu_contention` / `tool_failure` |

> This repository's records show `go test ./...` fully green (2026-09-21 and 2026-09-25 remediation records); the environment used to write this document had no Go installed, so it was not re-run. Confirm Go 1.22+ and the presence of `rca/fixtures/` before running.

### 5.3 console

Commands:

```bash
cd console
npm run verify     # typecheck + check:fixtures + check:css
npm run build      # tsc --noEmit && vite build
```

Last run: 2026-10-27, `npm run verify` passed. Checks:

| Check | Content | Latest result |
|---|---|---|
| `typecheck` | `tsc --noEmit`, strict mode, no `any` | passed |
| `check:fixtures` | four-scenario fixtures match the `API.md` contract and the evidence chains; both ends of every subgraph edge exist; impact is consistent with the incident; metric series are drawable; rule library has 4 rules with 5-dimension scoring | all PASS |
| `check:css` | CSS Module class-name reference integrity | passed |
| `build` | type check + Vite production build | passed per repository records; the build was not re-run this time |

---

## 6. Contract and data processing tests

| ID | Test item | Method | Expected | Result |
|---|---|---|---|---|
| C-01 | AppEvent ingestion | `test_ingest.py` | generates container / service / task identities and edges; application-layer events attach to the most specific entity first | passed |
| C-02 | Schema v1 full event | `test_util_schema.py` | fields retained per the whitelist; unknown fields go into `payload` | passed |
| C-03 | Loose vm-agent event | `test_util_schema.py` | any JSON containing `event_type` can be ingested; unknown fields go into `payload` | passed |
| C-04 | Dedup | `test_ingest.py` / `test_store.py` | the same `dedup_key` is ingested only once | passed |
| C-05 | Container short-ID normalization | `test_ingest.py` | the 12-character short-ID prefix is normalized to the 64-character container ID | passed |
| C-06 | VM→Container edge | `test_ingest.py` | `attributes.vm_uuid` generates `VM --contains--> Container` | passed |
| C-07 | Correlation cluster idempotency | `test_correlate.py` | correlating the same event set repeatedly produces no duplicate evidence | passed |
| C-08 | Clustering without correlation_id | `test_correlate.py` | clusters are formed by resource + time window | passed |
| C-09 | ZSvirt login | `test_rest_provider.py` | `sha512` password, OAuth headers, 401 re-login | passed |
| C-10 | ZSvirt alarm to event | `test_zsvirt_events.py` | only active alarms become events; dedup by uuid | passed |
| C-11 | Mock GPU | `test_mock_gpu.py` | `Host --contains--> GPU --assigned_to--> VM` | passed |
| C-12 | Frontend contract | `check-fixtures` | types and fields consistent; evidence chains consistent | passed |

---

## 7. End-to-end scenario acceptance

### 7.1 Acceptance flow

`tools/acceptance.sh` performs the following for each scenario:

1. `reset-platform.sh` clears the platform database to obtain a clean baseline;
2. restart vm-agent and confirm that direct reporting is ready;
3. inject the fault inside the business VM;
4. trigger one agent task via `faults/run-task.sh` and obtain a `correlation_id`;
5. restore the fault;
6. wait for events to be ingested, then query the counts from the platform health endpoint;
7. `POST /api/v1/correlate` to run correlation;
8. `tracesphere diagnose --correlation-id <corr> --window 10m` to output the diagnosis report;
9. `tracesphere capture` writes the real data back into `rca/fixtures/`.

### 7.2 Case summary

| ID | Scenario | Injection | Expected Top-1 | Measured Top-1 | Evidence Match | Data source |
|---|---|---|---|---|---:|---|
| E2E-01 | Container OOM | `docker update --memory=8m --memory-swap=8m tool-service` | Container OOM | Container OOM | **99/100** | platform=real, prometheus=real, fixture=off |
| E2E-02 | CPU contention | `cpu-stress` (2 workers, cpus=2) + `llama-server` cpus=0.5 | CPU resource contention | CPU resource contention | **85/100** | same as above |
| E2E-03 | Tool call failure | Toxiproxy shuts down the `tool` proxy | Agent tool call failure | Agent tool call failure | **67/100** | same as above |
| E2E-04 | GPU memory exhaustion | Mock DCGM `POST /inject {"mode":"exhaust"}` | GPU memory exhaustion | GPU memory exhaustion | **89/100** | platform=real, prometheus=real, Mock DCGM=mock |

Raw reports:

- [`docs/evidence/acceptance-2026-09-21/case1-oom.txt`](../evidence/acceptance-2026-09-21/case1-oom.txt)
- [`docs/evidence/acceptance-2026-09-21/case2-cpu.txt`](../evidence/acceptance-2026-09-21/case2-cpu.txt)
- [`docs/evidence/acceptance-2026-09-21/case3-tool-failure.txt`](../evidence/acceptance-2026-09-21/case3-tool-failure.txt)
- [`docs/evidence/acceptance-2026-09-21/case4-gpu-mock.txt`](../evidence/acceptance-2026-09-21/case4-gpu-mock.txt)

### 7.3 E2E-01 Container OOM

**Prerequisites**: platform / RCA / vm-agent / workload all ready; `tool-service` running normally.

**Steps**:

```bash
# 1) Tighten the memory limit of tool-service
sudo docker update --memory=8m --memory-swap=8m tool-service
# 2) Trigger a task
bash /opt/tracesphere/workload/faults/run-task.sh 'OOM drill task - expect tool call failure'
# 3) Recover
cd /opt/tracesphere/workload && sudo docker compose up -d --force-recreate tool-service
```

**Expected**: kernel OOM events, container restart, `task.failed`; Top-1 is `container_oom`.

**Measured (2026-09-30, correlation_id `bb03e1b2c022`)**:

- Time window: 2026-09-30T14:04:26Z ~ 14:14:26Z (600s);
- 34 evidence items;
- Top-1 `container_oom`, 99/100;
- Score breakdown: rule evidence match 55/55 (4 of 5 clauses: `memory.events.oom_kill`, `oom.ebpf`, `task.failed`, `container.restart`); temporal precedence 15/15 (`task.failed` 10.0s after the OOM); resource adjacency 9.4/10; signal strength 10/10; independent evidence 10/10 (four kinds: app_event / cgroup / ebpf / metric);
- Evidence cited by the Top-1 candidate (10 of the 34 items): `memory.events.oom_kill` (cgroup, value=7), 6 × `oom.ebpf`, 2 × `task.failed`, `container.restart` (metric, value=1).

**Conclusion**: passed. This scenario carries both kernel-level evidence at the container layer and application-layer failure evidence, making it the most complete evidence set of the four scenarios.

### 7.4 E2E-02 CPU contention

**Injection**:

```bash
bash /opt/tracesphere/workload/faults/cpu.sh
sudo docker update --cpus=0.5 llama-server
```

**Expected**: PSI `cpu.some` rises, `cpu.cfs.throttled_periods` increments, tasks time out; Top-1 is `cpu_contention`.

**Measured (2026-09-30, correlation_id `e40e7ba37a41`)**:

- Time window: 14:07:12Z ~ 14:17:12Z (600s);
- 28 evidence items;
- Top-1 `cpu_contention`, 85/100;
- Score breakdown: rule evidence match 45.3/55 (3 of 5 clauses: `psi_cpu_some_avg10`, `cpu.cfs.throttled_periods`, `task.failed`); temporal precedence 0/0 (the rule defines no `after`, so this dimension does not apply); resource adjacency 9.2/10; signal strength 8/10; independent evidence 10/10 (three kinds: app_event / cgroup / metric);
- Key evidence (5 items): PSI `cpu.some` peak 41.4%; `cpu.cfs.throttled_periods` at 1.21e3 for `llama-server` and 251 for `cpu-stress`; 2 × `task.failed`.

**Evidence boundary**: this run's evidence contains no `llama_latency_p95_ms`, so "inference latency P95 increased" cannot be written as measured evidence for this run; the rule keeps that clause, and when the evidence is missing the score breakdown shows it as missing.

**Conclusion**: passed.

### 7.5 E2E-03 Tool call failure

**Injection**:

```bash
bash /opt/tracesphere/workload/faults/tool-failure.sh down
```

**Expected**: `tool.result` errors, `task.failed`; Top-1 is `tool_failure`.

**Measured (2026-09-30, correlation_id `7fc1b31db642`)**:

- Time window: 14:07:44Z ~ 14:17:44Z (600s);
- 21 evidence items;
- Top-1 `tool_failure`, 67/100;
- Score breakdown: rule evidence match 32.4/55 (2 of 5 clauses: `tool.result`, `task.failed`); temporal precedence 15/15 (`task.failed` 0.0s after `tool.result`); resource adjacency 10/10; signal strength 8/10; independent evidence 2/10 (only the app_event kind);
- Evidence (4 items): 2 × `tool.result` and 2 × `task.failed`, all `app_event`.

**Evidence boundary**: this run has no transport-layer or kernel evidence (`tcp.retransmit` etc.), so this result cannot be stated as "the transport-layer anomaly has been proven". The transport-layer clause in the rule produced no evidence under the current collection conditions, which is why the score loses points on `rule_match` and `independent_evidence` — that is exactly where the 67 comes from.

**Conclusion**: passed (Top-1 correct), but evidence coverage is limited; collectable signals for connection failure / RST should be added later.

### 7.6 E2E-04 GPU memory exhaustion (Mock DCGM degradation)

**Prerequisites**: `mock_gpu` enabled on the platform, `Host --contains--> GPU --assigned_to--> VM` registered; the `mock-dcgm` container running.

**Injection**:

```bash
curl -s -X POST http://127.0.0.1:9400/inject \
  -H 'Content-Type: application/json' -d '{"mode":"exhaust"}'
```

**Expected**: memory utilization > 90%, `gpu.memory.exhausted` events; Top-1 is `gpu_memory_exhaustion`.

**Measured (2026-09-30, resource_id `gpu:mock-gpu0`)**:

- Time window: 14:08:23Z ~ 14:18:23Z (600s);
- 23 evidence items; the report notes that 61 system-layer raw events were added by resource topology + time window;
- Top-1 `gpu_memory_exhaustion`, 89/100;
- Score breakdown: rule evidence match 55/55 (2 of 3 clauses: `gpu.memory_used_ratio`, `gpu.memory.exhausted`); temporal precedence 0/0 (not applicable); resource adjacency 10/10; signal strength 9/10; independent evidence 2/10 (only the metric kind);
- Key evidence (3 items): `gpu.memory_used_ratio=0.995`, 2 × `gpu.memory.exhausted`.

**Evidence boundary**: the Mock DCGM metric names are `ts_gpu_*`; they are semantically compatible with the real DCGM exporter but are **not** the real DCGM metric naming. This run cannot be used to claim that "a real GPU has been validated".

**Conclusion**: passed (degraded mode). A real GPU environment requires replacing the data source and re-testing.

### 7.7 Score normalization

Evidence Match is a **rule-evidence hit score**, not a probability, and is not probability-calibrated. The total score is normalized over the "applicable dimensions":

```text
match_score = min(100, Σ dimension scores / Σ applicable dimension maxima × 100)
Σ applicable dimension maxima = 55 + (rule has after ? 15 : 0) + 10 + 10 + 10
```

Therefore:

| Scenario | Sum of dimension scores | Applicable maximum | Displayed score |
|---|---:|---:|---:|
| Case1 | 55 + 15 + 9.4 + 10 + 10 = 99.4 | 100 | 99 |
| Case2 | 45.3 + 0 + 9.2 + 8 + 10 = 72.5 | 85 | 85 |
| Case3 | 32.4 + 15 + 10 + 8 + 2 = 67.4 | 100 | 67 |
| Case4 | 55 + 0 + 10 + 9 + 2 = 76 | 85 | 89 |

The Case2 / Case4 rules have no `after` temporal constraint, so the temporal precedence dimension has `max=0` and does not participate in normalization; the sum of the sub-items therefore looks lower than the total score. This is designed behavior, not a calculation error.

---

## 8. Execution records

### 8.1 2026-09-20: three-case live drill

- Environment: ZSvirt business VM + vm-agent + Prometheus + sample workload;
- Result: Case1 OOM, Case2 CPU, and Case3 tool failure all completed injection → collection → correlation;
- Key observations: Case1 10 × OOM events, Case2 PSI 0.2 → 24.17, Case3 Toxiproxy latency 12s caused `tool.result error: timed out`;
- Records: `deploy/README.md` (internal material), `docs/evidence/case*-chain.md`.

### 8.2 2026-09-21: P0 integration and full acceptance

- Direct reporting went live; event-bridge was retired;
- Fixed missing container `vm_id`, container-name hash placeholders, missing evidence `value/delta`, and `/context` window.seconds=0;
- Conversion to systemd services;
- Full acceptance: Case1 91/100, Case2 79/100, Case3 74/100 (the batch at that time);
- Record: [`docs/fixlog-p0-2026-09-21.md`](../fixlog-p0-2026-09-21.md).

### 8.3 2026-09-21: closing competition-requirement gaps

- Added `docs/方案说明.md` and the MIT LICENSE;
- Added Mock DCGM, the GPU rule, and the Case4 scenario;
- Added the incident status API (silence / acknowledge / resolve / open);
- Four-scenario acceptance: Case1 90/100, Case2 85/100, Case3 74/100, Case4 89/100;
- platform 50 unit tests and `go test ./...` all green.

### 8.4 2026-09-25: security baseline remediation

- Unified tokens: platform `TRACESPHERE_API_TOKEN`, RCA `TRACESPHERE_RCA_TOKEN`;
- The platform refuses to start on a non-loopback address without a token;
- Rate limiting on platform / RCA write endpoints;
- The workload control plane binds to loopback by default;
- vm-agent identity mapping and spool retry;
- `ZSVIRT_SYNC_INTERVAL` periodic synchronization;
- Privacy minimization (question / answer bodies are not uploaded);
- Authentication matrix measured: platform health 200 / correlate without token 401 / with token 200; rca health 200 / incidents without token 401 / with token 200; VM writing to the platform without token 401;
- Four scenarios on the security-baseline build: Case1 99/100, Case2 85/100, Case3 67/100, Case4 89/100;
- Record: the audit remediation round in [`docs/fixlog-p0-2026-09-21.md`](../fixlog-p0-2026-09-21.md).

### 8.5 2026-09-30: latest four-scenario acceptance

- Data sources: `platform=real`, `prometheus=real`, `fixture=off`;
- Results: 99 / 85 / 67 / 89, all Top-1 correct;
- Reports: `../evidence/acceptance-2026-09-21/case{1,2,3,4}*.txt`;
- Replay data: `rca/fixtures/case{1,2,3,4}*.json`.

### 8.6 2026-10-27: re-runs during document authoring

| Check | Environment | Result |
|---|---|---|
| `python -m unittest discover -s tests -t . -v` | Windows + Python 3.14 | 50 tests passed |
| `npm run verify` | Windows + Node 24 | passed (typecheck + fixtures + css) |
| `go test ./...` | Go not installed | not re-run; repository records show passing |

> The platform unit tests emitted SQLite `ResourceWarning` output when run on Windows, but the test result was `OK`, which does not affect the conclusion; production runs Linux + Python 3.10+.

---

## 9. Security tests

### 9.1 Authentication matrix

| ID | Test | Request | Expected | Measured |
|---|---|---|---|---|
| S-01 | platform health exemption | `GET /api/v1/health` | 200 | 200 |
| S-02 | platform write endpoint without token | `POST /api/v1/correlate` without Authorization | 401 | 401 |
| S-03 | platform write endpoint with token | same as above + `Bearer <API_TOKEN>` | 200 | 200 |
| S-04 | rca health exemption | `GET /api/v1/health` | 200 | 200 |
| S-05 | rca read endpoint without token | `GET /api/v1/incidents` without Authorization | 401 | 401 |
| S-06 | rca read endpoint with token | same as above + `Bearer <RCA_TOKEN>` | 200 | 200 |
| S-07 | VM direct reporting without token | `POST /api/v1/events` without token | 401 | 401 |
| S-08 | startup on non-loopback without token | `--host 0.0.0.0` with no token configured | startup refused (exit code 3) | code path exists; confirmed by audit records |

### 9.2 Configuration checks

| ID | Item | Expected | Result |
|---|---|---|---|
| S-09 | platform token | must be configured for non-loopback binding | implemented |
| S-10 | RCA token | once configured, Bearer required for everything except health | implemented |
| S-11 | write endpoint rate limiting | 600 per IP per minute, configurable | implemented; re-testing per deployment environment is recommended |
| S-12 | workload control plane | loopback only by default | Compose defaults to `127.0.0.1` |
| S-13 | Prometheus cross-host access | explicit `PROM_BIND` | loopback by default; must be opened manually |
| S-14 | credentials | only in `/etc/tracesphere/*.env`, mode 600 | documentation and scripts agree |
| S-15 | field whitelist | unknown ingest fields are folded into `payload` | covered by unit tests |
| S-16 | privacy | question / answer / tool result bodies are not uploaded | code check: only `question_len` / `answer_len` / `result_len` |
| S-17 | ZSvirt read-only | the code does not call write APIs | code check; the actual account is `admin`, so read-only relies on code discipline rather than account permissions |
| S-18 | submission sanitization | residue scan `clean` | packaging record; newly added documents require re-running the scan |

### 9.3 Security boundary notes

- ZSvirt "read-only" is not guaranteed by a restricted account or RBAC; it is guaranteed by the platform calling only inventory GET and login endpoints. A dedicated account is still recommended at deployment time, but do not describe it as "least privilege validated".
- Console has no user system or role permissions, only a static token; multi-user scenarios require an outer reverse proxy / SSO.
- RCA CORS allows only the local dev server by default; same-origin production deployment does not rely on CORS.

---

## 10. Performance and overhead tests

### 10.1 vm-agent overhead

Method: `vm-agent/deploy/measure-overhead.sh` reads `/proc/<pid>/stat` and `/proc/<pid>/status` every 2 seconds; CPU% is calculated as a percentage of a single core.

| Scenario | Samples | Average CPU | Peak RSS |
|---|---:|---:|---:|
| idle (30s) | 15 | < 1% | 11 MB |
| load (cpu-stress + 3 inference tasks, 40s) | 20 | < 1% | 12 MB |

Design target: CPU < 2%, RSS < 100 MB. The measured values are significantly better than the target; the initial build with 3 × 16 MiB ringbufs had RSS ~103 MB, which dropped to 11 MB after switching to 1 MiB × 3.

### 10.2 Platform data scale

Platform-side counts at the end of Case3 ([`docs/evidence/rca-real-run.md`](../evidence/rca-real-run.md)):

```text
{'resources': 33, 'resource_edges': 32, 'events': 239, 'evidence': 239, 'clusters': 14, 'agents': 1}
```

This is the data scale during functional acceptance, not a capacity ceiling or a throughput conclusion. There are currently no large-scale stress tests, long-running soak tests, or concurrent-write test data.

### 10.3 Metrics not yet measured

- platform ingest throughput and P95/P99 latency;
- query latency over large windows (6h / 24h);
- multi-tenant / multi-VM concurrent reporting;
- RCA concurrent diagnosis latency;
- Console first-paint and large-topology rendering performance.

These metrics must not be given unverified numbers in external materials.

---

## 11. Degradation and reproducibility tests

| ID | Scenario | Method | Expected | Result |
|---|---|---|---|---|
| D-01 | No GPU | turn off `mock_gpu` and do not start mock-dcgm | the other three scenarios work normally; the GPU rule does not raise false positives when there is no evidence | passed |
| D-02 | Mock GPU | enable `mock_gpu` + `mock-dcgm` | Case4 Top-1 correct, source marked `mock` | passed (89/100) |
| D-03 | No eBPF | non-root or restricted memlock | prints a degradation notice; PSI/cgroup collection continues | verified ([`docs/evidence/vm-agent-overhead.md`](../evidence/vm-agent-overhead.md)) |
| D-04 | Partial eBPF hook failure | a single hook fails to attach | the remaining hooks continue; per-item degradation | implemented in code; re-testing on the target kernel is recommended |
| D-05 | Platform unavailable | stop the platform; RCA uses fixtures | returns fixture results, `platform=degraded/off`, `fixture=mock` | passed (after fix 2 in the fixlog) |
| D-06 | Explicit replay | `diagnose --scenario case1-oom` | produces Top-1 and evidence even without real data | passed |
| D-07 | Platform recovery | restart the platform | RCA's next request returns to `platform=real` and does not mix in fixtures | passed after the fix |
| D-08 | Clock skew | change the node time | when the correlation window becomes invalid, this should be visible in `sources.notes` | not systematically tested; use NTP at deployment |

---

## 12. UI tests

### 12.1 Page inventory

| Route | Page | Checks | Result |
|---|---|---|---|
| `/health` | Health overview | summary cards, time windows 15m/1h/6h, container/service filters, four sort orders, workload cards, timeline | passed |
| `/topology` | Resource topology | L1/L2/L3, focus dropdown, node drawer, incident badges, legend, recent events | passed |
| `/incidents` | Incident list | severity multi-select, rule filter, time windows 15m/1h/6h/24h, keyword, unresolved only, resource filter, table sorting | passed |
| `/incidents/:id` | Incident detail | evidence list ★, remediation advice, layered timeline, impact scope, alternative candidates, subgraph, metric curves, status operations | passed |
| `/diagnosis` | Root cause diagnosis | correlation_id / resource_id, time window, Top-N 1–5, sample input, five-dimension scoring, candidate switching, rule library | passed |

### 12.2 Data sources and error states

| ID | Check | Expected | Result |
|---|---|---|---|
| U-01 | Top bar badge | api shows `API LIVE`, fixture shows `FIXTURE REPLAY` | passed |
| U-02 | Footer source bar | shows real/degraded/mock/off for platform / prometheus / fixture | passed |
| U-03 | api mode failure | shows the error path, HTTP status, and handling guidance; no silent degradation | passed |
| U-04 | Empty diagnosis | explains "no anomaly in window / data source disabled / wrong anchor" | passed |
| U-05 | Incident without evidence | shows an empty state and does not fabricate evidence | passed |
| U-06 | Token | `?token=` is written to localStorage and subsequent requests carry Bearer | passed (code review) |

### 12.3 Not automated

The repository has no browser E2E tests (Playwright / Cypress); UI testing is manual. Responsive layout, accessibility, and cross-browser compatibility have not been systematically tested.

---

## 13. Defect records

All defects below have been fixed and verified; the records come from [`docs/fixlog-2026-09-21.md`](../fixlog-2026-09-21.md) and [`docs/fixlog-p0-2026-09-21.md`](../fixlog-p0-2026-09-21.md).

| ID | Symptom | Root cause | Fix | Verification | Status |
|---|---|---|---|---|---|
| DEF-01 | `/api/v1/health.last_sync` always had `finished_at=null`, and `sync_runs` never closed | `db.scalar("INSERT ...")` could not obtain `lastrowid`, so `sync_id=None` skipped the UPDATE | added `db.insert()` returning `lastrowid`; the guard changed to `sync_id > 0` | after restart `ok=1` with `finished_at/counts`; 47 unit tests passed | closed |
| DEF-02 | live diagnosis mixed in fixture replay data | the engine only checked `fixtures != nil`, not `Fixture.Enabled` | fixtures are merged only when explicitly enabled; added a degraded fallback for when the platform is unavailable; `views.go` fixed the fixture state | live diagnosis `fixture=off`; replay still `mock`; `go test ./...` fully green | closed |
| DEF-03 | container resources had no `vm_id` | ingest created containers lazily without persisting `vm_uuid` | `_ensure_container` reads `attributes.vm_uuid` and creates the `VM --contains--> Container` edge | 6/6 online containers have `vm_id` and the edge | closed |
| DEF-04 | container names were hash placeholders | the short-ID placeholder overwrote the real name | real names take precedence; fall back to the short ID only for newly created containers with no name | 6 containers display their real Docker names | closed |
| DEF-05 | evidence had no `value/delta` | correlate did not promote numeric payload values | `_evidence_for` promotes `value/delta/unit` to the evidence top level | value/delta visible on probe events | closed |
| DEF-06 | `/context` had `window.seconds=0` | the response was not populated | seconds are computed from from/to | response `window.seconds=960` | closed |
| DEF-07 | Case2 was misdiagnosed as OOM | after a journal polling restart the seen table was lost, replaying OOMs from 90s before startup | `journalOOMStart` time clamping: OOMs earlier than process start are only deduplicated, not reported | re-ran Case2 → CPU contention Top-1 | closed |
| DEF-08 | Case1 evidence weakened (missing `memory.current_ratio` / `container.restart`) | per-container cgroup sampling was lost after the bridge was retired | vm-agent added `containers.go`, sampling container cgroups every 15s | re-ran Case1 → 91/100 (that round) | closed |
| DEF-09 | security baseline missing: no token, no rate limiting, exposed control plane | found by audit | unified token, rate limiting, loopback binding, `PROM_BIND` / `TASK_TOKEN`, credential cleanup | authentication matrix measured; four scenarios passed | closed |
| DEF-10 | Case1 score was low (75) | eBPF events were not correlated to container identity | `identity.go`: PID → cgroup → container ID + `vm_uuid`, 60s cache | Case1 75 → 99 | closed |
| DEF-11 | scores drifted between rounds (Case2 97→85, Case3 93→67), and the regression thresholds were lowered accordingly | the reasons for remediation rounds and evidence changes were not recorded item by item | thresholds updated to the measured floor of the real fixtures | `go test ./...` passes | observation item; must be explained in the materials |

### 13.1 Defect trend notes

- The 2026-09-20 three-case drill exposed "missing container identity" and "missing evidence fields" classes of problems;
- The 2026-09-21 P0 integration fixed the direct-reporting path, the systemd conversion, and data completion;
- The 2026-09-25 audit remediation closed the security baseline and privacy minimization;
- The 2026-09-30 four-scenario re-test confirmed all Top-1 correct;
- Score drift is the risk point that most needs explaining during the defense: the score changes come from evidence added or removed and from identity mapping, not from model tuning.

---

## 14. Known limitations and uncovered scope

### 14.1 Evidence boundaries

| Item | Fact |
|---|---|
| Case3 transport-layer evidence | In the 2026-09-30 acceptance all evidence was `app_event`; there was no kernel evidence such as `tcp.retransmit`. It cannot be stated that "the transport-layer anomaly has been proven" |
| Case2 inference latency | That run had no `llama_latency_p95_ms` evidence; "inference latency increased" cannot be written as a measured conclusion |
| Case4 GPU | Uses Mock DCGM; metric names are `ts_gpu_*`, semantically compatible but not the real DCGM naming; no real GPU validation |
| eBPF hooks | what is implemented are tracepoints (exec/exit/OOM/retransmit); there are no kprobes |
| Resource graph | SQLite edge table + shallow BFS (correlation 1 hop, impact scope depth=2); not a graph database; no multi-hop propagation |
| Logs and tracing | no Fluent Bit / Loki log pipeline; no distributed tracing; the `trace_id` column exists but has no producer |
| Incidents | Alertmanager is not deployed; the current capability is in-house aggregation of "multiple events → correlation cluster → one incident" plus three-state operations (open / acknowledged / resolved + silenced) |
| ZSvirt read-only | guaranteed by the code not calling write APIs; the actual account is `admin`; no restricted-account validation |

### 14.2 Coverage gaps

- no real GPU / vGPU / DCGM exporter environment;
- no Kubernetes / multi-cluster / multi-tenancy;
- no production-grade HA, SQLite multi-writer, or RCA multi-instance;
- no long-running stability / memory-leak / soak testing;
- no large-scale event stress testing or query performance testing;
- no automated browser E2E, accessibility, or cross-browser testing;
- no automated upgrade / rollback testing;
- no drills for network partitions, disk-full, database corruption, etc.;
- no compatibility matrix across ZSvirt versions; validated only on v1.0.0.

### 14.3 Wording constraints for materials

- Evidence Match is an evidence-hit score, not a probability and not an accuracy rate;
- `health_score` is a display score and does not participate in RCA;
- the four-scenario results are results under controlled faults, not a general accuracy rate;
- design goals must not be written as measured results;
- Mock DCGM must not be written as real GPU validation;
- in-house incident aggregation must not be written as an Alertmanager capability.

---

## 15. Regression checklist

Run the following in order before release / submission:

```bash
# 1. Platform unit tests
cd platform && python -m unittest discover -s tests -t . -v

# 2. RCA rule and scenario regression
cd ../rca && go test ./...

# 3. Console contract and build
cd ../console && npm run verify && npm run build

# 4. fixture replay (no environment)
cd ../rca && ./bin/tracesphere diagnose --scenario case1-oom
./bin/tracesphere diagnose --scenario case2-cpu
./bin/tracesphere diagnose --scenario case3-tool-failure
./bin/tracesphere diagnose --scenario case4-gpu-mock

# 5. four-scenario live acceptance (requires environment variables)
cd .. && bash tools/acceptance.sh

# 6. security checks
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/api/v1/health
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://127.0.0.1:8000/api/v1/correlate
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8010/api/v1/incidents

# 7. submission sanitization
bash tools/sanitize-for-submission.sh /tmp/ts-submit
```

> `tools/sanitize-for-submission.sh` requires the local rules file `tools/sanitize-rules.local` (contains intranet identifiers, not distributed with the repository), or the rules file specified by `TS_SANITIZE_RULES`; if it is missing, the script fails with exit code 2. After the submission package is generated, documents and configuration still need manual spot-checking.

Pass criteria:

- the 50 platform unit tests are OK;
- the Go tests are fully green;
- `npm run verify` and `npm run build` succeed;
- the four scenarios' Top-1 is correct and their scores are not below the thresholds;
- the authentication matrix matches expectations;
- the sanitization scan outputs `clean`.

---

## 16. Reproduction guide

### 16.1 No cloud environment (fixture)

```bash
cd rca
go build -o bin/tracesphere ./cmd/tracesphere
./bin/tracesphere diagnose --scenario case1-oom
./bin/tracesphere alerts --fixture --scenario case1-oom
./bin/tracesphere topo --fixture --scenario case1-oom
```

### 16.2 Platform + replay

```bash
cd platform
python3 run.py --provider fixture --host 127.0.0.1 --port 8000

cd ../rca
./bin/tracesphere serve --fixture --scenario case1-oom \
  --listen :8010 --console ../console/dist
```

Open `http://127.0.0.1:8010/` in a browser. Note: in RCA's explicit fixture mode, `sources.fixture=mock`, so the page shows the replay badge.

### 16.3 Full live environment

Follow [Deployment guide](deployment-guide.md) §5–§8 to complete the ZSvirt, platform-side, and business VM deployment, then run `tools/acceptance.sh`.

### 16.4 Manual single-scenario reproduction

```bash
# Case1
sudo docker update --memory=8m --memory-swap=8m tool-service
bash /opt/tracesphere/workload/faults/run-task.sh 'OOM drill task'

# Case2
bash /opt/tracesphere/workload/faults/cpu.sh
sudo docker update --cpus=0.5 llama-server
bash /opt/tracesphere/workload/faults/run-task.sh 'CPU contention drill task'

# Case3
bash /opt/tracesphere/workload/faults/tool-failure.sh down
bash /opt/tracesphere/workload/faults/run-task.sh 'Tool failure drill task'

# Case4
curl -s -X POST http://127.0.0.1:9400/inject \
  -H 'Content-Type: application/json' -d '{"mode":"exhaust"}'
bash /opt/tracesphere/workload/faults/run-task.sh 'GPU memory exhaustion drill task'
```

---

## 17. Appendix

### 17.1 Evidence file index

| File | Content |
|---|---|
| [`docs/evidence/acceptance-2026-09-21/case1-oom.txt`](../evidence/acceptance-2026-09-21/case1-oom.txt) | full diagnosis report for the OOM scenario (99/100) |
| [`docs/evidence/acceptance-2026-09-21/case2-cpu.txt`](../evidence/acceptance-2026-09-21/case2-cpu.txt) | full diagnosis report for CPU contention (85/100) |
| [`docs/evidence/acceptance-2026-09-21/case3-tool-failure.txt`](../evidence/acceptance-2026-09-21/case3-tool-failure.txt) | full diagnosis report for the tool failure (67/100) |
| [`docs/evidence/acceptance-2026-09-21/case4-gpu-mock.txt`](../evidence/acceptance-2026-09-21/case4-gpu-mock.txt) | full diagnosis report for GPU memory exhaustion (89/100) |
| [`docs/evidence/case1-oom-chain.md`](../evidence/case1-oom-chain.md) | example OOM raw event → evidence chain |
| [`docs/evidence/case2-cpu-chain.md`](../evidence/case2-cpu-chain.md) | example CPU evidence chain |
| [`docs/evidence/case3-tool-failure-chain.md`](../evidence/case3-tool-failure-chain.md) | example tool failure evidence chain |
| [`docs/evidence/rca-real-run.md`](../evidence/rca-real-run.md) | real-environment acceptance from an earlier batch and platform scale |
| [`docs/evidence/vm-agent-overhead.md`](../evidence/vm-agent-overhead.md) | measured probe overhead |
| [`docs/fixlog-2026-09-21.md`](../fixlog-2026-09-21.md) | sync_runs and fixture-mixing fixes |
| [`docs/fixlog-p0-2026-09-21.md`](../fixlog-p0-2026-09-21.md) | P0 integration, gap closure, security remediation |

### 17.2 Glossary

| Term | Meaning |
|---|---|
| Evidence Match | rule-evidence hit score from 0 to 100, not a probability |
| correlation_id | application-layer correlation anchor for one agent task |
| resource_id | resource identifier in the form `<kind>:<key>` |
| incident | one correlation cluster + Top-1 diagnosis summary |
| fixture | replay data captured from a live drill |
| Mock DCGM | simulated memory metric source for environments without a GPU |
| degraded | data source availability is reduced; evidence is incomplete |
| spool | local retry queue on vm-agent when reporting fails |

### 17.3 Test document maintenance

- when adding rules / scenarios, update the thresholds in §2.3, the cases in §7, and the defect records in §13 at the same time;
- when adding data sources or changing scoring dimensions, update §5 and §7.7 at the same time;
- before each release, re-run the checklist in §15 and write the results into §8;
- any "measured" conclusion must point to a file under `docs/evidence/` or to a re-run record in this document.

---

*Document version: v1.0 (2026-10-27). Test conclusions follow the original evidence files.*
