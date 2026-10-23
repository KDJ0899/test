# State에서 파생되는 값을 계산하는 작은 순수 함수 모음 (LLM 호출 없음).
# 여러 노드(validate_preferences, ingest_tool_results, agent, plan_trip)가 같은 기준으로 단계/선택 경기를 판단하도록 모아 둔다.

import re
from datetime import date

from teams.team5.clock import today
from teams.team5.state import MyState

ISO_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")
MONTH_DAY_PATTERN = re.compile(r"(\d{1,2})\s*[/월]\s*(\d{1,2})")  # 11/4, 11월 4일
TIME_PATTERN = re.compile(r"(\d{1,2}):(\d{2})")
DAY_RANGE_PATTERN = re.compile(r"(\d{1,2})\s*일?\s*~\s*(\d{1,2})\s*일")  # 3~5일, 3일~5일


def find_event(state: MyState, event_id: str | None) -> dict | None:
    """현재 검색 캐시(sports_events)에 실제로 있는 경기만 돌려준다."""
    if not event_id:
        return None
    return next((e for e in state.get("sports_events") or [] if e["id"] == event_id), None)


def selected_event(state: MyState) -> dict | None:
    return find_event(state, state.get("selected_event_id"))


def _first_words(event: dict) -> set[str]:
    """경기의 두 팀 이름 첫 단어 ("KT 위즈" -> "KT")."""
    return {event[side].split()[0] for side in ("home_team", "away_team")}


def teams_in_text(events: list[dict], text: str) -> set[str]:
    """문장에 언급된 팀의 첫 단어 ("KT위즈"처럼 붙여 써도 "KT"로 찾는다). 팀 목록은 주어진 경기들에서 얻는다."""
    return {word for event in events for word in _first_words(event) if word in text}


def dates_in_text(text: str, years: set[str]) -> set[str]:
    """문장 속 날짜를 ISO 문자열 집합으로 읽는다. 2026-10-28 / 10/28 / 10월 28일 형식 (연도 없는 형식은 years 각각으로 해석)."""
    found = set(ISO_DATE_PATTERN.findall(text))
    for month, day in MONTH_DAY_PATTERN.findall(text):
        found |= {f"{year}-{int(month):02d}-{int(day):02d}" for year in years}
    return found


def _years(events: list[dict]) -> set[str]:
    return {e["start_at"][:4] for e in events} or {str(today().year)}


def narrow_events_by_text(events: list[dict], text: str) -> list[dict]:
    """사용자 문장이 가리키는 경기들: 날짜가 정확히 하나 있어야 하고, 시각(18:30)과 언급한 팀이 모두 맞는 경기만 남긴다."""
    mentioned = dates_in_text(text, _years(events))
    if len(mentioned) != 1:
        return []
    matches = [e for e in events if e["start_at"][:10] in mentioned]
    if found := TIME_PATTERN.search(text):
        hhmm = f"{int(found[1]):02d}:{found[2]}"
        matches = [e for e in matches if e["start_at"][11:16] == hhmm]
    teams = teams_in_text(events, text)
    return [e for e in matches if teams <= _first_words(e)]


def match_event_by_text(events: list[dict], text: str) -> str | None:
    """사용자 문장이 후보 중 정확히 한 경기를 가리키면 그 경기의 id를 돌려준다 (LLM이 선택을 못 채워도 코드가 인식하는 안전망).
    문장에 날짜가 하나가 아니면(범위 검색 등) 선택으로 보지 않는다."""
    matches = narrow_events_by_text(events, text)
    return matches[0]["id"] if len(matches) == 1 else None


def is_specific_game_request(events: list[dict], text: str) -> bool:
    """날짜 하나에 시각이나 팀까지 말해 특정 경기를 지목한 문장인가 ("11/4 경기 알려줘"처럼 날짜만 있으면 지목이 아니다)."""
    if len(dates_in_text(text, _years(events))) != 1:
        return False
    return bool(TIME_PATTERN.search(text)) or bool(teams_in_text(events, text))


