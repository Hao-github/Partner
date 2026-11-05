from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSelection:
    """会话选择的供应商和模型，不包含凭据或客户端。"""

    provider: str
    model: str


@dataclass(frozen=True)
class Delivery:
    """已生成的回复及其发送状态。"""

    reply: str
    sent: bool
