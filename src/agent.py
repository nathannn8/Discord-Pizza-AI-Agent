from src.client import GroqClient
from src.tools_registry import TOOL_DEFINITIONS, dispatch
from src.logger import get_logger

log = get_logger("agent")

MAX_ITERATIONS = 10

SYSTEM_PROMPT = """You are a helpful AI assistant and pizza ordering bot in a Discord server.
You have two tools: web_search (live internet search) and place_order (submit a pizza order).

GENERAL RULES:
1. For news, current events, or recent facts: call web_search and answer using those results directly.
2. NEVER say your information may be outdated. You have live search.
3. NEVER tell users to check other sources. Answer directly.
4. Be concise. Plain text only.

PIZZA ORDERING RULES:
When a user wants to order a pizza, guide them step by step through the menu below.
Collect ALL of the following before calling place_order:
  - Customer name
  - Phone number
  - Delivery location/address
  - Dough type
  - Sauce
  - Toppings (can be multiple)
  - Cook style
  - Any special notes (optional)

Once you have everything, confirm the full order with the user, then call place_order.

PIZZA MENU:
Dough:    Classic | Thin & Crispy | Thick & Fluffy | Stuffed Crust | Gluten-Free
Sauce:    Tomato Marinara | BBQ | Alfredo | Pesto | Spicy Arrabbiata
Toppings: Pepperoni, Salami, Ham, Chicken, Beef, Mozzarella, Cheddar, Parmesan,
          Mushrooms, Olives, Onions, Bell Peppers, Jalapeños, Spinach, Tomatoes, Corn, Pineapple
Cook:     Regular | Well Done | Light Bake"""


_DISCLAIMER_PREFIXES = (
    "note:", "please note", "disclaimer:", "important note",
    "as of my training", "my knowledge", "i cannot guarantee",
    "this information may", "these updates reflect",
)


def _strip_disclaimer(text: str) -> str:
    lines = text.splitlines()
    cleaned = [
        line for line in lines
        if not line.lower().lstrip().startswith(_DISCLAIMER_PREFIXES)
    ]
    return "\n".join(cleaned).strip()


class Agent:
    def __init__(self, model: str = "llama-3.3-70b-versatile"):
        self.client = GroqClient()
        self.model = model
        log.info("Agent initialised with model: %s", self.model)

    async def run(
        self,
        user_message: str,
        history: list[dict] | None = None,
    ) -> tuple[str, list[dict]]:
        """
        Run the agentic loop.
        Returns (response_text, updated_history) so callers can maintain
        multi-turn context (e.g. for the pizza ordering flow).
        history should contain only user/assistant/tool messages — no system prompt.
        """
        conversation: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        if history:
            conversation.extend(history)
        conversation.append({"role": "user", "content": user_message})

        log.debug("Starting agentic loop | history_len=%d | message: %r", len(history or []), user_message)

        for iteration in range(1, MAX_ITERATIONS + 1):
            log.debug("Iteration %d — calling model", iteration)

            response = await self.client.chat_completion(
                messages=conversation,
                tools=TOOL_DEFINITIONS,
                model=self.model,
            )

            choice = response["choices"][0]
            assistant_message = choice["message"]
            finish_reason = choice.get("finish_reason", "")

            log.debug("Iteration %d — finish_reason: %s", iteration, finish_reason)

            sanitized: dict = {"role": "assistant", "content": assistant_message.get("content")}
            if assistant_message.get("tool_calls"):
                sanitized["tool_calls"] = assistant_message["tool_calls"]
            conversation.append(sanitized)

            if finish_reason != "tool_calls" or not sanitized.get("tool_calls"):
                final = sanitized.get("content") or ""
                final = _strip_disclaimer(final)
                log.info("Agent finished in %d iteration(s) | response length: %d", iteration, len(final))
                # Return updated history (everything after the system prompt)
                updated_history = conversation[1:]
                return final, updated_history

            for tool_call in sanitized["tool_calls"]:
                name = tool_call["function"]["name"]
                arguments = tool_call["function"]["arguments"]
                log.info("Tool call: %s | args: %s", name, arguments)

                result = await dispatch(name, arguments)
                log.debug("Tool result for %s: %s", name, result[:300] if len(result) > 300 else result)

                label = "TOOL RESULT" if name == "place_order" else "LIVE SEARCH RESULTS"
                conversation.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": f"{label}:\n{result}",
                    }
                )

        log.warning("Agent hit MAX_ITERATIONS (%d) without finishing", MAX_ITERATIONS)
        updated_history = conversation[1:]
        return "I reached the maximum number of steps without a final answer.", updated_history
