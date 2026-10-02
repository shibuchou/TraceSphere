# TraceSphere 演示录屏操作手册（逐步照做版）

> 用法：从上往下照做即可完成 3–5 分钟演示视频。**每一步都标了在哪个窗口/机器操作**：
> - 【本地】= 你的 Windows（PowerShell 窗口 / 浏览器）
> - 【GPU1】= SSH 连 GPU1 后的终端（所有脚本都在 `~/tracesphere`）
> - 【GPU1→VM】= 在 GPU1 终端里执行，但命令会通过 sshpass 进入业务 VM
> - 🎙 = 这一步要读出来的话（照读即可）
>
> 成片目标 **4 分 30 秒 ± 30 秒**。本文件含真实凭据，属内部资料（提交打包已排除 `docs/demo-*.md`）。

---

# 一、窗口与素材总览（先看一眼）

| 窗口 | 用途 |
|---|---|
| 本地：SSH 隧道 PowerShell（保持不关） | 把 GPU1 的 8010/8000 映射到本机 |
| 本地：浏览器（3 个标签） | 拓扑 / 诊断 / 告警 |
| GPU1 终端 | 注入脚本、CLI 诊断、状态检查 |
| （可选）GPU1 第二个终端 | 跑验收或查看日志 |

浏览器三个标签（复制整行，已带 RCA Token）：
1. `http://127.0.0.1:8010/?token=0232425c9556e6a3cda1bf307762d0f7#/topology`
2. `http://127.0.0.1:8010/?token=0232425c9556e6a3cda1bf307762d0f7#/diagnosis`
3. `http://127.0.0.1:8010/?token=0232425c9556e6a3cda1bf307762d0f7#/incidents`

---

# 二、录制前 10 分钟（全部不入镜）

## 2.1【GPU1】导出环境变量（新终端里先跑）

```bash
export ZSVIRT_PASSWORD='zsvirt.123'
export TRACESPHERE_VM_UUID='63bbb4613a524e4e97090600af03da93'
export TRACESPHERE_VM_HOST='10.100.0.181'
export VM_PASSWORD='zsvirt.123'
export TRACESPHERE_PLATFORM_URL='http://192.168.122.1:8000'
export TRACESPHERE_PROMETHEUS_URL='http://10.100.0.181:9090'
export TRACESPHERE_API_TOKEN='2e987275b7d8b64ef4656c684f2bdecc'
export TRACESPHERE_PLATFORM_TOKEN="$TRACESPHERE_API_TOKEN"   # CLI 诊断读该变量
export TRACESPHERE_RCA_TOKEN='0232425c9556e6a3cda1bf307762d0f7'
```

> 注意：这行要**录制前**跑掉（含口令），别在镜头里输入。建议直接追加到 `~/.bashrc` 里一劳永逸。

## 2.2【GPU1】检查并启动三件套

```bash
bash ~/tracesphere/tools/demo-up.sh --status
```
期望输出三行：
```
platform : active
rca      : active
vm-agent : active
```
**任一行不是 active 就启动**：
```bash
sudo systemctl start tracesphere-platform tracesphere-rca
sshpass -p "$VM_PASSWORD" ssh ubuntu@$TRACESPHERE_VM_HOST 'sudo systemctl restart tracesphere-vm-agent'
```

## 2.3【GPU1→VM】检查负载容器与工具代理

```bash
sshpass -p "$VM_PASSWORD" ssh ubuntu@$TRACESPHERE_VM_HOST 'sudo docker ps --format "{{.Names}}\t{{.Status}}" | sort'
```
期望 7 个容器：`agent-service / cadvisor / llama-server / mock-dcgm / prometheus / tool-service / toxiproxy`。

**工具代理检查（重建容器后常丢，必须确认）**：
```bash
sshpass -p "$VM_PASSWORD" ssh ubuntu@$TRACESPHERE_VM_HOST 'curl -s http://127.0.0.1:8474/proxies'
# 若输出里没有 tool 代理，执行：
sshpass -p "$VM_PASSWORD" ssh ubuntu@$TRACESPHERE_VM_HOST 'cd /opt/tracesphere/workload && sudo bash toxiproxy-init.sh'
```

