# GPTPartner 交接摘要

更新：2026-11-06（Asia/Shanghai）。仅在恢复协作状态或排查本机环境时读取；开发约定见 [AGENTS.md](../AGENTS.md)，任务导航见 [文档索引](README.md)。

## 当前状态

- 运行入口为 Agent。已实现 CLI / QQ C2C 文本、OpenAI / DeepSeek、历史与会话隔离、会话模型切换、回复缓存及有限重试；本轮增加真实 MCP 时间/版本服务、高德天气与跨渠道 `/version`。
- 2026-11-05 曾完成本人 QQ 私聊真实联调；2026-11-06 完成本地 stdio、官方高德天气及模型工具循环联调，未重新验证 QQ 投递或部署常驻服务。
- 上下文输入预算、SIGTERM、独立补发、SOUL.md、长期记忆、运行时 Skill、睡梦整理及主动任务仍待实现；其他平台和媒体尚未接入。
- 文档按设计、运维、计划、归档分类；剩余 6 项优化方向暂缓。OPT-001/002 和 MCP 新能力 OPT-016 已归档，见 [完成索引](archive/README.md)；目录移动见 [OPT-014](archive/CHANGELOG.md#opt-014)。
- 仓库内 Codex 开发技能 `$review-optimizations` 用于评审与规划，见 [OPT-015](archive/CHANGELOG.md#opt-015)；最近筛选结果见 [评审摘要](plans/optimizations/review.md)。它不为 QQ/CLI 提供运行时 Skill 加载能力。

## 继续工作时

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

2026-11-06 MCP 交付：94 项测试、Ruff check 通过，Pyright 0 errors / 0 warnings；140 个本地文档链接、围栏及配置凭据泄漏检查通过。真实 stdio 时间/版本调用、高德北京天气及模型调用天气工具后回答通过。无数据库迁移、未读取私人会话。此前开发技能验证保留于 OPT-015；宿主 UI 发现结果仍未独立验证。
