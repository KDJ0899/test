# 멀티턴 State 관리 시나리오 테스트 (명세서 11장 T01~T08, T10, T14). 가짜 LLM 대본으로 그래프 전체를 끝까지 돌린다.
# 각 턴 뒤 graph.aget_state(config)로 trip_preferences / sports_events / selected_event_id / trip_plan / pending_approval을 확인한다.

import agent.nodes.agent as agent_mod
import agent.tools.local_tools as lt
import pytest
from agent.graph import build_graph
from agent.nodes.classify import IntentClassification
from agent.nodes.extract_preferences import PreferenceUpdate
from agent.nodes.plan_trip import PlanItemDraft, TripPlanDraft
from tests.conftest import tool_call_message
from langchain_core.messages import AIMessage

CONFIG = {"configurable": {"thread_id": "trip"}}
SATURDAYS = dict(date_from="2026-11-01", date_to="2026-11-30", preferred_weekdays=[5], duration_days=2)


def intents(*names):
    return [IntentClassification(intent=n) for n in names]


def good_draft() -> TripPlanDraft:
    """선택 경기 evt-2026-1114-sajik (11/14 토 14:00) 기준 1박 2일 일정."""
    return TripPlanDraft(
        title="사직 야구 1박 2일",
        items=[
            PlanItemDraft(day=1, start_at="2026-11-14T11:30:00", end_at="2026-11-14T12:30:00", place_id="rest-gukbap", activity="점심"),
            PlanItemDraft(day=1, start_at="2026-11-14T14:00:00", end_at="2026-11-14T17:00:00", event_id="evt-2026-1114-sajik", activity="롯데 vs LG 관람"),
            PlanItemDraft(day=2, start_at="2026-11-15T10:00:00", end_at="2026-11-15T12:00:00", place_id="place-haeundae", activity="바다 관광"),
        ],
    )


@pytest.fixture
async def graph_and_llms(fake_llms, fake_embeddings, monkeypatch):
    monkeypatch.setattr(lt, "SAVED_TRIPS_PATH", lt.DATA_DIR / "_unused_saved_trips.json")
    return await build_graph(), fake_llms


async def values(graph, config=CONFIG):
    return (await graph.aget_state(config)).values


async def run_until_selecting(graph, llms):
    """T04~T05: 조건 수집 -> 경기 검색 -> 후보 3개 제시까지 진행."""
    llms["classify"].responses += intents("trip", "trip")
    llms["extract"].responses += [PreferenceUpdate(team="롯데"), PreferenceUpdate(**SATURDAYS)]
    llms["agent"].responses += [
        tool_call_message("search_sports_events", {"team": "롯데", "start_date": "2026-11-01", "end_date": "2026-11-30", "weekdays": [5]}),
        AIMessage(content="후보: 1) 11/7 2) 11/14 3) 11/21"),
    ]
    await graph.ainvoke({"user_input": "롯데 경기 보고 여행 가고 싶어"}, CONFIG)
    return await graph.ainvoke({"user_input": "다음 달 토요일 중 1박 2일"}, CONFIG)


async def run_until_completed(graph, llms):
    await run_until_selecting(graph, llms)
    llms["classify"].responses += intents("trip")
    llms["extract"].responses += [PreferenceUpdate(selected_event_number=2)]
    llms["agent"].responses += [
        AIMessage(content="", tool_calls=[
            {"name": "search_places", "args": {"city": "부산", "near_venue": "사직야구장", "limit": 10}, "id": "p1", "type": "tool_call"},
            {"name": "search_restaurants", "args": {"city": "부산", "near_venue": "사직야구장", "limit": 10}, "id": "r1", "type": "tool_call"},
        ]),
        AIMessage(content="검색 완료"),
    ]
    llms["plan"].responses += [good_draft()]
    return await graph.ainvoke({"user_input": "두 번째 경기로"}, CONFIG)


async def test_t01_chat_path(graph_and_llms):
    graph, llms = graph_and_llms
    llms["classify"].responses += intents("chat")
    llms["agent"].responses += [AIMessage(content="안녕하세요!")]
    assert (await graph.ainvoke({"user_input": "안녕"}, CONFIG)) == {"answer": "안녕하세요!"}
    assert "trip_preferences" not in await values(graph)


