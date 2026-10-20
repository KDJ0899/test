"""FastAPI/UI 없이 CLI로 멀티턴 대화와 LangGraph State 관리를 확인하는 스크립트.

그래프는 InMemorySaver 체크포인터를 붙여 컴파일되고, 이 스크립트는 같은 그래프 인스턴스와 같은 thread_id로
매 턴 user_input만 보낸다. 이전 대화와 여행 상태(조건/후보/선택/일정/승인 대기)는 그래프 State가 기억한다.
프로세스를 끝내면 상태도 사라진다.

사용법: uv run python scripts/run_local.py
명령:   state(현재 State 요약) / reset(새 thread_id로 새 대화) / exit, quit(종료)
기준 날짜를 고정하려면 .env에 TODAY_OVERRIDE=2026-10-16 처럼 적는다 (샘플 경기 날짜가 2026-10~11월이다).
"""

import asyncio
import json
import sys

from agent.clock import today_label
from agent.config import settings
from agent.graph import build_graph


def _config(thread_id: str, recursion_limit: int) -> dict:
    return {"configurable": {"thread_id": thread_id}, "recursion_limit": recursion_limit}


async def _print_state(graph, config: dict) -> None:
    """get_state로 State의 여행 관련 필드를 요약해 보여준다 (messages 전체는 길어서 개수만)."""
    values = (await graph.aget_state(config)).values
    summary = {
        "trip_status": values.get("trip_status"),
        "trip_preferences": values.get("trip_preferences"),
        "sports_events": [e["id"] for e in values.get("sports_events") or []],
        "selected_event_id": values.get("selected_event_id"),
        "places": len(values.get("places") or []),
        "restaurants": len(values.get("restaurants") or []),
        "trip_plan": (values.get("trip_plan") or {}).get("title"),
        "pending_approval": values.get("pending_approval") and values["pending_approval"]["tool_name"],
        "messages": len(values.get("messages") or []),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


async def main() -> None:
    graph = await build_graph()
    # Tool 반복 한도(agent_max_iterations)는 agent 노드가 직접 세고, recursion_limit은 노드 수 기준 안전망이다.
    recursion_limit = settings.agent_max_iterations * 4 + 20
    session = 1
    thread_id = f"{settings.thread_id}-{session}"

    print(f"workflow 준비 완료. 기준 날짜: {today_label()} / thread_id: {thread_id}")
    print("명령: state, reset, exit")
    while True:
        try:
            query = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not query:
            continue
        if query.lower() in {"exit", "quit"}:
            break
        if query.lower() == "reset":
            session += 1
            thread_id = f"{settings.thread_id}-{session}"  # 새 thread_id = 이전 여행 상태 없는 새 대화
            print(f"새 대화를 시작합니다. (thread_id: {thread_id})")
            continue
        if query.lower() == "state":
            await _print_state(graph, _config(thread_id, recursion_limit))
            continue

        result = await graph.ainvoke({"user_input": query}, _config(thread_id, recursion_limit))
        print(f"ai > {result['answer']}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
