import json

from tools.web_search import TOOL_DEFINITION as WEB_SEARCH_DEF
from tools.web_search import execute as web_search_execute
from tools.order import TOOL_DEFINITION as ORDER_DEF
from tools.order import execute as order_execute

TOOL_DEFINITIONS = [WEB_SEARCH_DEF, ORDER_DEF]

_EXECUTORS = {
    "web_search": web_search_execute,
    "place_order": order_execute,
}


async def dispatch(tool_name: str, arguments: str | dict) -> str:
    if isinstance(arguments, str):
        arguments = json.loads(arguments)
    executor = _EXECUTORS.get(tool_name)
    if executor is None:
        return f"Error: unknown tool '{tool_name}'"
    return await executor(**arguments)
