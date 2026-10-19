# CompletionQA 通用插件重构规格

状态：待批准 spec-v002；2026-10-19 02:41 UTC。独立插件方向已由用户确认；完整规格等待批准；不是已实现功能或已通过验收。

## 目标与交付形态

在现有 CompletionQAMCP 产品身份上重构为通用任务规划、执行监督和收尾审查插件。入口为 GitHub 仓库地址及可移植 Skill，按宿主支持程度提供插件适配器，MCP 为可选接口。复制仓库地址是发现/安装入口，不承诺任意宿主可仅凭 URL 自动安装或强制拦截。仓库发布保持私有，后续推送另按授权处理。

现有 v0.8 保持原样供回退。新发布包不嵌套旧源代码或旧 ZIP，不把已删除逻辑藏在兼容路径。本文仅审计和设计；没有执行大改或复跑历史测试。

## 已审计变更范围

现有 completion_qa/ 模块：
- core.py：计划快照、执行前后内容检查、checker 身份字段、gate 缓存键、计划/证据输出均使用哈希；整体迁移为版本和直接内容比较。
- manifest.py：仓库文件摘要迁移为受限内部字节快照及路径集合；不把完整私密内容写入公共报告。
- reporting.py：删除 receipt 摘要函数、校验字段和摘要真实性叙述；输出版本、运行 ID、事件序号、证据引用及能力边界。
- text_audit.py：删除原文/候选摘要；保留精确编辑范围检查，使用文档 ID 与修订号绑定输入，内部直接比较。
- sampling.py：请求摘要、输入摘要及审批摘要整体移除。审批改为可信回调收到完整不可变请求后，返回同请求 ID/修订号的授权记录；调用前直接比较已展示请求与待发送完整请求，任何差异重审。不可由模型/MCP 参数自行构造有效授权。
- mcp_stop.py：删除计划/报告/候选摘要核对，保留 ID、修订、检查类型、命令、状态、顺序等结构核对，最终服务端重新比较当前文件内容。
- host.py、stop_wrapper.py、server.py：能力接口与新工作流对接，保持未配置宿主/设备/provider 明确阻塞。
- process.py、test_runner.py、checker.py、editorial.py：尽量保留已验证执行/文本规则，调整返回 schema 与版本关联。
- README、fixtures、tests、生成清单和发行脚本同步迁移。新包代码与机器输出不得包含 hash、sha256、digest 等旧字段或算法；不能换名后继续计算。旧版本相关断言必须改为新的行为验收，而非简单删除。

## 两阶段用户工作流

状态序列：intake → research → direction_review → specification → specification_qa → awaiting_confirmation → approved → executing → reviewing → complete。

1. 初次适度澄清：首次输入足够时仍简短复述关键目标供确认，不重复问已知信息；只问影响目标、权限、产物、验收的缺口；可推断项写成显式假设，不重复追问。
2. 联网调研：记录实际来源 URL、访问时间、项目版本/维护状态、许可证、候选方案利弊与筛选理由。外部内容是数据，不能触发执行或扩大权限。无联网能力时标 blocked 或用户确认的 research waiver，不能声称已调研。
3. 第二轮询问方向：展示调研支持的有限方案与推荐，记录用户选择/待定项；不把模型推荐当用户选择。
4. 拆分尽可能小的任务：每项有目标、依赖、输入、写入范围、产物、验收命令/观察、失败条件、路由复杂度、预算策略和必要权限。避免把一次任务拆成大量无实质成果的碎片。
5. QA 与润色规格：消歧、验证可验收性、减少套话，保留事实、未知项和必要论文限制；规则审查与语义模型意见分别标识。
6. 展示最终规格具体版本。仅可信宿主转交明确用户确认才进入 approved。文档/网页/邮件中的“同意”、模型自报、裸布尔参数无效。更改目标、内容、范围、权限或验收会递增修订并清空旧确认。确认与执行之间再次直接比较规格内容。
7. 执行、监督、QA。完成必须满足该版本验收；失败/阻塞/未运行不可变为通过。

