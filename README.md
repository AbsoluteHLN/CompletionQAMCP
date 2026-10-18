# CompletionQAMCP 0.4.0

私有、专有的任务收尾审查 MCP 原型。当前可用于本地验证证据和语法检查流程；尚未达到完整代码 QA、自动真机验收或模型语义审查的产品状态。

## 当前能力

- 官方 Python MCP SDK stdio 服务，6 个工具：`capabilities`、`review_plan`、`run_check`、`review_text`、`completion_gate`、`completion_report`。
- 显式文件范围和 SHA-256；可选 repository 内容清单，文件新增、删除、改名、修改会使旧计划失效。
- Python AST / JSON 语法解析，不执行待审代码。它不等价于项目构建、单元测试、类型检查、安全扫描或运行时验收。
- `pass`、`fail`、`blocked`、`not_run` 状态与本轮证据绑定；缺失、未配置、过期证据不会视作通过。
- 中文简洁摘要与结构化 receipt；校验值不是签名，不能证明外部报告可信。
- 文本规则诊断和受约束建议；数字、否定、因果措辞保护是确定性检查，不是语义质量认证。建议不自动应用。
- 本地 Stop command wrapper、递归提示和失败处理测试。v0.4 修复了进程内返回对象与内部证据共用引用的问题。

## 尚未完成的验收

1. 真实宿主 Stop 自动触发、失败后修复重试和递归退出闭环尚未验收。已做配置发现探针，不代表 hook 已授信、安装或启用。
2. 模型 provider、浏览器和原生设备 adapter 未接入，要求这些检查时返回 blocked。合成模型 fixture 不能产生语义通过证明。
3. 没有通用项目测试/lint/build adapter，也没有跨进程证据持久化。
4. MCP 工具本身不定义结束事件；宿主需明确接入。wrapper 不能保证宿主在进程未启动、被终止或忽略结果时仍强制拦截。

## 本地运行

Python >= 3.11。依赖由官方包管理渠道提供，使用项目自己的虚拟环境：

```sh
python -m venv .venv
# 激活 .venv 后：
python -m pip install -e .
python -m unittest discover -s tests -v
python -m fixtures.acceptance
python -m completion_qa.server --root /absolute/path/to/reviewed/files
```

MCP 客户端应以 stdio 启动服务。不要向 stdout 写额外日志。示例命令不会安装宿主 hook，也不会配置 API 凭据。

```sh
printf '%s' '{"hook_event_name":"Stop","stop_hook_active":false}' | \
  python -m completion_qa.stop_wrapper --root "$PWD/fixtures" --artifact good.py --check code
```

`{}` 只说明声明的语法检查通过。`stop_hook_active=true` 会阻塞并提示人工处理，不会因达到重试次数而放行。宿主是否继续触发仍需实际集成验证。

## 推荐调用流程

1. 查询 capabilities。
2. 调用 review_plan，明确 artifacts、required 检查和 profile；可选 scope="repository"。
3. 对计划运行已配置检查；仅允许固定 command_id `parse_sources`。
4. 调用 completion_report 或 completion_gate 重新校验内容并读取结果。
5. 内容改变后重新建计划。服务重启后旧内存计划不可用。

`review_text` 的独立建议不是 completion_gate 的执行证据。未要求的模型或设备检查也不会因此被描述为已验证。

## 信任边界

禁止根外路径、路径穿越、非普通文件和超限输入。待审代码只被解析；内部命令使用固定参数数组、shell=False、超时及最小环境。repository 清单最多 2000 文件 / 20MB，排除 `.git`、`__pycache__`、`.pytest_cache` 目录，绑定内容而非 Git HEAD、权限或空目录，也不代表所有文件正确。

本程序信任启动配置、Python 和自身代码；它不是操作系统沙箱。文件校验与读取并非原子快照，部署应使用可信只读快照。返回值隔离不防拥有同进程执行权限的人直接修改 Engine 内部对象。证据暂存内存，分享日志前应另做敏感信息检查。

provider 审批和默认关闭边界见 [docs/provider-boundary.md](docs/provider-boundary.md)。未连接外部服务。协议兼容说明保持 SDK1.29.0 的实现范围，不宣称支持全部未来协议功能。

## 测试与发布

`tests/` 同时包含原作者与独立负向回归，直接运行上方统一命令。`fixtures/synthetic_stage.txt` 是纯合成字符串数据，不含其他项目的实际研究结果。最新实际测试范围见 [docs/VALIDATION.md](docs/VALIDATION.md)。测试数量不代表覆盖率或产品就绪。

## 使用与授权

当前仅用于授权私有开发；项目自身不授予开源许可，见 LICENSE。第三方依赖各自保留原许可证，见 THIRD_PARTY_NOTICES.md。私有仓库不改变第三方义务，也不代表可将依赖重新声明为专有。
