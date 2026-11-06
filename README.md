# GPTPartner · 私人 AI 管家

终端与 QQ 私聊、SQLite 会话历史、模型工具调用。渠道和模型分别通过基类封装，使用时只需选择渠道、供应商和模型。

内部设计见 [docs 文档入口](docs/README.md)；优化想法、评估和状态见 [优化计划](docs/plans/optimizations/README.md)，已完成事项见 [变更归档](docs/archive/CHANGELOG.md)。

## 直接使用

已有凭据继续放在项目根目录 `.env`。激活环境后，可以直接指定组合：

```powershell
conda activate gptpartner
python main.py --channel qq --provider openai --model gpt-5-mini
python main.py --channel cli --provider deepseek --model deepseek-flash
```

省略 `--provider` / `--model` 时使用 `.env` 配置。切换供应商时，程序会使用新供应商的服务地址，并重新选择模型；OpenAI 需要明确指定模型。只改模型时会保留当前供应商和自定义地址。命令行选择不会改写 `.env` 或共享 `config`。

代码中统一通过 Agent 启动：

```python
from ai_butler import Agent

Agent(channel="qq", provider="openai", model="gpt-5-mini").run()
```

`run()` 阻塞接收消息，退出时自动关闭渠道与 MCP 资源。配置校验发生在初始化时；模型、QQ 和 MCP 连接在运行后按需建立。

## 对话中切换模型

CLI 和 QQ 都可直接发送以下命令：

| 命令 | 行为 |
| --- | --- |
| `/model` | 查看当前会话模型和用法 |
| `/model openai gpt-5-mini` | 选择供应商与模型 |
| `/model deepseek deepseek-flash` | 切换到另一供应商 |
| `/model 模型名` | 在当前供应商内更换模型 |
| `/model default` | 恢复本次启动的默认供应商与模型 |
| `/version` | 经 MCP 查看应用、配置、当前模型标识与环境版本 |

选择按会话保存到 SQLite，重启后恢复；CLI 的不同 `/session` 和不同 QQ 用户各自独立。启动参数定义默认模型，已有会话保存的选择优先生效。切换保留原对话历史，命令与确认文案不进入模型上下文。

切换命令只校验本地配置，需要 `.env` 中已配置目标供应商的 Key；失败时保留原选择。模型名称是否可用由下一次普通消息的 API 请求验证。命令本身不调用模型，也不修改 `.env`。QQ 重推旧的切换消息时复用回复缓存，不会覆盖较新的选择。

## 文件职责

数据流为 **Agent.run → Channel 收消息、读取会话 → Agent 路由模型、执行模型与工具循环 → Reply → Channel 保存并发送**。

入口和配置在根目录及 config.py；core 编排，providers 适配模型，channels 管理接入与交付，storage 保证持久化一致性，tools 提供工具，models 定义跨层数据。完整职责与依赖见 [架构设计](docs/design/architecture.md)。

## 文档导航

| 文档 | 内容 |
| --- | --- |
| [文档入口](docs/README.md) | 阅读顺序、实现状态与维护约定 |
| [架构设计](docs/design/architecture.md) | 依赖图、消息契约、事务、生命周期、扩展和设计决策 |
| [能力设计](docs/design/capabilities.md) | SOUL.md、上下文、长期记忆、MCP、Skill、睡梦与主动任务 |
| [运行与可靠性](docs/guides/operations.md) | Linux 常驻、发送恢复、备份、发布与回退方案 |
| [MCP 工具](docs/guides/mcp.md) | 时间、版本、高德天气的配置和故障边界 |
| [演进与验收](docs/plans/roadmap.md) | 阶段顺序、架构完整性清单和测试落点 |
| [变更记录](docs/archive/CHANGELOG.md) | 已完成变化和本地开发历史 |

当前已完成文本聊天 MVP、真实 MCP 时间/版本服务与高德天气接入；人设文件、长期记忆、运行时 Skill、睡梦整理和云端常驻仍处于设计阶段。

## 安装与启动

本机已经创建 Conda 环境 `gptpartner`。每次运行、测试或安装前先激活：

