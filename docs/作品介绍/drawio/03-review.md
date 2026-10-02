# Architecture Review

- Nodes: 11
- Edges: 12
- Errors: 0
- Warnings: 9

## Findings

- **WARNING · no-cycles · operator -> rca -> operator** — cyclic dependency detected
  - Suggested action: break the cycle or make the dependency asynchronous
- **WARNING · every-service-has-owner · platform** — Platform :8000
非回环必须配置 API Token has no owner
  - Suggested action: set properties.owner
- **WARNING · every-service-has-owner · rca** — RCA + Console :8010
RCA Token + CORS 白名单 has no owner
  - Suggested action: set properties.owner
- **WARNING · every-service-has-owner · sqlite** — SQLite WAL
resources / events / evidence / clusters has no owner
  - Suggested action: set properties.owner
- **WARNING · every-service-has-owner · app** — agent-service / tool-service
PLATFORM_TOKEN / TASK_TOKEN has no owner
  - Suggested action: set properties.owner
- **WARNING · every-service-has-owner · observability** — Prometheus / cAdvisor
默认回环，PROM_BIND 可覆盖 has no owner
  - Suggested action: set properties.owner
- **WARNING · every-service-has-owner · mockgpu** — Mock DCGM
默认回环 / GPU 降级 has no owner
  - Suggested action: set properties.owner
- **WARNING · single-point-of-failure · platform** — Platform :8000
非回环必须配置 API Token connects otherwise separated parts of the system
  - Suggested action: add redundancy or an alternate path
- **WARNING · single-point-of-failure · rca** — RCA + Console :8010
RCA Token + CORS 白名单 connects otherwise separated parts of the system
  - Suggested action: add redundancy or an alternate path
- **INFO · high-coupling · platform** — Platform :8000
非回环必须配置 API Token has 7 connections
  - Suggested action: verify the component is intentionally a hub
