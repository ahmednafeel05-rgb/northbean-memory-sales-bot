import os

import litellm

PRIMARY_MODEL = os.environ.get("REPLY_MODEL_PRIMARY", "gemini/gemini-2.5-flash")
FALLBACK_MODEL = os.environ.get("REPLY_MODEL_FALLBACK", "groq/openai/gpt-oss-20b")


def complete(messages, tools=None):
    """Reply-model call. Retry once on the primary, then switch provider (failure mode table, DESIGN_BRIEF §12)."""
    last_error = None
    for model in (PRIMARY_MODEL, PRIMARY_MODEL, FALLBACK_MODEL):
        try:
            return litellm.completion(model=model, messages=messages, tools=tools)
        except Exception as exc:
            last_error = exc
    raise RuntimeError("both LLM providers failed") from last_error
