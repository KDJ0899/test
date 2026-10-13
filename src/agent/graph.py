# workflow 그래프 조립. FastAPI는 build_graph()만 호출해서 컴파일된 그래프를 받는다 (CLAUDE.md 3장 계약).

from agent.llm import get_embeddings
from agent.nodes.agent import make_agent_node
from agent.nodes.approval import approval_node
from agent.nodes.classify import make_classify_node
from agent.nodes.error import error_node
from agent.nodes.respond import respond_node
from agent.nodes.retrieve import make_retrieve_node
from agent.rag.loader import load_and_split_docs
from agent.rag.retriever import build_vectorstore
from agent.routing import (
    route_after_agent,
    route_after_approval,
    route_after_classify,
    route_after_retrieve,
    route_after_tools,
)
from agent.state import AgentState
from agent.tools.registry import load_tools
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode


def _make_tools_node(tools: list[BaseTool]):
    """ToolNode를 감싸서 예외를 그대로 던지지 않고 {"error": ...}로 바꿔준다 (개별 툴 실패는 ToolNode가 이미 ToolMessage로 처리함)."""
    tool_node = ToolNode(tools)

    async def tools_node(state: AgentState) -> dict:
        try:
            return await tool_node.ainvoke(state)
        except Exception as exc:
            return {"error": str(exc)}

    return tools_node


async def build_graph(checkpointer: BaseCheckpointSaver | None = None) -> CompiledStateGraph:
    """앱 시작 시 1회 호출. 툴 로딩 + RAG 인덱싱 후
    classify -> (retrieve) -> agent -> (approval) -> tools -> agent -> respond 흐름을 조립한다.
    각 노드의 예외는 error 필드로 변환되어 error 노드로 모인다 (routing.py 참고).

    checkpointer는 멀티턴 대화 기억용이 아니라 HITL interrupt/resume을 위해 필요하다 (LangGraph 구조상 필수).
    대화 이력 자체는 UI가 들고 있다가 매 요청마다 messages에 전체를 담아 보낸다고 가정한다 (thread_id는 요청 단위로 새로 발급).
    기본은 InMemorySaver(예제용, 재시작 시 날아감). 교체하고 싶으면 인자로 넘긴다.
    """
    tools = await load_tools()

    docs = load_and_split_docs()
    vectorstore = await build_vectorstore(docs, get_embeddings())

    graph = StateGraph(AgentState)

    graph.add_node("classify", make_classify_node())
    graph.add_node("retrieve", make_retrieve_node(vectorstore))
    graph.add_node("agent", make_agent_node(tools))
    graph.add_node("approval", approval_node)
    graph.add_node("tools", _make_tools_node(tools))
    graph.add_node("respond", respond_node)
    graph.add_node("error", error_node)

    graph.add_edge(START, "classify")
    # error면 error로, intent가 rag면 retrieve로, 아니면 agent로 바로. 조건부 엣지 로직은 routing.py에 모아둔다.
    graph.add_conditional_edges(
        "classify", route_after_classify, {"error": "error", "retrieve": "retrieve", "agent": "agent"}
    )
    graph.add_conditional_edges("retrieve", route_after_retrieve, {"error": "error", "agent": "agent"})
    # error면 error로, tool_calls 있으면 승인 여부를 확인하는 approval로, 없으면 respond로.
    graph.add_conditional_edges(
        "agent", route_after_agent, {"error": "error", "approval": "approval", "respond": "respond"}
    )
    # approval에서 승인/승인 불필요면 tools로, 거절이면 agent로.
    graph.add_conditional_edges("approval", route_after_approval, {"tools": "tools", "agent": "agent"})
    graph.add_conditional_edges("tools", route_after_tools, {"error": "error", "agent": "agent"})
    graph.add_edge("respond", END)
    graph.add_edge("error", END)

    return graph.compile(checkpointer=checkpointer or InMemorySaver())
