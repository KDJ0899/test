# approval 노드 HITL 통합 테스트. 실제 LLM 없이 가짜 agent 노드로 interrupt/resume 동작만 확인한다.

from agent.nodes.approval import approval_node
from agent.routing import route_after_agent, route_after_approval
from agent.state import AgentState
from agent.tools.local_tools import save_note
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import Command


def _build_hitl_test_graph():
    """approval 노드 전후만 떼어낸 작은 그래프. agent는 매 호출마다 다르게 응답하는 가짜 노드."""
    call_count = {"n": 0}

    async def fake_agent(state: AgentState) -> dict:
        call_count["n"] += 1
        if call_count["n"] == 1:
            tool_call = {"name": "save_note", "args": {"note": "hitl test"}, "id": "call1"}
            return {"messages": [AIMessage(content="", tool_calls=[tool_call])]}
        last = state["messages"][-1]
        return {"messages": [AIMessage(content=f"last_message_type={type(last).__name__}")]}

    async def fake_respond(state: AgentState) -> dict:
        return {}

    graph = StateGraph(AgentState)
    graph.add_node("agent", fake_agent)
    graph.add_node("approval", approval_node)
    graph.add_node("tools", ToolNode([save_note]))
    graph.add_node("respond", fake_respond)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route_after_agent, {"approval": "approval", "respond": "respond", "error": "respond"})
    graph.add_conditional_edges("approval", route_after_approval, {"tools": "tools", "agent": "agent"})
    graph.add_edge("tools", "agent")
    graph.add_edge("respond", END)
    return graph.compile(checkpointer=InMemorySaver())


async def test_approval_runs_tool_when_approved(monkeypatch, tmp_path):
    from agent.tools import local_tools

    monkeypatch.setattr(local_tools, "NOTES_PATH", tmp_path / "notes.jsonl")

    graph = _build_hitl_test_graph()
    config = {"configurable": {"thread_id": "approve-case"}}

    first = await graph.ainvoke({"messages": [HumanMessage("메모 저장해줘")]}, config)
    assert first["__interrupt__"][0].value == {
        "type": "approval_request",
        "tool": "save_note",
        "args": {"note": "hitl test"},
        "message": "'save_note' 실행 전 승인이 필요합니다. 인자: {'note': 'hitl test'}",
    }

    second = await graph.ainvoke(Command(resume={"approved": True}), config)
    assert "last_message_type=ToolMessage" in second["messages"][-1].content
    assert (tmp_path / "notes.jsonl").exists()


async def test_approval_skips_tool_when_rejected(monkeypatch, tmp_path):
    from agent.tools import local_tools

    monkeypatch.setattr(local_tools, "NOTES_PATH", tmp_path / "notes.jsonl")

    graph = _build_hitl_test_graph()
    config = {"configurable": {"thread_id": "reject-case"}}

    await graph.ainvoke({"messages": [HumanMessage("메모 저장해줘")]}, config)
    second = await graph.ainvoke(Command(resume={"approved": False}), config)

    assert "last_message_type=ToolMessage" in second["messages"][-1].content
    assert not (tmp_path / "notes.jsonl").exists()