async def test_t02_guide_question_forces_retrieve_even_without_tool_call(graph_and_llms):
    graph, llms = graph_and_llms
    llms["classify"].responses += [IntentClassification(intent="qa", needs_guide=True)]
    llms["agent"].responses += [AIMessage(content="신분증과 모바일 티켓을 챙기세요.")]  # agent는 툴을 전혀 부르지 않는다
    result = await graph.ainvoke({"user_input": "야구장 준비물 알려줘"}, CONFIG)
    assert "출처:" in result["answer"] and ".md" in result["answer"]
    assert any("가이드 문서" in str(m.content) for m in llms["agent"].calls[0])  # 검색된 문서가 agent 컨텍스트에 들어갔다
    state = await values(graph)
    assert state["retrieved_docs"] and "trip_preferences" not in state  # 문서만 찾고 여행 State는 건드리지 않는다


async def test_t02b_no_guide_needed_skips_retrieve(graph_and_llms):
    graph, llms = graph_and_llms
    llms["classify"].responses += [IntentClassification(intent="chat", needs_guide=False)]
    llms["agent"].responses += [AIMessage(content="안녕하세요!")]
    result = await graph.ainvoke({"user_input": "안녕"}, CONFIG)
    assert result == {"answer": "안녕하세요!"} and not (await values(graph))["retrieved_docs"]


async def test_search_guide_docs_tool_still_works_as_supplement(graph_and_llms):
    graph, llms = graph_and_llms
    llms["classify"].responses += [IntentClassification(intent="qa", needs_guide=False)]
    llms["agent"].responses += [
        tool_call_message("search_guide_docs", {"query": "대중교통"}),
        AIMessage(content="3호선을 이용하세요."),
    ]
    result = await graph.ainvoke({"user_input": "사직 가는 법"}, CONFIG)
    assert "출처:" in result["answer"]


async def test_t03_schedule_query_does_not_ask_trip_conditions(graph_and_llms):
    graph, llms = graph_and_llms
    llms["classify"].responses += intents("qa")
    llms["agent"].responses += [
        tool_call_message("search_sports_events", {"team": "롯데", "start_date": "2026-10-12", "end_date": "2026-10-18"}),
        AIMessage(content="이번 주 롯데 경기는 10/18 NC전(가상 샘플 데이터)입니다."),
    ]
    result = await graph.ainvoke({"user_input": "이번 주 롯데 경기만 알려줘"}, CONFIG)
    assert "NC전" in result["answer"] and "여행 기간" not in result["answer"]
    state = await values(graph)
    assert "trip_preferences" not in state and not state.get("sports_events")  # 조회만 했으므로 여행 후보를 건드리지 않는다


async def test_t04_t05_collect_then_search_candidates(graph_and_llms):
    graph, llms = graph_and_llms
    result = await run_until_selecting(graph, llms)
    assert "후보" in result["answer"]
    state = await values(graph)
    assert state["trip_preferences"]["team"] == "롯데" and state["trip_preferences"]["preferred_weekdays"] == [5]
    assert [e["id"] for e in state["sports_events"]] == ["evt-2026-1107-sajik", "evt-2026-1114-sajik", "evt-2026-1121-sajik"]
    assert state["trip_status"] == "selecting" and state["selected_event_id"] is None


