"""
Service: Anthropic LLM Client
Responsibility: Centralised wrapper around the Anthropic Messages API.
All agents import this module instead of calling the SDK directly so that
model selection, retry logic, and token accounting live in one place.
"""

import os
import time
import logging
import anthropic

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 4096
_MAX_RETRIES = 3
_RETRY_DELAY = 2.0   # seconds


def call_claude(
    system_prompt: str,
    user_message: str,
    max_tokens: int = _MAX_TOKENS,
    temperature: float = 0.2,
) -> str:
    """
    Send a single-turn request to the Anthropic API and return the
    assistant's text response.

    Args:
        system_prompt: The system instruction / persona for this call.
        user_message:  The human-turn message.
        max_tokens:    Maximum tokens in the completion.
        temperature:   Sampling temperature (low = more deterministic).

    Returns:
        Assistant response text (str).

    Raises:
        RuntimeError: If all retries are exhausted.
    """
    client = anthropic.Anthropic()   # reads ANTHROPIC_API_KEY from env

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            logger.debug("Claude API call attempt %d/%d", attempt, _MAX_RETRIES)
            response = client.messages.create(
                model=_MODEL,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            text = response.content[0].text
            logger.debug("Claude API response received (%d chars)", len(text))
            return text

        except anthropic.RateLimitError:
            wait = _RETRY_DELAY * attempt
            logger.warning("Rate limited – retrying in %.1f s", wait)
            time.sleep(wait)

        except anthropic.APIStatusError as exc:
            logger.error("API status error: %s", exc)
            if attempt == _MAX_RETRIES:
                raise RuntimeError(f"Anthropic API error after {_MAX_RETRIES} attempts: {exc}") from exc
            time.sleep(_RETRY_DELAY)

    raise RuntimeError("Anthropic API call failed after all retries.")


def call_claude_multi_turn(
    system_prompt: str,
    messages: list,
    max_tokens: int = _MAX_TOKENS,
) -> str:
    """
    Multi-turn conversation call.  `messages` must be a list of
    {"role": "user"|"assistant", "content": str} dicts.
    """
    client = anthropic.Anthropic()

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = client.messages.create(
                model=_MODEL,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=messages,
            )
            return response.content[0].text
        except anthropic.RateLimitError:
            time.sleep(_RETRY_DELAY * attempt)
        except anthropic.APIStatusError as exc:
            if attempt == _MAX_RETRIES:
                raise RuntimeError(str(exc)) from exc
            time.sleep(_RETRY_DELAY)

    raise RuntimeError("Multi-turn call failed after all retries.")
