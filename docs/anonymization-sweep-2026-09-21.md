# 匿名化与凭据清理记录（P1-5）

- 日期：2026-09-21
- 范围：本地仓库 `tracesphere/`（同步 GPU1 `~/tracesphere/`）
- 目标：可提交物不含学校/个人标识，不含真实口令与内网地址；内部资料明确边界。

## 1. 扫描模式

```
zsvirt\.123        # 环境口令
ZSVIRT_PASSWORD=   # 口令变量赋值
222\.24\.18\.171   # 外网宿主
10\.100\.0\.181    # 业务 VM
192\.168\.122\.    # ZSvirt 管理网段
63bbb461…（VM uuid）
ailab1|87994|邮电|上海开源|Xidian|xiyou   # 身份/学校线索
```

## 2. 处置结果

### 2.1 入口脚本参数化（仓库内不含真实地址与口令）

| 文件 | 处理 |
|---|---|
| `tools/demo-up.sh` | `TRACESPHERE_VM_HOST / TRACESPHERE_VM_UUID / VM_PASSWORD / TRACESPHERE_PLATFORM_URL` 必填/可覆盖 |
| `tools/acceptance.sh` | 同上（环境变量必填，缺失即报错退出） |
| `tools/reset-platform.sh` | `ZSVIRT_PASSWORD` 必填 |
| `workload/docker-compose.yml` | `EVENTS_URL/VM_UUID` 改为 `${PLATFORM_EVENTS_URL}/${TRACESPHERE_VM_UUID}`（`.env` 注入，新增 `workload/.env.example`） |
| `deploy/systemd/*.service` | 改为 `__TS_USER__ / __TS_ROOT__` 模板，由 `install-services.sh` 按实际部署生成；Prometheus 地址移入 `EnvironmentFile=-/etc/tracesphere/rca.env` |

### 2.2 代码/文档默认值清理

- `platform/tsplatform/config.py`、`platform/config/platform.example.json`、`platform/tools/{capture_fixtures,probe_paths,verify_rest}.py` 默认 base_url → `http://127.0.0.1:8080/zstack/v1`（实测环境经 `ZSVIRT_BASE_URL` 覆盖，重启后 sync ok=True）。
- `rca/internal/config/config.go`、`cmd/tracesphere/main.go` 帮助文本、`rca/README.md`、`rca/docs/API.md` Prometheus 默认 → `http://127.0.0.1:9090`。
- `rca/tools/event-bridge.py`（legacy）默认平台地址 → `http://127.0.0.1:8000`。
- `README.md`、`platform/README.md`、`deploy/README.md` 中的示例 IP → `<占位符>` 或文档网段（`10.0.0.10`）。

### 2.3 数据文件脱敏（文档保留网段）

- `rca/fixtures/case{1,2,3}*.json`、`rca/tools/make_fixtures.py`、`console/src/mocks/*.json`、`rca/docs/API.md`：
  `192.168.122.123 → 192.0.2.10`、`10.100.0.181 → 10.0.0.10`（RCA 测试不依赖具体 IP，替换后 `go test` 通过）。

### 2.4 内部资料边界（不入提交物）

- `docs/开工交接-*.md`、`docs/交接文档-*.md`、`docs/fixlog-*.md`、`docs/evidence/`、`docs/anonymization-sweep-*.md`、`docs/demo-*.md`、`deploy/README.md`、`deploy/zs-*.sh`、`deploy/mn-*.sh`、`deploy/*.exp`、`deploy/login-try.sh`。
- 由 `tools/sanitize-for-submission.sh` 打包时通过 rsync `--exclude` 排除，并对其余文件做替换（含 VM uuid → 占位值），最后执行残留扫描（失败即退出非零）。

## 3. 残留说明（可接受）

- `deploy/` 内运维脚本、`docs/` 内部文档含真实地址/口令，仅存内部仓库，打包排除。
- `platform/fixtures/` 为 ZSvirt 真实响应抓取（内网 UUID/IP），提交副本由打包脚本统一替换网段与 VM uuid。
- `GPU1` 为主机别名（非学校/个人标识），保留。
- systemd 单元不含用户名（模板化）；已部署机器上 `/etc/systemd/system/*.service` 为本地生成，不入库。

## 4. 验证

```bash
bash tools/sanitize-for-submission.sh /tmp/ts-submit
# 期望最后输出：clean + 提交包就绪：/tmp/ts-submit.tar.gz
```

## 5. 审计整改补充（2026-09-25）

- **仓库内真实凭据/内网宿主机名已全部替换占位**：`deploy/` 42 个运维脚本（口令 → `${ZS_PW:?}`、管理节点/VM/宿主 IP → `${MN_IP:?}`/`${VM_IP:?}`/`${HOST_IP:?}`、expect 脚本用 `$env(ZS_PW)`）；内部文档（交接/开工/演示）中的口令、`222.24.18.171`、`ailab1` → 占位符。仅 `anonymization-sweep` 记录中的"扫描模式"文本保留（非真实值）。
- **提交包纳入公开证据**：`docs/evidence`（证据链报告 + 四场景验收报告）进入提交包，脱敏脚本统一替换网段/UUID；`docs/demo-*.md` 与内部交接/修复记录仍排除。
- **运行期 Token**：平台/RCA/直报链路的 Token 仅存在于服务器端 env 文件（`/etc/tracesphere/*.env`、VM `workload/.env` 与 `agent.env`），不入仓库。
- 重新执行打包扫描：**clean**（含证据目录）。
