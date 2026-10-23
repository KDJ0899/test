# extract_preferences 노드: 대화 이력 + 기존 trip_preferences + 이번 입력에서 여행 조건을 추출해 State에 병합한다 (LLM, Structured Output).
# 병합 규칙(apply_update)은 LLM 없는 순수 함수로 분리했다: 사용자가 명시적으로 바꾼 값만 덮어쓰고,
# 검색 조건(팀/날짜/요일)이 바뀌면 경기 후보·선택·일정을 무효화하고, 부가 조건만 바뀌면 선택 경기는 유지한 채 일정만 다시 만든다.

import json
from datetime import date
from collections.abc import Awaitable, Callable

from teams.team5.clock import today_label
from app.llm import get_llm
from teams.team5.prompts import EXTRACT_SYSTEM_PROMPT
from teams.team5.state import MyState, TripPreferences
from teams.team5.trip_state import date_span_days, describe_events, find_event, selected_event
from langchain_core.messages import SystemMessage
from pydantic import BaseModel, Field

# 이 값이 바뀌면 이전에 검색한 경기 후보는 더 이상 유효하지 않다.
SEARCH_KEYS = ("sport_type", "team", "date_from", "date_to", "preferred_weekdays")


class PreferenceUpdate(BaseModel):
    """이번 입력에서 사용자가 명시한 값만 채운다. 말하지 않은 값은 None/빈 리스트."""

    team: str | None = None
    destination: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    preferred_weekdays: list[int] | None = None
    duration_days: int | None = None
    travelers: int | None = None
    transport: str | None = None
    budget_krw: int | None = None
    interests: list[str] = Field(default_factory=list)
    selected_event_number: int | None = None
    selected_event_id: str | None = None
    clarification_note: str | None = None


MAX_TRIP_DAYS = 14


def _event_in_range(event: dict | None, prefs: TripPreferences) -> bool:
    """경기일이 새 날짜 범위 안인가. 경기가 없거나 시각을 모르거나 범위가 이상하면 False (기존대로 검색 조건 변경으로 처리)."""
    try:
        return date.fromisoformat(prefs["date_from"]) <= date.fromisoformat(event["start_at"][:10]) <= date.fromisoformat(prefs["date_to"])
    except (KeyError, TypeError, ValueError):
        return False


def apply_update(state: MyState, update: PreferenceUpdate) -> dict:
    """PreferenceUpdate를 기존 State에 병합한 State 변경분을 반환한다 (순수 함수)."""
    old: TripPreferences = state.get("trip_preferences", {})
    new: TripPreferences = {"sport_type": "baseball", **old}

    for key in ("team", "destination", "date_from", "date_to", "preferred_weekdays",
                "duration_days", "travelers", "transport", "budget_krw"):
        value = getattr(update, key)
        if value:  # None과 빈 값(0, [])은 "말하지 않음"으로 보고 기존 값을 유지한다.
            new[key] = value
    if update.interests:
        # 관심사는 누적한다 (기존 + 새로 말한 것, 중복 제거).
        new["interests"] = [*dict.fromkeys([*old.get("interests", []), *update.interests])]

    changes: dict = {"trip_preferences": new, "clarification_note": update.clarification_note}

    # 이번 입력에서 고른 경기를 먼저 확정한다 (번호 또는 event_id, 현재 후보에 실제로 있을 때만).
    # 날짜 변경을 "검색 조건 변경"으로 처리하기 전에 해야, "10/28 경기로 2박 3일"처럼 선택과 날짜를 함께 말해도 선택이 지워지지 않는다.
    events = state.get("sports_events") or []
    chosen_id = None
    if find_event(state, update.selected_event_id):
        chosen_id = update.selected_event_id
    elif update.selected_event_number and 1 <= update.selected_event_number <= len(events):
        chosen_id = events[update.selected_event_number - 1]["id"]
    new_choice = bool(chosen_id) and chosen_id != state.get("selected_event_id")

    changed = {k for k in SEARCH_KEYS if new.get(k) != old.get(k)}
    event = find_event(state, chosen_id) if chosen_id else selected_event(state)
    if changed and changed <= {"date_from", "date_to"} and _event_in_range(event, new):
        # 경기를 고른 뒤 날짜만 말하면 검색 범위가 아니라 "여행 기간"으로 본다: 고른 경기와 후보는 유지하고 일정만 다시 만든다.
        changes["trip_plan"] = None
        if new_choice:
            changes.update(selected_event_id=chosen_id, places=[], restaurants=[])
        span = date_span_days(new)
        if not update.duration_days and span and span <= MAX_TRIP_DAYS:
            new["duration_days"] = span  # 기간을 따로 말하지 않았으면 날짜 범위에서 계산한다.
        return changes

    if changed:
        # 검색 조건 변경: 후보/선택/계획/장소 캐시를 모두 무효화한다.
        changes.update(sports_events=[], selected_event_id=None, trip_plan=None, places=[], restaurants=[])
        return changes

    # 검색 조건이 그대로면 현재 후보 안에서 사용자의 선택을 반영한다.
    if new_choice:
        changes.update(selected_event_id=chosen_id, trip_plan=None, places=[], restaurants=[])
    elif any(new.get(k) != old.get(k) for k in new if k not in SEARCH_KEYS) and state.get("trip_plan"):
        # 인원/이동수단/관심사/여행 일수만 바뀜: 선택 경기는 유지하고 일정만 다시 만든다.
        changes["trip_plan"] = None
    return changes


def make_extract_preferences_node() -> Callable[[MyState], Awaitable[dict]]:
    structured_llm = get_llm().with_structured_output(PreferenceUpdate)

    async def extract_preferences_node(state: MyState) -> dict:
        system = EXTRACT_SYSTEM_PROMPT.format(
            today=today_label(),
            preferences=json.dumps(state.get("trip_preferences", {}), ensure_ascii=False),
            events=describe_events(state),
        )
        try:
            update = await structured_llm.ainvoke(
                [SystemMessage(content=system), *state["messages"]], config={"tags": ["internal"]}
            )
            return apply_update(state, update)
        except Exception as exc:
            return {"error": str(exc)}

    return extract_preferences_node
