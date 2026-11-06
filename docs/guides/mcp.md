# MCP 工具与版本查询

当前已接入真实 MCP 协议，工具描述来自服务器发现结果。运行 `conda activate gptpartner` 后安装项目依赖：`python -m pip install -e ".[dev]"`。

## 当前能力

| 工具 | 传输 / 来源 | 用法 |
| --- | --- | --- |
| `get_beijing_time` | 本项目 MCP 服务，stdio 子进程 | 对话中询问日期、时间或星期 |
| `get_version` | 同一 stdio MCP 服务 | 对话中询问版本，或发送 `/version` |
| `maps_weather` | 高德官方 MCP，Streamable HTTP | 对话中询问指定城市天气，例如“北京今天天气如何？” |

首次需要工具时自动连接，stdio 子进程使用当前 Python 解释器，无需手动启动第二个终端。高德只向模型开放天气工具，其他地图工具未启用；未配置 Key 时保留时间与版本工具。

## 本机配置

在项目根目录 `.env` 设置 `AMAP_MAPS_API_KEY` 为自己的高德 Key，重启后生效。Key 只保存在本机，不加入版本控制、模型上下文或工具结果；`.env.example` 仅保留空值。

高德地址为 `https://mcp.amap.com/mcp`，按官方要求用查询参数传入 Key。应用不输出带 Key 的连接错误；SDK 传输日志只保留固定警告事件，避免打印 URL、正文和异常内容。详见 [高德官方接入说明](https://developer.amap.com/api/mcp-server/gettingstarted) 和 [能力说明](https://developer.amap.com/api/mcp-server/summary)。

## 版本的含义

- `application_version`：已安装项目的包版本，来源为 pyproject.toml。
- `config_version`：显式配置修订号 `BUTLER_CONFIG_VERSION`，默认 `1`。调整配置后可自行更新；不自动计算配置内容或密钥的哈希。
- `model.version`：当前会话使用的模型标识；`version_source=configured_model_id`。模型供应商没有提供内部构建号时，不推测其真实快照版本。
- `environment`：Python、解释器实现、操作系统及版本、Conda 环境名和 MCP SDK 版本。不会返回环境变量全集、路径、主机名或密钥。

CLI、QQ 的 `/version` 均通过同一个 MCP 工具查询，不调用模型、不进入聊天历史，也不需要连接高德。对话式版本查询由模型决定调用工具，其结果作为正常对话的一部分保存。

## 失败与边界

工具参数在注册表入口按服务器 JSON Schema 校验；重名拒绝注册，未知工具和参数错误返回 JSON 错误。时间工具与版本工具无参数。天气接受城市名或 adcode，具体参数以服务发现结果为准。

天气发现失败时本轮仅提供本地工具，记录 `mcp_weather_unavailable`；已连接工具调用失败或超时会终止本轮，不保存不完整对话。网络恢复后如连接已失效可重启应用。单次 MCP 请求读取超时使用 `BUTLER_TIMEOUT_SECONDS`；SDK 管理连接及 HTTP 传输超时。整轮截止时间、工具结果大小预算和自动重连策略仍待后续设计。

Agent 退出时依次关闭渠道、MCP 会话、子进程及后台事件循环。测试使用真实 stdio 协议验证本地服务，高德网络用测试替身；实际 Key 与官方服务的联调另行记录。MCP 接入不代表运行时 Skill 加载已实现，见 [能力设计](../design/capabilities.md#skill-的最小实现)。

[返回文档入口](../README.md)