```powershell
conda activate gptpartner
cd C:\Users\HUAWEI\Desktop\program\GPTPartner
python -m pip install -e ".[dev]"
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

在编辑器中填写 `.env` 的 `DEEPSEEK_API_KEY`，然后：

```powershell
python main.py
```

`main.py` 和 `python -m ai_butler` 都使用包所在的项目根目录寻找 `.env`。在其他机器可先用 `conda env create -f environment.yml` 建立环境。

运行依赖统一声明在 `pyproject.toml`，包括 `python-dotenv`、`websockets`、MCP SDK、异步适配与参数校验依赖，安装项目时一并安装。Ruff、Pyright 是开发检查工具。真实对话会调用收费 API，需具备相应账户、权限和网络连接。

切换 OpenAI：在 `.env` 中设置 `BUTLER_PROVIDER=openai`、`OPENAI_API_KEY`，并将 `BUTLER_MODEL` 改为账户可用且支持 Chat Completions 和 function calling 的模型。自定义过 `BUTLER_BASE_URL` 时也需同步修改或删除。

## 配置使用

```python
from ai_butler.config import config

print(config.model)
print(config.history_turns)
```

模块加载时，`python-dotenv` 从项目 `.env` 读取变量；dataclass `Config()` 保存环境快照及公共配置，生成共享实例 `config`。供应商工厂应用所选子类的默认模型和地址后校验。环境变量优先于 `.env`。修改 `.env` 后重启程序生效，不会在每条消息中重复读取文件。

业务代码使用共享实例；测试可传入单独的 `Config(...)`，以隔离模型配置和临时数据库。修改副本直接使用 `dataclasses.replace`，例如 `replace(settings, options=settings.options | {"OPENAI_API_KEY": "test-key"})`。`Config.model`、base_url 在未显式配置时可为空，由工厂填入供应商默认值。暂不自定义异常层级：配置问题使用 `ValueError`，模型与工具循环失败使用 `RuntimeError`。

| 变量 | 默认 / 用途 |
| --- | --- |
| `BUTLER_PROVIDER` | `deepseek` 或 `openai` |
| `BUTLER_MODEL` | DeepSeek 默认 `deepseek-flash`；OpenAI 显式指定 |
| `DEEPSEEK_API_KEY` / `OPENAI_API_KEY` | 对应模型服务凭据 |
| `{PROVIDER}_API_KEY` / `_MODEL` / `_BASE_URL` | 新供应商按名称前缀读取选项；后两项覆盖该供应商默认值 |
| `BUTLER_BASE_URL` | 未设置时自动选择对应服务根地址 |
| `BUTLER_DB_PATH` | `data/sessions.sqlite3`，相对项目根目录 |
| `BUTLER_TIMEOUT_SECONDS` | 单次请求 30 秒 |
| `BUTLER_MAX_RETRIES` | 额外重试 2 次 |
| `BUTLER_HISTORY_TURNS` | 最近 20 轮完整对话进入模型上下文 |
| `BUTLER_MAX_OUTPUT_TOKENS` | 单次回复最多 2048 tokens |
| `BUTLER_MAX_TOOL_ROUNDS` | 最多 3 轮工具执行 |
| `BUTLER_CONFIG_VERSION` | 配置修订号，默认 `1`，手动维护 |
| `AMAP_MAPS_API_KEY` | 可选；启用高德官方 MCP 天气工具 |

Key 不参与 dataclass 的 repr；日志不输出密钥、请求正文或完整对话。`.env` 和会话数据库已在 `.gitignore` 中排除。

HTTP 的重试循环使用 `range(max_retries + 1)`，包含首次请求；工具循环使用 `range(max_tool_rounds + 1)`，包含工具执行后的最终回答机会。网关持续接收与重连使用受关闭事件控制的 while 循环。

## 会话与内部消息

```powershell
python main.py --session personal
```

命令：`/help`、`/history`、`/session 名称`、`/model`、`/version`、`/exit`。同名会话重启后继续，不同名称相互隔离。

`IncomingMessage` 包含 `channel`、`user_id`、`session_id`、`text`、可选 `message_id` 和会话 `model`。渠道生成会话键：QQ 单聊为 `qq:<appid>:c2c:<user_openid>`，CLI 为 `live:<会话名>`。基类补入已保存的 ModelSelection，业务只使用统一的数据类。

应用代码无需手动创建渠道或供应商。诊断入口同样通过 Agent：

```python
from ai_butler import Agent

