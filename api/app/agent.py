import json

from . import llm, reply_checker, tools

SYSTEM_PROMPT = (
    "You are the Northbean Coffee sales assistant. Recommend only coffees returned by the "
    "search_products or check_stock tools; never invent a product, price, or discount. "
    "If nothing in the catalog matches, say so honestly. Keep replies short.\n\n"
    "When the customer names a place, origin, or specific coffee (e.g. 'Honduras', 'Guji', "
    "'order me the Marcala'), call search_products with that text as the query parameter -- "
    "don't rely on brew_method/max_price/decaf alone to find it. If that returns more than one "
    "match, list the matches briefly and ask which one they mean before proceeding -- unless "
    "what you know about this customer or their current message already names one of the "
    "matches exactly (e.g. they said 'Ethiopia Guji' and the matches are 'Ethiopia Guji' and "
    "'Ethiopia Guji Natural Reserve'): then treat the exact name they used as the match, "
    "proceed with it, and don't mention the other similarly-named variant. This demo "
    "has no checkout system, so 'order'/'buy' means confirm the exact matching product (name, "
    "price, stock) enthusiastically as their sales assistant -- never claim to have placed a "
    "real order.\n\n"
    "Reply in plain conversational sentences only: no markdown (no **bold**, no * bullet "
    "lists, no headers). Use plain dashes or commas if you need to list a few items.\n\n"
    "If the customer asks something unrelated to Northbean coffee or coffee shopping (e.g. "
    "general tech questions, unrelated products, 'what can you do'), say plainly that you're "
    "Northbean's coffee sales assistant and can only help with coffee recommendations and "
    "orders, then invite them back to coffee. Don't attempt to answer the unrelated question.\n\n"
    "If the customer objects to the price (too expensive, can't afford it, out of budget) and "
    "you haven't already offered a discount this conversation, call apply_discount. If it "
    "returns newly_granted=true, offer that exact code and percent enthusiastically as a "
    "one-time first-order discount. If newly_granted=false, they've already used their one-time "
    "discount -- don't offer it again. Never state a discount code or percentage that didn't "
    "come from apply_discount's result."
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
                    "query": {
                        "type": "string",
                        "description": (
                            "Free-text match against the product name or origin, e.g. "
                            "'Honduras', 'Guji', or 'Marcala'. Use this whenever the customer "
                            "names a place, origin, or specific coffee."
                        ),
                    },
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

DISCOUNT_TOOL = {
    "type": "function",
    "function": {
        "name": "apply_discount",
        "description": (
            "Check this customer's eligibility for the one-time 10% first-order discount and "
            "grant it if they haven't already had one. Takes no arguments -- the customer is "
            "already known from the conversation."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}

MAX_TOOL_ROUNDS = 3


def _run_tool(name: str, args: dict, customer_id) -> list[dict] | dict:
    """Anything that fails here degrades the reply, never crashes it (I3, NFR-3): a tool
    result of {"error": ...} just gives the model something honest to apologise with."""
    try:
        if name == "search_products":
            return tools.search_products(**args)
        if name == "check_stock":
            row = tools.check_stock(args["product_id"])
            return [row] if row else []
        if name == "apply_discount" and customer_id is not None:
            return tools.apply_discount(customer_id)
        return []
    except Exception:
        return {"error": "catalog temporarily unavailable"}


def run_turn(user_message: str, memory_context: str = "", customer_id=None) -> str:
    system_prompt = f"{SYSTEM_PROMPT}\n\n{memory_context}" if memory_context else SYSTEM_PROMPT
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    tools_for_call = TOOLS + [DISCOUNT_TOOL] if customer_id is not None else TOOLS
    seen_products: dict[str, dict] = {}
    discount_result = None
    reply = "Sorry, I'm having trouble right now — please try again."

    for _ in range(MAX_TOOL_ROUNDS):
        try:
            response = llm.complete(messages, tools=tools_for_call)
        except Exception:
            break
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
            result = _run_tool(tc.function.name, args, customer_id)
            if tc.function.name == "apply_discount" and isinstance(result, dict) and "error" not in result:
                discount_result = result
            elif isinstance(result, list):
                for p in result:
                    seen_products[p["id"]] = p
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result, default=str)})

    violations = reply_checker.check(reply, list(seen_products.values()), user_message, discount_result)
    if violations:
        reply = reply_checker.safe_fallback(list(seen_products.values()))
    return reply