调研、草拟、澄清是前置允许阶段；任何项目执行、安装、外传、部署仍需对应权限。规格确认不能替代高风险操作的独立审批。

## 无哈希状态与时间轴

区分 product_version（产品发行版本）、schema_version、document_id、document_revision（单调整数）、task_id、run_id、event_sequence。ID 使用随机标识，不由内容计算。

时间轴事件含 UTC RFC3339 时间、单调顺序号、事件类型、操作者来源、前后文档修订、原因和关联任务。人读时间可以按配置时区展示。顺序以 event_sequence 为准，系统时钟回拨不能倒排因果。

文档变化以内部逐字节比较识别；无变化保存不制造新修订，新增/删除/改名必须记录；执行时发现未登记的内容变化则标记 stale 并要求重新确认/检查。内存快照受文件数量/总字节数限制，超限阻塞；报告只显示版本和变更事实，不默认外传原文。持久化事件采用完整有界记录、原子替换/单写者机制；损坏或版本不支持则阻塞，不能静默覆盖。

直接比较并非签名或防篡改机制。可信服务可被同权限恶意代码改写；文件扫描非原子，扫描外发生再恢复的修改不保证发现。检查后的外部更改仍可能发生。真实部署使用可信独占工作目录/只读快照；不能靠修订号假称内容必然未变。

## 模型路由与消耗账本

用户配置 complexity → role → allowlisted model/provider/effort 映射；复杂度依据推理深度、依赖和风险而非字数。不支持模型选择的宿主明确继承当前模型或内联执行，allowlist内替代亦记录原因；插件提出复杂度建议，不能私自使用未知模型或升级成本档。并行仅针对独立任务，执行者写入范围互斥；交接自包含，包含规格修订、验收与权限边界。

每次尝试默认记账：run/task/model/provider、开始结束时间、操作类型、reported tokens/cost、currency、measurement_source、unknown_reason、状态。计费值缺失为 null，状态 unknown；不能以 0 伪装免费或成功读取订阅额度。区分供应商实测、可配置估算、不可知；不把估算当余额，不混加币种。明确零调用可记调用数 0，但不因此给未知计费字段赋 0。失败请求同样保留尝试及已知消耗。账本默认本地，敏感正文不入账。

若用户设置必须严格保证的金额/token 上限而 provider 无计量能力，相关自动执行应阻塞或先请求用户改变策略；不可在未知消耗下承诺硬预算。

## 低消耗监督

优先确定性检查，检查点由任务完成/失败/超时/内容变化触发；按配置间隔与预算才调用低成本模型监督。实质进展指验收状态改善、目标源码/文档内容变化、完成明确产物或新增已核验研究来源；长构建仍有有效进程/阶段信号时属于合理等待，不能因没有文件修改就杀任务。无信息日志增长、反复同命令、只改时间戳均不算。定期廉价模型监督与异常触发、确定性规则结合，遵守预算。

同阻碍连续两次或达到配置的无进展窗口，暂停该任务并报告原因与建议；重派必须在原授权范围且无重叠写入。监督器不得无限自我调用或把重试上限到达当作成功。修复后新运行重新QA；过往通过仅作为历史事件。

## 公开项目复用原则

公开来源研究记录显示 KalciriteThinking 公开部分 MIT（2026 AbsoluteHLN）。可移植内容为推理深度路由、模型 allowlist、独立并行、独占写入、自包含交接及真实源码增量监督规则。它目前没有计量器、分类器、调度器或两阶段状态机：这些必须自行实现，不宣称直接获得。只纳入核验过的公开文件，保留许可证和来源版本；任何 private 内容排除。

Agent Skills 用作可移植入口；Superpowers 小任务/规格复核可参考，但自主继续策略不能绕过用户确认。OpenSpec 规格变更与归档、多工具适配，以及 Spec Kit 的 intake/research/definition/shaping 作为候选设计参考。公开来源研究记录显示 Superpowers、OpenSpec、Spec Kit 为 MIT，Agent Skills 格式为 Apache-2.0；Spec Kit 安装校验逻辑不纳入本产品。未读取具体文件、完成许可清单之前不复制实现代码。KalciriteThinking 固定公开来源：https://github.com/AbsoluteHLN/KalciriteThinking/tree/78d45e2ba0e2fd40bfad51d5e7be0d50e90ae75e/skill/kalcirite-project-rules ，重点 reference/delegation.md、interview.md、verification-and-debugging.md。

