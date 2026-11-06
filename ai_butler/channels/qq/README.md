# QQ 官方机器人私聊

已实现 WebSocket 私聊接入。`QQChannel(Channel)` 负责平台收发和工作线程，`ChannelService` 管理历史、去重、回复缓存与保存；QQ 实现只把统一消息交给服务回调，不导入 Agent 或 storage。Agent 通过服务接口运行。2026-11-05 曾完成真实 QQ 入站、OpenAI 时间工具调用和私聊回复；后续封装调整通过临时数据库和 mock 网络验证，当前交接状态见 [docs/HANDOFF.md](../../../docs/HANDOFF.md)。

## 1. 创建并添加机器人

1. 登录 [QQ 开放平台](https://q.qq.com/)，创建机器人并取得 AppID、AppSecret。
2. 确认应用可使用单聊消息事件 `C2C_MESSAGE_CREATE`，以及 WebSocket 接入方式；当前程序使用 `GROUP_AND_C2C_EVENT (1<<25)` 订阅，但只处理单聊事件。
3. 按控制台要求将自己加入开发测试范围，使用平台提供的添加入口，与机器人建立私聊关系。

若你的应用只提供 Webhook 接入，本实现不能直接接收事件，需要增加 Webhook transport；不要把 Webhook URL 当作 WebSocket 地址。

## 2. 本机配置

```powershell
conda activate gptpartner
cd C:\Users\HUAWEI\Desktop\program\GPTPartner
python -m pip install -e ".[dev]"
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

只在本机 `.env` 中填写：

```dotenv
QQ_APP_ID=你的机器人AppID
QQ_APP_SECRET=你的机器人AppSecret
QQ_ALLOWED_USERS=
```

模型可选择 OpenAI 或 DeepSeek，使用已有的 `BUTLER_PROVIDER`、`BUTLER_MODEL` 和对应 API Key。OpenAI 凭据与 QQ 凭据分别使用，不相互转发。配置修改后重启生效。

## 3. 检查 QQ 鉴权

```powershell
python main.py --channel qq --check
```

此模式验证 Access Token 和 `/gateway` 接口，不要求模型 Key 或用户允许名单，不调用模型、不发 QQ 消息。它不能代替实际收发权限验证。

## 4. 获取自己的 OpenID

```powershell
python main.py --channel qq --discover
```

看到“QQ 机器人已在线”后，在 QQ 中给机器人发一条私聊。终端会输出该发送者的 OpenID，并提示填写 `QQ_ALLOWED_USERS`。**这是机器人应用下的 OpenID，不是普通 QQ 号。** 确认是自己发送的消息后填写，再 Ctrl+C 退出识别模式。

```dotenv
QQ_ALLOWED_USERS=自己的OpenID
```

多个允许用户用英文逗号分隔。此模式不保存聊天正文、不调用模型、不回复消息；只用于本机确认发送者。

## 5. 开启模型私聊回复

```powershell
python main.py --channel qq
```

需要按次指定模型时：

```powershell
python main.py --channel qq --provider openai --model gpt-5-mini
```

普通模式需要 QQ 凭据、允许名单和模型 Key。只响应允许名单中的纯文本私聊；群聊、附件和其他未实现的消息类型会忽略。

建议在 QQ 测试：

1. 发“你好，只回复一句话”，检查普通回复。
2. 发 `/version` 检查版本工具；已配置高德 Key 时可再询问城市天气。本地时间工具已退役。
3. 告诉它一个名字，重启程序后继续询问，检查会话历史恢复。

终端出现 READY 代表网关已登录；你的账号仍须在机器人可用范围内，才能验证真正的私聊消息和回复。

## 文件分工

| 文件 | 职责 |
| --- | --- |
| `_channel.py` | 内部 QQChannel：平台收发、允许名单、工作线程、限速、检查与识别 |
| `_client.py` | 内部 HTTP 实现：Access Token 缓存/刷新、网关查询、纯文本回复 |
| `_gateway.py` | 内部 WebSocket 实现：Identify / Resume、事件接收、心跳和断线恢复 |
| `channels/_base.py` | 平台收发契约、停止状态、清理与失败呈现钩子 |
| `channels/_service.py` | 渠道装配、会话、去重、保存、交付与存储错误处理 |
| `storage/sessions.py` | 同一事务保存对话与回复缓存，封装 SQLite 连接 |

单个工作线程串行运行服务回调，避免阻塞网关心跳。ChannelService 在处理线程打开 SQLite 连接，读取历史，保存业务回调返回的完整轮次和回复缓存，再调用渠道发送并标记交付；渠道不管理存储。会话键仍为 `qq:<appid>:c2c:<user_openid>`，与 CLI 及其他应用隔离。

应用通过 `Agent(channel="qq").run()` 接入，诊断通过 `Agent.inspect("qq", discover=...)` 执行，均交给 ChannelService 选择实现；包入口只导出服务。HTTP 客户端与网关继续由 QQChannel 内部创建。

## 当前行为与边界

- 收到重复消息时，已发送的回复不重复调用模型；已生成但发送失败的回复在平台重推同一消息时复用。回复使用原 `msg_id` 和固定 `msg_seq=1`；平台返回重复发送码 `40054005` 时视为已送达。
- 发送前每用户默认间隔 3 秒，由 `QQ_MIN_INTERVAL_SECONDS` 配置。队列最多容纳 16 个任务，队列满时记录安全日志。
- 本机默认将单条回复限制为 1800 个字符（`QQ_REPLY_MAX_CHARS`），超出会添加截断说明。这是本项目的输出策略，不是宣称 QQ 的统一字符上限。
- SQLite 保存完整会话以及回复缓存，不记录凭据。日志不输出 token、Secret、模型 Key、原始平台错误正文或私聊正文。
- 对话与回复缓存同一事务保存，消除了两次分开提交造成的重复轮次。网络发送和本地发送状态无法一起提交，仍通过原消息 ID 和平台重复发送码处理重试；消息过期、持续断网或队列溢出时可能需要重新提问。重启不会批量补发过期消息。
- Ctrl+C 停止收消息并取消排队任务；当前模型请求会按已有超时结束，退出等待期间不继续发送缓存回复。
- 尚未实现群聊、图片、语音、流式回复、Webhook 和云部署。

## 官方协议依据（2026-11-05 核对）

- [鉴权](https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/access-token.html)：`POST https://api.bot.qq.com/app/getAppAccessToken`，请求使用 AppID / AppSecret，API 请求头为 `Authorization: QQBot <access_token>`。
- [网关](https://bot.q.qq.com/wiki/develop/api-v2/openapi/wss/url_get.html)：`GET /gateway` 返回 WSS 地址。
- [WebSocket](https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/event-emit/websocket.html)：Hello、Identify、心跳 ACK、Resume。
- [单聊事件](https://bot.q.qq.com/wiki/develop/api-v2/autogen/event/c2c_message_create.html)：`C2C_MESSAGE_CREATE`、`author.user_openid`。
- [单聊回复](https://bot.q.qq.com/wiki/develop/api-v2/autogen/api/v2_users_user_openid_messages.post.html)：`POST /v2/users/{user_openid}/messages`，携带 `msg_id`、`msg_seq`。

官方单聊发送页的概述与字段表对回复窗口有不同描述。程序尽快回复，不依赖最长窗口；机器人权限、开发环境和实际频控仍需在账号上验证。
