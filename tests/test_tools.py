# 로컬 Tool 단위 테스트 (데이터 검색, 응답 형식, 저장, 외부 API 실패 처리).

import json

import teams.team5.tools.local_tools as lt
import teams.team5.clock as clock
from teams.team5.tools.local_tools import (
    get_current_datetime,
    save_trip_plan,
    search_places,
    search_restaurants,
    search_sports_events,
)
from teams.team5.tools.registry import REQUIRES_APPROVAL, get_tool, load_tools


def call(tool_obj, **kwargs) -> dict:
    return json.loads(tool_obj.invoke(kwargs))


def test_datetime_uses_clock_override(monkeypatch):
    monkeypatch.setattr(clock.config, "TODAY_OVERRIDE", "2026-10-16")
    out = call(get_current_datetime)
    assert out["status"] == "ok" and out["data"]["today"] == "2026-10-16" and out["data"]["weekday"] == "금"


def test_events_filter_by_team_range_and_weekday():
    out = call(search_sports_events, team="롯데", start_date="2026-11-01", end_date="2026-11-30", weekdays=[5])
    events = out["data"]["events"]
    assert [e["id"] for e in events] == ["evt-2026-1107-sajik", "evt-2026-1114-sajik", "evt-2026-1121-sajik"]
    assert all(e["is_demo"] and e["source_type"] == "sample" for e in events)


def test_events_zero_result_is_empty_not_invented():
    out = call(search_sports_events, team="한화", start_date="2026-11-01", end_date="2026-11-30")
    assert out["status"] == "ok" and out["data"]["events"] == [] and out["data"]["count"] == 0


def test_events_bad_date_returns_error_result():
    out = call(search_sports_events, team="롯데", start_date="내일")
    assert out["status"] == "error" and out["error"]


def test_places_category_and_near_venue_first():
    sea = call(search_places, city="부산", category="sea")["data"]["places"]
    assert sea and all(p["category"] == "sea" for p in sea)
    near = call(search_places, city="부산", near_venue="사직야구장", limit=2)["data"]["places"]
    assert all("사직야구장" in p["nearby_venues"] for p in near)


def test_sample_data_is_large_enough_and_marked_demo():
    events = call(search_sports_events, team="롯데")["data"]["events"]
    assert len(events) >= 5 and all(e["is_demo"] for e in events)
    assert len(call(search_places, city="부산", limit=20)["data"]["places"]) >= 8
    assert len(call(search_restaurants, city="부산", limit=20)["data"]["restaurants"]) >= 8


def test_save_trip_plan_appends_file(monkeypatch, tmp_path):
    monkeypatch.setattr(lt, "SAVED_TRIPS_PATH", tmp_path / "saved.json")
    first = call(save_trip_plan, trip_plan={"title": "a"})
    second = call(save_trip_plan, trip_plan={"title": "b"})
    saved = json.loads((tmp_path / "saved.json").read_text(encoding="utf-8"))
    assert [s["trip_plan"]["title"] for s in saved] == ["a", "b"]
    assert first["data"]["saved_id"] != second["data"]["saved_id"]


async def test_registry_loads_tools_and_approval_defaults():
    names = {t.name for t in await load_tools()}
    assert {"search_sports_events", "search_places", "search_restaurants", "save_trip_plan"} <= names
    assert REQUIRES_APPROVAL == {"save_trip_plan"}
    assert get_tool("search_web") is None and get_tool("save_trip_plan") is not None and get_tool("rm_rf") is None