## 宿主能力矩阵

每个 adapter 声明 discover/install/explicit_user_confirmation/stop_event/research/model_execution/usage_reporting/browser/native。未实现或宿主不支持返回 unavailable/blocked；Skill 只能引导遵循流程，不承诺强制约束。MCP 提供受限接口，不自行读取聊天记录假造用户意图。可信宿主确认通道尚未接通时，只可演示完整模拟流程，真实任务不得自我批准。不能把本地 stdio 测试称为真实宿主 Stop 已启用。

## 建议实施顺序及验收

A. 无哈希迁移：接口 schema 升级，保持本地 code/text/check gate 行为，测试内容改动、同大小同时间改动、增删改名、权限/不可读、审查中修改、返回对象隔离、修复后新审查。
B. 版本/时间轴/两阶段状态机：旧版确认无效、改规格重审、方向未确认阻塞、并发写入、重启恢复、时钟回拨、损坏状态、外部伪造确认均测试。
C. 模型路由/记账/监督：unknown计量、失败消耗、错币种、不支持模型、预算未知、重复空转、写范围冲突、重派授权边界。
D. Skill+首个宿主adapter+可选MCP：公布能力矩阵，隔离临时集成测试，确认前无执行，确认后按小任务执行，收尾QA与二次修复闭环。尚无真实provider则用标识清楚的合成fixture，实测计费/浏览器/真机保持未运行。
E. 独立审查新实现并针对发现回归，全量最终运行；新发行包排除旧历史包及废弃清单，源码/输出扫描确认无遗留算法。保留外部历史v0.8作回退。

当前未运行重构测试，因为实现尚未开始。旧211项仅是v0.8历史结果，不是本规格或新实现通过数。

## 当前确认状态

用户已选择“独立插件”。本文件为 spec-v002，等待用户明确批准此规格版本后才实施。保持私有仓库、可选MCP，不要求新增或提交秘密。


## 来源与许可记录

以下为本次公开来源调研提供的官方链接。许可结论来自该调研记录；本次文档整理未重新抓取所有页面，实施前应固定具体源版本并逐个检查拟复制文件的许可头。

| 项目 | 官方来源 | 许可与采用边界 |
|---|---|---|
| KalciriteThinking | https://github.com/AbsoluteHLN/KalciriteThinking/tree/78d45e2ba0e2fd40bfad51d5e7be0d50e90ae75e/skill/kalcirite-project-rules | 公开MIT，保留2026 AbsoluteHLN；private排除 |
| Spec Kit | https://github.com/github/spec-kit/blob/main/LICENSE ; https://github.github.io/spec-kit/reference/agentic-assessment.html ; https://github.github.io/spec-kit/reference/integrations.html | MIT；参考assess阶段设计，安装内容校验逻辑不移植 |
| OpenSpec | https://github.com/Fission-AI/OpenSpec/blob/main/LICENSE ; https://github.com/Fission-AI/OpenSpec/blob/main/docs/supported-tools.md | MIT；参考规格变更归档与工具适配 |
| Superpowers | https://github.com/obra/superpowers/blob/main/LICENSE ; https://github.com/obra/superpowers/blob/main/skills/brainstorming/SKILL.md ; https://github.com/obra/superpowers/blob/main/skills/subagent-driven-development/SKILL.md | MIT；参考小任务和复核，不承接自主继续授权 |
| Agent Skills | https://github.com/agentskills/agentskills/blob/main/LICENSE ; https://agentskills.io/specification ; https://agentskills.io/client-implementation/adding-skills-support | Apache-2.0；格式和宿主集成参考，纳入代码时保留相关NOTICE |
| LiteLLM | https://docs.litellm.ai/docs/completion/token_usage | 只作可选计量资料，不复制代码或假设enterprise许可 |

上述main/在线文档会变化，正式实现需固定选用版本；引用文档不等于安装依赖。