Agent.inspect("qq")  # 检查凭据与网关，不要求模型 Key
Agent.inspect("qq", discover=True)  # 显式识别发送者，不调用模型、不回复
```

内部渠道回调接收 `(IncomingMessage, list[Message])`，返回 `Reply(text, messages, model)`；messages 是本次完整轮次，包含用户、模型及工具消息。只返回 `Reply(text)` 会发送文本但不加入会话历史；返回非空 model 时同步更新会话选择。

渠道内部管理最近完整轮次、发送目标及平台协议；`receive(handler)` 自动发送回复。没有平台消息 ID 的 CLI 消息不去重，有 ID 的消息按会话与 ID 缓存交付状态。

维护内部实现时，新增平台继承 `channels/_base.py` 的 Channel，实现 `_receive(handler)`、`_send(incoming, text)`，在内部渠道工厂注册。接收的统一消息交给 `_process`；资源清理放在 `_close()`。新增供应商继承 `providers/_base.py` 的 Provider，在独立模块实现 `complete(messages, tools)` 及安全错误提示，再在内部模型工厂注册。

## 日志约定

使用标准库 `logging`，每个模块通过 `getLogger(__name__)` 获取 logger；只有命令行入口配置输出格式。默认显示 WARNING / ERROR，`--verbose` 增加 INFO，包含时间、级别和模块名。调用 Python API 时，由调用方配置 logging。

| 级别 | 事件与允许字段 |
| --- | --- |
| DEBUG | 请求开始、消息被忽略；只记录固定原因 |
| INFO | 应用启停、渠道在线、模型 HTTP 完成、工具轮次、回复发送或缓存复用；记录渠道、供应商、模型名、耗时和数量 |
| WARNING | 网络重试、队列已满、业务回调失败；记录重试次数、HTTP 状态及固定原因 |
| ERROR | 最终模型请求失败、消息处理失败；记录状态或异常类型 |

日志不记录密钥、完整 URL、平台原始响应、消息正文、回复正文、用户 ID 或会话 ID，也不使用异常堆栈输出第三方错误正文。QQ 识别模式由用户显式启动，才在终端显示发送者 OpenID；它不属于运行日志。

数据库以完整轮次保存用户、模型和工具消息，失败轮次不落库。对话和回复缓存同一事务提交，缓存写入失败时对话写入也会回滚。网络发送与本地保存仍分为两个步骤，发送失败时重推消息复用缓存。全部成功历史保留在本机，每次只读取最近若干轮。当前没有自动摘要或结构化长期记忆，数据库暂未加密；备份时退出程序后复制数据库。

## 验证

在已激活的环境中运行：

```powershell
python -m unittest discover -s tests -v
python -m ruff check .
python -m ruff format --check .
python -m pyright
```

测试使用 mock 模型、临时数据库与真实本地 MCP stdio 服务，不连接外部服务。Windows 事件循环允许本机回环连接。真实模型、QQ 与高德连通性需在本机配置凭据后单独验证。

测试按职责集中在 8 个模块，各组用独立 TestCase 区分；共享替身放在 `tests/helpers.py`，测试模块之间不互相导入。职责对应见 [验证落点](docs/plans/roadmap.md)。可用 `python -m unittest tests.test_app.ModelSwitchTests -v` 单独运行一组。

Pyright 已启用 `reportDeprecated = "error"`，弃用 API 或类型重载会使检查失败。需要同时检查运行时弃用警告时，执行：

```powershell
python -W error::DeprecationWarning -W error::PendingDeprecationWarning -m unittest discover -s tests -v
```

## QQ 与后续渠道

QQ 私聊接入已实现。先在激活的环境中执行 `python -m pip install -e ".[dev]"`，在本机 `.env` 配置 QQ 凭据，再依次运行：

```powershell
python main.py --channel qq --check
python main.py --channel qq --discover
# 收到自己的 OpenID 后，Ctrl+C 退出，填写 .env 的 QQ_ALLOWED_USERS。
python main.py --channel qq
```

检查模式只验证凭据和网关；识别模式只显示私聊发送者的 OpenID，均不调用模型或发送回复。正式模式只为允许名单中的用户回复纯文本。完整操作见 [QQ 接入说明](ai_butler/channels/qq/README.md)。真实收发仍需平台应用权限、开发范围和本机连通性验证。

[微信渠道说明](ai_butler/channels/wechat/README.md) 记录了未来选型需要先明确的账号类型。
