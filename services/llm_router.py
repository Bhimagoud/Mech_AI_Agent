"""
Service: LLM Router
--------------------
Single call interface that routes to the configured LLM provider.

Supported providers (set LLM_PROVIDER in .env):
  - openai     →  OpenAI (gpt-4o by default)
  - groq       →  Llama / Mixtral via Groq API (ultra-fast inference)
  - gemini     →  Google Gemini API

All agents import `call_llm` from here instead of calling any
SDK directly, so switching provider is a one-line env change.
"""

import os
import time
import logging

logger = logging.getLogger(__name__)

# ── Provider selection ────────────────────────────────────────────────────────
PROVIDER = os.getenv("LLM_PROVIDER", "openai").strip().lower()

# ── OpenAI settings ──────────────────────────────────────────────────────────
_OPENAI_MODEL      = os.getenv("OPENAI_MODEL", "gpt-4o")
_OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "4096"))

# ── Groq settings ────────────────────────────────────────────────────────────
_GROQ_MODEL      = os.getenv("GROQ_MODEL", "llama-3.1-70b-versatile")
_GROQ_MAX_TOKENS = int(os.getenv("GROQ_MAX_TOKENS", "4096"))

# ── Gemini settings ──────────────────────────────────────────────────────────
_GEMINI_MODEL      = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
_GEMINI_MAX_TOKENS = int(os.getenv("GEMINI_MAX_TOKENS", "4096"))

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
    elif PROVIDER == "gemini":
        return _call_gemini(
            system_prompt, user_message, temperature,
            max_tokens or _GEMINI_MAX_TOKENS,
        )
    else:  # default: openai
        return _call_openai(
            system_prompt, user_message, temperature,
            max_tokens or _OPENAI_MAX_TOKENS,
        )


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------

def _call_openai(
    system_prompt: str,
    user_message: str,
    temperature: float,
    max_tokens: int,
) -> str:
    try:
        import openai
    except ImportError:
        raise RuntimeError("openai package not installed. Run: pip install openai")

    client = openai.OpenAI()   # reads OPENAI_API_KEY from env

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=_OPENAI_MODEL,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
            )
            text = response.choices[0].message.content
            logger.debug("OpenAI: received %d chars (model=%s)", len(text), _OPENAI_MODEL)
            return text

        except Exception as exc:
            err_str = str(exc)
            if attempt == _MAX_RETRIES:
                raise RuntimeError(f"OpenAI API error after {_MAX_RETRIES} attempts: {exc}") from exc
            elif "rate" in err_str.lower() or "429" in err_str:
                wait = _RETRY_DELAY * attempt
                logger.warning("OpenAI: rate-limited, retrying in %.1f s (attempt %d)", wait, attempt)
                time.sleep(wait)
            else:
                logger.warning("OpenAI attempt %d failed: %s", attempt, exc)
                time.sleep(_RETRY_DELAY)

    raise RuntimeError("OpenAI: all retries exhausted.")


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
            if attempt == _MAX_RETRIES:
                raise RuntimeError(f"Groq API error after {_MAX_RETRIES} attempts: {exc}") from exc
            elif "rate" in err_str.lower() or "429" in err_str:
                wait = _RETRY_DELAY * attempt
                logger.warning("Groq: rate-limited, retrying in %.1f s", wait)
                time.sleep(wait)
            else:
                logger.warning("Groq attempt %d failed: %s", attempt, exc)
                time.sleep(_RETRY_DELAY)

    raise RuntimeError("Groq: all retries exhausted.")


def _call_gemini(
    system_prompt: str,
    user_message: str,
    temperature: float,
    max_tokens: int,
) -> str:
    try:
        import google.generativeai as genai
    except ImportError:
        raise RuntimeError("google-generativeai package not installed. Run: pip install google-generativeai")

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not found in environment.")
    
    genai.configure(api_key=api_key)

    generation_config = genai.types.GenerationConfig(
        temperature=temperature,
        max_output_tokens=max_tokens,
        response_mime_type="application/json",
    )

    model = genai.GenerativeModel(
        model_name=_GEMINI_MODEL,
        system_instruction=system_prompt,
    )

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = model.generate_content(
                user_message,
                generation_config=generation_config
            )
            text = response.text
            logger.debug("Gemini: received %d chars (model=%s)", len(text), _GEMINI_MODEL)
            return text

        except Exception as exc:
            err_str = str(exc)
            if attempt == _MAX_RETRIES:
                raise RuntimeError(f"Gemini API error after {_MAX_RETRIES} attempts: {exc}") from exc
            elif "rate" in err_str.lower() or "429" in err_str or "quota" in err_str.lower() or "429" in err_str:
                wait = _RETRY_DELAY * attempt
                logger.warning("Gemini: rate-limited/quota, retrying in %.1f s", wait)
                time.sleep(wait)
            else:
                logger.warning("Gemini attempt %d failed: %s", attempt, exc)
                time.sleep(_RETRY_DELAY)

    raise RuntimeError("Gemini: all retries exhausted.")


# ---------------------------------------------------------------------------
# Backward-compat shim — keeps existing llm_client.py imports working
# ---------------------------------------------------------------------------

def call_claude(system_prompt: str, user_message: str, temperature: float = 0.2) -> str:
    """Backward-compatible alias — routes through the full LLM router."""
    return call_llm(system_prompt, user_message, temperature)
