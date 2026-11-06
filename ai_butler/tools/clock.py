from datetime import datetime, timedelta, timezone


def get_beijing_time() -> dict:
    """获取当前北京时间、日期和星期。"""
    # 当前北京时间固定 UTC+08:00，无需 Windows 额外安装 IANA 时区数据库。
    now = datetime.now(timezone(timedelta(hours=8), name="Asia/Shanghai"))
    return {
        "timezone": "Asia/Shanghai",
        "datetime": now.isoformat(timespec="seconds"),
        "weekday": f"星期{'一二三四五六日'[now.weekday()]}",
    }
