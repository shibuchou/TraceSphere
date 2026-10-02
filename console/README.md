# TraceSphere Web Console

成员 C 的**前端主界面**（P0 交付物）。四个页面把 C 侧诊断服务的输出变成可读、可演示的运维控制台：
资源拓扑 → 健康总览 → 告警详情 → 根因诊断。

- 目标平台：**Linux + Node 22**（Windows 亦可，脚本全部跨平台）
- 技术栈（冻结）：React 18 + TypeScript + Vite 5 · Ant Design 5 · **AntV G6 v5**（拓扑 Combo 层级）·
  Apache ECharts 5（指标曲线）· react-router-dom 6
- 接口契约：`rca/docs/API.md`（W1 冻结 v1）——本目录所有类型定义与它逐字段对应
- 证据与规则来源：`docs/evidence/case{1,2,3}-*.md`、`rca/rules/*.yaml`

---

## 1. 快速开始

```bash
cd tracesphere/console

# 1) 安装依赖（工作区缓存，避免沙箱 / 代理环境下的 EPERM）
npm install --cache ../.npm-cache --registry https://registry.npmmirror.com
#    受限沙箱（无子进程权限）下追加 --ignore-scripts：本项目无需要构建期脚本的依赖
#    npm install --ignore-scripts --cache ../.npm-cache --registry https://registry.npmmirror.com

# 2) 类型检查（零错误是验收项）
npm run typecheck        # 等价于 npx tsc --noEmit

# 3) 生产构建（产出 dist/）
npm run build            # = tsc --noEmit && vite build

# 4) 本地预览构建产物
npm run preview          # http://127.0.0.1:4173

# 5) 开发调试
npm run dev              # http://127.0.0.1:5173

# 6) 附加自检（不依赖构建工具链，可在受限环境下运行）
npm run check:fixtures   # 夹具与 API.md 契约 / 证据链的一致性
npm run check:css        # CSS Module 类名引用完整性（tsc 不报的一类错误）
npm run verify           # typecheck + check:fixtures + check:css
```

> 仓库根目录已提供 `.npmrc`（`registry`/`cache` 指向工作区缓存），因此 `npm install` 也可直接跑通。
>
> **构建环境要求**：Vite 需要把配置文件交给 esbuild 转译，这一步会拉起 esbuild 子进程
> （`stdio: pipe`）。在禁止子进程 / 命名管道的受限沙箱里会以 `Error: spawn EPERM` 失败——
> 这是环境限制而非配置问题，请在具备子进程权限的普通 shell 中执行 `npm run build` / `npm run dev`
> （Linux + Node 22 的目标环境即为普通 shell）。若受限环境仍要安装依赖，
> 可加 `--ignore-scripts`（本项目依赖均无必要的构建期脚本）。

---

## 2. 两种数据源模式（P0 降级 / 回放，方案 §2.1）

数据源模式由**构建期环境变量** `VITE_DATA_SOURCE` 决定，运行时只读——这是刻意设计：
评审必须能从页脚 / 顶栏角标一眼确认当前展示的是**真实数据**还是**回放数据**。

| 模式 | 值 | 行为 |
|---|---|---|
| 真实服务 | `api`（默认） | 按 API.md §4 请求 `VITE_RCA_BASE_URL`（留空则用相对路径 `/api/v1`，走 dev server / nginx 反向代理） |
| 本地回放 | `fixture` | 读取 `src/mocks/*.json`，**响应结构与 API 完全一致**，无需后端即可完整演示 |

### fixture 模式（推荐用于录屏 / 无后端环境）

```bash
# Linux / macOS
VITE_DATA_SOURCE=fixture npm run dev

# Windows PowerShell
$env:VITE_DATA_SOURCE="fixture"; npm run dev

# 或写入 .env.local
cp .env.example .env.local && echo "VITE_DATA_SOURCE=fixture" >> .env.local
```

### api 模式（联调 rca-serve）

```bash
# 终端 1：启动诊断服务
rca-serve --listen :8010

# 终端 2：
VITE_DATA_SOURCE=api npm run dev          # 默认经 vite proxy 转发 /api → 127.0.0.1:8010
# 或直连：
VITE_DATA_SOURCE=api VITE_RCA_BASE_URL=http://127.0.0.1:8010 npm run dev
```

**重要**：`api` 模式下请求失败**不会静默降级**到夹具。页面会渲染错误态，给出
「请求路径 + HTTP 状态 + 处理指引 + 一键跳到夹具场景」——保证演示时不会把回放数据误当真实数据。

### 当前数据源标识