## 2.4【GPU1→VM】把模拟 GPU 重置为正常态

```bash
sshpass -p "$VM_PASSWORD" ssh ubuntu@$TRACESPHERE_VM_HOST 'curl -s -X POST http://127.0.0.1:9400/inject -H "Content-Type: application/json" -d "{\"mode\":\"normal\"}"'
```

## 2.5【GPU1】清平台基线（推荐，让视频里事件从零开始）

```bash
bash ~/tracesphere/tools/reset-platform.sh
sleep 15    # 等探针/指标重新上报一圈
```

## 2.6【本地】开 SSH 隧道（保持窗口不关）

```powershell
ssh -N -L 8010:127.0.0.1:8010 -L 8000:127.0.0.1:8000 GPU1
```
验证（浏览器先访问一次，能看到 JSON 即可）：
```
http://127.0.0.1:8010/api/v1/health
```
> 备选：用 VS Code Remote-SSH 连 GPU1，Ports 面板会自动转发 8010，无需手敲隧道。

## 2.7【本地】打开浏览器三个标签（见 §一），并摆好窗口

建议布局：左半屏浏览器、右半屏 GPU1 终端；浏览器先停在 **标签 1（拓扑）**。

## 2.8【GPU1】终端整理

字号 ≥16pt、`clear` 清屏；确认 `demo-up --status` 的输出图（三行 active）就是镜头第一个终端画面。

## 2.9 预演（强烈建议）

把 §三 的 B 段命令**空跑一遍**（会真的注入一次 OOM，但脚本结束后自动恢复；就是一次彩排）。

---

# 三、正式录制：逐步分镜（4:30）

> 每一步格式：**在哪 → 做什么（命令）→ 屏幕预期 → 🎙 说什么**。
> 时间轴：A1 0:00–0:15｜A2 0:15–0:35｜A3 0:35–0:50｜B1 0:50–1:10｜B2 1:10–1:30｜B3 1:30–1:55｜B4 1:55–2:25｜C1 2:25–2:55｜C2 2:55–3:20｜C3 3:20–3:45｜D1 3:45–4:10｜D2 4:10–4:30。

### A1（0:00–0:15）健康总览
- **在哪**：【本地】浏览器切到标签 1 之外先看 health？——不，先切到 **`#/health`**（在标签 1 地址栏把 `#/topology` 改成 `#/health` 回车）。
- **操作**：鼠标沿指标卡片缓慢滑过。
- **预期**：VM/容器指标卡片、事件计数在跳动。
- 🎙：“这是 TraceSphere——面向 ZSvirt 虚拟机内智能体工作负载的全栈可观测与根因诊断平台。当前是健康总览：宿主机、虚拟机、容器与 GPU 的指标和事件在持续汇入。”

### A2（0:15–0:35）资源拓扑（跨层关联）
- **在哪**：【本地】浏览器切到 **标签 1（`#/topology`）**。
- **操作**：拖动/缩放拓扑图；依次 hover **GPU 节点**、**workload-vm**、**agent-service 容器**；点击 GPU 节点看右侧/详情。
- **预期**：`Host → GPU → VM → Container` 的 contains/assigned_to 边、真实容器名。
- 🎙：“资源图覆盖五层对象：宿主机、GPU、虚拟机、容器、以及 Agent 服务与任务。GPU 节点通过 assigned_to 关联到业务 VM——无 GPU 硬件时由 Mock DCGM 提供同样的模型与指标，替换为真实 DCGM 后规则不变。”

### A3（0:35–0:50）常驻服务
- **在哪**：【GPU1】终端。
- **操作**：执行（若 §2.2 已跑过，这里重跑一次给镜头看）：
  ```bash
  bash ~/tracesphere/tools/demo-up.sh --status
  ```
- **预期**：三行 active。
- 🎙：“平台、诊断与控制台、以及 VM 内探针都以 systemd 常驻：探针用 eBPF、PSI 和 cgroup 采集，直接上报平台，不依赖任何桥接进程。”

