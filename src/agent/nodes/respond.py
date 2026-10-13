# respond 노드: 최종 AI 메시지를 정리해 사용자에게 보여줄 형태로 마무리한다.
# RAG로 검색한 문서가 있으면 출처(파일명)를 덧붙인다 (6단계에서 실제 동작 추가).

from agent.state import AgentState


async def respond_node(state: AgentState) -> dict:
    docs = state.get("retrieved_docs") or []
    if not docs:
        return {}

    sources = sorted({doc.metadata.get("source", "unknown") for doc in docs})
    last_message = state["messages"][-1]
    annotated_content = f"{last_message.content}\n\n출처: {', '.join(sources)}"
    return {"messages": [last_message.model_copy(update={"content": annotated_content})]}
