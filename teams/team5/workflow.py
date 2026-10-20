# workflow 그래프 조립. build_graph()가 툴 로딩, RAG 인덱싱, 노드/엣지 연결을 하고 컴파일된 그래프를 돌려준다.
# 체크포인터 없이 컴파일한다. ainvoke가 돌려주는 전체 State(대화, 여행 조건, 후보, 일정, 승인 대기)를
# 호출자가 보관했다가 다음 턴에 user_input과 함께 다시 넘기면 대화가 이어진다.
# LLM을 부르는 노드(classify, extract_preferences, agent, plan_trip)는 async라서 그래프는 ainvoke로 호출해야 한다.

from app.llm import get_embeddings
from teams.team5.nodes.agent import make_agent_node
from teams.team5.nodes.approval import (
    ask_approval_again_node,
    execute_approved_tool_node,
    request_approval_node,
    resolve_approval_node,
)
from teams.team5.nodes.ask_clarification import ask_clarification_node
from teams.team5.nodes.classify import make_classify_node
from teams.team5.nodes.error import error_node
from teams.team5.nodes.extract_preferences import make_extract_preferences_node
from teams.team5.nodes.ingest_tool_results import ingest_tool_results_node
from teams.team5.nodes.plan_trip import make_plan_trip_node
from teams.team5.nodes.respond import respond_node
from teams.team5.nodes.retrieve import make_retrieve_node
from teams.team5.nodes.validate_preferences import validate_preferences_node
from teams.team5.rag.loader import load_and_split_docs
from teams.team5.rag.guide_tool import make_search_guide_tool
from teams.team5.rag.retriever import build_vectorstore
from teams.team5.routing import (
    route_after_agent,
    route_after_classify,
    route_after_execute,
    route_after_extract,
    route_after_ingest,
    route_after_plan_trip,
    route_after_retrieve,
    route_after_retrieve_for_plan,
    route_after_resolve_approval,
    route_after_tools,
    route_after_validate,
)
from teams.team5.state import MyState
from teams.team5.tools.registry import load_tools
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode


def _make_tools_node(tools: list[BaseTool]):
    """ToolNode를 감싸서 예외를 그대로 던지지 않고 {"error": ...}로 바꿔준다 (개별 툴 실패는 ToolNode가 이미 ToolMessage로 처리함)."""
    tool_node = ToolNode(tools)

    def tools_node(state: MyState) -> dict:
        try:
            return tool_node.invoke(state)
        except Exception as exc:
            return {"error": str(exc)}

    return tools_node


def build_graph() -> CompiledStateGraph:
    """프로세스 안에서 1회 호출. 툴 로딩 + RAG 인덱싱 후 노드를 조립해 컴파일한다.
    State는 저장하지 않는다 (호출자가 invoke 결과를 들고 있다가 다음 턴에 다시 넘긴다)."""
    vectorstore = build_vectorstore(load_and_split_docs(), get_embeddings())
    # RAG는 별도 노드가 아니라 Agent가 고르는 툴(search_guide_docs)이다: 질문/여행 계획 어디서든 필요할 때 문서를 찾는다.
    tools = [*load_tools(), make_search_guide_tool(vectorstore)]

    graph = StateGraph(MyState)

    graph.add_node("classify", make_classify_node())
    graph.add_node("extract_preferences", make_extract_preferences_node())
    graph.add_node("validate_preferences", validate_preferences_node)
    graph.add_node("ask_clarification", ask_clarification_node)
    graph.add_node("retrieve", make_retrieve_node(vectorstore))  # needs_guide 질문: agent 전에 문서 검색 강제
    graph.add_node("retrieve_for_plan", make_retrieve_node(vectorstore, for_plan=True))  # 일정 작성 직전 고정 질의 검색
    graph.add_node("agent", make_agent_node(tools))
    graph.add_node("tools", _make_tools_node(tools))  # ToolNode: 승인이 필요 없는 Tool 실행
    graph.add_node("ingest_tool_results", ingest_tool_results_node)
    graph.add_node("plan_trip", make_plan_trip_node())
    graph.add_node("request_approval", request_approval_node)
    graph.add_node("resolve_approval", resolve_approval_node)
    graph.add_node("ask_approval_again", ask_approval_again_node)
    graph.add_node("execute_approved_tool", execute_approved_tool_node)
    graph.add_node("respond", respond_node)
    graph.add_node("error", error_node)

    graph.add_edge(START, "classify")
    # 조건부 엣지: 분기 판단은 전부 routing.py의 함수가 하고, 여기서는 반환값 -> 노드 연결만 선언한다.
    graph.add_conditional_edges("classify", route_after_classify,
        ["error", "resolve_approval", "extract_preferences", "retrieve", "agent"])
    graph.add_conditional_edges("extract_preferences", route_after_extract, ["error", "validate_preferences"])
    graph.add_conditional_edges("validate_preferences", route_after_validate, ["ask_clarification", "agent"])
    graph.add_conditional_edges("agent", route_after_agent,
        ["error", "request_approval", "tools", "retrieve_for_plan", "respond"])
    graph.add_conditional_edges("retrieve", route_after_retrieve, ["error", "agent"])
    graph.add_conditional_edges("retrieve_for_plan", route_after_retrieve_for_plan, ["error", "plan_trip"])
    graph.add_conditional_edges("tools", route_after_tools, ["error", "ingest_tool_results"])
    graph.add_conditional_edges("ingest_tool_results", route_after_ingest, ["error", "agent"])
    graph.add_conditional_edges("plan_trip", route_after_plan_trip, ["error", "respond"])
    graph.add_conditional_edges("resolve_approval", route_after_resolve_approval,
        ["execute_approved_tool", "respond", "ask_approval_again"])
    graph.add_conditional_edges("execute_approved_tool", route_after_execute,
        ["error", "ingest_tool_results", "respond"])

    # 사용자에게 질문/승인 요청을 내보내는 노드와 respond/error는 턴을 끝낸다. 다음 턴은 State가 이어받는다.
    for node in ("ask_clarification", "request_approval", "ask_approval_again", "respond", "error"):
        graph.add_edge(node, END)

    return graph.compile()