### B1（0:50–1:10）故障注入：容器 OOM
- **在哪**：【GPU1】终端，逐条执行：
  ```bash
  cd ~/tracesphere
  sshpass -p "$VM_PASSWORD" scp tools/case1-oom-real.sh ubuntu@$TRACESPHERE_VM_HOST:/tmp/
  sshpass -p "$VM_PASSWORD" ssh ubuntu@$TRACESPHERE_VM_HOST 'sudo bash /tmp/case1-oom-real.sh'
  ```
- **预期**：脚本打印“基线任务成功 → tool-service 被 OOM 杀掉并重启（RestartCount 增长）→ 再触发任务失败”。
- 🎙：“现场演练：把工具服务的容器内存上限压到 8MB，低于 Python 运行所需。可以看到它被内核 OOM 杀掉并自动重启，重启计数增长。”

### B2（1:10–1:30）拿到证据入口 correlation_id
- **在哪**：【GPU1】终端（脚本输出里）。
- **操作**：找到输出最后一行的 `CORR=xxxxxxxx`，**选中复制**，然后粘贴成一条命令（把 `粘贴的CORR` 换成实际值）：
  ```bash
  CORR=粘贴的CORR
  ```
- **预期**：屏幕停留在这两行（任务失败 JSON + CORR=…）。
- 🎙：“请求触发的 Agent 任务会真实调用工具并失败。注意输出里的 correlation_id——它是贯穿任务、事件与诊断的证据入口。”

### B3（1:30–1:55）平台关联 + CLI 诊断
- **在哪**：【GPU1】终端。
  ```bash
  curl -s -X POST "$TRACESPHERE_PLATFORM_URL/api/v1/correlate" \
    -H "Authorization: Bearer $TRACESPHERE_API_TOKEN" -H 'Content-Type: application/json' \
    -d '{"window_seconds":5}'; echo
  cd ~/tracesphere/rca
  ./bin/tracesphere diagnose --correlation-id "$CORR" --window 10m | head -25
  ```
- **预期**：报告头显示 `Top-1 容器内存耗尽（Container OOM）`、`Evidence Match: 99/100`、证据 ID 列表。
- 🎙：“平台先做窗口关联，把任务、容器、内核证据归到同一条证据链；然后 RCA 诊断给出 Top-1：容器内存耗尽，证据命中评分 99 分，并列出命中的证据 ID。”

### B4（1:55–2:25）诊断页 + 告警运营
- **在哪**：【本地】浏览器切到 **标签 2（`#/diagnosis`）**；若想看刚才那条告警，切 **标签 3（`#/incidents`）** 点最新一条。
- **操作**：
  1. 展示五维评分明细（规则匹配 / 时序 / 资源邻接 / 信号强度 / 独立证据）；
  2. 点开一条证据看原始 payload；
  3. 在告警详情右上角点一次 **静默**（再点 **取消静默** 恢复，避免留下状态）。
- **预期**：评分分解、时间线按层着色、处置建议（依据/操作/风险）、状态变 silenced 再恢复。
- 🎙：“诊断页：评分由规则匹配、时序、资源邻接、信号强度、独立证据五个维度加权，是‘证据命中评分’，不是概率；每条证据可溯源。告警运营支持确认、静默与已处理，状态持久化并在列表中标记。”

### C1（2:25–2:55）回放 Case2：CPU 争抢
- **在哪**：【GPU1】终端。
  ```bash
  cd ~/tracesphere/rca
  ./bin/tracesphere diagnose --scenario case2-cpu | head -14
  ```
- **预期**：`CPU 资源争抢`，`Evidence Match: 85/100`，`数据源：fixture=mock`。
- 🎙：“接下来的场景用当时真实演练抓取的回放数据演示，链路与现场一致：CPU 资源争抢，评分 85。”

### C2（2:55–3:20）回放 Case3：工具调用失败
- **在哪**：【GPU1】终端。
  ```bash
  ./bin/tracesphere diagnose --scenario case3-tool-failure | head -14
  ```
- **预期**：`Agent 工具调用失败`，`67/100`。
- 🎙：“工具端点不可达，评分 67。四个场景的 Top-1 都命中对应根因。”

