import json

from . import llm, reply_checker, tools

SYSTEM_PROMPT = (
    "You are the Northbean Coffee sales assistant. Recommend only coffees returned by the "
    "search_products or check_stock tools; never invent a product, price, or discount. "
    "If nothing in the catalog matches, say so honestly. Keep replies short."
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": (
                "Search the Northbean coffee catalog. Returns in-stock matches only "
                "unless in_stock_only is set to false."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "brew_method": {
                        "type": "string",
                        "description": "french_press, espresso, pour_over, aeropress, moka_pot, or cold_brew",
                    },
                    "max_price": {"type": "number"},
                    "decaf": {"type": "boolean"},
                    "in_stock_only": {"type": "boolean"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_stock",
            "description": "Look up one product by id: current stock and price.",
            "parameters": {
                "type": "object",
                "properties": {"product_id": {"type": "string"}},
                "required": ["product_id"],
            },
        },
    },
]

MAX_TOOL_ROUNDS = 3


def _run_tool(name: str, args: dict) -> list[dict]:
    if name == "search_products":
        return tools.search_products(**args)
    if name == "check_stock":
        row = tools.check_stock(args["product_id"])
        return [row] if row else []
    return []


def run_turn(user_message: str) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]
    seen_products: dict[str, dict] = {}
    reply = "Sorry, I'm having trouble right now — please try again."

    for _ in range(MAX_TOOL_ROUNDS):
        response = llm.complete(messages, tools=TOOLS)
        choice = response.choices[0].message
        tool_calls = choice.tool_calls or []
        if not tool_calls:
            reply = choice.content or reply
            break

        messages.append(
            {
                "role": "assistant",
                "content": choice.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in tool_calls
                ],
            }
        )
        for tc in tool_calls:
            args = json.loads(tc.function.arguments or "{}")
            results = _run_tool(tc.function.name, args)
            for p in results:
                seen_products[p["id"]] = p
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(results, default=str)})

    violations = reply_checker.check(reply, list(seen_products.values()), user_message)
    if violations:
        reply = reply_checker.safe_fallback(list(seen_products.values()))
    return reply
