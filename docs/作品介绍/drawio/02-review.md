# Architecture Review

- Nodes: 13
- Edges: 13
- Errors: 0
- Warnings: 10

## Findings

- **WARNING · no-cycles · correlate -> evidence -> rules -> score -> result -> operate -> correlate** — cyclic dependency detected
  - Suggested action: break the cycle or make the dependency asynchronous
- **WARNING · every-service-has-owner · normalize** — Schema v1 归一化
字段白名单 + Token + 隐私最小化 has no owner
  - Suggested action: set properties.owner
- **WARNING · every-service-has-owner · identity** — 身份映射
PID → cgroup → container → VM
GPU assigned_to VM has no owner
  - Suggested action: set properties.owner
- **WARNING · every-service-has-owner · correlate** — 关联簇
correlation_id + 时间窗 + 资源图 has no owner
  - Suggested action: set properties.owner
- **WARNING · every-service-has-owner · evidence** — 证据快照
来源 / 时间 / 数值 / source_event_ids has no owner
  - Suggested action: set properties.owner
- **WARNING · every-service-has-owner · rules** — 规则匹配
YAML 条款 + 必选 / 可选 / 时序 has no owner
  - Suggested action: set properties.owner
- **WARNING · every-service-has-owner · score** — Evidence Match
规则命中 55
时序 15 / 邻接 10 / 强度 10 / 独立性 10 has no owner
  - Suggested action: set properties.owner
- **WARNING · single-point-of-failure · correlate** — 关联簇
correlation_id + 时间窗 + 资源图 connects otherwise separated parts of the system
  - Suggested action: add redundancy or an alternate path
- **WARNING · single-point-of-failure · identity** — 身份映射
PID → cgroup → container → VM
GPU assigned_to VM connects otherwise separated parts of the system
  - Suggested action: add redundancy or an alternate path
- **WARNING · single-point-of-failure · normalize** — Schema v1 归一化
字段白名单 + Token + 隐私最小化 connects otherwise separated parts of the system
  - Suggested action: add redundancy or an alternate path
- **INFO · high-coupling · normalize** — Schema v1 归一化
字段白名单 + Token + 隐私最小化 has 6 connections
  - Suggested action: verify the component is intentionally a hub
