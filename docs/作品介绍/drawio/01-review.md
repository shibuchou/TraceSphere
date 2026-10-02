# Architecture Review

- Nodes: 15
- Edges: 17
- Errors: 0
- Warnings: 15

## Findings

- **WARNING · no-cycles · console -> api -> rca -> console** — cyclic dependency detected
  - Suggested action: break the cycle or make the dependency asynchronous
- **WARNING · every-service-has-owner · registry** — Resource Registry
Host / VM / GPU / Container has no owner
  - Suggested action: set properties.owner
- **WARNING · every-service-has-owner · ingest** — Event Ingest
Schema v1 + 身份补全 has no owner
  - Suggested action: set properties.owner
- **WARNING · every-service-has-owner · correlate** — Correlation Engine
时间窗 + 资源图 + correlation_id has no owner
  - Suggested action: set properties.owner
- **WARNING · every-service-has-owner · evidence** — Evidence Store
SQLite WAL has no owner
  - Suggested action: set properties.owner
- **WARNING · every-service-has-owner · api** — Platform API
/api/v1 has no owner
  - Suggested action: set properties.owner
- **WARNING · every-service-has-owner · workload** — AI 工作负载
agent-service → tool-service
→ llama.cpp has no owner
  - Suggested action: set properties.owner
- **WARNING · every-service-has-owner · metrics** — Prometheus + cAdvisor
5s 指标抓取 has no owner
  - Suggested action: set properties.owner
- **WARNING · every-service-has-owner · gpu** — Mock DCGM / DCGM exporter
GPU 显存与耗尽事件 has no owner
  - Suggested action: set properties.owner
- **WARNING · every-service-has-owner · rca** — RCA Rule Engine
YAML 规则 + Evidence Match 五维评分 has no owner
  - Suggested action: set properties.owner
- **WARNING · single-point-of-failure · correlate** — Correlation Engine
时间窗 + 资源图 + correlation_id connects otherwise separated parts of the system
  - Suggested action: add redundancy or an alternate path
- **WARNING · single-point-of-failure · evidence** — Evidence Store
SQLite WAL connects otherwise separated parts of the system
  - Suggested action: add redundancy or an alternate path
- **WARNING · single-point-of-failure · ingest** — Event Ingest
Schema v1 + 身份补全 connects otherwise separated parts of the system
  - Suggested action: add redundancy or an alternate path
- **WARNING · single-point-of-failure · rca** — RCA Rule Engine
YAML 规则 + Evidence Match 五维评分 connects otherwise separated parts of the system
  - Suggested action: add redundancy or an alternate path
- **WARNING · single-point-of-failure · registry** — Resource Registry
Host / VM / GPU / Container connects otherwise separated parts of the system
  - Suggested action: add redundancy or an alternate path
