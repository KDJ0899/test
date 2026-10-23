# plan_trip 노드: 선택한 경기 + 확보한 관광지/식당 + 여행 조건으로 일정을 만든다 (LLM, Structured Output).
# 초안의 흔한 실수(없는 장소 ID, 중복, 시간 역전/겹침)는 repair_items로 코드가 먼저 고치고, validate_trip_plan(순수 함수)으로 검증한다.
# 그래도 실패하면 위반 내용을 LLM에 알려 PLAN_MAX_ATTEMPTS까지 다시 만든다. 끝내 실패하면 일정을 확정하지 않고 위반 내용은 로그에만 남긴다.
# 성공한 일정만 State(trip_plan)에 저장한다.

import json
import logging
from collections.abc import Awaitable, Callable

from app.llm import get_llm
from teams.team5 import config
from teams.team5.prompts import PLAN_FAILED_MESSAGE, PLAN_NOTICE, PLAN_RETRY_FEEDBACK, PLAN_SYSTEM_PROMPT
from teams.team5.state import MyState
from teams.team5.trip_state import describe_event, selected_event, trip_start_date
from teams.team5.trip_validation import repair_items, validate_trip_plan
from langchain_core.messages import AIMessage, SystemMessage
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class PlanItemDraft(BaseModel):
    day: int
    start_at: str  # YYYY-MM-DDTHH:MM:SS
    end_at: str
    place_id: str | None = None
    event_id: str | None = None
    activity: str
    notes: str = ""
    is_estimated: bool = True


class TripPlanDraft(BaseModel):
    title: str
    items: list[PlanItemDraft]
    notes: str = ""


def build_plan(draft: TripPlanDraft, event: dict, duration_days: int, state: MyState) -> dict:
    """LLM 초안에 출처 정보를 코드로 덧붙여 최종 plan dict를 만든다 (출처는 LLM이 쓰지 않는다)."""
    catalog = {p["id"]: p for p in [*(state.get("places") or []), *(state.get("restaurants") or [])]}
    used = {i.place_id for i in draft.items if i.place_id in catalog}
    sources = [{"id": event["id"], "name": f"{event['home_team']} vs {event['away_team']}", **_source(event)}]
    sources += [{"id": pid, "name": catalog[pid]["name"], **_source(catalog[pid])} for pid in sorted(used)]
    return {
        "title": draft.title,
        "event_id": event["id"],
        "duration_days": duration_days,
        "items": [i.model_dump() for i in draft.items],
        "notes": draft.notes,
        "sources": sources,
    }


def _source(record: dict) -> dict:
    return {"source_type": record.get("source_type"), "is_demo": record.get("is_demo", False),
            "source_url": record.get("source_url"), "verified_at": record.get("verified_at")}


def format_trip_plan(plan: dict, state: MyState) -> str:
    """plan dict를 사용자에게 보여줄 텍스트로 바꾼다 (LLM 없음). 장소 이름은 검색 캐시에서 찾는다."""
    catalog = {p["id"]: p["name"] for p in [*(state.get("places") or []), *(state.get("restaurants") or [])]}
    lines = [f"## {plan['title']}"]
    event = selected_event(state)
    if event:
        lines.append(f"경기: {describe_event(event)}")
    for day in range(1, plan["duration_days"] + 1):
        lines.append(f"\n**Day {day}**")
        for item in sorted((i for i in plan["items"] if i["day"] == day), key=lambda i: i["start_at"]):
            span = f"{item['start_at'][11:16]}~{item['end_at'][11:16]}" + (" (예상)" if item["is_estimated"] else "")
            place = f" [{catalog[item['place_id']]}]" if item.get("place_id") in catalog else ""
            note = f" - {item['notes']}" if item["notes"] else ""
            lines.append(f"- {span} {item['activity']}{place}{note}")
    if plan["notes"]:
        lines.append(f"\n{plan['notes']}")
    demo = any(s["is_demo"] for s in plan["sources"])
    lines.append("\n" + PLAN_NOTICE.format(source_note="가상 샘플 데이터(실제 확정 일정 아님)" if demo else "검증 상태 확인이 필요한 데이터"))
    return "\n".join(lines)


def make_plan_trip_node() -> Callable[[MyState], Awaitable[dict]]:
    structured_llm = get_llm().with_structured_output(TripPlanDraft)

    async def plan_trip_node(state: MyState) -> dict:
        event = selected_event(state)
        if not event:
            return {"error": "선택한 경기를 찾을 수 없어 일정을 만들 수 없습니다."}
        prefs = state.get("trip_preferences", {})
        duration = prefs.get("duration_days") or 2
        start_date = trip_start_date(event, prefs)  # 경기 전후 날짜를 포함한 여행 기간이면 그 시작일이 Day 1
        known_ids = {p["id"] for p in [*(state.get("places") or []), *(state.get("restaurants") or [])]}

        errors: list[str] = []
        try:
            for _attempt in range(config.PLAN_MAX_ATTEMPTS):  # 초안 1회 + 검증 실패 시 재작성
                feedback = PLAN_RETRY_FEEDBACK.format(errors="\n".join(f"- {e}" for e in errors)) if errors else ""
                system = PLAN_SYSTEM_PROMPT.format(
                    event_start=event["start_at"],
                    duration_days=duration,
                    first_date=start_date.isoformat(),
                    preferences=json.dumps(prefs, ensure_ascii=False),
                    event=json.dumps(event, ensure_ascii=False),
                    places=json.dumps(state.get("places") or [], ensure_ascii=False),
                    restaurants=json.dumps(state.get("restaurants") or [], ensure_ascii=False),
                    guide="\n".join(d.page_content for d in state.get("retrieved_docs") or []) or "(없음)",
                    feedback=feedback,
                )
                draft = await structured_llm.ainvoke(
                    [SystemMessage(content=system), *state["messages"]], config={"tags": ["internal"]}
                )
                # 검증 전에 고칠 수 있는 실수는 코드로 고친다 (출처 목록도 고친 항목 기준으로 만들어진다).
                fixed = repair_items([i.model_dump() for i in draft.items], event, known_ids)
                draft = draft.model_copy(update={"items": [PlanItemDraft(**i) for i in fixed]})
                plan = build_plan(draft, event, duration, state)
                errors = validate_trip_plan(plan, event, duration, known_ids, start_date)
                if not errors:
                    answer = format_trip_plan(plan, state)
                    return {
                        "trip_plan": plan,
                        "trip_status": "completed",
                        "messages": [AIMessage(content=answer)],
                    }
        except Exception as exc:
            return {"error": str(exc)}

        logger.warning("일정 검증 실패 (%d회 시도): %s", config.PLAN_MAX_ATTEMPTS, errors)
        return {"trip_plan": None, "messages": [AIMessage(content=PLAN_FAILED_MESSAGE)]}

    return plan_trip_node
