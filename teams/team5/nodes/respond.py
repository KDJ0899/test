# respond 노드: 마지막 AI 메시지를 최종 답변 문자열(answer)로 꺼내 State에 담는다.
# RAG로 검색한 문서가 있으면 출처(파일명)를 덧붙인다.

from teams.team5.state import MyState


def respond_node(state: MyState) -> dict:
    answer = str(state["messages"][-1].content)

    docs = state.get("retrieved_docs") or []
    if docs:
        sources = sorted({doc.metadata.get("source", "unknown") for doc in docs})
        answer = f"{answer}\n\n출처: {', '.join(sources)}"

    return {"answer": answer}