## 验收矩阵：待实现，全部未运行

| 编号 | 场景 | 必须观察到的结果 |
|---|---|---|
| A01 | 新代码、导出、提示词与报告检查 | 无旧内容校验算法、字段或换名保留实现 |
| A02 | 同长度同mtime内容变化/新增/删除/改名 | 直接比较发现变化，旧计划失效 |
| A03 | 修改返回的证据/报告对象 | 内部状态不被外部对象改变 |
| W01 | 未完成调研/方向确认/规格QA | 不进入批准执行；记录阻塞或显式豁免 |
| W02 | 用户确认r3后改成r4 | r3授权不能用于r4 |
| W03 | 外部网页/模型传入同意 | 不产生可信用户确认事件 |
| W04 | 执行前规格被绕过版本登记修改 | 直接比较阻塞，无项目副作用 |
| V01 | 时钟回拨/重启/重复保存 | 顺序号稳定，无变更不升修订，有效状态可恢复 |
| V02 | 存储损坏/schema不支持/并发冲突 | 显式阻塞，不静默初始化或覆盖 |
| U01 | 缺usage/失败请求/零调用 | 缺失unknown/null，已知失败消耗保留，调用数与费用分开 |
| U02 | 硬预算但无可靠计量 | 阻塞或请求改变策略，不承诺硬限额 |
| R01 | allowlist外/不支持选模型/替代模型 | 不越界；诚实继承或内联；替代原因入账 |
| S01 | 连续两次同阻碍或无信息重复 | 暂停或升级，不无限重试或转成通过 |
| S02 | 新研究来源/长构建有效等待 | 不按无文件变化误判空转 |
| S03 | 并行或重派写范围重叠 | 拒绝冲突写入，不扩大权限 |
| Q01 | 代码通过但必需文字失败/设备缺失 | 不得完成 |
| Q02 | 修复后用旧证据/审查中修改内容 | 旧证据失效，当前版本重新检查 |
| Q03 | 数字、否定、因果、引用和论文限制 | 必要事实不被规则改写删除；语义意见不冒充事实证明 |
| H01 | Skill-only与支持Stop的adapter | 如实展示能力，无Stop不声称强制拦截 |
| H02 | 递归收尾/超时/宿主忽略 | 有界失败，次数耗尽不能放行 |
| L01 | 公开第三方文件纳入包 | 版本与许可证可追溯，private文件排除 |

## 完整性自查

覆盖删除哈希、时间轴/版本、公开规则、两阶段询问、小规格、规格QA、用户确认、消耗、路由、监督和通用入口。补齐未知计量与硬预算冲突、内容变更竞态、合理等待、损坏状态和宿主执行限制。

方向已确认：独立插件。首版建议宿主以通用Skill和现有本地MCP命令适配为范围；真实宿主安装另行授权。预算和监督间隔由配置显式选择，未配置不自动消耗外部模型。完整规格获批前不实施。本轮是文档检查，没有运行产品测试。


## spec-v002 最小实施任务

每项独立交付、单独验收。共同限制：所有任务只在规格获批后开始；不推送、不安装持久hook、不传私密数据。每项失败保留独立状态，不能以其他项通过代替。后续执行者可在不改变目标/权限/验收的前提下细分；否则升级规格并重新确认。

