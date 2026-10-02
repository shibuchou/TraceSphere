"""Mock GPU 资源注册（无 GPU 硬件的降级模式，赛题 §4「模拟数据/最小化降级」）。

评测环境通常没有 GPU/vGPU，但赛题要求资源关联模型覆盖
``宿主机 - GPU/vGPU - 虚拟机 - 容器/进程 - AI 服务/Agent``。
本模块在平台启动同步后，把配置声明的「模拟 GPU」注册为一等资源，并建立

    host --contains--> gpu --assigned_to--> vm

两条边，使资源图与证据链具备 GPU 层；配套 ``workload/mock/gpu_exporter.py``
持续上报 ``gpu.metric`` / ``gpu.memory.exhausted`` 事件（origin=mock），
RCA 侧 ``rules/gpu_memory.yaml`` 据此给出「GPU 显存耗尽」诊断。

真实环境有 GPU 时：关闭 ``mock_gpu.enabled``（默认即关闭），
GPU 资源可由 ZSvirt 清单或真实 DCGM exporter 接入，模型无需改动。
"""

from typing import Any, Dict, Optional

from . import domain


def register_mock_gpu(store, cfg: Dict[str, Any]) -> Optional[str]:
    """把配置中的模拟 GPU 注册为资源并建边；未启用时返回 None。"""
    mock = cfg.get("mock_gpu") or {}
    if not mock.get("enabled"):
        return None

    uuid = str(mock.get("uuid") or "mock-gpu0")
    gpu_rid = domain.gpu_id(uuid)

    vm_uuid = str(mock.get("vm_uuid") or "")
    vm_rid = domain.vm_id(vm_uuid) if vm_uuid else None
    host_rid = None
    if vm_rid:
        vm_row = store.get(vm_rid) or {}
        host_rid = vm_row.get("host_id") or None
    if not host_rid:
        host_uuid = str(mock.get("host_uuid") or "")
        host_rid = domain.host_id(host_uuid) if host_uuid else None

    store.upsert(
        {
            "resource_id": gpu_rid,
            "kind": domain.KIND_GPU,
            "name": str(mock.get("name") or "Mock GPU"),
            "state": "online",
            "host_id": host_rid,
            "vm_id": vm_rid,
            "origin": "mock",
            "mode": "mock",
            "labels": {
                "vendor": str(mock.get("vendor") or "NVIDIA (Mock)"),
                "mock": "true",
            },
            "attributes": {
                "memory_total_bytes": mock.get("memory_total_bytes") or 8589934592,
                "driver": "mock-dcgm",
                "note": "无 GPU 硬件的模拟数据源（赛题 §4 降级模式）",
            },
        }
    )
    if host_rid:
        store.upsert_edge(
            {
                "src_id": host_rid,
                "dst_id": gpu_rid,
                "relation": domain.REL_CONTAINS,
                "origin": "mock",
                "mode": "mock",
            }
        )
    if vm_rid:
        store.upsert_edge(
            {
                "src_id": gpu_rid,
                "dst_id": vm_rid,
                "relation": domain.REL_ASSIGNED_TO,
                "origin": "mock",
                "mode": "mock",
            }
        )
    return gpu_rid
