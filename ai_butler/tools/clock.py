from datetime import datetime, timedelta, timezone

TIME_TOOL = {
    "type": "function",
    "function": {
        "name": "get_beijing_time",
        "description": "获取当前北京时间。回答现在的日期、星期或时间时使用此工具。",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
}


def get_beijing_time() -> dict:
    # 当前北京时间固定 UTC+08:00，无需 Windows 额外安装 IANA 时区数据库。
    now = datetime.now(timezone(timedelta(hours=8), name="Asia/Shanghai"))
    return {
        "timezone": "Asia/Shanghai",
        "datetime": now.isoformat(timespec="seconds"),
        "weekday": "星期" + "一二三四五六日"[now.weekday()],
    }
