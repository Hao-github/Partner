# GPTPartner 交接摘要

更新：2026-11-06（Asia/Shanghai）。仅在恢复协作状态或排查本机环境时读取；开发约定见 [AGENTS.md](../AGENTS.md)，任务导航见 [文档索引](README.md)。

## 当前状态

- 运行入口为 Agent。已实现 CLI / QQ C2C 文本、OpenAI / DeepSeek、历史与会话隔离、会话模型切换、回复缓存及有限重试、真实 MCP 版本服务、高德天气与跨渠道 `/version`；本地时间工具已按 OPT-018 退役，无替代精确时钟。
- 2026-11-05 曾完成本人 QQ 私聊真实联调；2026-11-06 完成本地 stdio、官方高德天气及模型工具循环联调，未重新验证 QQ 投递或部署常驻服务。
- 上下文输入预算、SIGTERM、独立补发、SOUL.md、长期记忆、运行时 Skill、睡梦整理及主动任务仍待实现；其他平台和媒体尚未接入。
- 剩余 6 项优化方向暂缓；[OPT-017](archive/CHANGELOG.md#opt-017) 的服务与渠道交付迁移已完成。完整结果见 [完成索引](archive/README.md)，后续想法只维护单项详情与优化索引，避免多份文档重复维护。
- OPT-017 最终边界：ModelService 管理模型配置、选择和客户端缓存；ChannelService 管理历史、去重、业务调用、保存及回复交付。Base 只保留平台契约与停止/清理钩子；服务专属工厂为 staticmethod。测试使用真实本地客户端，仅 mock 模型 complete，不再模拟整类默认值与配置赋值。
- [OPT-019](archive/CHANGELOG.md#opt-019) 已冻结 Config 与 options；Provider 初始化并校验完整、冻结的 ModelConfig，工厂只选类型和构造实例。Agent 不再读取模型配置，模型切换与工具调用只传 ModelSelection；生产函数均补齐中文 docstring。
- 仓库内 Codex 开发技能 `$review-optimizations` 用于评审与规划，见 [OPT-015](archive/CHANGELOG.md#opt-015)；最近筛选结果见 [评审摘要](plans/optimizations/review.md)。它不为 QQ/CLI 提供运行时 Skill 加载能力。

## 继续工作时

本轮完成 OPT-019，不推进剩余项。新对话先读本摘要，再按优化索引选择单项；不要默认按编号实施。后续每完成一个灵感文件，执行检查、归档、简短更新本摘要，然后提交并 push 一次；长期约定见 AGENTS.md。

| 任务 | 读取入口 |
| --- | --- |
| 选择下一步优化 | [待优化索引](plans/optimizations/README.md)，只展开选中条目 |
| 输入预算、可靠运行、人设/记忆等阶段 | [演进与验收](plans/roadmap.md) |
| 模块边界、协议或事务 | [架构设计](design/architecture.md) 对应小节 |
| 启动、配置和现有命令 | [项目 README](../README.md) |
| 云端常驻与故障恢复 | [运行与可靠性](guides/operations.md) |
| 历史实现和验证依据 | [归档索引](archive/README.md)，按编号或日期定位 |

## 本机特殊事项

- 项目为 `C:\Users\HUAWEI\Desktop\program\GPTPartner`，Python、测试及安装前激活 Conda `gptpartner`。解释器为 `C:\Users\HUAWEI\miniconda3\envs\gptpartner\python.exe`，此前记录 Python 3.13.18。
- PowerShell Conda hook 曾被执行策略阻止；可在同一 CMD 会话激活并执行：

```bat
call C:\Users\HUAWEI\miniconda3\condabin\conda.bat activate gptpartner
python -m unittest discover -s tests -v
python -m ruff check .
python -m pyright
```

- 本机 `.env` 和数据库包含真实数据，不打印、不清空、不提交；模型 mock 只在 tests。
- `.vscode/` 保留本地并由 Git 忽略。用户已授权 GitHub 推送，origin 为 `https://github.com/Hao-github/Partner.git`，master 跟踪 origin/master；历史提交从归档按需查看。
- 高德 Key 已配置在本机 `.env` 的 AMAP_MAPS_API_KEY，不打印或提交；配置/版本语义与故障边界见 [MCP 指南](guides/mcp.md)。
- 测试为 8 个模块与 `tests/helpers.py`，具体分工见 [验证落点](plans/roadmap.md#验证落点)。

## 最近验证

2026-11-06 OPT-019：100 项测试、Ruff check / format check 通过，Pyright 0 errors / 0 warnings；配置冻结、供应商默认值与覆盖、缓存、模型切换及无凭据版本查询通过，所有生产函数的 docstring 已核对。无依赖或数据库迁移，未读取私人会话、未重新联调外部服务；真实 MCP/天气联调留在 OPT-016。交付基线为包含本摘要的最新提交，可用 git log -1 查看。
