# GPTPartner · 私人 AI 管家

终端与 QQ 私聊、SQLite 会话历史、模型工具调用。渠道和模型分别通过基类封装，使用时只需选择渠道、供应商和模型。

## 直接使用

已有凭据继续放在项目根目录 `.env`。激活环境后，可以直接指定组合：

```powershell
conda activate gptpartner
python main.py --channel qq --provider openai --model gpt-5-mini
python main.py --channel cli --provider deepseek --model deepseek-flash
```

省略 `--provider` / `--model` 时使用 `.env` 配置。切换供应商时，程序会使用新供应商的服务地址，并重新选择模型；OpenAI 需要明确指定模型。只改模型时会保留当前供应商和自定义地址。命令行选择不会改写 `.env` 或共享 `config`。

代码中使用统一应用类：

```python
from ai_butler import Butler

Butler(channel="qq", provider="openai", model="gpt-5-mini").run()
```

`run()` 阻塞接收消息，退出时自动关闭渠道。配置校验发生在初始化时；模型和 QQ 的网络请求在运行后才发生。

## 对话中切换模型

CLI 和 QQ 都可直接发送以下命令：

| 命令 | 行为 |
| --- | --- |
| `/model` | 查看当前会话模型和用法 |
| `/model openai gpt-5-mini` | 选择供应商与模型 |
| `/model deepseek deepseek-flash` | 切换到另一供应商 |
| `/model 模型名` | 在当前供应商内更换模型 |
| `/model default` | 恢复本次启动的默认供应商与模型 |

选择按会话保存到 SQLite，重启后恢复；CLI 的不同 `/session` 和不同 QQ 用户各自独立。启动参数定义默认模型，已有会话保存的选择优先生效。切换保留原对话历史，命令与确认文案不进入模型上下文。

切换命令只校验本地配置，需要 `.env` 中已配置目标供应商的 Key；失败时保留原选择。模型名称是否可用由下一次普通消息的 API 请求验证。命令本身不调用模型，也不修改 `.env`。QQ 重推旧的切换消息时复用回复缓存，不会覆盖较新的选择。

## 文件职责

```text
GPTPartner/
├── main.py                        命令行与 IDE 运行入口
├── ai_butler/
│   ├── app.py                     Butler 组装组件、按会话路由模型
│   ├── config.py                  读取 .env，提供共享 dataclass config
│   ├── models/
│   │   ├── messages.py            IncomingMessage / Reply / Message
│   │   └── session.py             ModelSelection / Delivery
│   ├── core/
│   │   └── agent.py               多轮模型与工具调用循环
│   ├── providers/
│   │   ├── base.py                Provider 抽象基类
│   │   └── chat_completions.py    共用传输层及 OpenAI / DeepSeek 子类
│   ├── storage/
│   │   └── sessions.py            一次事务保存会话、模型选择与回复缓存
│   ├── tools/
│   │   ├── registry.py            工具描述与执行分发
│   │   └── clock.py               本地北京时间工具
│   └── channels/
│       ├── base.py                Channel 公共流程：历史、去重、保存、交付
│       ├── cli/
│       │   └── channel.py         CLIChannel：终端输入、命令、输出
│       ├── qq/
│       │   ├── channel.py         QQChannel：平台收发、检查与识别
│       │   ├── _client.py         内部 HTTP 实现
│       │   └── _gateway.py        内部 WebSocket 实现
│       └── wechat/README.md       微信渠道预留与选型边界
├── tests/
│   ├── helpers.py                 测试数据、临时数据库与 mock 基础
│   ├── test_config.py
│   ├── test_agent.py
│   ├── test_providers.py
│   ├── test_cli.py
│   └── test_tools.py
├── .env.example
├── environment.yml
├── pyproject.toml
└── AGENTS.md
```

数据流为 **平台收消息 → Channel 读取历史与模型选择 → Butler 路由 → Agent / Provider / Tools → Reply → Channel 保存并发送**。

