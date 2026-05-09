import os
import aiohttp
from src.logger import get_logger

log = get_logger("tool.web_search")

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Search the web for current information, news, or facts. "
            "Use this when you need up-to-date information you don't already know."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to look up"
                }
            },
            "required": ["query"]
        }
    }
}


async def execute(query: str) -> str:
    log.info("Web search: %r", query)
    api_key = os.getenv("TAVILY_API_KEY")
    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": "basic",
        "max_results": 3,
        "include_answer": True,
    }
    async with aiohttp.ClientSession() as session:
        async with session.post("https://api.tavily.com/search", json=payload) as resp:
            resp.raise_for_status()
            data = await resp.json()

    parts = []
    if data.get("answer"):
        # Tavily's own summary is usually enough — cap it to keep tokens low
        parts.append(f"Summary: {data['answer'][:400]}")

    for r in data.get("results", []):
        title = r.get("title", "")
        url = r.get("url", "")
        content = r.get("content", "")[:500]  # truncate each snippet
        parts.append(f"[{title}]({url})\n{content}")

    result = "\n\n".join(parts) if parts else "No results found."
    log.debug("Search returned %d chars", len(result))
    return result
