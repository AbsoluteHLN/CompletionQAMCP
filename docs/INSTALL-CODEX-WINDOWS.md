# Codex 与 Windows 手动试用（v0.1.2）

2026-10-19。仓库现为独立 Completion Review Plugin；旧 CompletionQAMCP v0.4 保留在 Git 历史。新代码无需 API key；模型候选生成使用已授权宿主，未接入时明确 blocked。

## 1. 获取与运行

在有此私有仓库访问权的 PowerShell 中：

```powershell
git clone https://github.com/AbsoluteHLN/CompletionQAMCP.git
Set-Location CompletionQAMCP
py -3 --version
py -3 -m completion_plugin.cli --help
```

要求 Python 3.11 或更新。核心 CLI 使用标准库，可以不安装。完整测试包含可选 MCP SDK；如要运行全量，使用项目独立虚拟环境（无需更改 PowerShell 执行策略）：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[mcp]"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

包来自正常 PyPI 依赖安装，不会安装宿主 Stop hook、注册凭据或自动启用 DSH。

## 2. 在 Codex 中加载 Skill

仓库已包含 `.agents/skills/completion-review/SKILL.md`，在此仓库打开 Codex。CLI/IDE 可用 `/skills` 或 `$completion-review` 选择；桌面按当前技能选择界面操作。未出现时重启该 Codex 会话。

在其他项目使用时，将本仓库 `skills/completion-review` 文件夹复制至目标项目 `.agents/skills/completion-review`，保留完整目录。此操作只复制技能说明；需要 Python 检查工具时，保留本仓库并使用这里的虚拟环境 Python。不得假设每个宿主会自动识别一个 GitHub URL，或把 Skill 被发现当作原生 Stop 已启用。

建议首条任务：使用 completion-review，先确认目标，调研可用方案，展示小任务规格和验收；等我批准具体版本后再执行。收尾时核对实际证据并润色总结。

官方文档核验于 2026-10-19：https://learn.chatgpt.com/docs/build-skills 。本仓库接入是项目 Skill 路径，不是已上架通用插件目录。

## 3. Windows 原生检查

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_windows_process.py -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_project_execution.py -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_unicode_storage.py -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_locking.py -v
```

Windows runner 预期 11 通过、1 个仅非 Windows 适用的检查跳过，其中 8 个原生用例检查真实 Job Object、超时、输出阈值和后代退出。全量在 Windows 可能跳过 POSIX PTY 用例。任何 skip 不能计为该平台通过。现有云端结果：154 Python 通过、8 Windows 原生跳过，13 JavaScript 通过；Windows 尚未实测。

## 4. 真实终端取消与恢复

用一个临时测试项目，状态放在项目外；示例路径请按机器调整：

```powershell
py -3 -m completion_plugin.cli wizard --root C:\QA-Trial --state C:\QA-State\task.json --artifact main.py
py -3 -m completion_plugin.cli resume --state C:\QA-State\task.json
```

先创建 `C:\QA-Trial\main.py`，内容 `x = 1`。依提示输入中文目标；调研链接在此简化向导里不会联网读取，必须明确承认未核验或选择豁免。先拒绝最终规格，再 resume，确认显示同一规格后输入其要求的精确批准文本。此向导只执行语法检查，不能代替项目测试或文字语义审查。

反馈时提供 Python/Windows 版本、命令、完整错误、通过/失败/跳过数。不要上传密钥、个人正文或其他项目资料。