- `CLIChannel`、`QQChannel` 显式继承 `Channel`；`OpenAIProvider`、`DeepSeekProvider` 通过共用传输层继承 `Provider`。
- Butler 按供应商和模型复用 Agent，在回调中处理模型命令和路由；不直接管理数据库连接。
- `models` 集中存放跨层传递的数据类，统一从 `ai_butler.models` 导入。Config 保留在 config.py，集中读取配置；运行逻辑仍放在各自的业务模块中。
- `cli`、`qq` 子包各自只导出渠道类。QQ 的 client、gateway 是私有模块，仅由 QQChannel 在内部组装；连接检查和发送者识别也通过渠道类完成。外层无需导入或创建 QQClient。
- Channel 基类统一负责历史读取、去重、回复缓存、保存、发送状态和连接生命周期。CLI、QQ 不导入 storage，也不识别 SQLite 异常；新增平台直接复用这些行为。
- 渠道通过 `receive(handler)` 串行调用 `handler(incoming, history)`，业务返回 `Reply(text, messages)`。QQ 在工作线程运行这段公共流程，网关接收和心跳不受模型耗时影响。

- Agent 不导入 channels 或 storage，只接收统一消息和历史，返回回答文本与完整对话轮次；不修改传入的历史。
- `providers` 负责模型协议。两家共用 Chat Completions 格式，因此目前共用一个实现，差异在请求参数中处理。后续新模型协议再增加对应适配器。
- `storage/sessions.py` 在同一事务保存完整轮次、模型选择与回复缓存，隐藏 SQLite 连接。已有表和消息键继续使用，新增 session_models 表保存会话选择。
- `tools` 现在只有本地工具。MCP 是后续引入远端工具的一种接入方式，届时在工具层增加客户端并通过 registry 供 Agent 使用。
- QQ 目录已实现官方机器人 WebSocket 单聊；微信仍预留。渠道不导入 Agent 或模型实现，平台收发协议放在各自渠道目录中。
- HTTP 请求直接在各自实现中使用标准库 `urllib.request.urlopen`，不再单独封装 network 层。

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

运行依赖 `python-dotenv`、`websockets` 统一声明在 `pyproject.toml`，安装项目时一并安装。Ruff、Pyright 是开发检查工具。真实对话会调用收费 API，需具备相应账户、权限和网络连接。

切换 OpenAI：在 `.env` 中设置 `BUTLER_PROVIDER=openai`、`OPENAI_API_KEY`，并将 `BUTLER_MODEL` 改为账户可用且支持 Chat Completions 和 function calling 的模型。自定义过 `BUTLER_BASE_URL` 时也需同步修改或删除。

## 配置使用

```python
from ai_butler.config import config

print(config.model)
print(config.history_turns)
```

模块加载时，`python-dotenv` 从项目 `.env` 读取变量；dataclass `Config()` 将其转换为类型明确的配置，并生成共享实例 `config`。环境变量优先于 `.env`。修改 `.env` 后重启程序生效，不会在每条消息中重复读取文件。

业务代码直接使用共享实例；测试可传入单独的 `Config(...)`，以隔离模型配置和临时数据库。`config.validate()` 在启动时检查必要配置。暂不自定义异常层级：配置问题使用 `ValueError`，模型与工具循环失败使用 `RuntimeError`。

| 变量 | 默认 / 用途 |
| --- | --- |
| `BUTLER_PROVIDER` | `deepseek` 或 `openai` |
| `BUTLER_MODEL` | DeepSeek 默认 `deepseek-flash`；OpenAI 显式指定 |
| `DEEPSEEK_API_KEY` / `OPENAI_API_KEY` | 对应模型服务凭据 |
| `BUTLER_BASE_URL` | 未设置时自动选择对应服务根地址 |
| `BUTLER_DB_PATH` | `data/sessions.sqlite3`，相对项目根目录 |
| `BUTLER_TIMEOUT_SECONDS` | 单次请求 30 秒 |
| `BUTLER_MAX_RETRIES` | 额外重试 2 次 |
| `BUTLER_HISTORY_TURNS` | 最近 20 轮完整对话进入模型上下文 |
| `BUTLER_MAX_OUTPUT_TOKENS` | 单次回复最多 2048 tokens |
| `BUTLER_MAX_TOOL_ROUNDS` | 最多 3 轮工具执行 |

