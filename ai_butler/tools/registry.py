import json

from .clock import TIME_TOOL, get_beijing_time

TOOL_SCHEMAS = [TIME_TOOL]


def execute_tool(name: str, arguments: str) -> str:
    if name != "get_beijing_time":
        return json.dumps({"error": "未知工具，当前只支持 get_beijing_time。"}, ensure_ascii=False)
    try:
        params = json.loads(arguments)
    except (json.JSONDecodeError, TypeError):
        return json.dumps({"error": "参数必须是 JSON 对象 {}。"}, ensure_ascii=False)
    if params != {}:
        return json.dumps({"error": "时间工具不接受参数，请传入 {}。"}, ensure_ascii=False)
    return json.dumps(get_beijing_time(), ensure_ascii=False)