### C3（3:20–3:45）回放 Case4：GPU 显存耗尽（降级模式）
- **在哪**：【GPU1】终端。
  ```bash
  ./bin/tracesphere diagnose --scenario case4-gpu-mock | head -14
  ```
- **预期**：`GPU 显存耗尽`，`89/100`。
- 🎙：“第四个场景是 GPU 显存耗尽，评分 89。评测环境没有 GPU，我们用 Mock DCGM 上报模拟显存指标：占用率超过 90% 并出现耗尽事件后，诊断给出 GPU 显存耗尽。这对应赛题的模拟数据降级要求。”

### D1（3:45–4:10）告警总览 + 拓扑收束
- **在哪**：【GPU1】终端 + 【本地】浏览器。
  ```bash
  ./bin/tracesphere alerts --window 15m | head -20
  ```
  然后浏览器切回 **标签 1（拓扑）**，点任一高亮资源。
- 🎙：“平台还提供窗口级告警总览与资源图联动；每条告警都能回到拓扑定位到具体资源。”

### D2（4:10–4:30）收尾
- **在哪**：【本地】浏览器先停在 `#/health` 或 README 快速开始页截图。
- 🎙：“整套流程一键复现：acceptance 脚本依次完成四个场景的注入、采集、关联、诊断与回放数据回写。部署与最小环境说明在 README。TraceSphere，用证据说话。”

---

# 四、录完收尾（善后 2 分钟）

1. 确认 B 段脚本已自动恢复：B1 输出末尾应有 `tool-service 已恢复`；C 段为回放无副作用。
2. 如想留干净环境：`bash ~/tracesphere/tools/reset-platform.sh`；mock GPU 已在 normal。
3. 关闭【本地】隧道窗口；浏览器可留。
4. 若视频里点过静默，确认已在 B4 取消（或去告警页取消）。

---

# 五、兜底与排障（录到一半出问题怎么办）

| 现象 | 处理 |
|---|---|
| 浏览器打不开 / 一直转圈 | 隧道窗口关了：重开 §2.6 的 `ssh -N -L ...` 命令 |
| 页面 401 或“无法连接诊断服务” | 地址漏了 `?token=...`：用 §一 的三个完整 URL |
| B 段 CORR 没抓出来 | 打开 `#/incidents` 取最新一条告警进详情页（诊断一样展示） |
| B 段注入失败/超时 | 直接切 C 段回放（口径不变），或整段重拍 |
| 页面报“数据源 fixture” | 那是回放状态提示（正常）；现场诊断请确认 `demo-up --status` 三件套 active |
| toxiproxy 容器被重建过 | 重跑 `toxiproxy-init.sh`（§2.3 末尾命令） |
| 服务异常 | `sudo systemctl restart tracesphere-platform tracesphere-rca`；VM 探针：`ssh ... 'sudo systemctl restart tracesphere-vm-agent'` |
| GPU1 的 GPU 被别人占满 | **与我们无关**：TraceSphere 全程 CPU 推理（llama.cpp）+ Mock DCGM，不受影响 |

---

# 六、备用命令卡（需要全现场版本时用）

### 6.1 全现场 Case2（约 +1 分钟）
```bash
cd ~/tracesphere
sshpass -p "$VM_PASSWORD" ssh ubuntu@$TRACESPHERE_VM_HOST '
  bash /opt/tracesphere/workload/faults/cpu.sh
  sudo docker update --cpus=0.5 llama-server
  sleep 4
  bash /opt/tracesphere/workload/faults/run-task.sh "CPU 争抢演练任务 - 期望推理超时"'
# 恢复：
sshpass -p "$VM_PASSWORD" ssh ubuntu@$TRACESPHERE_VM_HOST '
  sudo docker rm -f cpu-stress; sudo docker update --cpus=0 llama-server
  cd /opt/tracesphere/workload && sudo docker compose up -d --force-recreate llama-server'
```

