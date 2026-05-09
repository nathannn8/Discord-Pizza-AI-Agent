import asyncio
import json
import re as _re
import os
import aiohttp
from src.logger import get_logger

log = get_logger("client")

GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# Llama generates tool calls in various broken formats. Try them all.
# Format 1: <function=name={"key":"val"}></function>
# Format 2: <function=name [{"key":"val"}](url)</function>
# Format 3: <function=name({"key":"val"})>
_LEGACY_PATTERNS = [
    _re.compile(r"<function=([\w_]+)=(\{.*?\})>", _re.DOTALL),
    _re.compile(r"<function=([\w_]+)\s*\[(\{.*?\})\]", _re.DOTALL),
    _re.compile(r"<function=([\w_]+)\((\{.*?\})\)>", _re.DOTALL),
]


def _parse_legacy_tool_call(failed_gen: str) -> dict | None:
    for pattern in _LEGACY_PATTERNS:
        match = pattern.search(failed_gen)
        if not match:
            continue
        tool_name = match.group(1)
        arguments = match.group(2)
        try:
            json.loads(arguments)
        except (json.JSONDecodeError, ValueError):
            continue
        log.warning("Recovered legacy tool call [pattern %d]: %s(%s)", _LEGACY_PATTERNS.index(pattern) + 1, tool_name, arguments)
        return {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": f"call_{tool_name}_recovered",
                        "type": "function",
                        "function": {"name": tool_name, "arguments": arguments},
                    }],
                },
                "finish_reason": "tool_calls",
            }]
        }

    # Last resort: find tool name + first JSON object anywhere in the string
    name_match = _re.search(r"<function=([\w_]+)", failed_gen)
    json_match = _re.search(r"(\{[^{}]+\})", failed_gen)
    if name_match and json_match:
        tool_name = name_match.group(1)
        arguments = json_match.group(1)
        try:
            json.loads(arguments)
            log.warning("Recovered legacy tool call [fallback]: %s(%s)", tool_name, arguments)
            return {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": f"call_{tool_name}_recovered",
                            "type": "function",
                            "function": {"name": tool_name, "arguments": arguments},
                        }],
                    },
                    "finish_reason": "tool_calls",
                }]
            }
        except (json.JSONDecodeError, ValueError):
            pass

    return None


class GroqClient:
    def __init__(self):
        raw = os.getenv("GROQ_API_KEY", "")
        self.api_key = raw.strip().strip('"').strip("'")
        self.base_url = GROQ_BASE_URL
        if self.api_key:
            log.info("GROQ_API_KEY loaded (prefix: %s...)", self.api_key[:8])
        else:
            log.error("GROQ_API_KEY is not set — add it to .env")

    async def chat_completion(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        model: str = "llama-3.3-70b-versatile",
    ) -> dict:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict = {"model": model, "messages": messages, "max_tokens": 1024}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        async with aiohttp.ClientSession() as session:
            for attempt in range(3):
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                ) as resp:
                    if resp.status == 429:
                        wait = float(resp.headers.get("retry-after", 25))
                        log.warning("Rate limited — retrying in %.1fs (attempt %d/3)", wait, attempt + 1)
                        await asyncio.sleep(wait)
                        continue
                    if not resp.ok:
                        body = await resp.text()
                        log.error("Groq API error %d: %s", resp.status, body)
                        if resp.status == 400:
                            try:
                                err = json.loads(body)
                                failed_gen = err.get("error", {}).get("failed_generation", "")
                                recovered = _parse_legacy_tool_call(failed_gen)
                                if recovered:
                                    return recovered
                            except (json.JSONDecodeError, AttributeError):
                                pass
                        resp.raise_for_status()
                    return await resp.json()

        raise RuntimeError("Groq request failed after 3 attempts (rate limit)")
