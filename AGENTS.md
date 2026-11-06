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

## 文档按需读取与优化归档

- 需要项目文档时先读 `docs/README.md`，按任务选择索引、目标详情及必要源码；已知 OPT 编号可直接读单项。不要默认全量读取 docs、全部优化项或历史归档。恢复协作/本机环境时才读 `docs/HANDOFF.md`。
- 评审待优化项、比较优先级或选择下一步时，使用仓库技能 `.agents/skills/review-optimizations/SKILL.md`；普通实现和修复无需额外开展优化评审。
- 对话产生的优化想法须在本轮去重记录到 `docs/plans/optimizations/opt-xxx.md`，更新同目录 README 摘要；保留稳定编号、来源/日期、问题/方案、涉及模块、可行性、优化度、成本/风险、触发条件、验收和状态。维护时按需读该目录的 `process.md`。
- 评估须写理由，优化度为预期收益；未经测量不编造提升比例。未完成项区分待评估、候选、进行中、暂缓；记录方向不代表承诺实施，不为计划创建空模块或多余模式。
- 核对实际结果和验收证据后，将完整完成项移至 `docs/archive/CHANGELOG.md`，从待优化目录移除详情，并更新 `docs/archive/README.md` 的已完成索引及原编号链接；保留来源、评估、完成/核验日期、结果和证据。文档完成不等于功能完成，历史完成日期不得推测。
- 重新评估沿用原编号，保留旧归档并标明重开。只同步受影响的设计、运维、路线图和交接摘要，索引不重复长篇方案；变更路径时核对引用。完整记录与状态流转规则以 `docs/plans/optimizations/process.md` 为准。
