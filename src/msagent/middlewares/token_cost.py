"""Middleware for tracking token usage."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage

from msagent.agents.context import AgentContext
from msagent.agents.state import AgentState
from msagent.core.logging import get_logger

if TYPE_CHECKING:
    from langgraph.runtime import Runtime

logger = get_logger(__name__)


class TokenCostMiddleware(AgentMiddleware[AgentState, AgentContext]):
    """Middleware to track token usage.

    Extracts usage metadata from model responses and updates state with:
    - current_input_tokens: Input tokens for this call
    - current_output_tokens: Output tokens accumulated for the turn
    """

    state_schema = AgentState

    async def aafter_model(
        self, state: AgentState, runtime: Runtime[AgentContext]
    ) -> dict[str, Any] | None:
        """Extract usage metadata after each model call."""
        messages = state.get("messages", [])
        if not messages:
            return None

        latest_message = messages[-1]
        if not isinstance(latest_message, AIMessage):
            return None

        usage_metadata = getattr(latest_message, "usage_metadata", None)
        if not usage_metadata:
            return None

        input_tokens = usage_metadata.get("input_tokens", 0)
        output_tokens = usage_metadata.get("output_tokens", 0)

        update: dict[str, Any] = {
            "current_input_tokens": input_tokens,
            "current_output_tokens": output_tokens,
        }
        logger.debug("Token usage: %s in, %s out", input_tokens, output_tokens)

        return update
