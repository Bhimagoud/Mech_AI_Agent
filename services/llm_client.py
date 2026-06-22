"""
Service: LLM Client (legacy shim)
-----------------------------------
This module now delegates all calls to services.llm_router so that
existing code that imports `call_claude` continues to work unchanged.

New code should import from services.llm_router directly:
    from services.llm_router import call_llm
"""

from services.llm_router import call_llm, call_claude   # noqa: F401 — re-export

__all__ = ["call_llm", "call_claude"]
