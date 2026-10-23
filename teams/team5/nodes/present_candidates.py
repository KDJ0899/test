# present_candidates 노드: 일정을 짜기 전에 확보한 관광지/식당 후보를 번호와 함께 보여주고, 원하는 곳을 고르게 하며 턴을 끝낸다 (LLM 없음).
# 사용자의 답은 다음 턴 extract_preferences가 번호로 해석해 place_choice(status=done)에 담고, 그 뒤 plan_trip이 고른 장소를 반드시 포함해 일정을 만든다.
# 경기를 고른 직후 한 번만 보여준다: place_choice가 현재 선택 경기와 같으면 이 노드를 건너뛴다 (routing.route_after_agent).

from teams.team5.prompts import PLACE_CATEGORY_LABELS, PLACE_CHOICE_TEMPLATE, PLACE_LINE_TEMPLATE, PLACE_NONE
from teams.team5.state import MyState
from teams.team5.trip_state import place_options, selected_event
from langchain_core.messages import AIMessage


def _lines(items: list[dict], kind_of) -> str:
    if not items:
        return PLACE_NONE
    return "\n".join(
        PLACE_LINE_TEMPLATE.format(number=i, name=p["name"], kind=kind_of(p), minutes=p.get("estimated_duration_min", 60))
        for i, p in enumerate(items, start=1)
    )


def present_candidates_node(state: MyState) -> dict:
    event = selected_event(state)
    places, restaurants = place_options(state)
    answer = PLACE_CHOICE_TEMPLATE.format(
        event=f"{event['start_at'][:16].replace('T', ' ')} {event['home_team']} vs {event['away_team']}, {event['venue']}",
        places=_lines(places, lambda p: PLACE_CATEGORY_LABELS.get(p.get("category"), "관광")),
        restaurants=_lines(restaurants, lambda r: r.get("cuisine", "식당")),
    )
    # answer는 호출자에게 가는 값이고, 같은 문장을 messages에도 남겨야 다음 턴 LLM이 무엇을 안내했는지 안다.
    return {
        "messages": [AIMessage(content=answer)],
        "answer": answer,
        "place_choice": {"event_id": event["id"], "status": "asked", "picked_ids": []},
    }