- 顶栏右侧角标：`API LIVE` / `FIXTURE REPLAY`（悬停显示请求基址与切换命令）
- 页脚：来源状态条（`platform: 真实 / prometheus: 真实 / fixture: 回放`）+ 最近取数时间 + API 基址

---

## 3. 四个页面（方案 §6.5）

| 路由 | 页面 | 数据接口 | 要点 |
|---|---|---|---|
| `/topology` | 资源拓扑 | `GET /api/v1/topology` | G6 v5 渲染 combos + nodes + edges；层级 `Host Combo → VM Combo → 容器/服务/任务`；按 `status` 着色 + 图例；点击节点弹 Drawer（详情 + 相关事件 + 邻接资源）；`incident_count > 0` 显示角标；深度切换 L1/L2/L3；「聚焦某资源」下拉 + 缩放/适应画布 |
| `/health` | 健康总览 | `GET /api/v1/overview?window_seconds=` | 顶部汇总指标卡（资源总数/健康/警告/严重、任务总数/失败、告警数）；中部工作负载健康卡片（health_score、状态、信号、关键指标含阈值进度条、任务失败数）；底部全局事件时间线按层着色；时间窗 15m/1h/6h |
| `/incidents` | 告警列表 | `GET /api/v1/incidents` | AntD Table：严重度、规则/标题、重点资源、Evidence Match、影响任务数、首次/最近、状态；按严重度（多选）/规则/时间窗过滤 + 关键字搜索 |
| `/incidents/:id` | 告警详情 | `GET /api/v1/incidents/{id}` | 事件摘要 → **证据列表**（evidence_id / signal / kind+layer / 资源 / 时间 / 描述，展开看原始 payload）→ 按层分组时间线 → 影响范围（受影响 AgentTask 清单）→ 相关资源子图（复用 G6 组件）→ 指标曲线 |
| `/diagnosis` | 根因诊断 | `POST /api/v1/diagnose` | 输入 `correlation_id` 或 `resource_id` + 时间窗 + Top-N；展示根因候选 Top-N（标题、**`Evidence Match: 92/100`** 醒目且标注「证据命中评分，非概率」、五维度 `score_breakdown` 进度条 + detail、引用证据 ID、处置建议三段式 依据/操作/风险、备选候选）；**规则库**区域展示三条规则 YAML 结构与权重分布 |

`/` 默认重定向到 `/health`。

### 演示路径（录屏用）

顶栏「演示路径」提供 **Case1 OOM → Case2 CPU → Case3 工具失败 → Case4 GPU 显存耗尽** 一键切换，切换后：

- 拓扑页自动聚焦该场景的焦点资源；
- 诊断页自动把 `correlation_id` 填入并执行；
- 告警页高亮对应告警（标记「当前场景」）。

四个场景的关联锚点（Case4 使用模拟 DCGM 信号）：

| 场景 | correlation_id | 焦点资源 | 规则 |
|---|---|---|---|
| Case1 容器 OOM | `d38fc66c8364` | `container:7196bcad3bc1`（tool-service） | `container_oom` |
| Case2 CPU 争抢 | `cf6d4dfcd64a` | `container:e5d6f856a747`（cpu-stress） | `cpu_contention` |
| Case3 工具失败 | `8da4d26c78f6` | `container:e6eab2f12b53`（toxiproxy） | `tool_failure` |
| Case4 GPU 显存耗尽 | `85bcc7f9b016` | `gpu:mock-gpu0`（Mock GPU 0） | `gpu_memory_exhaustion` |

---

## 4. 目录结构