Key 不参与 dataclass 的 repr；日志不输出密钥、请求正文或完整对话。`.env` 和会话数据库已在 `.gitignore` 中排除。

## 会话与消息接口

```powershell
python main.py --session personal
```

命令：`/help`、`/history`、`/session 名称`、`/model`、`/exit`。同名会话重启后继续，不同名称相互隔离。

`IncomingMessage` 包含 `channel`、`user_id`、`session_id`、`text`、可选 `message_id` 和会话 `model`。渠道生成会话键：QQ 单聊为 `qq:<appid>:c2c:<user_openid>`，CLI 为 `live:<会话名>`。基类补入已保存的 ModelSelection，业务只使用统一的数据类。

独立组合渠道与业务回调时：

```python
from ai_butler.channels import create_channel
from ai_butler.core.agent import Agent
from ai_butler.providers import create_provider

channel = create_channel("qq")
agent = Agent(create_provider())
try:
    channel.receive(agent.reply)
finally:
    channel.close()
```

回调接收 `(IncomingMessage, list[Message])`，返回 `Reply(text, messages, model)`；messages 是本次完整轮次，包含用户、模型及工具消息。只返回 `Reply(text)` 会发送文本但不加入会话历史；返回非空 model 时同步更新会话选择。独立使用 Agent 回调不包含模型切换命令，使用 Butler 可获得完整的对话内切换功能。

`channel.history(session_id)` 读取最近完整轮次。`channel.reply(incoming, text)` 封装发送目标和平台协议，可用于定制接入；常规 `receive(handler)` 已自动发送。没有平台消息 ID 的 CLI 消息不去重，有 ID 的消息按会话与 ID 缓存交付状态。

新增平台时，继承 Channel 并调用 `super().__init__(settings)`，实现 `_receive(handler)` 和 `_send(incoming, text)`。接收的统一消息交给 `_process`；有连接或工作线程时实现 `_close()`，平台需要特殊错误提示时实现 `_failure_reply()`。公共的 receive、reply、history、close 及存储流程不再重写。新增模型协议时继承 Provider，实现 `complete(messages, tools)` 并在模型工厂注册。

## 日志约定

使用标准库 `logging`，每个模块通过 `getLogger(__name__)` 获取 logger；只有命令行入口配置输出格式。默认显示 WARNING / ERROR，`--verbose` 增加 INFO，包含时间、级别和模块名。调用 Python API 时，由调用方配置 logging。

| 级别 | 事件与允许字段 |
| --- | --- |
| DEBUG | 请求开始、消息被忽略；只记录固定原因 |
| INFO | 应用启停、渠道在线、模型完成、工具轮次、回复发送或缓存复用；记录渠道、供应商、模型名、耗时和数量 |
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

测试使用 mock 模型、临时数据库，不调用真实服务。生产入口只连接配置的模型。真实模型与 QQ 连通性需在本机配置凭据后验证。

Pyright 已启用 `reportDeprecated = "error"`，弃用 API 或类型重载会使检查失败。需要同时检查运行时弃用警告时，执行：

```powershell
python -W error::DeprecationWarning -W error::PendingDeprecationWarning -m unittest discover -s tests -v
```

## QQ 与后续渠道

QQ 私聊接入已实现。先在激活的环境中执行 `python -m pip install -e ".[dev]"`，在本机 `.env` 配置 QQ 凭据，再依次运行：

```powershell
python main.py --channel qq --qq-check
python main.py --channel qq --qq-discover
# 收到自己的 OpenID 后，Ctrl+C 退出，填写 .env 的 QQ_ALLOWED_USERS。
python main.py --channel qq
```

检查模式只验证凭据和网关；识别模式只显示私聊发送者的 OpenID，均不调用模型或发送回复。正式模式只为允许名单中的用户回复纯文本。完整操作见 [QQ 接入说明](ai_butler/channels/qq/README.md)。真实收发仍需平台应用权限、开发范围和本机连通性验证。

[微信渠道说明](ai_butler/channels/wechat/README.md) 记录了未来选型需要先明确的账号类型。
