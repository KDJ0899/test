# validate_preferences 노드: LLM 없이 규칙만으로 여행 조건이 충분한지 검사한다 (결정적).
# 필수 조건: 팀(또는 선택한 경기), 검색 가능한 날짜 범위, 여행 일수. 부족하면 missing_fields에 담아 ask_clarification으로 보낸다.

from datetime import date

from teams.team5.state import MyState
from teams.team5.trip_state import compute_trip_status, selected_event


def find_missing_fields(state: MyState) -> list[str]:
    prefs = state.get("trip_preferences", {})
    missing = []
    if not prefs.get("team") and not selected_event(state):
        missing.append("team")
    if not (prefs.get("date_from") and prefs.get("date_to")) and not selected_event(state):
        missing.append("date_range")
    elif prefs.get("date_from") and prefs.get("date_to"):
        try:
            if date.fromisoformat(prefs["date_from"]) > date.fromisoformat(prefs["date_to"]):
                missing.append("date_range")  # 시작이 종료보다 늦으면 모순이므로 다시 묻는다.
        except ValueError:
            missing.append("date_range")
    if not prefs.get("duration_days"):
        missing.append("duration_days")
    return missing


async def validate_preferences_node(state: MyState) -> dict:
    missing = find_missing_fields(state)
    # 값은 그대로 두고 단계(trip_status)만 갱신한다. 판단은 compute_trip_status에 모아 둔다.
    status = compute_trip_status({**state, "missing_fields": missing})
    if state.get("clarification_note"):
        status = "collecting"  # 날짜가 모호/모순이면 필수값이 있어도 확인 질문을 먼저 한다.
    return {"missing_fields": missing, "trip_status": status}
