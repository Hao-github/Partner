# GPTPartner 交接文档

更新：2026-11-06，Asia/Shanghai。下一次对话先读本文件和项目 AGENTS.md。

## 当前状态

项目：`C:\Users\HUAWEI\Desktop\program\GPTPartner`。QQ 官方机器人「莫念」的本人私聊此前已经完成真实收发与模型工具调用，已有结构整理和对话内模型切换。本轮在项目目录的新 Git 仓库建立历史基线并整理测试，验证使用 mock 模型、临时数据库。当前没有常驻机器人进程。

本轮用户要求均已实现：

- 确认项目目录已单独 `git init`，后续历史迭代使用这里的仓库。
- 先提交现有代码基线 `27a6ae4`，再单独提交测试整理，便于对比和回退。
- 测试文件从 14 个合并为 7 个，保留全部 77 项测试的断言和流程。
- 共享 `RecordingChannel` 移入 `tests/helpers.py`，测试模块之间不再互相导入；渠道工厂测试归入渠道，QQ 凭据隐藏测试归入配置。
- 更新 README 和本交接文档；仅本地提交，不推送远端。

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

## 云端常驻规划（尚未部署）

用户目前没有云服务器，选择先规划小型 Linux 云服务器方案，使本机关闭后 QQ 机器人仍能运行。

- 初步建议单台 Ubuntu LTS 云服务器、单个 QQ 进程，由 systemd 管理开机启动、异常重启和日志。起步资源按 1–2 核、2 GB 内存、20 GB 以上磁盘估算；模型通过 API 调用，不需要 GPU。
- 当前实现主动建立出站 WebSocket / HTTPS 连接，没有业务监听端口；现有接入方式不要求新增域名或公开 HTTP 回调服务。服务器地区需按 QQ 接口及实际模型服务的支持地区和连通性选择。
- 延续 Conda `gptpartner` 环境及 `python main.py --channel qq` 入口，配置仍由 config.py 集中读取。服务器凭据独立配置，不进入 Git。
- SQLite 使用持久磁盘上的固定路径，保留单实例运行；迁移旧聊天记录前停掉本机机器人并备份数据库，切换后避免本地和云端同时接入同一机器人。
- 后续落地需准备 systemd 服务配置、停止信号处理方案、数据库备份及发布/回退步骤，再在目标服务器验证重启恢复和真实 QQ 收发。当前仅规划，没有购买服务器、上传凭据或部署运行。

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

本轮：整理前后均为 77 项单元与流程测试通过，Ruff check / format check 通过，Pyright 0 errors / 0 warnings。覆盖会话模型切换、保持历史、会话隔离、重启恢复、错误配置恢复、旧 QQ 命令重推、事务回滚和根目录入口。整理时逐项比对全部测试方法，保留原有断言和流程。测试不调用真实模型或发送 QQ 消息。

Git 仓库实际根目录已是 `C:\Users\HUAWEI\Desktop\program\GPTPartner`，当前分支为 `master`；旧文档中关于使用父目录仓库的说明已经失效。现有代码基线为 `27a6ae4`（`chore: establish GPTPartner project baseline`），测试整理另作一个提交。真实 .env、数据库、缓存和构建产物均通过项目 .gitignore 排除。

本交接文档与整理一起提交。本地提交标识请在项目目录执行 `git log -2 --oneline` 查看；后续按独立改动提交到此仓库，不推送远端。
