# 微信渠道预留

此目录用于未来的微信适配器，目前没有实现收发功能。

接入前先明确用户希望使用的账号与场景：个人微信、企业微信、公众号等需要分别评估对应的官方能力与权限，再查当时的文档选择方案。

确定方案后，在本目录实现 `WeChatChannel(Channel)`，通过 `super().__init__(settings)` 复用公共配置与停止状态。平台实现 `_receive(handler)`、`_send(incoming, text)`，有资源时实现 `_close()`；不要重写公共存储和交付流程。

入站消息转换为 `models.IncomingMessage`，使用 `wechat:` 命名空间的会话 ID，再交给基类 `_process`。基类负责历史、去重和原子保存，业务回调接收消息与历史并返回 Reply；微信实现不导入 storage、Agent 或模型供应商。
