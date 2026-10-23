# ask_clarification 노드: 채워진 조건과 부족한 필수 조건을 한눈에 보여주는 질문을 answer로 내보내고 턴을 끝낸다 (LLM 없음).
# extract가 날짜 모호/모순을 발견해 clarification_note를 남겼다면 그 질문을 부족한 정보 맨 위에 함께 보여준다.

from teams.team5.prompts import (
    CLARIFICATION_NONE_FILLED,
    CLARIFICATION_TEMPLATE,
    FIELD_LABELS,
    MISSING_FIELD_QUESTIONS,
)
from teams.team5.state import MyState
from teams.team5.trip_state import describe_event, selected_event
from langchain_core.messages import AIMessage


def _filled_value(field: str, state: MyState) -> str | None:
    """필수 조건 하나의 현재 값을 사용자에게 보여줄 문구로 만든다. 값이 없으면 None."""
    prefs = state.get("trip_preferences", {})
    event = selected_event(state)
    if field == "team":
        return prefs.get("team") or (describe_event(event) if event else None)
    if field == "date_range":
        if prefs.get("date_from") and prefs.get("date_to"):
            return f"{prefs['date_from']} ~ {prefs['date_to']}"
        return f"선택한 경기일({event['start_at'][:10]}) 기준" if event else None
    if field == "duration_days":
        return f"{prefs['duration_days']}일" if prefs.get("duration_days") else None
    return None


def build_clarification_message(state: MyState) -> str:
    missing_fields = state.get("missing_fields", [])
    filled = [
        f"- {FIELD_LABELS[f]}: {value}"
        for f in FIELD_LABELS
        if f not in missing_fields and (value := _filled_value(f, state))
    ]
    missing = [f"- {MISSING_FIELD_QUESTIONS[f]}" for f in missing_fields]
    if note := state.get("clarification_note"):
        missing.insert(0, f"- {note}")
    return CLARIFICATION_TEMPLATE.format(
        filled="\n".join(filled) or CLARIFICATION_NONE_FILLED,
        missing="\n".join(missing),
    )


def ask_clarification_node(state: MyState) -> dict:
    answer = build_clarification_message(state)
    # answer는 호출자에게 가는 값이고, 같은 문장을 messages에도 남겨야 다음 턴 LLM이 무엇을 물었는지 안다.
    return {"messages": [AIMessage(content=answer)], "answer": answer}
