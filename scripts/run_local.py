"""FastAPI 없이 CLI로 workflow 테스트하는 스크립트.

대화 이력은 서버(그래프)가 기억하지 않는다. 실제 서비스에서 UI가 하는 역할(전체 히스토리를
들고 있다가 매 요청에 함께 보내는 것)을 여기서는 이 스크립트가 흉내낸다.
thread_id는 매 턴 새로 발급한다 - checkpointer는 HITL interrupt/resume 때문에만 필요하다.

사용법: uv run python scripts/run_local.py
종료: exit / quit / Ctrl+C
"""

import asyncio
import sys
import uuid

from agent.config import settings
from agent.graph import build_graph
from langchain_core.messages import AnyMessage, HumanMessage
from langgraph.types import Command


async def _run_turn(graph, recursion_limit: int, history: list[AnyMessage], query: str) -> list[AnyMessage]:
    """한 턴을 실행한다. interrupt(승인 요청)가 뜨면 콘솔에서 y/n을 받아 resume까지 처리하고,
    최종 메시지 히스토리(이번 턴까지 누적된 전체)를 반환한다."""
    config = {
        "configurable": {"thread_id": str(uuid.uuid4())},  # 턴 전용 id. 이전 턴과 공유하지 않는다.
        "recursion_limit": recursion_limit,
    }

    payload = {"messages": [*history, HumanMessage(content=query)]}
    result = await graph.ainvoke(payload, config)

    while result.get("__interrupt__"):
        request = result["__interrupt__"][0].value
        print(f"[승인 필요] {request['message']}")
        answer = input("approve? (y/n)> ").strip().lower()
        result = await graph.ainvoke(Command(resume={"approved": answer == "y"}), config)

    print(f"ai > {result['messages'][-1].content}")
    return result["messages"]


async def main() -> None:
    graph = await build_graph()
    history: list[AnyMessage] = []

    print("workflow 준비 완료. 'exit' 입력 시 종료.")
    while True:
        try:
            query = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not query:
            continue
        if query.lower() in {"exit", "quit"}:
            break

        history = await _run_turn(graph, settings.agent_max_iterations, history, query)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
