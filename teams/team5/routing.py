# 조건부 엣지 함수 모음. 분기 로직을 전부 여기 한 곳에 모아서 flow를 한눈에 볼 수 있게 한다.
# 각 함수는 State만 읽는 순수 함수이고, 반환값은 workflow.py의 add_conditional_edges 매핑 키와 같다.
# 노드는 예외를 던지지 않고 state["error"]에 기록하므로, 대부분의 분기는 "error가 있으면 handle_error 노드로"로 시작한다.

from typing import Literal

from teams.team5.state import MyState


def _tool_calls(state: MyState) -> list[dict]:
    last_message = state["messages"][-1]
    return getattr(last_message, "tool_calls", None) or []


def route_after_classify(state: MyState) -> Literal["handle_error", "extract_preferences", "retrieve", "agent"]:
    """error면 handle_error로. trip은 조건 수집으로, 가이드가 필요한 질문은 retrieve로, 나머지는 agent로 간다."""
    if state.get("error"):
        return "handle_error"
    intent = state.get("intent")
    if intent == "trip":
        return "extract_preferences"
    if state.get("needs_guide"):
        return "retrieve"  # 가이드 문서가 필요한 질문은 LLM의 툴 선택에 맡기지 않고 먼저 검색한다.
    return "agent"  # 그 외 chat / qa


def route_after_extract(state: MyState) -> Literal["handle_error", "validate_preferences"]:
    return "handle_error" if state.get("error") else "validate_preferences"


def route_after_validate(state: MyState) -> Literal["ask_clarification", "agent"]:
    """필수 조건이 부족하거나 확인 질문이 필요하면 질문하고 턴을 끝내고, 충분하면 agent로 간다."""
    if state.get("missing_fields") or state.get("clarification_note"):
        return "ask_clarification"
    return "agent"


def route_after_agent(
    state: MyState,
) -> Literal["handle_error", "tools", "present_candidates", "retrieve_for_plan", "respond"]:
    """tool_calls가 있으면 tools로, 없으면 일정 작성 단계인지 보고
    present_candidates(관광지/식당 후보를 보여주고 고르게 함, 경기당 1회) / retrieve_for_plan(가이드 검색 후 plan_trip) / respond."""
    if state.get("error"):
        return "handle_error"
    if _tool_calls(state):
        return "tools"
    if state.get("intent") == "trip" and state.get("trip_status") == "planning" and state.get("selected_event_id"):
        choice = state.get("place_choice")
        has_candidates = bool(state.get("places") or state.get("restaurants"))
        if has_candidates and not (choice and choice["event_id"] == state["selected_event_id"]):
            return "present_candidates"  # 후보를 아직 안 보여줬다: 사용자가 원하는 곳을 고르게 하고 이번 턴을 끝낸다.
        return "retrieve_for_plan"
    return "respond"


def route_after_retrieve(state: MyState) -> Literal["handle_error", "agent"]:
    return "handle_error" if state.get("error") else "agent"


def route_after_retrieve_for_plan(state: MyState) -> Literal["handle_error", "plan_trip"]:
    return "handle_error" if state.get("error") else "plan_trip"


def route_after_tools(state: MyState) -> Literal["handle_error", "ingest_tool_results"]:
    return "handle_error" if state.get("error") else "ingest_tool_results"


def route_after_ingest(state: MyState) -> Literal["handle_error", "agent"]:
    return "handle_error" if state.get("error") else "agent"


def route_after_plan_trip(state: MyState) -> Literal["handle_error", "respond"]:
    return "handle_error" if state.get("error") else "respond"
