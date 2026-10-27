# ingest_tool_results 노드: tools 노드가 만든 ToolMessage의 구조화된 결과({status, source, data})를 State 검색 캐시에 반영한다.
# 같은 ToolMessage를 두 번 처리하지 않도록 처리한 tool_call_id를 processed_tool_call_ids에 기록한다.
# 이번 턴 사용자 입력 이후의 ToolMessage만 대상으로 삼고, 여행(trip) 의도일 때만 캐시를 갱신한다
# (경기 일정만 물어본 qa 질문이 진행 중인 여행 후보를 덮어쓰지 않게). 단, 아직 고른 경기가 없다면
# 경기 목록 조회는 qa여도 후보로 저장한다 (조회 결과 중 하나를 다음 턴에 골라 여행을 시작할 수 있게).

import json
import logging

from teams.team5.prompts import EVENT_NOT_FOUND_NOTICE
from teams.team5.state import MyState
from teams.team5.trip_state import (
    compute_trip_status,
    find_event,
    is_specific_game_request,
    load_all_events,
    match_event_by_text,
    narrow_events_by_text,
    similar_events,
)
from langchain_core.documents import Document
from langchain_core.messages import ToolMessage

logger = logging.getLogger(__name__)


def _merge_by_id(old: list[dict], new: list[dict]) -> list[dict]:
    merged = {item["id"]: item for item in old}
    merged.update({item["id"]: item for item in new})
    return list(merged.values())


def _parse(message: ToolMessage) -> dict | None:
    try:
        parsed = json.loads(message.content)
    except (TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) and parsed.get("status") == "ok" else None


def _latest_tool_messages(state: MyState) -> list[ToolMessage]:
    """마지막 사용자 메시지 이후의 ToolMessage (= 이번 턴에 새로 생긴 것)."""
    messages = state["messages"]
    last_human = max((i for i, m in enumerate(messages) if m.type == "human"), default=-1)
    return [m for m in messages[last_human + 1 :] if isinstance(m, ToolMessage)]


def _pick_named_event(found: list[dict], text: str) -> dict:
    """문장이 지목한 경기를 고른다. 검색 결과에 없으면 전체 일정에서 다시 찾고, 그래도 없으면 비슷한 시간대/언급한 팀의 경기를 후보로 바꾼다."""
    if chosen := match_event_by_text(found, text):
        return {"selected_event_id": chosen}
    if not is_specific_game_request(found, text):
        return {}  # 날짜만 말했거나 범위 검색이면 검색 결과 목록을 그대로 보여준다.
    if narrow_events_by_text(found, text):
        return {}  # 지목한 조건에 맞는 경기가 여럿이면 그 목록에서 사용자가 고르게 한다.
    # 검색 결과에 없다: LLM이 좁게 검색했을 수 있으니 전체 일정에서 한 번 더 찾는다 (로컬 툴이라 외부 호출이 아니다).
    all_events = load_all_events()
    if narrowed := narrow_events_by_text(all_events, text):
        return {"sports_events": narrowed, **({"selected_event_id": narrowed[0]["id"]} if len(narrowed) == 1 else {})}
    if similar := similar_events(all_events, text):
        return {"sports_events": similar, "event_notice": EVENT_NOT_FOUND_NOTICE}
    return {}


def ingest_tool_results_node(state: MyState) -> dict:
    processed = list(state.get("processed_tool_call_ids", []))
    changes: dict = {}
    new_messages = [m for m in _latest_tool_messages(state) if m.tool_call_id not in processed]

    try:
        for message in new_messages:
            processed.append(message.tool_call_id)
            result = _parse(message)
            if not result:
                continue  # 실패한 결과는 캐시에 반영하지 않는다.
            data = result["data"]
            if message.name == "search_guide_docs":
                # 가이드 문서는 어떤 의도에서든 반영한다: respond가 출처를 표시하고 plan_trip이 참고한다.
                found = [Document(page_content=d["content"], metadata={"source": d["source"]}) for d in data["docs"]]
                changes["retrieved_docs"] = [*changes.get("retrieved_docs", state.get("retrieved_docs") or []), *found]
                continue
            # 경기 목록 조회(qa)도 아직 고른 경기가 없으면 후보로 저장한다: 그래야 다음 턴에 "그중 28일 경기로 ..."처럼 고를 수 있다.
            first_lookup = message.name == "search_sports_events" and not state.get("selected_event_id")
            if state.get("intent") != "trip" and not first_lookup:
                continue  # 그 외 경기/장소 검색 캐시는 trip 흐름에서만 갱신한다.
            if message.name == "search_sports_events":
                changes["sports_events"] = data["events"]  # 최신 검색 결과가 후보가 된다
            elif message.name == "search_places":
                changes["places"] = _merge_by_id(changes.get("places", state.get("places") or []), data["places"])
            elif message.name == "search_restaurants":
                changes["restaurants"] = _merge_by_id(
                    changes.get("restaurants", state.get("restaurants") or []), data["restaurants"]
                )
    except Exception as exc:
        return {"error": f"Tool 결과를 처리하지 못했습니다: {exc}"}

    # 후보 없이 "11/4 KT 위즈 vs LG 트윈스 경기로 ..."처럼 경기를 바로 지목한 여행 요청이면, 검색 결과에서 그 경기를 바로 선택한다.
    if state.get("intent") == "trip" and "sports_events" in changes and not state.get("selected_event_id"):
        changes.update(_pick_named_event(changes["sports_events"], state.get("user_input", "")))

    merged = {**state, **changes}
    # 선택 경기는 반드시 현재 후보에 있는 실제 ID여야 한다: 후보가 바뀌어 사라졌다면 선택과 계획도 무효화한다.
    if merged.get("selected_event_id") and not find_event(merged, merged["selected_event_id"]):
        changes.update(selected_event_id=None, trip_plan=None, places=[], restaurants=[])
        merged = {**state, **changes}

    changes["processed_tool_call_ids"] = processed
    changes["tool_iterations"] = state.get("tool_iterations", 0) + 1
    if state.get("intent") == "trip":
        changes["trip_status"] = compute_trip_status(merged)
    return changes