```text
console/
├─ index.html                  # 入口 + 首屏骨架（避免 JS 加载期白屏）
├─ vite.config.mjs             # Vite 配置（刻意用 .mjs：免去配置文件的 esbuild 转译）
├─ tsconfig.json               # strict + noUnusedLocals + @/* 路径别名
├─ .env.example                # 两种模式的环境变量说明
└─ src/
   ├─ types.ts                 # ★ 与 API.md 逐字段对应的类型定义（无 any）
   ├─ main.tsx / App.tsx       # 入口、ConfigProvider 主题、路由表
   ├─ data/
   │   ├─ client.ts            # ★ 数据访问层：api / fixture 双模式，零调用方分支
   │   ├─ fixtures.ts          # 夹具适配层：把 mocks/*.json 包装成 API 结构 + 时间平移
   │   ├─ scenarios.ts         # 三个演示场景定义（真实 correlation/resource/id）
   │   └─ errors.ts            # ApiError：带 path / mode / status / hint
   ├─ mocks/                   # ★ 夹具，数值取自 docs/evidence/*.md 真实证据链
   │   ├─ topology.json  overview.json  incidents.json
   │   ├─ incident-oom.json  incident-cpu.json  incident-tool-failure.json
   │   ├─ metrics-series-oom.json  metrics-series-cpu.json
   │   └─ meta.json            # 规则清单（含三条规则的结构化 YAML 关键字段）
   ├─ state/AppContext.tsx     # 数据源 / 场景 / 全局刷新信号
   ├─ hooks/useAsync.ts        # 统一请求 hook：取消、重试、轮询、错误归一
   ├─ theme/tokens.ts          # 设计令牌唯一出处（CSS 变量镜像同一套值）
   ├─ styles/global.css        # 设计基座（浅色 + 单一工程蓝主色）
   ├─ components/
   │   ├─ layout/AppShell.tsx          # 顶栏导航 + 演示路径控制条 + 页脚数据源
   │   ├─ common/                      # Panel / PageHead / Tags / States / Icon / 数据源角标
   │   ├─ topology/TopologyGraph.tsx   # ★ G6 v5 图组件（Combo 层级 + 确定性泳道布局）
   │   ├─ topology/NodeDrawer.tsx      # 节点详情侧栏
   │   ├─ evidence/EvidenceList.tsx    # 证据列表（可展开原始 payload）
   │   ├─ timeline/LayerTimeline.tsx   # 分层时间线（因果刻度尺）
   │   ├─ diagnosis/ScoreBreakdown.tsx # ★ Evidence Match 五维度明细 + 候选排序
   │   ├─ metrics/MetricCharts.tsx     # ECharts 曲线（含阈值线）
   │   └─ rules/RuleLibrary.tsx        # 规则库 hook
   └─ pages/                   # Topology / Health / Incidents / IncidentDetail / Diagnosis
```

---

## 5. 设计说明（为什么长这样）

**方向：GRID LEDGER（刻度账本）** —— 面向 SRE 的高密度工程控制台，不是营销页面。

- **浅色 + 单一主色**：底色 `#F6F7F9`，主色工程蓝 `#2B5B8F`。状态色**只**用于表达
  `healthy / warning / critical / unknown`（绿 `#2E8B57` / 橙 `#D97B10` / 红 `#C0392B` / 灰 `#7C8794`），
  在 G6 节点填充、状态标签、指标条之间保持同一套语义。
- **签名元素：因果刻度尺**。时间线左侧的时间列 / 层级列 / 刻度轨构成一把竖向刻度尺，
  层级色（应用蓝、容器青、虚拟机紫、云平台褐）沿刻度排列，
  「系统层信号在前、应用层表现在后」这件事被结构直接表达出来，而不是靠文字说明。
- **结构即信息**：页面用编号 `01–04` 导航；面板标题前的 3px 主色竖条是唯一的装饰；
  圆角统一 2px，分隔线统一 1px 发丝线；图标为 16px 网格 1.5px 描边的自绘几何图标集。
- **数据字排版**：所有 ID / 时间戳 / 指标值 / 分数使用等宽字体（`tabular-nums`），
  与正文（系统无衬线）形成两层，扫读时能立刻区分「标识」与「叙述」。
- **克制**：无渐变、无大圆角、无阴影浮层（仅 Drawer 有一层投影）。

---

## 6. 已知限制

- **本仓库的构建尚未在本机验证通过**：当前受限沙箱禁止子进程 / 命名管道，Vite 加载配置时的
  `spawn EPERM` 属环境限制。`npx tsc --noEmit` 已零错误、`npm run check:fixtures` 与
  `npm run check:css` 全部通过；请在普通 shell 中执行一次 `npm run build` 与 `npm run dev` 确认。
- `VITE_DATA_SOURCE` 是构建期变量：切换模式需要重启 dev server / 重新构建。
  运行时不提供热切换，以避免「以为是真实数据、实际是回放」的演示事故。
- 夹具中的事件时间在加载时会整体平移到「最近 N 分钟」，使 `15m / 1h / 6h` 时间窗与录屏始终有效
  （原始采集时间保留在证据 payload 的 `raw` / `note` 字段里）。
- 6h 时间窗在夹具模式下仍只覆盖夹具内的 15 分钟数据，页面会如实显示空部分。
- 拓扑的 L3（进程层）仅在采集到 `kind: process` 节点时有内容；夹具未包含进程节点。
- 指标曲线的 `resource_id` 仅容器类资源有夹具（`tool-service` / `cpu-stress`），其余资源会显示明确的空状态。
- `incidents.json` 中 `inc_source = rule_scan` 的两条历史告警在夹具里没有配套的详情证据，
  详情页会显示「证据为空」的空状态（这本身也是需要被演示到的降级路径）。
