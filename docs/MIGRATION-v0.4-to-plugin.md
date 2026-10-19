# 从旧 MCP v0.4 迁移

新产品版本为 Completion Review Plugin 0.1.2。版本序列重新开始；不表示功能回退到旧 MCP 0.1。

- 原 `completion_qa` 包及旧命令已从当前树移除，仍可在 Git 历史恢复。
- 新入口为 `python -m completion_plugin.cli`，可选 MCP 为 `python -m completion_plugin.server`。旧六工具 API 不兼容；新 MCP 仅公开能力与文本诊断，批准与执行留在可信宿主/交互路径。
- 旧计划、摘要校验及证据结构不导入。新工作流使用显式版本、修订事件和有界直接内容比较；不是防篡改方案。
- 三种润色 profile 为 conversation_summary、technical_document、academic。实际模型能力需宿主授权与接线；无模型不能报告语义通过。
- DSH 适配器位于 adapters/dsh；可打包不等于已装入真实 DSH。模型指定与原生团队能力限制见其 README。
- 旧版本回退请在独立目录检出历史提交，避免混装两代包。当前发布保留父提交历史，没有强制改写分支。

详细使用见 INSTALL-CODEX-WINDOWS.md 与 TASK-MATRIX.md。
