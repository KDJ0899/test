# 로컬 툴 모음. 검색 툴은 data/*.json(샘플 가상 데이터)만 읽는다.
# 외부 API는 호출하지 않는다 (전부 저장소 안 데이터만 사용).
# 모든 툴은 {status, source, data, error?} 형태의 JSON 문자열을 돌려준다 (ingest_tool_results가 이 형식을 읽어 State에 반영).

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from teams.team5.clock import WEEKDAY_NAMES, today
from langchain_core.tools import tool

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
EVENTS_PATH = DATA_DIR / "sports_events.json"
PLACES_PATH = DATA_DIR / "tourist_places.json"
RESTAURANTS_PATH = DATA_DIR / "restaurants.json"


def _ok(source: str, data: Any) -> str:
    return json.dumps({"status": "ok", "source": source, "data": data}, ensure_ascii=False)


def _fail(source: str, error: str) -> str:
    return json.dumps({"status": "error", "source": source, "data": None, "error": error}, ensure_ascii=False)


def _load(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def _near_first(items: list[dict], near_venue: str | None) -> list[dict]:
    """near_venue가 있으면 그 경기장 근처로 표시된 항목을 앞으로 보낸다 (제외하지는 않는다)."""
    if not near_venue:
        return items
    return sorted(items, key=lambda x: near_venue not in x.get("nearby_venues", []))


@tool
def get_current_datetime() -> str:
    """현재 날짜와 시간, 요일, 타임존을 반환한다. '다음 달', '이번 주' 같은 상대 날짜를 해석할 때 먼저 사용한다. 인자가 필요 없다."""
    now = datetime.now().astimezone()
    d = today()
    return _ok(
        "local_system",
        {
            "today": d.isoformat(),
            "weekday": WEEKDAY_NAMES[d.weekday()],
            "now": now.isoformat(timespec="seconds"),
            "timezone": str(now.tzinfo),
        },
    )


@tool
def search_sports_events(
    sport_type: str = "baseball",
    team: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    city: str | None = None,
    weekdays: list[int] | None = None,
) -> str:
    """경기 일정을 검색한다. 팀 이름 일부(예: '롯데'), 날짜 범위(YYYY-MM-DD), 도시, 요일(월=0 ... 일=6)로 거를 수 있다.
    여행할 경기를 찾거나 경기 일정을 물어볼 때 사용한다. 결과가 0건이면 경기를 지어내지 말고 그대로 알려야 한다.
    현재는 가상 샘플 데이터(is_demo=true)라 실제 확정 경기가 아니다."""
    try:
        start = date.fromisoformat(start_date) if start_date else None
        end = date.fromisoformat(end_date) if end_date else None
    except ValueError:
        return _fail("sample:sports_events.json", "날짜는 YYYY-MM-DD 형식이어야 한다.")

    events = [e for e in _load(EVENTS_PATH) if e["sport_type"] == sport_type]
    if team:
        events = [e for e in events if team in e["home_team"] or team in e["away_team"]]
    if city:
        events = [e for e in events if e["city"] == city]
    if start:
        events = [e for e in events if date.fromisoformat(e["start_at"][:10]) >= start]
    if end:
        events = [e for e in events if date.fromisoformat(e["start_at"][:10]) <= end]
    if weekdays:
        events = [e for e in events if date.fromisoformat(e["start_at"][:10]).weekday() in weekdays]
    events.sort(key=lambda e: e["start_at"])
    return _ok("sample:sports_events.json", {"events": events, "count": len(events)})


@tool
def search_places(city: str, category: str | None = None, near_venue: str | None = None, limit: int = 5) -> str:
    """도시의 관광지를 검색한다. category는 sea(바다), culture(문화), market(시장), nature(자연) 중 하나.
    near_venue에 경기장 이름을 주면 근처 장소를 앞에 둔다. 일정에 넣을 장소 후보를 찾을 때 사용한다. (가상 샘플 데이터)"""
    places = [p for p in _load(PLACES_PATH) if p["city"] == city]
    if category:
        places = [p for p in places if p["category"] == category]
    places = _near_first(places, near_venue)[:limit]
    return _ok("sample:tourist_places.json", {"places": places, "count": len(places)})


@tool
def search_restaurants(city: str, cuisine: str | None = None, near_venue: str | None = None, limit: int = 5) -> str:
    """도시의 식당을 검색한다. cuisine은 음식 종류(예: 돼지국밥, 회). near_venue에 경기장 이름을 주면 근처 식당을 앞에 둔다.
    식사 장소 후보가 필요할 때 사용한다. (가상 샘플 데이터, 영업시간 정보 없음)"""
    restaurants = [r for r in _load(RESTAURANTS_PATH) if r["city"] == city]
    if cuisine:
        restaurants = [r for r in restaurants if cuisine in r["cuisine"]]
    restaurants = _near_first(restaurants, near_venue)[:limit]
    return _ok("sample:restaurants.json", {"restaurants": restaurants, "count": len(restaurants)})


LOCAL_TOOLS = [get_current_datetime, search_sports_events, search_places, search_restaurants]
