# ask_clarification 노드: 부족한 필수 조건을 한 번의 질문으로 묶어 answer로 내보내고 턴을 끝낸다 (LLM 없음).
# extract가 날짜 모호/모순을 발견해 clarification_note를 남겼다면 그 질문을 함께 보여준다.

from agent.prompts import CLARIFICATION_TEMPLATE, MISSING_FIELD_QUESTIONS
from agent.state import AgentState
from langchain_core.messages import AIMessage


async def ask_clarification_node(state: AgentState) -> dict:
    items = [f"- {MISSING_FIELD_QUESTIONS[f]}" for f in state.get("missing_fields", [])]
    if note := state.get("clarification_note"):
        items.insert(0, f"- {note}")
    answer = CLARIFICATION_TEMPLATE.format(items="\n".join(items))
    # answer는 호출자에게 가는 값이고, 같은 문장을 messages에도 남겨야 다음 턴 LLM이 무엇을 물었는지 안다.
    return {"messages": [AIMessage(content=answer)], "answer": answer}
