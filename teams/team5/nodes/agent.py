# agent 노드: 시스템 프롬프트 + 여행 상태 컨텍스트 + 대화 이력으로 LLM을 호출한다 (ReAct의 '추론' 부분).
# 툴은 build_graph()에서 1회 bind_tools로 묶어 재사용한다. intent가 trip/qa일 때만 툴을 바인딩한 모델을 쓴다.
# Tool 반복 횟수(tool_iterations)가 한도를 넘으면 LLM을 부르지 않고 error로 보낸다 (무한 루프 방지).

import json
import logging
from collections.abc import Awaitable, Callable

from teams.team5.clock import today_label
from teams.team5 import config
from app.llm import get_llm
from teams.team5.prompts import NO_NOTICE, SYSTEM_PROMPT, TRIP_CONTEXT_TEMPLATE
from teams.team5.state import MyState
from teams.team5.trip_state import describe_event, describe_events, selected_event
from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)


def build_trip_context(state: MyState) -> str:
    event = selected_event(state)
    return TRIP_CONTEXT_TEMPLATE.format(
        today=today_label(),
        trip_status=state.get("trip_status", "idle"),
        preferences=json.dumps(state.get("trip_preferences", {}), ensure_ascii=False),
        selected_event=describe_event(event) if event else "(없음)",
        events=describe_events(state),
        place_count=len(state.get("places") or []),
        restaurant_count=len(state.get("restaurants") or []),
        has_plan="있음" if state.get("trip_plan") else "없음",
        notice=state.get("event_notice") or NO_NOTICE,
    )


def make_agent_node(tools: list[BaseTool] | None = None) -> Callable[[MyState], Awaitable[dict]]:
    llm = get_llm()
    llm_with_tools = llm.bind_tools(tools) if tools else llm

    async def agent_node(state: MyState) -> dict:
        if state.get("tool_iterations", 0) >= config.AGENT_MAX_ITERATIONS:
            return {"error": f"Tool 호출이 최대 {config.AGENT_MAX_ITERATIONS}회를 넘어 중단했습니다."}

        intent = state.get("intent")
        model = llm_with_tools if intent in ("trip", "qa") else llm

        messages = [SystemMessage(content=SYSTEM_PROMPT)]
        if intent in ("trip", "qa"):
            messages.append(SystemMessage(content=build_trip_context(state)))
        messages.extend(state["messages"])

        try:
            response = await model.ainvoke(messages)
        except Exception as exc:
            return {"error": str(exc)}
        return {"messages": [response]}

    return agent_node
