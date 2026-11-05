# GPTPartner 交接文档

更新：2026-11-06，Asia/Shanghai。下一次对话先读本文件和项目 AGENTS.md。

## 当前状态

项目：`C:\Users\HUAWEI\Desktop\program\GPTPartner`。QQ 官方机器人「莫念」的本人私聊此前已经完成真实收发与模型工具调用，支持对话内模型切换。运行入口已统一为 Agent，渠道和模型实现收为内部模块。最新代码迭代为 `99440c7`，验证使用 mock 模型、临时数据库；当前没有常驻机器人进程。

本轮建立 [docs 文档入口](docs/README.md) 和 [CHANGELOG](CHANGELOG.md)。用户强调除内容设计外还要考虑架构完整性，因此文档覆盖依赖、数据契约、事务、资源生命周期、失败恢复、扩展责任及分阶段验收。SOUL.md、长期记忆、MCP、Skill、睡梦机制和常驻运行均仍是待实现设计，本轮没有修改运行代码或数据库。

工作区同期增加了 [优化计划](docs/optimization-plan.md) 及 AGENTS.md 的评估、归档规则；后续沿用稳定 OPT 编号，候选/暂缓与已完成分别记录，完整完成项在 CHANGELOG 归档，计划保留追溯链接。

最近代码迭代（99440c7）：

- 启动时由工厂创建默认 Provider，将其已解析配置和实例直接交给 Agent 缓存；后续模型选择仍按需创建并复用。
- 工具轮次使用有界循环，供应商解析用赋值表达式读取工具调用，路径归一化复用 pathlib 的绝对路径语义。
- QQ 登录完成后用 login_deadline=None 表示取消登录期限，去掉重复的 logged_in 标记；协议事件与 opcode 使用 match 分派，保留必要的心跳、会话及关闭状态。
- 动态日志、URL、会话键和提示等统一优先 f-string，日志布局使用花括号模板；SQL 参数继续绑定。
- README 明确门面、策略/适配器、简单工厂、模板方法和事务封装各自的位置与扩展方式；工作约定同步到 AGENTS.md。
- 默认模型和地址归各 Provider 子类，通过 `_provider_type` 选择实现；Config 按名称读取 `NAME_API_KEY`、`NAME_MODEL`、`NAME_BASE_URL`，不枚举供应商。环境快照不参与 repr，新增渠道直接从 options 字典读取专属配置，在构造边界用 int / float 转换并校验。
- 删除 Config 的 option、integer、number、with_options 和渠道诊断的纯转发函数。直接使用字典及 dataclasses.replace；保留承担协议、校验、生命周期和共享业务规则的接口，不按行数拆函数。
- 渠道类型统一由 `_channel_type` 选择；诊断走 Channel.inspect 钩子。CLI 不枚举供应商和渠道，诊断参数统一为 `--check`、`--discover`，移除原先 QQ 专属参数名。
- 模型和 QQ HTTP 尝试次数均用 `range(max_retries + 1)`；工具循环用 `range(max_tool_rounds + 1)`。不再使用 itertools.count；网关常驻循环由关闭事件控制。
- 继续使用 7 个测试模块，当前 84 项测试通过；更新文档并保存为独立本地 Git 迭代，不推送远端。

## 环境与约定

- Python、测试和安装前必须激活 Conda `gptpartner`，不能使用 base 或系统 Python。
- 解释器：`C:\Users\HUAWEI\miniconda3\envs\gptpartner\python.exe`，Python 3.13.18。
- 此机器的 PowerShell Conda hook 曾被执行策略阻止。工具执行可在同一 CMD 会话使用：

```bat
call C:\Users\HUAWEI\miniconda3\condabin\conda.bat activate gptpartner
python -m unittest discover -s tests -v
python -m ruff check .
python -m pyright
```