async def test_t06_t07_select_event_plan_and_revise(graph_and_llms):
    graph, llms = graph_and_llms
    result = await run_until_completed(graph, llms)
    state = await values(graph)
    assert state["selected_event_id"] == "evt-2026-1114-sajik"  # 두 번째 후보의 정확한 event_id
    assert state["trip_status"] == "completed" and state["trip_plan"]["event_id"] == "evt-2026-1114-sajik"
    assert {p["id"] for p in state["places"]} >= {"place-haeundae"} and state["restaurants"]
    assert "Day 1" in result["answer"] and "가상 샘플 데이터" in result["answer"] and "확인 필요" in result["answer"]
    assert state["trip_plan"]["sources"][0]["is_demo"] is True
    # 일정 작성 직전에 가이드 검색이 코드로 강제된다 (agent가 search_guide_docs를 부르지 않았어도).
    assert state["retrieved_docs"] and "출처:" in result["answer"]
    assert "(없음)" not in llms["plan"].calls[0][0].content.split("참고 가이드 문서")[1].split("\n")[0]

    # T07: 이동수단/관심사만 바꾸면 선택 경기는 유지하고 일정을 다시 만든다 (검색 캐시 재사용 -> 추가 Tool 호출 없음)
    revised = good_draft()
    revised.title = "대중교통 + 바다 관광"
    llms["classify"].responses += intents("trip")
    llms["extract"].responses += [PreferenceUpdate(transport="public_transit", interests=["둘째 날 바다 관광"])]
    llms["agent"].responses += [AIMessage(content="검색 완료")]
    llms["plan"].responses += [revised]
    await graph.ainvoke({"user_input": "차 없이 갈 거고 둘째 날 바다 관광 추가해 줘"}, CONFIG)
    state = await values(graph)
    assert state["selected_event_id"] == "evt-2026-1114-sajik"
    assert state["trip_plan"]["title"] == "대중교통 + 바다 관광"
    assert state["trip_preferences"]["transport"] == "public_transit"
    assert state["trip_preferences"]["interests"] == ["둘째 날 바다 관광"]
    assert state["trip_preferences"]["team"] == "롯데"  # 이전 조건 유지


async def test_changing_team_invalidates_selection_and_plan(graph_and_llms):
    graph, llms = graph_and_llms
    await run_until_completed(graph, llms)
    llms["classify"].responses += intents("trip")
    llms["extract"].responses += [PreferenceUpdate(team="LG")]
    llms["agent"].responses += [AIMessage(content="LG 경기를 다시 검색할게요")]
    await graph.ainvoke({"user_input": "LG로 바꿔줘"}, CONFIG)
    state = await values(graph)
    assert state["selected_event_id"] is None and state["trip_plan"] is None and state["sports_events"] == []
    assert state["trip_status"] == "searching"


async def test_t10_zero_events_does_not_invent_games(graph_and_llms):
    graph, llms = graph_and_llms
    llms["classify"].responses += intents("trip")
    llms["extract"].responses += [PreferenceUpdate(team="한화", **SATURDAYS)]
    llms["agent"].responses += [
        tool_call_message("search_sports_events", {"team": "한화", "start_date": "2026-11-01", "end_date": "2026-11-30"}),
        AIMessage(content="조건에 맞는 경기가 없어요. 날짜 범위를 바꿔볼까요?"),
    ]
    result = await graph.ainvoke({"user_input": "한화 경기 보고 싶어 다음 달 토요일 1박 2일"}, CONFIG)
    state = await values(graph)
    assert state["sports_events"] == [] and state["selected_event_id"] is None and state["trip_status"] == "searching"
    assert "없어요" in result["answer"]


async def test_t14_new_thread_has_no_previous_trip_state(graph_and_llms):
    graph, llms = graph_and_llms
    await run_until_selecting(graph, llms)
    other = {"configurable": {"thread_id": "after-reset"}}
    assert await values(graph, other) == {}  # reset = 새 thread_id: 이전 여행 상태가 없다
    llms["classify"].responses += intents("trip")
    llms["extract"].responses += [PreferenceUpdate(team="KIA")]
    await graph.ainvoke({"user_input": "KIA 경기 보고 싶어"}, other)
    assert (await values(graph, other))["trip_preferences"] == {"sport_type": "baseball", "team": "KIA"}


async def test_tool_loop_stops_at_max_iterations(graph_and_llms, monkeypatch):
    graph, llms = graph_and_llms
    monkeypatch.setattr(agent_mod.settings, "agent_max_iterations", 2)
    llms["classify"].responses += intents("qa")
    llms["agent"].responses += [tool_call_message("get_current_datetime", {}, f"c{i}") for i in range(5)]
    result = await graph.ainvoke({"user_input": "계속 시간 알려줘"}, CONFIG)
    assert "문제가 발생" in result["answer"] and "최대 2회" in result["answer"]
    assert len(llms["agent"].calls) == 2  # 2번 실행한 뒤 3번째 agent 진입에서 LLM 호출 없이 중단
