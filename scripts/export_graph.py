"""그래프 구조를 PNG로 뽑아보는 스크립트. LangGraph 내장 기능(draw_mermaid_png)을 쓴다.

build_graph()가 RAG 인덱싱 때문에 실제로 임베딩 API를 호출하므로, .env에 유효한
OPENAI_API_KEY(또는 사내 호환 엔드포인트)가 있어야 한다. draw_mermaid_png 자체는
mermaid.ink API로 렌더링하므로 인터넷 연결이 필요하다.

사용법:
    uv run python scripts/export_graph.py
    uv run python scripts/export_graph.py --out docs/graph.png
"""

import argparse
import asyncio

from agent.graph import build_graph


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="graph.png", help="저장할 PNG 경로 (기본: graph.png)")
    args = parser.parse_args()

    graph = await build_graph()
    graph.get_graph().draw_mermaid_png(output_file_path=args.out)
    print(f"저장됨: {args.out}")


if __name__ == "__main__":
    asyncio.run(main())
