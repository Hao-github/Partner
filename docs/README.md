# GPTPartner 文档索引

需要项目背景时先读本页，再按任务选择一条路径。默认只读相关索引、目标详情和必要源码；按需展开链接。当前基线为文本聊天 MVP，规划方案不代表功能已实现。

| 当前任务 | 按需读取 |
| --- | --- |
| 配置、启动、用户命令 | [项目 README](../README.md) 的对应小节 |
| 版本和高德天气 MCP | [MCP 接入](guides/mcp.md) |
| 恢复协作状态、处理本机环境 | [交接摘要](HANDOFF.md) |
| 选择或实施优化 | [待优化索引](plans/optimizations/README.md) → 单项详情 → 所列源码/测试 |
| 比较优化优先级、重复开展评审 | [开发技能](../.agents/skills/review-optimizations/SKILL.md)；最近结论见 [评审摘要](plans/optimizations/review.md) |
| 安排能力阶段或检查缺口 | [演进与验收](plans/roadmap.md) |
| 调整依赖、消息、事务或生命周期 | [架构设计](design/architecture.md) 的相关小节 |
| 人设、上下文、记忆、MCP、Skill、后台整理 | [能力设计](design/capabilities.md) 的对应能力 |
| 常驻、交付恢复、备份或发布 | [运行与可靠性](guides/operations.md) 的对应小节 |
| 核对已完成事项或历史决策 | [归档索引](archive/README.md) → 对应 changelog 小节 |

目录职责：`design/` 保存设计，`guides/` 保存操作与运行约束，`plans/` 保存未来阶段和未完成项，`archive/` 保存完成记录。

本目录也承担仓库内轻量事项追踪，可理解为小型 Jira：优化索引是待办列表，稳定 OPT 编号关联需求来源、方案、评估、状态和验收证据，完成后进入归档。它管理项目工作，不是管家运行时的任务调度系统；具体状态流转见 [维护流程](plans/optimizations/process.md)。

## 阅读与维护

- 已知编号时直接读对应 `plans/optimizations/opt-xxx.md`；先用标题或编号定位长文段落，避免一次读取整个 docs 或所有优化详情。
- 新增或流转想法时才读 [优化项维护流程](plans/optimizations/process.md)；新条目复用稳定编号、定性评估与完成验收规则。
- 方案、验收与完整历史各保留一份；总索引、条目索引和交接只保留摘要与链接。修改位置后检查入链与相对路径。
- 状态区分已实现、待实现、待决策；优化项另区分候选、进行中、暂缓。凭据、真实身份和私人会话不进入文档。
