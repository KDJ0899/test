# classify 노드: 마지막 사용자 질의를 chat/rag/tool 중 하나로 분류한다.
# 분류용 LLM 호출은 사용자에게 보일 필요가 없어서 tags=["internal"]을 붙인다 (FastAPI가 필터링할 수 있게, 5.9).

from collections.abc import Awaitable, Callable
from typing import Literal

from agent.llm import get_llm
from agent.prompts import CLASSIFY_SYSTEM_PROMPT
from agent.state import AgentState
from langchain_core.messages import SystemMessage
from pydantic import BaseModel


class IntentClassification(BaseModel):
    intent: Literal["chat", "rag", "tool"]


def make_classify_node() -> Callable[[AgentState], Awaitable[dict]]:
    structured_llm = get_llm().with_structured_output(IntentClassification)

    async def classify_node(state: AgentState) -> dict:
        try:
            messages = [SystemMessage(content=CLASSIFY_SYSTEM_PROMPT), *state["messages"]]
            result = await structured_llm.ainvoke(messages, config={"tags": ["internal"]})
        except Exception as exc:
            return {"error": str(exc)}
        # 매 턴 시작 시 intent/retrieved_docs/error를 분류 노드가 덮어쓴다 (5.1).
        return {"intent": result.intent, "retrieved_docs": [], "error": None}

    return classify_node
