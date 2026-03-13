from typing import TypeVar

from msagent.agents.context import AgentContext
from msagent.agents.state import AgentState

StateSchema = TypeVar("StateSchema", bound=AgentState)
StateSchemaType = type[StateSchema]

ContextSchema = TypeVar("ContextSchema", bound=AgentContext)
ContextSchemaType = type[ContextSchema]
