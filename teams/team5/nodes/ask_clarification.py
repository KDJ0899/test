# ask_clarification 노드: 채워진 조건과 부족한 필수 조건을 한눈에 보여주는 질문을 answer로 내보내고 턴을 끝낸다 (LLM 없음).
# extract가 날짜 모호/모순을 발견해 clarification_note를 남겼다면 그 질문을 부족한 정보 맨 위에 함께 보여준다.

from datetime import date, timedelta

from teams.team5.prompts import (
    CLARIFICATION_NONE_FILLED,
    CLARIFICATION_TEMPLATE,
    FIELD_LABELS,
    MISSING_FIELD_QUESTIONS,
)
from teams.team5.state import MyState
from teams.team5.trip_state import describe_event, selected_event, trip_period_start
from langchain_core.messages import AIMessage


def _filled_value(field: str, state: MyState) -> str | None:
    """필수 조건 하나의 현재 값을 사용자에게 보여줄 문구로 만든다. 값이 없으면 None."""
    prefs = state.get("trip_preferences", {})
    event = selected_event(state)
    if field == "team":
        return prefs.get("team") or (describe_event(event) if event else None)
    if field == "date_range":
        if event and not trip_period_start(event, prefs):
            return f"선택한 경기일({event['start_at'][:10]}) 기준"  # 날짜 범위가 아직 여행 기간으로 확정되지 않았다.
        if prefs.get("date_from") and prefs.get("date_to"):
            return f"{prefs['date_from']} ~ {prefs['date_to']}"
        return None
    if field == "duration_days":
        return f"{prefs['duration_days']}일" if prefs.get("duration_days") else None
    return None


def _question(field: str, state: MyState) -> str:
    """부족한 조건별 질문. trip_start는 경기일을 포함하는 가능한 여행 날짜 후보를 계산해 보여준다."""
    question = MISSING_FIELD_QUESTIONS[field]
    if field != "trip_start":
        return question
    duration = state["trip_preferences"]["duration_days"]
    event_date = date.fromisoformat(selected_event(state)["start_at"][:10])
    options = []
    for offset in range(duration):  # 경기일이 1일차, 2일차, ... 인 경우 각각의 여행 기간
        start = event_date - timedelta(days=offset)
        end = start + timedelta(days=duration - 1)
        options.append(f"{start.month}/{start.day}~{end.month}/{end.day}")
    return question.format(event_date=event_date.isoformat(), duration_days=duration, options=", ".join(options))


def build_clarification_message(state: MyState) -> str:
    missing_fields = state.get("missing_fields", [])
    filled = [
        f"- {FIELD_LABELS[f]}: {value}"
        for f in FIELD_LABELS
        if f not in missing_fields and (value := _filled_value(f, state))
    ]
    missing = [f"- {_question(f, state)}" for f in missing_fields]
    note = state.get("clarification_note")
    if note and "trip_start" not in missing_fields:  # 여행 날짜 질문은 코드가 이미 구체적으로 묻는다 (LLM 질문과 중복 방지).
        missing.insert(0, f"- {note}")
    return CLARIFICATION_TEMPLATE.format(
        filled="\n".join(filled) or CLARIFICATION_NONE_FILLED,
        missing="\n".join(missing),
    )


def ask_clarification_node(state: MyState) -> dict:
    answer = build_clarification_message(state)
    # answer는 호출자에게 가는 값이고, 같은 문장을 messages에도 남겨야 다음 턴 LLM이 무엇을 물었는지 안다.
    return {"messages": [AIMessage(content=answer)], "answer": answer}
