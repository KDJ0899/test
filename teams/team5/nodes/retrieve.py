# retrieve 노드: 벡터스토어에서 가이드 문서를 검색해 retrieved_docs에 담는다 (LLM의 툴 선택과 무관하게 코드가 검색을 강제한다).
# 두 곳에서 쓴다: (1) classify가 needs_guide=True로 판단한 질문의 agent 호출 전, (2) 일정 작성(plan_trip) 직전.
# (2)는 항상 필요하므로 판단 없이 조건에서 만든 고정 질의로 검색한다. 이미 툴로 찾은 문서와는 내용 기준으로 중복을 제거한다.

from collections.abc import Awaitable, Callable

from teams.team5 import config
from teams.team5.prompts import PLAN_GUIDE_QUERY_TEMPLATE, TRANSPORT_LABELS
from teams.team5.rag.retriever import retrieve_docs
from teams.team5.state import MyState
from langchain_core.vectorstores import VectorStore


def build_plan_guide_query(state: MyState) -> str:
    transport = state.get("trip_preferences", {}).get("transport", "unspecified")
    return PLAN_GUIDE_QUERY_TEMPLATE.format(transport=TRANSPORT_LABELS.get(transport, TRANSPORT_LABELS["unspecified"]))


def make_retrieve_node(vectorstore: VectorStore, for_plan: bool = False) -> Callable[[MyState], Awaitable[dict]]:
    async def retrieve_node(state: MyState) -> dict:
        try:
            query = build_plan_guide_query(state) if for_plan else state["user_input"]
            docs = await retrieve_docs(vectorstore, query, config.RAG_TOP_K)
        except Exception as exc:
            return {"error": str(exc)}
        existing = state.get("retrieved_docs") or []
        seen = {d.page_content for d in existing}
        return {"retrieved_docs": [*existing, *(d for d in docs if d.page_content not in seen)]}

    return retrieve_node
