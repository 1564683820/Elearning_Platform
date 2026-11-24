"""Base agent interface — all agents inherit from this."""
from abc import ABC, abstractmethod
from typing import Any


class BaseAgent(ABC):
    """Base agent that all domain agents extend.

    Provides the standard interface for:
    - run(): execute the agent's core task
    - get_name(): human-readable agent name
    - get_description(): what this agent does
    """

    @abstractmethod
    async def run(self, **kwargs) -> Any:
        """Execute the agent's primary task."""
        ...

    @classmethod
    def get_name(cls) -> str:
        return cls.__name__.replace("Agent", "")

    @classmethod
    def get_description(cls) -> str:
        return cls.__doc__ or ""