- 用户偏好简洁、短函数、dataclass、早返回、显式继承、直接导入；只有一个人使用和部署，不要增加多余的动态加载、兼容包装或通用基础设施。
- 直接使用 Python 字典、类型转换和 dataclasses.replace；不要为这些标准能力添加薄封装。短函数应有实际职责，避免为设计模式增加无意义的层次。
- 动态文本优先 f-string，包含日志；日志布局使用 `{}` 模板，SQL 继续用参数绑定。短路、赋值表达式和模式匹配用于简化流程，保留真实状态初始化。
- 新供应商/平台只修改对应实现和工厂的类型选择分支，不修改 Agent、CLI 路由或会话存储。凭据及专属配置通过 Config 的通用环境快照读取，业务模块不读取 os.environ 或 .env。
- 不通过忽略注释或关闭诊断消除编辑器警告。Pyright 已设置 `reportDeprecated = "error"`。
- `.env` 只由 `config.py` 读取，通过共享 Config 实例使用；不在业务模块重复解析。
- 真实凭据与 QQ 允许名单已在本机 `.env`。不要输出、提交或再次索要密钥，不输出真实会话内容。
- 本机数据库已有真实聊天记录，不删除、不清空、不打印。
- 模型 mock 只放在测试中，不提供离线演示模式。
- `.vscode/` 是本机编辑器设置，加入 `.gitignore` 并取消 Git 跟踪，保留本地文件。此前要求将其跟踪的理解已由用户纠正。

## 启动和使用

```powershell
conda activate gptpartner
cd C:\Users\HUAWEI\Desktop\program\GPTPartner
python main.py --channel qq
```

也可以显式设置启动默认值：

```powershell
python main.py --channel qq --provider openai --model gpt-5-mini
python main.py --channel cli --provider deepseek --model deepseek-flash
python main.py --session personal
```

根目录 main.py、`python -m ai_butler` 和 `ai-butler` 使用同一个 main 函数。pyproject 的控制台入口已改为 `main:main`，通过 `py-modules = ["main"]` 安装根模块。此前已在 gptpartner 中离线刷新本地可编辑安装并验证 `ai-butler --help`。

Python API：

```python
from ai_butler import Agent

Agent(channel="qq", provider="openai", model="gpt-5-mini").run()
```

CLI 支持 `/help`、`/history`、`/session 名称`、`/model`、`/exit`。

## 对话内模型切换

CLI 和 QQ 使用同一组命令：

```text
/model                         查看当前会话模型和用法
/model openai gpt-5-mini        指定供应商和模型
/model deepseek deepseek-flash  切换供应商
/model 模型名                   在当前供应商内更换模型
/model default                 恢复本次启动默认值
```

- 选择按完整 session_id 保存到新增的 session_models 表，重启后恢复；CLI 的不同会话、不同 QQ 用户互不影响。
- 启动参数定义默认值；已有会话的显式选择优先。`/model default` 会恢复到本次启动的默认配置。
- 切换保留历史；命令和确认回复不进入模型历史。
- 命令只验证本地配置，不调用模型。目标供应商的 Key 必须已配置；模型名称是否可用由下一条普通消息的 API 请求验证。
- 验证失败时保留原选择。若重启后选中模型的 Key 不再可用，会提示通过 `/model default` 恢复。
- 模型选择与回复缓存同一事务提交。QQ 重推旧命令时直接复用缓存，不重新执行切换，避免覆盖较新的选择。
- 不修改 `.env`，不在切换时输出密钥或聊天正文。

## 结构和职责

完整设计维护在 [架构设计](docs/architecture.md)，后续人设、记忆和工具能力见 [能力设计](docs/capabilities.md)，优先级和完成条件见 [演进与验收](docs/roadmap.md)。修改边界时同步更新这些文件，不在 HANDOFF 复制整份设计。

- 保持 core、providers、storage、tools、channels、models 分层，应用通过 Agent 的 run、close、inspect 运行。
- Channel 公共流程管理历史、去重、保存和交付；Agent 通过回调返回 Reply，不直接创建 SessionStore。连接只在当前处理线程使用。
- 新供应商或渠道在现有文本/工具契约内只需各自实现、工厂导入和类型选择分支；新增媒体或不同协议能力先调整统一契约。
- 模型默认值归子类，专属配置来自 Config.options；业务层不重新读取环境。Config.model / base_url 可以暂空，由工厂补齐。
- 保存对话、模型选择和回复缓存为同一事务，平台发送与标记另行发生；当前没有独立补发或 schema 版本迁移。
- 本轮优先设计输入预算、SIGTERM 和投递恢复，再做人设与显式长期记忆；后台整理不自动改写人格或复活已忘记事实。

