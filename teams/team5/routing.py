# 조건부 엣지 함수 모음. 분기 로직을 전부 여기 한 곳에 모아서 flow를 한눈에 볼 수 있게 한다.
# 각 함수는 State만 읽는 순수 함수이고, 반환값은 workflow.py의 add_conditional_edges 매핑 키와 같다.
# 노드는 예외를 던지지 않고 state["error"]에 기록하므로, 대부분의 분기는 "error가 있으면 error 노드로"로 시작한다.

from typing import Literal

from teams.team5.state import Mystate
from teams.team5.tools.registry import REQUIRES_APPROVAL
from langchain_core.messages import AIMessage


def _tool_calls(state: Mystate) -> list[dict]:
    last_message = state["messages"][-1]
    return getattr(last_message, "tool_calls", None) or []


def route_after_classify(
    state: Mystate,
) -> Literal["error", "resolve_approval", "extract_preferences", "retrieve", "agent"]:
    """error면 error로. 승인 대기가 있으면 의도 분류보다 승인 처리를 우선한다. trip은 조건 수집으로, 가이드가 필요한 질문은 retrieve로, 나머지는 agent로 간다."""
    if state.get("error"):
        return "error"
    if state.get("pending_approval"):
        return "resolve_approval"
    intent = state.get("intent")
    if intent == "trip":
        return "extract_preferences"
    if state.get("needs_guide"):
        return "retrieve"  # 가이드 문서가 필요한 질문은 LLM의 툴 선택에 맡기지 않고 먼저 검색한다.
    return "agent"  # 그 외 chat / qa


def route_after_extract(state: Mystate) -> Literal["error", "validate_preferences"]:
    return "error" if state.get("error") else "validate_preferences"


def route_after_validate(state: Mystate) -> Literal["ask_clarification", "agent"]:
    """필수 조건이 부족하거나 확인 질문이 필요하면 질문하고 턴을 끝내고, 충분하면 agent로 간다."""
    if state.get("missing_fields") or state.get("clarification_note"):
        return "ask_clarification"
    return "agent"


def route_after_agent(
    state: Mystate,
) -> Literal["error", "request_approval", "tools", "retrieve_for_plan", "respond"]:
    """tool_calls가 있으면 승인 대상 여부로 request_approval / tools를 고르고, 없으면 일정 작성 단계인지 보고 retrieve_for_plan(가이드 검색 후 plan_trip) / respond."""
    if state.get("error"):
        return "error"
    calls = _tool_calls(state)
    if calls:
        # 하나라도 승인 대상이면 이번 묶음 전체를 실행하지 않고 승인부터 받는다.
        if any(call["name"] in REQUIRES_APPROVAL for call in calls):
            return "request_approval"
        return "tools"
    if state.get("intent") == "trip" and state.get("trip_status") == "planning" and state.get("selected_event_id"):
        return "retrieve_for_plan"
    return "respond"


def route_after_retrieve(state: Mystate) -> Literal["error", "agent"]:
    return "error" if state.get("error") else "agent"


def route_after_retrieve_for_plan(state: Mystate) -> Literal["error", "plan_trip"]:
    return "error" if state.get("error") else "plan_trip"


def route_after_tools(state: Mystate) -> Literal["error", "ingest_tool_results"]:
    return "error" if state.get("error") else "ingest_tool_results"


def route_after_ingest(state: Mystate) -> Literal["error", "agent"]:
    return "error" if state.get("error") else "agent"


def route_after_plan_trip(state: Mystate) -> Literal["error", "respond"]:
    return "error" if state.get("error") else "respond"


def route_after_resolve_approval(
    state: Mystate,
) -> Literal["execute_approved_tool", "respond", "ask_approval_again"]:
    """승인이면 저장된 인자로 실행, 거절이면 실행 없이 응답, 승인/거절이 불분명하면 다시 묻는다."""
    decision = state.get("approval_decision")
    if decision == "approved":
        return "execute_approved_tool"
    if decision == "rejected":
        return "respond"
    return "ask_approval_again"


def route_after_execute(state: Mystate) -> Literal["error", "ingest_tool_results", "respond"]:
    """승인 실행 결과가 곧 최종 답이면(마지막이 tool_calls 없는 AI 메시지, 예: 저장 완료) respond, 아니면 ingest -> agent."""
    if state.get("error"):
        return "error"
    last_message = state["messages"][-1]
    if isinstance(last_message, AIMessage) and not last_message.tool_calls:
        return "respond"
    return "ingest_tool_results"