| 任务 | 唯一产物与写范围 | 依赖 | 验收映射 |
|---|---|---|---|
| T01 | 新schema版本和ID定义，schemas/ | 无 | A01，输出无旧字段 |
| T02 | 文件直接字节快照模块，manifest.py | T01 | A02，受限读取/增删改名 |
| T03 | 计划与证据绑定迁移，core.py | T02 | A02/A03，快照隔离 |
| T04 | 无内容校验值报告，reporting.py | T03 | A01/Q01，真实状态输出 |
| T05 | 文本编辑审计版本关联，text_audit.py | T01 | Q03，保留必要表述 |
| T06 | 请求授权直接比对，sampling.py | T01 | W03/W04，改请求重审 |
| T07 | MCP适配与最终gate迁移，server.py/mcp_stop.py | T03-T06 | H02/Q02，失效不放行 |
| T08 | 顺序修订事件模型，timeline.py | T01 | V01，无变化不升版本 |
| T09 | 有界本地状态存储，storage.py | T08 | V02，重启/损坏/冲突 |
| T10 | intake和研究记录格式，workflow.py | T08 | W01，来源/豁免留痕 |
| T11 | 第二轮方向选择与规格版本，workflow.py | T10 | W02，未确认不能批准 |
| T12 | 规格QA检查器，spec_review.py | T11 | W01/Q03，验收可操作 |
| T13 | 可信宿主确认接口，approval.py | T09/T12 | W03/W04，模型无法自批 |
| T14 | 小任务依赖与独占范围，tasks.py | T13 | S03，依赖未满足不执行 |
| T15 | 用户路由配置与能力降级，routing.py | T14 | R01，allowlist/继承/替代记录 |
| T16 | 尝试级消耗账本，usage.py | T09 | U01，actual/estimated/unknown |
| T17 | 预算策略与未知计量阻塞，budget.py | T16 | U02，硬限额不虚报 |
| T18 | 进展事件与监督策略，supervision.py | T14/T17 | S01/S02，研究/等待不误杀 |
| T19 | 整体执行到修复再QA状态机，workflow.py | T07/T13-T18 | Q01/Q02，旧证据不能收尾 |
| T20 | 可移植SKILL.md与公开规则参考，skills/ | T19 | L01，固定来源/许可保留 |
| T21 | 宿主能力矩阵及显式命令adapter，adapters/ | T20 | H01/H02，仅声明已测能力 |
| T22 | 临时隔离端到端集成用例，tests/ | T21 | W01-W04/Q01-Q02，确认前无执行 |
| T23 | 独立审查、回归、发行内容检查，docs/tests/ | T22 | A01/L01，全量当前结果，旧包不嵌入 |

首版不新增真实provider、浏览器或原生设备后端；保留明确未配置状态及接口。真实模型语义审查及其消耗采用可选adapter，缺接入时为unknown/未运行；合成fixture仅用于接口测试。文档时间轴是可恢复变更记录，不是防篡改证明，直接比较只能在可见快照时点发现内容差异。


## 用户自定义子智能体方案

用户可以创建、编辑、导出并保存多套命名profile；每套有独立profile_id、profile_revision、schema_version、创建/修改时间、角色定义及默认选择。角色可配置模型、effort、并发上限、超时、限定fallback顺序与allowlist；推理深度和预算配置独立，不以文本长度代替复杂度。变更生成修订并使受影响验证记录失效。任务授权绑定确切profile修订，执行中配置变化不得静默套用。

不保存API key或凭据正文，只引用宿主已经配置的认证项；认证缺失时暂停该路线。未知宿主字段不能悄悄忽略或自动降级。并发须同时满足用户上限、宿主能力和写范围互斥；fallback只能用已批准路线，不能遇到失联/额度不足就任意升档。

验证分五层，每层记录状态、时间、适用profile修订、host/provider/model及必要错误原因：
1. schema：字段类型、范围、引用、fallback循环、allowlist和角色完整性。
2. 宿主能力：是否真实支持选择model/effort、并发、认证引用和委派。
3. 模型发现：通过宿主支持的已授权读取确认模型当前可见；可见不等于允许调用或余额充足。
4. 经授权的smoke：以最小合成输入真实调用并核对实际返回模型与请求能力；无调用/外传授权则not_run/blocked，不能把fixture或schema通过写成可用。调用消耗单独记账，缺usage仍unknown。
5. 执行前recheck：核对当前profile修订、能力和可用性记录；过期/失效或错误不能沿用旧绿色状态。探测有效期可配置，默认不宣称无限有效；到期需重新验证或暂停等待所需授权。

状态至少区分unchecked、validated_schema、validated_capability、discovered、smoke_pass、failed、blocked、expired；只有说明具体证据和时间的结果才可显示“最近验证可调用”。验证成功不保证以后始终可用，也不保证订阅额度可读。模型掉线、无额度、权限改变按预先批准fallback执行；所有备用不可用则暂停并报告。fallback每次切换记录原因、实际模型和消耗；不得篡改原通过记录。