### 6.2 全现场 Case3（约 +1 分钟）
```bash
sshpass -p "$VM_PASSWORD" ssh ubuntu@$TRACESPHERE_VM_HOST '
  bash /opt/tracesphere/workload/faults/tool-failure.sh down
  sleep 2
  bash /opt/tracesphere/workload/faults/run-task.sh "工具故障演练任务 - 期望连接失败"'
sshpass -p "$VM_PASSWORD" ssh ubuntu@$TRACESPHERE_VM_HOST 'bash /opt/tracesphere/workload/faults/tool-failure.sh clear'
```

### 6.3 全现场 Case4（GPU 模拟，一条龙）
```bash
bash ~/tracesphere/tools/case4-gpu-mock.sh
```

### 6.4 全量验收（D 段想展示一键复现）
```bash
cd ~/tracesphere && bash tools/acceptance.sh
# 产出 /tmp/final/case{1,2,3,4}*.txt；历史报告见 docs/evidence/acceptance-2026-09-21/
```

---

# 七、完整解说词（通读备用；与 §三 逐句一致）

> A1 “这是 TraceSphere——面向 ZSvirt 虚拟机内智能体工作负载的全栈可观测与根因诊断平台。当前是健康总览：宿主机、虚拟机、容器与 GPU 的指标和事件在持续汇入。”
> A2 “资源图覆盖五层对象：宿主机、GPU、虚拟机、容器、以及 Agent 服务与任务。GPU 节点通过 assigned_to 关联到业务 VM——无 GPU 硬件时由 Mock DCGM 提供同样的模型与指标，替换为真实 DCGM 后规则不变。”
> A3 “平台、诊断与控制台、以及 VM 内探针都以 systemd 常驻：探针用 eBPF、PSI 和 cgroup 采集，直接上报平台，不依赖任何桥接进程。”
> B1 “现场演练：把工具服务的容器内存上限压到 8MB，低于 Python 运行所需。可以看到它被内核 OOM 杀掉并自动重启，重启计数增长。”
> B2 “请求触发的 Agent 任务会真实调用工具并失败。注意输出里的 correlation_id——它是贯穿任务、事件与诊断的证据入口。”
> B3 “平台先做窗口关联，把任务、容器、内核证据归到同一条证据链；然后 RCA 诊断给出 Top-1：容器内存耗尽，证据命中评分 99 分，并列出命中的证据 ID。”
> B4 “诊断页：评分由规则匹配、时序、资源邻接、信号强度、独立证据五个维度加权，是‘证据命中评分’，不是概率；每条证据可溯源。告警运营支持确认、静默与已处理，状态持久化并在列表中标记。”
> C1 “接下来的场景用当时真实演练抓取的回放数据演示，链路与现场一致：CPU 资源争抢，评分 85。”
> C2 “工具端点不可达，评分 67。四个场景的 Top-1 都命中对应根因。”
> C3 “第四个场景是 GPU 显存耗尽，评分 89。评测环境没有 GPU，我们用 Mock DCGM 上报模拟显存指标：占用率超过 90% 并出现耗尽事件后，诊断给出 GPU 显存耗尽。这对应赛题的模拟数据降级要求。”
> D1 “平台还提供窗口级告警总览与资源图联动；每条告警都能回到拓扑定位到具体资源。”
> D2 “整套流程一键复现：acceptance 脚本依次完成四个场景的注入、采集、关联、诊断与回放数据回写。部署与最小环境说明在 README。TraceSphere，用证据说话。”

---

# 八、录制前检查清单（逐项打勾）

- [ ] GPU1 三件套 `demo-up --status` 三行 active
- [ ] VM 7 个容器全在跑；`/proxies` 里能看到 `tool`
- [ ] mock-dcgm 已重置 normal
- [ ] 平台已重置基线（reset-platform）
- [ ] 本地隧道窗口已开且 `/api/v1/health` 可访问
- [ ] 浏览器三标签已开（带 token）
- [ ] GPU1 终端已 source 环境变量、字号调大、`clear`
- [ ] B 段已空跑过一次（彩排完成）
- [ ] 录屏软件已选窗口/区域（建议全屏 + 1080p60）
- [ ] 手机/系统通知已静音
