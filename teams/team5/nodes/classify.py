# classify 노드: 이번 턴 사용자 입력(user_input)을 messages에 정확히 한 번 추가하고, 의도를 chat/trip/qa로 분류하고, 가이드 문서 검색이 필요한지(needs_guide)도 같은 호출에서 판단한다.
# 승인 대기(pending_approval)가 있으면 LLM 분류 없이 승인 처리로 보낸다 (routing.py의 route_after_classify).
# 분류 LLM 호출은 사용자에게 보일 필요가 없어서 tags=["internal"]을 붙인다 (FastAPI가 필터링할 수 있게).

from collections.abc import Awaitable, Callable
from typing import Literal

from app.llm import get_llm
from teams.team5.prompts import CLASSIFY_SYSTEM_PROMPT
from teams.team5.state import MyState
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field


class IntentClassification(BaseModel):
    intent: Literal["chat", "trip", "qa"]
    needs_guide: bool = Field(
        default=False,
        description="야구장 준비물/관람 방법/여행 원칙/대중교통 같은 가이드 문서가 있어야 답할 수 있는 질문이면 true",
    )


def make_classify_node() -> Callable[[MyState], Awaitable[dict]]:
    structured_llm = get_llm().with_structured_output(IntentClassification)

    async def classify_node(state: MyState) -> dict:
        user_message = HumanMessage(content=state["user_input"])
        # 호출자가 넘겨준 이전 messages 뒤에 이번 입력만 add_messages로 한 번 추가한다.
        # 턴 단위 값(intent/missing_fields/retrieved_docs/error/answer)은 여기서 초기화하고,
        # 여행 상태(trip_preferences, sports_events, trip_plan, pending_approval ...)는 건드리지 않아 다음 턴에도 유지된다.
        reset = {
            "messages": [user_message],
            "retrieved_docs": [],
            "needs_guide": False,
            "missing_fields": [],
            "clarification_note": None,
            "approval_decision": None,
            "tool_iterations": 0,
            "error": None,
            "answer": "",
        }

        if state.get("pending_approval"):
            return {**reset, "intent": None}

        try:
            system = CLASSIFY_SYSTEM_PROMPT.format(trip_status=state.get("trip_status", "idle"))
            messages = [SystemMessage(content=system), *state.get("messages", []), user_message]
            result = await structured_llm.ainvoke(messages, config={"tags": ["internal"]})
        except Exception as exc:
            return {**reset, "intent": None, "error": str(exc)}
        return {**reset, "intent": result.intent, "needs_guide": result.needs_guide}

    return classify_node
