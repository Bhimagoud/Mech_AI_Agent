"""
Service: LLM Router
--------------------
Single call interface that routes to the configured LLM provider.

Supported providers (set LLM_PROVIDER in .env):
  - anthropic  →  Claude (claude-sonnet-4-6 by default)
  - groq       →  Llama / Mixtral via Groq API (ultra-fast inference)

All agents import `call_llm` from here instead of calling any
SDK directly, so switching provider is a one-line env change.
"""

import os
import time
import logging

logger = logging.getLogger(__name__)

# ── Provider selection ────────────────────────────────────────────────────────
PROVIDER = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()

# ── Anthropic settings ───────────────────────────────────────────────────────
_ANTHROPIC_MODEL      = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
_ANTHROPIC_MAX_TOKENS = int(os.getenv("ANTHROPIC_MAX_TOKENS", "4096"))

# ── Groq settings ────────────────────────────────────────────────────────────
_GROQ_MODEL      = os.getenv("GROQ_MODEL", "llama-3.1-70b-versatile")
_GROQ_MAX_TOKENS = int(os.getenv("GROQ_MAX_TOKENS", "4096"))

# ── Retry policy ─────────────────────────────────────────────────────────────
_MAX_RETRIES  = 3
_RETRY_DELAY  = 2.0  # seconds (multiplied by attempt number on rate-limit)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def call_llm(
    system_prompt: str,
    user_message: str,
    temperature: float = 0.2,
    max_tokens: int = None,
) -> str:
    """
    Send a single-turn LLM request and return the assistant's text response.

    Routes to the provider defined by LLM_PROVIDER env var.

    Args:
        system_prompt: The system/persona instruction.
        user_message:  The human-turn message.
        temperature:   Sampling temperature (lower = more deterministic).
        max_tokens:    Override the default max tokens for this call.

    Returns:
        Assistant response as a plain string.

    Raises:
        RuntimeError: If all retries are exhausted.
    """
    logger.debug("LLM Router: provider=%s  temp=%.2f", PROVIDER, temperature)

    if PROVIDER == "groq":
        return _call_groq(
            system_prompt, user_message, temperature,
            max_tokens or _GROQ_MAX_TOKENS,
        )
    else:  # default: anthropic
        return _call_anthropic(
            system_prompt, user_message, temperature,
            max_tokens or _ANTHROPIC_MAX_TOKENS,
        )


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------

def _call_anthropic(
    system_prompt: str,
    user_message: str,
    temperature: float,
    max_tokens: int,
) -> str:
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic package not installed. Run: pip install anthropic")

    client = anthropic.Anthropic()   # reads ANTHROPIC_API_KEY from env

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = client.messages.create(
                model=_ANTHROPIC_MODEL,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            text = response.content[0].text
            logger.debug("Anthropic: received %d chars (model=%s)", len(text), _ANTHROPIC_MODEL)
            return text

        except anthropic.RateLimitError:
            wait = _RETRY_DELAY * attempt
            logger.warning("Anthropic: rate-limited, retrying in %.1f s (attempt %d)", wait, attempt)
            time.sleep(wait)

        except anthropic.APIStatusError as exc:
            logger.error("Anthropic API error: %s", exc)
            if attempt == _MAX_RETRIES:
                raise RuntimeError(f"Anthropic API error after {_MAX_RETRIES} attempts: {exc}") from exc
            time.sleep(_RETRY_DELAY)

    raise RuntimeError("Anthropic: all retries exhausted.")


def _call_groq(
    system_prompt: str,
    user_message: str,
    temperature: float,
    max_tokens: int,
) -> str:
    try:
        from groq import Groq
    except ImportError:
        raise RuntimeError("groq package not installed. Run: pip install groq")

    client = Groq()   # reads GROQ_API_KEY from env

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=_GROQ_MODEL,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_message},
                ],
            )
            text = response.choices[0].message.content
            logger.debug("Groq: received %d chars (model=%s)", len(text), _GROQ_MODEL)
            return text

        except Exception as exc:
            err_str = str(exc)
            if "rate" in err_str.lower() or "429" in err_str:
                wait = _RETRY_DELAY * attempt
                logger.warning("Groq: rate-limited, retrying in %.1f s", wait)
                time.sleep(wait)
            elif attempt == _MAX_RETRIES:
                raise RuntimeError(f"Groq API error after {_MAX_RETRIES} attempts: {exc}") from exc
            else:
                logger.warning("Groq attempt %d failed: %s", attempt, exc)
                time.sleep(_RETRY_DELAY)

    raise RuntimeError("Groq: all retries exhausted.")


# ---------------------------------------------------------------------------
# Backward-compat shim — keeps existing llm_client.py imports working
# ---------------------------------------------------------------------------

def call_claude(system_prompt: str, user_message: str, temperature: float = 0.2) -> str:
    """Backward-compatible alias — routes through the full LLM router."""
    return call_llm(system_prompt, user_message, temperature)
