"""Provider-agnostic structured-output call.

The storefront does not care who serves the model. Both backends are given the
same JSON schema -- including the enum of real skill IDs -- so the hard constraint
that the planner cannot invent a skill holds either way.

Pick with LLM_PROVIDER=openai|anthropic, or leave it unset and whichever key is
present wins.
"""
from __future__ import annotations

import json
import os
from typing import Any


class LLMError(RuntimeError):
    pass


def active_provider() -> str:
    explicit = os.environ.get("LLM_PROVIDER", "").strip().lower()
    if explicit in {"openai", "anthropic"}:
        return explicit
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return "anthropic"
    raise LLMError(
        "No model credentials. Put OPENAI_API_KEY or ANTHROPIC_API_KEY in .env."
    )


def default_model(provider: str) -> str:
    env = os.environ.get("COMPILER_MODEL", "").strip()
    if env:
        return env
    return "gpt-4o-mini" if provider == "openai" else "claude-opus-5-5"


def structured_call(system: str, user: str, schema: dict[str, Any],
                    schema_name: str = "plan", model: str | None = None) -> dict[str, Any]:
    """Return a dict guaranteed to match `schema`."""
    provider = active_provider()
    model = model or default_model(provider)
    if provider == "openai":
        return _openai(system, user, schema, schema_name, model)
    return _anthropic(system, user, schema, model)


def _openai(system: str, user: str, schema: dict, name: str, model: str) -> dict:
    import openai  # noqa: PLC0415

    client = openai.OpenAI()
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": name, "schema": schema, "strict": True},
            },
            temperature=0,
        )
    except openai.AuthenticationError as exc:
        raise LLMError("OpenAI rejected the key in .env") from exc
    except openai.RateLimitError as exc:
        raise LLMError("OpenAI rate limit or no credit on this key") from exc
    except openai.APIError as exc:
        raise LLMError(f"OpenAI error: {exc}") from exc

    choice = resp.choices[0]
    if choice.finish_reason == "length":
        raise LLMError("model hit the token limit before finishing the plan")
    if getattr(choice.message, "refusal", None):
        raise LLMError(f"model declined: {choice.message.refusal}")
    try:
        return json.loads(choice.message.content or "")
    except json.JSONDecodeError as exc:
        raise LLMError(f"model returned unparseable JSON: {exc}") from exc


def _anthropic(system: str, user: str, schema: dict, model: str) -> dict:
    import anthropic  # noqa: PLC0415

    request = dict(
        model=model,
        max_tokens=16000,
        system=[{"type": "text", "text": system,
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
        output_config={
            "effort": os.environ.get("COMPILER_EFFORT", "medium"),
            "format": {"type": "json_schema", "schema": schema},
        },
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    # COMPILER_SPEED=fast: the same model, generating faster at a higher price.
    # The wait is almost all output tokens, so this is the latency knob.
    fast = os.environ.get("COMPILER_SPEED", "").strip().lower() == "fast"
    try:
        client = anthropic.Anthropic()
        if fast:
            try:
                resp = client.beta.messages.create(
                    **{**request, "betas": request["betas"] + ["fast-mode-2026-02-01"]},
                    speed="fast")
            except anthropic.RateLimitError:
                resp = client.beta.messages.create(**request)  # fast mode has its own limit
        else:
            resp = client.beta.messages.create(**request)
    except anthropic.AuthenticationError as exc:
        raise LLMError("Anthropic rejected the key in .env") from exc
    except anthropic.APIError as exc:
        raise LLMError(f"Anthropic error: {exc}") from exc
    except TypeError as exc:
        if "authentication" in str(exc).lower():
            raise LLMError("No Anthropic credentials found") from exc
        raise

    if resp.stop_reason == "refusal":
        raise LLMError("model declined this request")
    if resp.stop_reason == "max_tokens":
        raise LLMError("model hit the token limit before finishing the plan")
    text = next((b.text for b in resp.content if b.type == "text"), "")
    if not text:
        raise LLMError("model returned no text")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMError(f"model returned unparseable JSON: {exc}") from exc
