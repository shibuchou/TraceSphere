# TraceSphere 文档索引

> 本目录保存方案、部署、测试、使用说明、验收证据和演示材料。
> 标注“内部资料”的文件含部署环境细节，不随提交包分发。

## 面向评审与使用

| 文档 | 内容 | 适用读者 |
|---|---|---|
| [项目 README](../README.md) | 项目总览、快速开始、接口与权限声明、提交边界 | 全部 |
| [方案说明](方案说明.md) | 总体架构、部署边界、数据模型、采集、关联、告警、诊断、ZSvirt 集成 | 评审 / 研发 |
| [部署文档](部署文档.md) | 三种部署形态、ZSvirt 与业务 VM、平台/RCA/Console、配置参考、运维、排障 | 部署 / 运维 |
| [测试文档](测试文档.md) | 测试策略、用例、四场景验收、安全与性能、缺陷、已知限制、回归清单 | 评审 / 测试 |
| [用户手册](用户手册.md) | Console 四个页面、告警状态操作、诊断解读、CLI、FAQ | SRE / 研发 / 演示 |
| [作品介绍](作品介绍.md) | 项目定位、架构、场景、创新点、交付形态 | 评审 |
| [RCA 接口契约](../rca/docs/API.md) | 规则 YAML、证据模型、五维评分、诊断 HTTP API | 研发 |
| [平台接口说明](../platform/README.md) | `/api/v1` 平台接口、Schema v1、关联引擎 | 研发 |
| [探针说明](../vm-agent/README.md) | vm-agent 采集能力、构建、降级、开销 | 研发 |

## 验收证据

| 路径 | 内容 |
|---|---|
| [evidence/acceptance-2026-09-21/](evidence/acceptance-2026-09-21/) | 四场景真实数据源诊断报告（报告时间窗 2026-09-30） |
| [evidence/case1-oom-chain.md](evidence/case1-oom-chain.md) | OOM 原始事件 → 关联 → 证据链 |
| [evidence/case2-cpu-chain.md](evidence/case2-cpu-chain.md) | CPU 争抢证据链 |
| [evidence/case3-tool-failure-chain.md](evidence/case3-tool-failure-chain.md) | 工具失败证据链 |
| [evidence/rca-real-run.md](evidence/rca-real-run.md) | 真实环境验收记录与平台规模 |
| [evidence/vm-agent-overhead.md](evidence/vm-agent-overhead.md) | 探针开销实测 |

## 图表与视频

| 路径 | 内容 |
|---|---|
| [diagrams/](diagrams/) | 架构、关联流程、RCA 数据流、资源图（SVG / PNG / Draw.io） |
| [作品介绍/diagrams/](作品介绍/diagrams/) | 作品介绍用图（Mermaid 源） |
| [作品介绍/drawio/](作品介绍/drawio/) | 可编辑 Draw.io 源文件 |
| [作品介绍/pdf/](作品介绍/pdf/) | 作品介绍 PDF |
| [video/](video/) | 演示视频、旁白稿、字幕与视频流程 |

## 内部资料（不随提交包分发）

| 文件 | 内容 |
|---|---|
| `开工交接-B与C.md`、`开工交接-C.md` | 成员交接记录 |
| `交接文档-B-平台集成.md` | 平台侧交接 |
| `fixlog-2026-09-21.md`、`fixlog-p0-2026-09-21.md` | 修复记录 |
| `anonymization-sweep-2026-09-21.md` | 脱敏扫描记录 |
| `demo-演示流程与解说词.md` | 演示脚本与录屏流程 |
| `决赛答辩/` | 答辩材料构建目录 |
| `../deploy/README.md`、`../deploy/zs-*.sh`、`../deploy/mn-*.sh`、`../deploy/*.exp`、`../deploy/login-try.sh` | 实测环境运维脚本与记录 |

## 文档维护约定

1. 部署命令、配置项、端口变化时，更新 [部署文档](部署文档.md)；
2. 规则、阈值、评分维度变化时，更新 [测试文档](测试文档.md) 与 [方案说明](方案说明.md)；
3. 页面、筛选项、状态操作变化时，更新 [用户手册](用户手册.md)；
4. 任何“已实测”结论必须能指向 `evidence/` 中的文件；
5. 提交前执行 `tools/sanitize-for-submission.sh`，确认残留扫描为 `clean`；脚本需要 `tools/sanitize-rules.local` 或 `TS_SANITIZE_RULES` 指定的规则文件。
