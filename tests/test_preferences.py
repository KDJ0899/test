# 여행 조건 병합/검증 테스트 (apply_update, find_missing_fields) + 조건 수집 멀티턴 (T04, T05).

from teams.team5.workflow import build_graph
from teams.team5.nodes.classify import IntentClassification
from teams.team5.nodes.extract_preferences import PreferenceUpdate, apply_update
from teams.team5.nodes.validate_preferences import find_missing_fields
from langchain_core.messages import AIMessage

CONFIG = {"configurable": {"thread_id": "pref"}}
EVENTS = [{"id": "e1"}, {"id": "e2"}, {"id": "e3"}]


def state_with(**kw):
    return {"trip_preferences": {"sport_type": "baseball", "team": "롯데", "date_from": "2026-11-01",
                                 "date_to": "2026-11-30", "preferred_weekdays": [5], "duration_days": 2},
            "sports_events": EVENTS, "selected_event_id": "e2", "trip_plan": {"title": "p"},
            "places": [{"id": "p"}], "restaurants": [{"id": "r"}], **kw}


def test_apply_update_keeps_unmentioned_values():
    out = apply_update(state_with(), PreferenceUpdate(travelers=2))
    prefs = out["trip_preferences"]
    assert prefs["team"] == "롯데" and prefs["preferred_weekdays"] == [5] and prefs["travelers"] == 2


def test_search_condition_change_invalidates_selection_and_plan():
    out = apply_update(state_with(), PreferenceUpdate(team="LG"))
    assert out["trip_preferences"]["team"] == "LG"
    assert out["sports_events"] == [] and out["selected_event_id"] is None and out["trip_plan"] is None


def test_non_search_change_keeps_event_but_resets_plan():
    out = apply_update(state_with(), PreferenceUpdate(transport="public_transit", interests=["바다 관광"]))
    assert "selected_event_id" not in out and "sports_events" not in out
    assert out["trip_plan"] is None
    assert out["trip_preferences"]["interests"] == ["바다 관광"]


def test_interests_accumulate_without_duplicates():
    s = state_with()
    s["trip_preferences"]["interests"] = ["맛집"]
    out = apply_update(s, PreferenceUpdate(interests=["맛집", "바다 관광"]))
    assert out["trip_preferences"]["interests"] == ["맛집", "바다 관광"]


def test_select_by_number_maps_to_real_event_id():
    out = apply_update(state_with(selected_event_id=None, trip_plan=None), PreferenceUpdate(selected_event_number=2))
    assert out["selected_event_id"] == "e2"


def test_select_ignores_unknown_id_and_out_of_range_number():
    base = state_with(selected_event_id=None, trip_plan=None)
    assert "selected_event_id" not in apply_update(base, PreferenceUpdate(selected_event_id="evt-fake"))
    assert "selected_event_id" not in apply_update(base, PreferenceUpdate(selected_event_number=9))


def test_changing_selection_resets_plan_and_place_cache():
    out = apply_update(state_with(), PreferenceUpdate(selected_event_number=3))
    assert out["selected_event_id"] == "e3" and out["trip_plan"] is None and out["places"] == []


def test_missing_fields():
    assert find_missing_fields({}) == ["team", "date_range", "duration_days"]
    assert find_missing_fields(state_with()) == []
    bad = state_with()
    bad["trip_preferences"]["date_from"] = "2026-12-01"
    assert find_missing_fields(bad) == ["date_range"]


async def test_collect_conditions_over_two_turns(fake_llms, fake_embeddings):
    """T04: 팀만 말하면 날짜/일수를 묻는다. T05: 다음 턴 입력이 이전 팀 조건과 병합된다."""
    fake_llms["classify"].responses = [IntentClassification(intent="trip")] * 2
    fake_llms["extract"].responses = [
        PreferenceUpdate(team="롯데"),
        PreferenceUpdate(date_from="2026-11-01", date_to="2026-11-30", preferred_weekdays=[5], duration_days=2),
    ]
    fake_llms["agent"].responses = [AIMessage(content="후보 검색 단계")]
    graph = await build_graph()

    r1 = await graph.ainvoke({"user_input": "롯데 경기 보고 여행 가고 싶어"}, CONFIG)
    assert "날짜 범위" in r1["answer"] and "여행 기간" in r1["answer"] and "팀" not in r1["answer"]
    s1 = (await graph.aget_state(CONFIG)).values
    assert s1["trip_preferences"]["team"] == "롯데" and s1["trip_status"] == "collecting"

    r2 = await graph.ainvoke({"user_input": "다음 달 토요일 중 1박 2일"}, CONFIG)
    s2 = (await graph.aget_state(CONFIG)).values
    assert s2["trip_preferences"] == {"sport_type": "baseball", "team": "롯데", "date_from": "2026-11-01",
                                      "date_to": "2026-11-30", "preferred_weekdays": [5], "duration_days": 2}
    assert s2["missing_fields"] == [] and s2["trip_status"] == "searching"
    assert r2["answer"] == "후보 검색 단계"
    # 질문(AI)도 이력에 남아 있다: H, A(질문), H, A
    assert [m.type for m in s2["messages"]] == ["human", "ai", "human", "ai"]


async def test_ambiguous_date_asks_confirmation(fake_llms, fake_embeddings):
    fake_llms["classify"].responses = [IntentClassification(intent="trip")]
    fake_llms["extract"].responses = [
        PreferenceUpdate(team="롯데", date_from="2026-11-01", date_to="2026-11-30", duration_days=2,
                         clarification_note="'주말 아무 때나'는 11월 전체로 볼까요, 특정 주로 한정할까요?")
    ]
    graph = await build_graph()
    r = await graph.ainvoke({"user_input": "주말 아무 때나"}, CONFIG)
    assert "11월 전체" in r["answer"]
