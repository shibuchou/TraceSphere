# 样例模型（本地文件，不入仓库）

`model.gguf`：Qwen3.5-0.8B（GGUF Q8_0），供 `llama-server` 容器 CPU 推理（compose 只读挂载 `/opt/tracesphere/models`）。

| 项 | 值 |
|---|---|
| 文件 | `model.gguf` |
| 大小 | 833,592,096 字节（约 795 MiB） |
| SHA256 | `37ae482d336108d23516fa35e8e0c4126688d81018b87178a18d752a1357814f` |
| 许可证 | Apache-2.0（Qwen 系列模型许可证见模型页） |

校验：`sha256sum /opt/tracesphere/models/model.gguf`
