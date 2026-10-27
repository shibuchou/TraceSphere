# TraceSphere Documentation (English)

[中文](../README.md) | English

This directory contains the English documentation set for GitHub readers. It mirrors the Chinese docs and keeps the same evidence boundaries. The Chinese originals remain the submission reference.

## Core documents

| Document | Contents |
|---|---|
| [Project README](../../README.en.md) | Overview, quick start, data contract, ZSvirt integration, security, submission boundary |
| [Solution overview](solution-overview.md) | Architecture, deployment boundaries, data model, collection, correlation, alerting, diagnosis, ZSvirt integration |
| [Deployment guide](deployment-guide.md) | Three deployment modes, ZSvirt / business VM / platform-side setup, configuration reference, operations, troubleshooting |
| [Testing guide](testing-guide.md) | Test strategy, unit/contract/E2E tests, four-scenario acceptance, security, performance, defects, limitations, regression checklist |
| [User guide](user-guide.md) | Console pages, incident operations, diagnosis interpretation, CLI, FAQ, glossary |
| [Project introduction](project-introduction.md) | Positioning, architecture, scenarios, innovation, delivery forms, boundaries |

## Chinese originals

| Document | Contents |
|---|---|
| [README (Chinese)](../../README.md) | Chinese project README and submission boundary |
| [方案说明](../方案说明.md) | Chinese solution overview |
| [部署文档](../部署文档.md) | Chinese deployment guide |
| [测试文档](../测试文档.md) | Chinese testing guide |
| [用户手册](../用户手册.md) | Chinese user guide |
| [作品介绍](../作品介绍.md) | Chinese project introduction |

## Acceptance evidence

| Path | Contents |
|---|---|
| [evidence/acceptance-2026-09-21/](../evidence/acceptance-2026-09-21/) | Four-scenario reports from a real data source (report window 2026-09-30) |
| [evidence/case1-oom-chain.md](../evidence/case1-oom-chain.md) | OOM raw events → correlation → evidence chain |
| [evidence/case2-cpu-chain.md](../evidence/case2-cpu-chain.md) | CPU contention evidence chain |
| [evidence/case3-tool-failure-chain.md](../evidence/case3-tool-failure-chain.md) | Tool failure evidence chain |
| [evidence/rca-real-run.md](../evidence/rca-real-run.md) | Real-environment acceptance and platform scale |
| [evidence/vm-agent-overhead.md](../evidence/vm-agent-overhead.md) | Probe overhead measurement |

## Diagrams and video

| Path | Contents |
|---|---|
| [diagrams/](../diagrams/) | Architecture, correlation flow, RCA data flow, resource graph (SVG / PNG / Draw.io) |
| [作品介绍/diagrams/](../作品介绍/diagrams/) | Diagrams used by the project introduction (Mermaid sources) |
| [作品介绍/drawio/](../作品介绍/drawio/) | Editable Draw.io sources |
| [video/](../video/) | Demo video, narration, subtitles, and production notes |

## Internal material

The following are kept locally and are not part of the public submission package:

- `docs/开工交接-*.md`, `docs/交接文档-*.md`
- `docs/fixlog-*.md`, `docs/anonymization-sweep-*.md`, `docs/demo-*.md`
- `docs/决赛答辩/`
- `deploy/README.md`, `deploy/zs-*.sh`, `deploy/mn-*.sh`, `deploy/*.exp`, `deploy/login-try.sh`

## Maintenance rules

1. When a deployment command, configuration key, or port changes, update [deployment-guide.md](deployment-guide.md) and the Chinese original.
2. When a rule, threshold, or score dimension changes, update [testing-guide.md](testing-guide.md), [solution-overview.md](solution-overview.md), and the Chinese originals.
3. When a Console page, filter, or incident action changes, update [user-guide.md](user-guide.md).
4. Any "measured" claim must point to a file under `docs/evidence/`.
5. Keep English and Chinese docs aligned. If they diverge, the evidence files and the Chinese submission set take precedence.
