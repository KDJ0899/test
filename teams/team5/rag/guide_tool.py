# search_guide_docs 툴: RAG를 별도 노드가 아니라 Agent가 고를 수 있는 툴로 제공한다.
# 벡터스토어는 build_graph()에서 1회 만들어 이 툴에 주입한다 (요청마다 인덱싱하지 않음).
# 결과는 다른 툴과 같은 {status, source, data} 형식이고, ingest_tool_results가 State의 retrieved_docs에 반영해 respond가 출처를 표시한다.

import json

from teams.team5 import config
from teams.team5.rag.retriever import retrieve_docs
from langchain_core.tools import BaseTool, tool
from langchain_core.vectorstores import VectorStore

SOURCE = "local:docs"


def make_search_guide_tool(vectorstore: VectorStore) -> BaseTool:
    @tool
    def search_guide_docs(query: str) -> str:
        """야구장 관람 준비물, 입장/관람 방법, 여행 일정 원칙, 대중교통 이용 같은 가이드 문서를 검색한다.
        일반 안내 질문에 답하거나 일정을 만들 때 참고 원칙이 필요하면 사용한다.
        실제 경기 일정은 이 툴이 아니라 search_sports_events로 확인해야 한다."""
        try:
            docs = retrieve_docs(vectorstore, query, config.RAG_TOP_K)
        except Exception as exc:
            return json.dumps({"status": "error", "source": SOURCE, "data": None, "error": f"문서 검색 실패: {exc}"}, ensure_ascii=False)
        items = [{"source": d.metadata.get("source", "unknown"), "content": d.page_content} for d in docs]
        return json.dumps({"status": "ok", "source": SOURCE, "data": {"docs": items, "count": len(items)}}, ensure_ascii=False)

    return search_guide_docs
