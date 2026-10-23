# State에서 파생되는 값을 계산하는 작은 순수 함수 모음 (LLM 호출 없음).
# 여러 노드(validate_preferences, ingest_tool_results, agent, plan_trip)가 같은 기준으로 단계/선택 경기를 판단하도록 모아 둔다.

from datetime import date

from teams.team5.state import MyState


def find_event(state: MyState, event_id: str | None) -> dict | None:
    """현재 검색 캐시(sports_events)에 실제로 있는 경기만 돌려준다."""
    if not event_id:
        return None
    return next((e for e in state.get("sports_events") or [] if e["id"] == event_id), None)


def selected_event(state: MyState) -> dict | None:
    return find_event(state, state.get("selected_event_id"))


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
