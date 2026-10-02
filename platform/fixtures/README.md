# fixtures

ZSvirt API responses consumed by `FixtureProvider`（方案 §4.2）。**当前为真实抓取**（`_capture.json` 中 `provisional: false`）。

- 每个文件保存官方 REST Response 的原样结构，**不自行设计格式**。
- 上层（Registry / Graph / Correlation）与 `RESTProvider` 共用同一 `mapper`，`mode=real|mock` 切换对上层零影响。
- 场景回放：在 `fixtures/<scenario>/` 下放同名文件即可按文件覆盖（配置 `zsvirt.fixture_scenario`）。

## 抓取信息（2026-09-20，管理节点 <MN_IP>）

| 集合 | 文件 | 已验证路径 | total |
|---|---|---|---|
| Zone | `zones.json` | `zones` | 1 |
| Cluster | `clusters.json` | `clusters` | 1 |
| Host | `hosts.json` | `hosts` | 1 |
| VM | `vms.json` | `vm-instances` | 1 |
| 镜像 | `images.json` | `images` | 1 |
| L3 网络 | `l3-networks.json` | `l3-networks` | 2 |
| L2 网络 | `l2-networks.json` | `l2-networks` | 3 |
| 端口组 | `port-groups.json` | `l2-networks/port-groups` | 0 |
| 主存储 | `primary-storages.json` | `primary-storage`（单数） | 1 |
| 镜像存储 | `backup-storages.json` | `backup-storage`（单数） | 1 |
| 实例规格 | `instance-offerings.json` | `instance-offerings` | 1 |
| 告警定义 | `alerts.json` | `zwatch/alarms` | 18（1 条 Alarm） |
| 监控事件 | `events.json` | `zwatch/events`（`{"success":true,"events":[...]}`） | 4 |

时钟偏差：-0.85s（`_capture.json.clock`），在 ±5s 关联窗内。

### 真实字段注意事项（已写入 mapper）

- `/l3-networks` 返回的是 `type=portGroup`（不是 `L3BasicNetwork`）；`pg-demo` 的父级是 L2PortGroup `04eb58aa...`，
  再上联 DSwitch(`virtualSwitch`) `db58a900...`，资源图用 `over` 边表达该层级。
- VM `vmNics[].ip` 为空（10.100.0.0/24 的 DHCP 由宿主机手工提供）；VM IP 经 **Agent Registration** 的 `ips` 合并进 VM 资源。
- `/zwatch/alarms` 是告警**定义**：只有 `status=Alarm` 的条目会转成 `zsvirt.alarm` 事件（默认过滤 OK，降噪）；
  dedup key 含 status + lastOpDate，可保留激活/恢复的状态变化。
- ZStack 展示时间如 `Aug 23, 2026 7:55:35 PM` 与 events 的 `time`（epoch 毫秒）均已兼容解析。

## 刷新方式（GPU1 上执行）

```bash
export ZSVIRT_PASSWORD='<admin 密码>'
cd ~/tracesphere/platform
python3 tools/capture_fixtures.py --out fixtures     # 抓取并更新 _capture.json
python3 tools/probe_paths.py                         # 可选：探测/核对 API 路径
python3 tools/verify_rest.py                         # 可选：REST 模式全链路验证
```

抓取后把 `fixtures/` 同步回本地并跑 `python -m unittest discover -s tests -t .` 回归。

## 安全

- 严禁把 ZSvirt 密码写入任何 fixture / 配置文件（方案 §8）；`_capture.json` 只记录账号名，不记录密码或 session uuid。