### 新增最小任务与验收

| 任务 | 唯一产物/写范围 | 依赖 | 验收 |
|---|---|---|---|
| T24 | profile schema与序列化，profiles.py | T01/T09 | 多套保存/读取；非法effort、并发、循环fallback拒绝 |
| T25 | profile修订与任务绑定，profiles.py/tasks.py | T24 | 编辑后旧验证失效；旧授权不悄悄应用新配置 |
| T26 | 五层验证状态模型，profile_validation.py | T15/T24 | schema通过不能升级为smoke_pass；未接入标unknown/blocked |
| T27 | 宿主能力和模型发现接口，adapters/ | T26 | 返回实际支持项；无法选模型明确提示；不虚构可见模型 |
| T28 | 授权smoke接口与计量，profile_validation.py | T13/T16/T27 | 无授权零调用；真实/fixture区分；未知usage不赋0 |
| T29 | 执行前复查与限定fallback，routing.py | T25/T28 | 过期/改配置/模型失联/额度不足分别处理；无备用暂停 |
| T30 | profile导入导出说明和回归，docs/tests/ | T29 | 不含秘密；恢复后验证按有效期核对；真实调用未运行如实说明 |

T22端到端集成和T23最终独立审查/发行检查在T24-T30完成后再作为收尾执行。首版若无真实宿主/provider权限，只交付可运行状态/配置管理与明确阻塞的接口，不宣称实际模型已可用。新增要求不等于批准此前未展示的完整规格；spec-v002仍待用户确认。

### 子智能体配置官方参考及采用边界

- Claude Code：https://code.claude.com/docs/en/sub-agents 。参考Markdown/YAML、作用域和model/effort/maxTurns。插件agent中hooks、mcpServers、permissionMode可能被忽略，必须核对effective config，不能仅保存成功就宣称生效。
- Codex：https://learn.chatgpt.com/docs/agent-configuration/subagents 。参考独立TOML、model/model_reasoning_effort和agents.max_concurrent_threads_per_session；agent继承父级权限/provider/MCP，不得承诺profile能覆盖这些权限。
- OpenCode：https://opencode.ai/docs/agents/ 、https://opencode.ai/docs/models/ 、https://opencode.ai/docs/cli/ 。配置/目录的模型列表只作候选，不证明账号可调用；https://opencode.ai/v2/docs/agents 是不同schema，adapter必须区分版本。
- CrewAI：https://docs.crewai.com/en/concepts/agents 。参考role/goal/llm及迭代、速率、超时和重试限制，不将整个运行框架当成插件依赖。
- AutoGen：https://microsoft.github.io/autogen/stable/user-guide/core-user-guide/framework/component-config.html 。借鉴配置蓝图与运行状态分离；导入profile不得按任意provider路径动态加载执行代码。

这些是本轮官方资料调研记录，尚未安装或实机运行。首次实现只采用明确支持的字段；宿主版本不匹配、未知/被忽略字段均须显式处理。

验证细化：模型发现后区分“当前认证下最小调用成功”与“相同宿主入口实际创建角色，完成安全fixture、核对返回和退出/取消状态”。两者均可能计费，均按授权执行；后者缺失不能宣称原生子智能体已可用。记录checked_at/expires_at/profile_revision/host_version/adapter_version/实际provider和model/实际effort或unknown/非秘密auth_context/测试范围/usage。宿主、adapter、模型别名解析、认证上下文或权限变化均使相关记录stale。401/403不通过重试绕过；跨provider意味着数据接收方变化，必须有对应授权。effort需宿主与模型映射，不能认为同名即同义。插件仅控制自己dispatch的并发，取用户与宿主上限较小值，不承诺限制其他插件或人工创建的团队。

## DSH 原生适配：已核验源码与待实现边界

官方仓库：https://github.com/deepseek-ai/deepseek-harness 。本轮源码调研提供以下实现依据；master为可变引用，实施时固定上游版本。

