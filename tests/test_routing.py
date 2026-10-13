# routing.py 조건부 엣지 함수 단위 테스트.

from agent.routing import (
    route_after_agent,
    route_after_approval,
    route_after_classify,
    route_after_retrieve,
    route_after_tools,
)
from langchain_core.messages import AIMessage, ToolMessage


def test_route_after_classify_error_first():
    assert route_after_classify({"error": "boom", "intent": "rag"}) == "error"


def test_route_after_classify_rag():
    assert route_after_classify({"intent": "rag"}) == "retrieve"


def test_route_after_classify_chat_and_tool():
    assert route_after_classify({"intent": "chat"}) == "agent"
    assert route_after_classify({"intent": "tool"}) == "agent"


def test_route_after_retrieve():
    assert route_after_retrieve({"error": "boom"}) == "error"
    assert route_after_retrieve({}) == "agent"


def test_route_after_agent_error_first():
    assert route_after_agent({"error": "boom", "messages": [AIMessage(content="hi")]}) == "error"


def test_route_after_agent_with_tool_calls():
    msg = AIMessage(content="", tool_calls=[{"name": "calculate", "args": {}, "id": "1"}])
    assert route_after_agent({"messages": [msg]}) == "approval"


def test_route_after_agent_without_tool_calls():
    msg = AIMessage(content="답변")
    assert route_after_agent({"messages": [msg]}) == "respond"


def test_route_after_approval():
    assert route_after_approval({"messages": [ToolMessage(content="거절", tool_call_id="1")]}) == "agent"
    assert route_after_approval({"messages": [AIMessage(content="", tool_calls=[])]}) == "tools"


def test_route_after_tools():
    assert route_after_tools({"error": "boom"}) == "error"
    assert route_after_tools({}) == "agent"