def similar_events(all_events: list[dict], text: str, limit: int = 8) -> list[dict]:
    """지목한 경기가 없을 때 보여줄 대안: 같은 날짜 경기 + 언급한 팀의 경기를 날짜가 가깝고 시각이 비슷한 순으로 돌려준다."""
    (wanted,) = dates_in_text(text, _years(all_events))
    teams = teams_in_text(all_events, text)
    found = TIME_PATTERN.search(text)
    wanted_minutes = int(found[1]) * 60 + int(found[2]) if found else None
    pool = [e for e in all_events if e["start_at"][:10] == wanted or (teams and teams & _first_words(e))]

    def distance(event: dict) -> tuple[int, int]:
        days = abs((date.fromisoformat(event["start_at"][:10]) - date.fromisoformat(wanted)).days)
        minutes = int(event["start_at"][11:13]) * 60 + int(event["start_at"][14:16])
        return days, abs(minutes - wanted_minutes) if wanted_minutes is not None else 0

    return sorted(pool, key=distance)[:limit]


def trip_dates_in_text(text: str, event: dict | None) -> tuple[str, str] | None:
    """"3~5일로 갈 거야"처럼 일(日)만 말한 여행 날짜를 경기의 달(없으면 문장 속 "11/4" 같은 날짜의 달)에 붙여 (시작, 종료)로 만든다.
    경기일이 그 범위에 들어갈 때만 인정한다 (11/4 경기에 3~5일이면 11/3~11/5)."""
    found = DAY_RANGE_PATTERN.search(text)
    if not found:
        return None
    if event:
        ref = date.fromisoformat(event["start_at"][:10])
    elif mentioned := MONTH_DAY_PATTERN.search(text):
        try:
            ref = date(today().year, int(mentioned[1]), int(mentioned[2]))
        except ValueError:
            return None
    else:
        return None
    try:
        start, end = ref.replace(day=int(found[1])), ref.replace(day=int(found[2]))
    except ValueError:
        return None
    return (start.isoformat(), end.isoformat()) if start <= ref <= end else None


def date_span_days(prefs: dict) -> int | None:
    """date_from~date_to가 유효하면 양끝 포함 일수를 돌려준다."""
    try:
        return (date.fromisoformat(prefs["date_to"]) - date.fromisoformat(prefs["date_from"])).days + 1
    except (KeyError, TypeError, ValueError):
        return None


def trip_period_start(event: dict, prefs: dict) -> date | None:
    """날짜 범위가 여행 기간(범위 일수 == duration_days)이고 경기일을 포함하면 그 시작일, 아니면 None."""
    event_date = date.fromisoformat(event["start_at"][:10])
    span = date_span_days(prefs)
    if span and span == prefs.get("duration_days"):
        start = date.fromisoformat(prefs["date_from"])
        if start <= event_date <= start.fromordinal(start.toordinal() + span - 1):
            return start
    return None


def trip_start_date(event: dict, prefs: dict) -> date:
    """일정 Day 1의 날짜. 여행 기간이 정해졌으면 그 시작일, 아니면(검색용 넓은 범위) 경기일을 Day 1로 본다."""
    return trip_period_start(event, prefs) or date.fromisoformat(event["start_at"][:10])


def compute_trip_status(state: MyState) -> str:
    """조건/캐시/선택/계획 유무로 여행 단계를 결정한다."""
    if state.get("missing_fields"):
        return "collecting"
    if state.get("trip_plan"):
        return "completed"
    if selected_event(state):
        return "planning"
    if state.get("sports_events"):
        return "selecting"
    return "searching"


def describe_event(event: dict) -> str:
    kind = "가상 샘플 데이터" if event.get("is_demo") else event.get("source_type", "")
    return (
        f"{event['id']} | {event['start_at']} | {event['home_team']} vs {event['away_team']} | "
        f"{event['venue']} ({event['city']}) | 출처: {kind}"
    )


def describe_events(state: MyState) -> str:
    events = state.get("sports_events") or []
    if not events:
        return "  (없음)"
    return "\n".join(f"  {i}. {describe_event(e)}" for i, e in enumerate(events, start=1))
