# retrieve 노드: 벡터스토어에서 마지막 사용자 질의와 관련된 문서를 검색해 retrieved_docs에 담는다.

from collections.abc import Awaitable, Callable

from agent.config import settings
from agent.rag.retriever import retrieve_docs
from agent.state import AgentState
from langchain_core.vectorstores import VectorStore


def make_retrieve_node(vectorstore: VectorStore) -> Callable[[AgentState], Awaitable[dict]]:
    async def retrieve_node(state: AgentState) -> dict:
        try:
            query = state["messages"][-1].content
            docs = await retrieve_docs(vectorstore, query, settings.rag_top_k)
        except Exception as exc:
            return {"error": str(exc)}
        return {"retrieved_docs": docs}

    return retrieve_node
