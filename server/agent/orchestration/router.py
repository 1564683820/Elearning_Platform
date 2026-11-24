"""Agent router — determines which agent handles a request."""

from typing import Any
from agent.agents.ppt_agent import PPTAgent
from agent.agents.exam_agent import ExamAgent
from agent.agents.xiao_e_agent import XiaoEAgent


_AGENTS = {
    "ppt": PPTAgent,
    "exam": ExamAgent,
    "xiao_e": XiaoEAgent,
}


def get_agent(name: str):
    """Get an agent class by name."""
    agent_cls = _AGENTS.get(name)
    if not agent_cls:
        raise ValueError("Unknown agent: {}. Available: {}".format(name, list(_AGENTS.keys())))
    return agent_cls()


async def route(domain: str, **kwargs) -> Any:
    """Route a request to the appropriate agent and execute it."""
    agent = get_agent(domain)
    return await agent.run(**kwargs)