## QQ 现有边界

- 官方机器人 WebSocket 单聊，只处理允许名单内的普通文本 C2C 消息。
- 会话键：`qq:<appid>:c2c:<openid>`；CLI 沿用 `live:<session>`。
- 单工作线程串行处理消息，网关心跳独立；默认容量 16、每用户发送间隔 3 秒、回复本地上限 1800 字符。
- `python main.py --channel qq --check` 只检查凭据与网关。
- `python main.py --channel qq --discover` 只在用户明确启动时显示发送者 OpenID，不调用模型或回复。
- 目前没有群聊、图片、语音、Webhook、微信、长期事实记忆、定时任务或 MCP 客户端，也没有部署常驻服务。

## 云端常驻规划（尚未部署）

用户目前没有云服务器，选择先规划小型 Linux 云服务器方案，使本机关闭后 QQ 机器人仍能运行。

选定方向为单台 Linux LTS、Conda gptpartner、单实例 QQ、SQLite 持久目录和 systemd 管理。资源仅有 1–2 核、2 GB 内存、20 GB 以上磁盘的初始估算，购买前仍需验证地区和服务访问条件。

停止信号、投递恢复、备份、迁移和发布回退的完整约束见 [运行与可靠性](docs/operations.md)。当前仅规划，没有购买服务器、上传凭据、安装服务或部署运行；不得在未实现 SIGTERM 和停止期限前将服务监督配置视为上线完成。

## 验证与本地 Git

测试按职责集中在 7 个模块，每个模块内部保留独立 TestCase：

| 模块 | 范围 |
| --- | --- |
| `tests/test_app.py` | 应用组装、入口、会话模型切换 |
| `tests/test_channels.py` | 渠道公共流程、工厂、CLI |
| `tests/test_config.py` | 配置读取、校验、凭据隐藏 |
| `tests/test_core.py` | Agent 循环、本地工具 |
| `tests/test_providers.py` | 模型协议、请求、重试 |
| `tests/test_qq.py` | QQ 启动、渠道、HTTP、WebSocket 网关 |
| `tests/test_storage.py` | 数据兼容、事务回滚 |

共享数据、临时数据库、网络禁止保护及 `RecordingChannel` 放在 `tests/helpers.py`。新增测试优先放入对应模块和 TestCase；出现独立职责或模块过大时再拆分。单组运行示例：`python -m unittest tests.test_app.ModelSwitchTests -v`。

本轮：84 项单元与流程测试通过，Ruff check / format check 通过，Pyright 0 errors / 0 warnings。继续覆盖会话隔离、模型切换、重启恢复、旧 QQ 命令重推、事务回滚、公开 Agent 工具调用、供应商解析和重试。新增：QQ 已登录连接超过初始登录期限继续运行、Config 新凭据的隐藏和快照、第三种 Provider + Channel 只扩展工厂分支即可完成 CLI 启动/模型切换/落库/关闭、通用诊断不创建模型。重试覆盖 0/1/2 次额外重试，工具测试覆盖耗尽工具轮次后的最终回答。第三种协议仅为测试替身，不是 Grok/Gemini 或新平台的真实接入。

Git 仓库实际根目录已是 `C:\Users\HUAWEI\Desktop\program\GPTPartner`，当前分支为 `master`；旧文档中关于使用父目录仓库的说明已经失效。历史基线为 `27a6ae4`，测试整理为 `f56468b`，`.vscode/` 取消跟踪及云端规划为 `f154d8f`，Agent 接口收拢及供应商拆分为 `dbb2c99`，码风、计数器和接入扩展边界为 `99440c7`。本轮文档体系另作独立提交，历史摘要见 CHANGELOG.md。真实 .env、数据库、缓存和构建产物均通过项目 .gitignore 排除。

本交接文档与实现一起提交。本地提交标识请在项目目录执行 `git log -5 --oneline` 查看；后续按独立改动提交到此仓库，不推送远端。
