# GPTPartner 交接文档

更新：2026-11-06，Asia/Shanghai。下一次对话先读本文件和项目 AGENTS.md。

## 当前状态

项目：`C:\Users\HUAWEI\Desktop\program\GPTPartner`。QQ 官方机器人「莫念」的本人私聊此前已经完成真实收发与模型工具调用；本轮完成结构整理和对话内模型切换，验证使用 mock 模型、临时数据库。当前没有常驻机器人进程。

本轮用户要求均已实现：

- 对话中用 `/model` 切换模型，选择按会话持久化，其他会话不受影响。
- 命令行入口移到根目录 `main.py`，删除 `first.py` 和包内 `ai_butler/main.py`。
- 数据结构集中到 `ai_butler/models/`，删除 `core/messages.py`，统一从 `ai_butler.models` 导入。
- 更新本交接文档，并把当前项目提交到本地 Git；不推送远端。

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
- 不通过忽略注释或关闭诊断消除编辑器警告。Pyright 已设置 `reportDeprecated = "error"`。
- `.env` 只由 `config.py` 读取，通过共享 Config 实例使用；不在业务模块重复解析。
- 真实凭据与 QQ 允许名单已在本机 `.env`。不要输出、提交或再次索要密钥，不输出真实会话内容。
- 本机数据库已有真实聊天记录，不删除、不清空、不打印。
- 模型 mock 只放在测试中，不提供离线演示模式。

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

根目录 main.py、`python -m ai_butler` 和 `ai-butler` 使用同一个 main 函数。pyproject 的控制台入口已改为 `main:main`，通过 `py-modules = ["main"]` 安装根模块。本轮已在 gptpartner 中离线刷新本地可编辑安装并验证 `ai-butler --help`。

Python API：

```python
from ai_butler import Butler

Butler(channel="qq", provider="openai", model="gpt-5-mini").run()
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

```text
GPTPartner/
├── main.py                       唯一 main 函数和参数解析
├── ai_butler/
│   ├── app.py                    Butler：组装、模型命令、按模型缓存 Agent
│   ├── config.py                 配置 dataclass、.env 读取和校验
│   ├── models/
│   │   ├── __init__.py            统一数据类型导出
│   │   ├── messages.py            IncomingMessage / Reply / Message
│   │   └── session.py             ModelSelection / Delivery
│   ├── core/agent.py              纯模型与工具循环
│   ├── providers/
│   │   ├── base.py                Provider 抽象基类
│   │   └── chat_completions.py    共用传输层与供应商子类
│   ├── storage/sessions.py        轮次、会话模型、回复缓存的原子保存
│   ├── tools/                    工具定义与执行分发
│   └── channels/
│       ├── base.py                公共历史、模型选择、去重、保存、发送状态
│       ├── cli/channel.py         终端输入输出与命令
│       ├── qq/
│       │   ├── channel.py         QQ 收发、白名单、限速、工作线程、检查/识别
│       │   ├── _client.py         内部 HTTP、token 与平台回复
│       │   └── _gateway.py        内部 WebSocket、心跳与重连
│       └── wechat/README.md       尚未实现
├── tests/                        模型 mock、临时数据库和网络禁止保护
├── pyproject.toml
├── environment.yml
├── AGENTS.md
└── HANDOFF.md
```

- 数据类集中在 models；Config 仍在 config.py，保持配置读取集中。Agent、渠道等行为类保留在对应业务模块，不把全部类堆到一个目录。
- CLIChannel 和 QQChannel 显式继承 Channel。公开方法为 receive、reply、history、close；平台实现 `_receive`、`_send`、可选 `_close` 和错误文案钩子。
- 业务回调为 `(incoming, history) -> Reply`。IncomingMessage.model 携带已保存的会话选择；Reply.model 非空表示本次更新选择，None 表示保留。Reply.messages 为完整成功轮次；空列表只发送文本。
- Channel 基类集中打开和关闭一个当前线程内的 SQLite 连接，并统一存储错误。CLI、QQ、Butler、Agent 不直接创建 SessionStore。
- Agent 不访问数据库，只执行 Provider 和工具循环。Butler 按 ModelSelection 复用 Agent；会话状态由渠道存储提供，Agent 不持有会话历史。
- 保留 turns、deliveries 的原表与消息键，新增 session_models；不需要清空旧库。轮次、模型选择和回复缓存同一事务保存，写入失败全部回滚。
- 网络发送与数据库发送状态仍是两个步骤；QQ 使用原 msg_id、固定 msg_seq=1 和平台重复码处理重试，不宣称严格恰好一次交付。
- 删除过设计的 network 层、自定义 opener 和 NoRedirect；HTTP 实现直接使用标准库 urlopen。
- websockets 为正式依赖，不使用可选 QQ 依赖、动态模块加载或缺依赖兜底。
- contextmanager 本身继续使用；`_store()` 返回注解为 `Generator[SessionStore, None, None]`，已修复旧 Iterator 重载的弃用告警。

## QQ 现有边界

- 官方机器人 WebSocket 单聊，只处理允许名单内的普通文本 C2C 消息。
- 会话键：`qq:<appid>:c2c:<openid>`；CLI 沿用 `live:<session>`。
- 单工作线程串行处理消息，网关心跳独立；默认容量 16、每用户发送间隔 3 秒、回复本地上限 1800 字符。
- `python main.py --channel qq --qq-check` 只检查凭据与网关。
- `python main.py --channel qq --qq-discover` 只在用户明确启动时显示发送者 OpenID，不调用模型或回复。
- 目前没有群聊、图片、语音、Webhook、微信、长期事实记忆、定时任务或 MCP 客户端，也没有部署常驻服务。

## 验证与本地 Git

本轮：77 项单元与流程测试通过，Ruff check / format check 通过，Pyright 0 errors / 0 warnings。新增覆盖会话模型切换、保持历史、会话隔离、重启恢复、错误配置恢复、旧 QQ 命令重推、事务回滚和根目录入口。测试不调用真实模型或发送 QQ 消息。

Git 仓库实际根目录为 `C:\Users\HUAWEI\Desktop\program`，GPTPartner 此前尚未被跟踪。本轮提交范围仅为 GPTPartner 目录；父目录的 .gitignore、Lotus.py 及其他未跟踪文件属于已有独立改动，不混入提交。真实 .env、数据库、缓存和构建产物均通过项目 .gitignore 排除。

本交接文档与实现一起提交。本地提交标识请在项目目录执行 `git log -1 --oneline -- .` 查看；不推送远端。