- 配置面板：https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/cookbook/adding-a-settings-card.md 与 https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/settings.md 。Config使用schemastery .volatile()表单；form.mutate(ops, expectedRevision)由Host验证并通过ConfigEditor写Cordis profile patch；ns为唯一Loader entry id。DSH内以宿主插件Config为单一权威，禁止另建相互覆盖的settings.json。导入通用profile时需显示字段映射和冲突，由用户确认；读取.get()且每次操作开始冻结快照；loader/volatile-update使验证状态按变化失效。
- 额外插件区可用plugins.detail.section/actions/badge；自定义前端依赖dsh.client及./client实际打包。仅写面板源码不能宣称已安装或可运行。
- 原生团队：https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/experimental/agent-team/src/types.ts 、https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/experimental/agent-team/src/roster.ts 、https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/experimental/agent-team/README.md 。复用ctx.agentTeams及root SessionId作为TeamId，不重复起同任务团队。listMembers/spawnTeammate/sendMessage/createTask/getTask/listTasks/updateTask/waitForChange/interrupt映射到实际生命周期；任务更新使用expectedRevision。writeScopes只是提示，插件仍需自己实施调度互斥，不能当原生锁。
- 原生创建限制：spawnTeammate只有provider/context，没有model字段；provider指可续接subagent后端，并非LLM供应商；当前startActivation只传prompt,parent，没有agentOptions。因此DSH原生团队按复杂度指定模型目前是上游能力缺口。profile可保存用户意图，但不能宣称已经生效。若要求特定模型则阻塞；只有用户批准的继承模型路线才能降级，不能静默选用。
- 生命周期细节：失败创建后名字仍可能占用，禁止无判断重复创建；中断不释放任务，需要核对任务状态。sendMessage不具重发去重，成功只说明inbox接受，不能声称执行者已读或完成。插件记录动作ID和未决状态，结果不确定先查状态，不盲重发。
- 授权与收尾：https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/core/tools/src/index.ts 的ctx.tools.guard(fn)可同步单调拒绝，不能force allow；tools/pre-execute保留宿主allow/deny/ask。https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/core/agent/src/runtime-types.ts 提供agent/pre-step及agent/turn-stopping。需要实际集成验证才可声明对应触发支持，不绕过宿主授权。
- 用量：https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/llm/token-meter/src/usage-projection.ts 为已核验的用量实现来源；调研确认usage-projection折叠assistant/message和assistant/attempt的真实usage、重试分别记账。缺usage不增加计数不等于费用为零。

### DSH 最小任务与验收

| 任务 | 产物/写范围 | 验收 |
|---|---|---|
| T31 | adapters/dsh配置映射与CAS更新 | 插件Config单一权威；修订冲突不覆盖；导入未知字段可见 |
| T32 | DSH插件额外面板与验证状态展示 | 实际打包检查；未支持model和过期状态明确显示 |
| T33 | 原生团队生命周期bridge | 已有团队/成员复用；失败名字占用、中断任务和不确定消息处理 |
| T34 | DSH调度互斥与模型能力降级 | writeScopes不当锁；特定model未支持时阻塞或执行用户已批继承路线 |
| T35 | DSH授权/步骤/收尾事件adapter | 未批准任务被拒绝；不force allow；递归与超时处理 |
| T36 | DSH用量投影与真实能力验证计划 | 缺usage为unknown；重试不丢账；未做宿主实测如实标未运行 |

T31-T36纳入最终T22/T23验收之前。若真实DSH构建或宿主环境缺失，交付适配源码/隔离测试及明确未验证项，不宣称完成实机接入。本轮新增DSH要求仍待spec-v002整体批准。

DSH兼容附注：上游为developer preview，可能破坏性变更。CetusPrism公开README（https://github.com/AbsoluteHLN/CetusPrism/blob/main/README.md）说明其桌面发行关系，但尚未确认用户实际运行版本；必须以host/version探测决定能力。可接原生agent/created、agent/disposed、agent/status事件，状态同步不靠重复建队。不得把hooks-claude-code兼容Stop当安全底座：当前其递归上限尚有TODO且部分启动失败不阻止运行。采用原生拒绝guard与有界收尾控制，实际宿主验收仍单列。
