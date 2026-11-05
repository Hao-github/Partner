# GPTPartner 工作约定

- 项目路径为 `C:\Users\HUAWEI\Desktop\program\GPTPartner`。
- 执行 Python、测试或安装依赖前，先激活 `conda activate gptpartner`；不要使用 base 或系统 Python 运行项目。
- 用户偏好简洁代码、短函数、dataclass 和早返回。仅在配置、网络、工具参数等外部边界保留必要校验，避免对标准 API 响应逐字段重复检查或添加无法到达的兜底分支。
- 修改后在该环境中运行 `python -m unittest discover -s tests -v`、`python -m ruff check .` 和 `python -m pyright`。
- 不要通过关闭诊断或添加忽略注释来消除编辑器警告。
- 不打印或提交 `.env`、真实密钥和私人会话内容。
- 用户不需要离线演示模式；模型 mock 仅放在测试中。
- `.env` 由 `config.py` 集中读取，通过 dataclass 共享实例 `config` 访问；不要在业务模块重复解析配置。
- 按 core、providers、storage、tools、channels 分层；QQ、微信等新增渠道放在 channels 的独立目录，通过 IncomingMessage 接入 Agent。
