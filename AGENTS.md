# GPTPartner 工作约定

- 项目路径为 `C:\Users\HUAWEI\Desktop\program\GPTPartner`。
- 执行 Python、测试或安装依赖前，先激活 `conda activate gptpartner`；不要使用 base 或系统 Python 运行项目。
- 用户偏好简洁代码、短函数、dataclass 和早返回。仅在配置、网络、工具参数等外部边界保留必要校验，避免对标准 API 响应逐字段重复检查或添加无法到达的兜底分支。
- 直接使用字典、int / float、dataclasses.replace 等 Python 内置能力；不为单次取值、类型转换或参数转发增加薄封装。抽象应承担协议适配、校验、生命周期或共享业务规则等实际职责。
- 动态文本优先使用 f-string，包括日志；日志布局模板使用 `{}` 风格，SQL 参数继续使用占位符绑定。短路、赋值表达式和模式匹配以清晰表达流程为准，保留必要的状态初始化。
- 架构沿用 Agent 统一入口、Provider 策略/适配器、内部简单工厂、Channel 模板方法和 SessionStore 事务封装；新增实现放在对应层，优先复用现有扩展点。
- 新供应商或渠道只新增各自实现及工厂类型选择分支；Agent、CLI 路由、会话存储不维护供应商/渠道名单。默认模型和地址属于 Provider 子类，新接入配置从 Config 的环境快照读取。
- 有上限的尝试次数使用 range；max_retries 表示额外重试次数，总尝试次数为 max_retries + 1。网关常驻接收循环以关闭事件为退出条件。
- 修改后在该环境中运行 `python -m unittest discover -s tests -v`、`python -m ruff check .` 和 `python -m pyright`。
- 不要通过关闭诊断或添加忽略注释来消除编辑器警告。
- 不打印或提交 `.env`、真实密钥和私人会话内容。
- 用户不需要离线演示模式；模型 mock 仅放在测试中。
- `.env` 由 `config.py` 集中读取，通过 dataclass 共享实例 `config` 访问；业务模块不再读取环境变量或 .env，专属选项直接从 config.options 取值，并在接入边界转换类型、校验。
- 按 core、providers、storage、tools、channels 分层；QQ、微信等新增渠道放在 channels 的独立目录，通过 IncomingMessage 接入 Agent。
