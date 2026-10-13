# respond 노드: 마지막 AI 메시지를 최종 답변 문자열(answer)로 꺼내 그래프 출력으로 넘긴다.
# RAG로 검색한 문서가 있으면 출처(파일명)를 덧붙인다.

from agent.state import AgentState


async def respond_node(state: AgentState) -> dict:
    answer = str(state["messages"][-1].content)

    docs = state.get("retrieved_docs") or []
    if docs:
        sources = sorted({doc.metadata.get("source", "unknown") for doc in docs})
        answer = f"{answer}\n\n출처: {', '.join(sources)}"

    # output_schema(OutputState)에 정의된 answer 키만 호출자에게 반환된다.
    return {"answer": answer}
