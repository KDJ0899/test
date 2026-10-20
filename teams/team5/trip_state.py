# State에서 파생되는 값을 계산하는 작은 순수 함수 모음 (LLM 호출 없음).
# 여러 노드(validate_preferences, ingest_tool_results, agent, plan_trip)가 같은 기준으로 단계/선택 경기를 판단하도록 모아 둔다.

from teams.team5.state import Mystate


def find_event(state: Mystate, event_id: str | None) -> dict | None:
    """현재 검색 캐시(sports_events)에 실제로 있는 경기만 돌려준다."""
    if not event_id:
        return None
    return next((e for e in state.get("sports_events") or [] if e["id"] == event_id), None)


def selected_event(state: Mystate) -> dict | None:
    return find_event(state, state.get("selected_event_id"))


def compute_trip_status(state: Mystate) -> str:
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


def describe_events(state: Mystate) -> str:
    events = state.get("sports_events") or []
    if not events:
        return "  (없음)"
    return "\n".join(f"  {i}. {describe_event(e)}" for i, e in enumerate(events, start=1))
