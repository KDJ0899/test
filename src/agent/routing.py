# 조건부 엣지 함수 모음. 분기 로직을 전부 여기 한 곳에 모아서 flow를 한눈에 볼 수 있게 한다.

from typing import Literal

from agent.state import AgentState
from langchain_core.messages import ToolMessage


def route_after_classify(state: AgentState) -> Literal["error", "retrieve", "agent"]:
    """error가 있으면 error로. 아니면 intent가 rag면 retrieve로, 그 외(chat/tool)는 agent로 바로."""
    if state.get("error"):
        return "error"
    return "retrieve" if state.get("intent") == "rag" else "agent"


def route_after_retrieve(state: AgentState) -> Literal["error", "agent"]:
    """error가 있으면 error로, 아니면 agent로."""
    return "error" if state.get("error") else "agent"


def route_after_agent(state: AgentState) -> Literal["error", "approval", "respond"]:
    """error가 있으면 error로. 아니면 tool_calls가 있으면 approval로, 없으면 respond로."""
    if state.get("error"):
        return "error"
    last_message = state["messages"][-1]
    if getattr(last_message, "tool_calls", None):
        return "approval"
    return "respond"


def route_after_approval(state: AgentState) -> Literal["tools", "agent"]:
    """approval 노드가 거절 ToolMessage를 추가했으면(마지막 메시지가 ToolMessage) agent로, 아니면 tools로."""
    last_message = state["messages"][-1]
    return "agent" if isinstance(last_message, ToolMessage) else "tools"


def route_after_tools(state: AgentState) -> Literal["error", "agent"]:
    """error가 있으면 error로, 아니면 agent로."""
    return "error" if state.get("error") else "agent"
