# GPTPartner 交接摘要

更新：2026-11-06（Asia/Shanghai）。仅在恢复协作状态或排查本机环境时读取；开发约定见 [AGENTS.md](../AGENTS.md)，任务导航见 [文档索引](README.md)。

## 当前状态

- 代码基线 `11aebf9`（Provider 解析错误装饰器）；文档分类提交为 `bef426a`。运行入口为 Agent。已实现 CLI / QQ C2C 文本、OpenAI / DeepSeek、历史与会话隔离、会话模型切换、本地时间工具、回复缓存及有限重试。
- 2026-11-05 曾完成本人 QQ 私聊、模型和时间工具真实联调；后续调整由 mock 网络与临时数据库验证。最近交接记录为未部署常驻服务，本轮仅整理文档。
- 上下文输入预算、SIGTERM、独立补发、SOUL.md、长期记忆、MCP、Skill、睡梦整理及主动任务仍待实现；Grok、Gemini、Telegram、WhatsApp、微信及媒体接入尚未实现。
- 文档已按设计、运维、计划、归档分类；8 项未来方向按编号拆分。已完成项及其验证保留于归档，目录移动记录见 [OPT-014](archive/CHANGELOG.md#opt-014)。
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
- `.vscode/` 保留本地并由 Git 忽略。项目使用自身 Git 仓库；历史提交从归档按需查看，不推送远端。
- 测试沿用 7 个模块与 `tests/helpers.py`，具体分工见 [验证落点](plans/roadmap.md#验证落点)。

## 最近验证

2026-11-06 开发技能与评审交付：85 项测试、Ruff check 通过，Pyright 0 errors / 0 warnings；技能格式与 UI 元数据校验、129 个本地链接与锚点及代码围栏检查通过。已完成一次按技能进行的实例评审；本次未修改运行代码或数据库，宿主 UI 发现结果尚未独立验证。
