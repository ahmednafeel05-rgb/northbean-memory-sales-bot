import logging
import os

import litellm

logger = logging.getLogger(__name__)

PRIMARY_MODEL = os.environ.get("REPLY_MODEL_PRIMARY", "vertex_ai/gemini-3.5-flash")
FALLBACK_MODEL = os.environ.get("REPLY_MODEL_FALLBACK", "groq/openai/gpt-oss-20b")
VERTEX_PROJECT = os.environ.get("VERTEX_PROJECT")
VERTEX_LOCATION = os.environ.get("VERTEX_LOCATION", "global")


def complete(messages, tools=None, **kwargs):
    """Reply-model call. Retry once on the primary, then switch provider (failure mode table, DESIGN_BRIEF §12).
    Each attempt's failure is logged -- a prior session burned a full day's Groq quota with
    Gemini silently failing every single call and no record of why."""
    last_error = None
    for model in (PRIMARY_MODEL, PRIMARY_MODEL, FALLBACK_MODEL):
        call_kwargs = dict(kwargs)
        if model.startswith("vertex_ai/") and VERTEX_PROJECT:
            call_kwargs["vertex_project"] = VERTEX_PROJECT
            call_kwargs["vertex_location"] = VERTEX_LOCATION
        try:
            return litellm.completion(model=model, messages=messages, tools=tools, **call_kwargs)
        except Exception as exc:
            logger.warning("LLM call failed on %s: %s", model, exc)
            last_error = exc
    raise RuntimeError("both LLM providers failed") from last_error
