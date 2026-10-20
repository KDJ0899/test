# 조건부 엣지 함수 단위 테스트. State만 만들어 넣고 분기 결과를 확인한다.

import agent.routing as r
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


def call(name, args=None):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args or {}, "id": "c1", "type": "tool_call"}])


def test_classify_routes_by_intent():
    assert r.route_after_classify({"error": "x"}) == "error"
    assert r.route_after_classify({"intent": "trip"}) == "extract_preferences"
    assert r.route_after_classify({"intent": "chat"}) == "agent"
    assert r.route_after_classify({"intent": "qa"}) == "agent"
    assert r.route_after_classify({"intent": "qa", "needs_guide": True}) == "retrieve"
    assert r.route_after_classify({"intent": "trip", "needs_guide": True}) == "extract_preferences"


def test_pending_approval_beats_intent():
    state = {"intent": "trip", "pending_approval": {"approval_id": "a"}}
    assert r.route_after_classify(state) == "resolve_approval"


def test_validate_routes_to_clarification_when_missing():
    assert r.route_after_validate({"missing_fields": ["team"]}) == "ask_clarification"
    assert r.route_after_validate({"missing_fields": [], "clarification_note": "날짜?"}) == "ask_clarification"
    assert r.route_after_validate({"missing_fields": []}) == "agent"


def test_agent_routes_tools_vs_approval_vs_respond():
    assert r.route_after_agent({"messages": [call("search_places")]}) == "tools"
    assert r.route_after_agent({"messages": [call("save_trip_plan")]}) == "request_approval"
    assert r.route_after_agent({"messages": [AIMessage(content="끝")], "intent": "chat"}) == "respond"
    assert r.route_after_agent({"messages": [AIMessage(content="끝")], "error": "x"}) == "error"


def test_agent_routes_to_plan_trip_only_when_planning_with_selection():
    base = {"messages": [AIMessage(content="검색 완료")], "intent": "trip"}
    assert r.route_after_agent({**base, "trip_status": "planning", "selected_event_id": "e1"}) == "retrieve_for_plan"
    assert r.route_after_agent({**base, "trip_status": "selecting"}) == "respond"
    assert r.route_after_agent({**base, "trip_status": "planning"}) == "respond"


def test_resolve_approval_routes():
    assert r.route_after_resolve_approval({"approval_decision": "approved"}) == "execute_approved_tool"
    assert r.route_after_resolve_approval({"approval_decision": "rejected"}) == "respond"
    assert r.route_after_resolve_approval({"approval_decision": "unclear"}) == "ask_approval_again"


def test_execute_routes_final_message_to_respond_else_ingest():
    assert r.route_after_execute({"messages": [AIMessage(content="저장했어요")]}) == "respond"
    done = [call("search_places"), ToolMessage(content="{}", tool_call_id="c1")]
    assert r.route_after_execute({"messages": done}) == "ingest_tool_results"
    assert r.route_after_execute({"messages": [HumanMessage("x")], "error": "e"}) == "error"


def test_simple_error_routes():
    for fn, ok in [
        (r.route_after_extract, "validate_preferences"),
        (r.route_after_tools, "ingest_tool_results"),
        (r.route_after_ingest, "agent"),
        (r.route_after_plan_trip, "respond"),
        (r.route_after_retrieve, "agent"),
        (r.route_after_retrieve_for_plan, "plan_trip"),
    ]:
        assert fn({"error": "x"}) == "error"
        assert fn({}) == ok
