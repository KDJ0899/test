# validate_trip_plan 단위 테스트 + plan_trip 노드의 재시도/실패 처리 (T13).

import copy

from agent.nodes.plan_trip import PlanItemDraft, TripPlanDraft, make_plan_trip_node
from agent.trip_validation import validate_trip_plan

EVENT = {"id": "e1", "start_at": "2026-11-14T14:00:00", "home_team": "롯데 자이언츠", "away_team": "LG 트윈스",
         "venue": "사직야구장", "city": "부산", "is_demo": True, "source_type": "sample"}


def item(day, start, end, **kw):
    return {"day": day, "start_at": start, "end_at": end, "activity": kw.pop("activity", f"활동{start}"),
            "notes": "", "is_estimated": True, **kw}


def good_plan():
    return {"items": [
        item(1, "2026-11-14T11:00:00", "2026-11-14T12:00:00", place_id="p1", activity="점심"),
        item(1, "2026-11-14T14:00:00", "2026-11-14T17:00:00", event_id="e1", activity="경기"),
        item(2, "2026-11-15T10:00:00", "2026-11-15T12:00:00", place_id="p2", activity="바다"),
    ]}


def errors(plan, duration=2, known=frozenset({"p1", "p2"})):
    return validate_trip_plan(plan, EVENT, duration, set(known))


def test_valid_plan_passes():
    assert errors(good_plan()) == []


def test_no_selected_event():
    assert validate_trip_plan(good_plan(), None) == ["선택한 경기가 없다."]


def test_missing_event_item():
    plan = good_plan()
    plan["items"].pop(1)
    assert any("항목이 일정에 없다" in e for e in errors(plan))


def test_event_start_mismatch():
    plan = good_plan()
    plan["items"][1]["start_at"] = "2026-11-14T15:00:00"
    assert any("경기 시작 시각" in e for e in errors(plan))


def test_time_reversal():
    plan = good_plan()
    plan["items"][0]["start_at"], plan["items"][0]["end_at"] = "2026-11-14T12:00:00", "2026-11-14T11:00:00"
    assert any("시간 역전" in e for e in errors(plan))


def test_overlap_on_same_day():
    plan = good_plan()
    plan["items"][0]["end_at"] = "2026-11-14T14:30:00"  # 점심이 경기 시작 이후까지 이어짐
    assert any("겹친다" in e for e in errors(plan))


def test_duplicate_place_and_activity():
    plan = good_plan()
    plan["items"].append(item(2, "2026-11-15T13:00:00", "2026-11-15T14:00:00", place_id="p2", activity="바다"))
    msgs = errors(plan)
    assert any("p2" in e and "중복" in e for e in msgs) and any("같은 활동" in e for e in msgs)


def test_out_of_trip_range():
    plan = good_plan()
    plan["items"].append(item(3, "2026-11-16T10:00:00", "2026-11-16T11:00:00", activity="3일째"))
    assert any("여행 기간" in e for e in errors(plan))


def test_day_and_date_mismatch():
    plan = good_plan()
    plan["items"][2]["start_at"], plan["items"][2]["end_at"] = "2026-11-20T10:00:00", "2026-11-20T12:00:00"
    assert any("Day 2" in e for e in errors(plan))


def test_unknown_place_id():
    plan = copy.deepcopy(good_plan())
    plan["items"][0]["place_id"] = "place-invented"
    assert any("검색 결과에 없는 장소" in e for e in errors(plan))


def _state():
    return {"messages": [], "selected_event_id": "e1", "sports_events": [EVENT], "trip_preferences": {"duration_days": 2},
            "places": [{"id": "p1", "name": "A", "source_type": "sample", "is_demo": True},
                       {"id": "p2", "name": "B", "source_type": "sample", "is_demo": True}], "restaurants": []}


def _draft(overlap: bool) -> TripPlanDraft:
    end = "2026-11-14T14:30:00" if overlap else "2026-11-14T12:00:00"
    return TripPlanDraft(title="t", items=[
        PlanItemDraft(day=1, start_at="2026-11-14T11:00:00", end_at=end, place_id="p1", activity="점심"),
        PlanItemDraft(day=1, start_at="2026-11-14T14:00:00", end_at="2026-11-14T17:00:00", event_id="e1", activity="경기"),
        PlanItemDraft(day=2, start_at="2026-11-15T10:00:00", end_at="2026-11-15T12:00:00", place_id="p2", activity="바다"),
    ])


def _node(monkeypatch, drafts):
    import agent.nodes.plan_trip as mod
    from tests.conftest import ScriptedLLM

    llm = ScriptedLLM(drafts)
    monkeypatch.setattr(mod, "get_llm", lambda **kw: llm)
    return make_plan_trip_node(), llm


async def test_plan_trip_retries_once_then_succeeds(monkeypatch):
    node, llm = _node(monkeypatch, [_draft(overlap=True), _draft(overlap=False)])
    result = await node(_state())
    assert result["trip_plan"]["event_id"] == "e1" and result["trip_status"] == "completed"
    assert len(llm.calls) == 2 and "겹친다" in llm.calls[1][0].content  # 재시도 프롬프트에 위반 내용이 들어간다


async def test_t13_plan_trip_conflict_fails_after_one_retry(monkeypatch):
    node, llm = _node(monkeypatch, [_draft(overlap=True), _draft(overlap=True)])
    result = await node(_state())
    assert result["trip_plan"] is None and "겹친다" in result["messages"][0].content
    assert len(llm.calls) == 2  # 무한 재시도 없음


async def test_plan_trip_llm_failure_goes_to_error(monkeypatch):
    node, _ = _node(monkeypatch, [RuntimeError("llm down")])
    assert (await node(_state())) == {"error": "llm down"}
