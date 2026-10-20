"""workflow 그래프 구조를 mermaid(.mmd)와 PNG로 저장한다. LLM/임베딩 호출 없이 구조만 그린다.

사용법: uv run python scripts/draw_workflow.py  ->  docs/graph.mmd, docs/graph.png
PNG는 mermaid.ink 서비스를 호출해 만든다(외부 접속 필요). 실패하면 .mmd만 저장된다.
"""

import asyncio
from pathlib import Path

import teams.team5.workflow as graph_module
from teams.team5 import config

OUT_DIR = Path(__file__).resolve().parents[1] / "docs"


class _Stub:
    """그래프 구조만 필요하므로 LLM/임베딩/벡터스토어는 가짜로 대체한다."""

    def bind_tools(self, tools):
        return self

    def with_structured_output(self, schema):
        return self


async def main() -> None:
    config.OPENAI_API_KEY = config.OPENAI_API_KEY or "dummy"
    graph_module.get_llm = lambda **kw: _Stub()
    graph_module.get_embeddings = lambda: None

    async def _no_index(docs, embeddings):
        return None

    graph_module.build_vectorstore = _no_index
    # 노드 팩토리들이 모듈 안에서 get_llm을 직접 import하므로 해당 모듈에도 같은 대체를 적용한다.
    import teams.team5.nodes.agent as agent_node
    import teams.team5.nodes.classify as classify_node

    agent_node.get_llm = classify_node.get_llm = lambda **kw: _Stub()

    graph = (await graph_module.build_graph()).get_graph()
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "graph.mmd").write_text(graph.draw_mermaid(), encoding="utf-8")
    print(f"saved {OUT_DIR / 'graph.mmd'}")
    try:
        (OUT_DIR / "graph.png").write_bytes(graph.draw_mermaid_png())
        print(f"saved {OUT_DIR / 'graph.png'}")
    except Exception as exc:
        print(f"PNG 생성 실패 (.mmd만 저장): {exc}")


if __name__ == "__main__":
    asyncio.run(main())
