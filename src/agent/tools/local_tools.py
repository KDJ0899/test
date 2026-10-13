# 로컬 샘플 툴 모음. 주제 중립적인 범용 툴로, 조회/계산/변경 각 유형을 하나씩 보여준다.
# save_note는 상태를 바꾸는 툴이라 HITL 승인 대상이다 (registry.py의 REQUIRES_APPROVAL).
# search_web은 저장소 안 데이터가 아니라 실제 외부 API(Tavily)를 호출하는 유일한 예외다 (CLAUDE.md 환경 제약 참고).

import ast
import json
import operator
from datetime import datetime
from pathlib import Path

from agent.config import settings
from langchain_core.tools import tool
from tavily import AsyncTavilyClient

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
ITEMS_PATH = DATA_DIR / "sample_items.json"
NOTES_PATH = DATA_DIR / "notes.jsonl"

_ALLOWED_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_ALLOWED_UNARY_OPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _safe_eval(node: ast.AST) -> float:
    """eval 없이 사칙연산 수식만 안전하게 계산하는 재귀 평가기. 허용되지 않은 노드는 거부한다."""
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BIN_OPS:
        return _ALLOWED_BIN_OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARY_OPS:
        return _ALLOWED_UNARY_OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError(f"허용되지 않은 수식입니다: {ast.dump(node)}")


@tool
def get_current_datetime() -> str:
    """현재 날짜와 시간을 ISO 8601 형식 문자열로 반환한다. 인자가 필요 없다."""
    return datetime.now().isoformat(timespec="seconds")


@tool
def calculate(expression: str) -> str:
    """사칙연산(+ - * / ** % 괄호) 수식을 계산한다. 예: "(3 + 5) * 2". eval을 쓰지 않는 안전한 파서로 계산한다."""
    try:
        tree = ast.parse(expression, mode="eval")
        result = _safe_eval(tree)
    except Exception as exc:
        return f"계산 실패: {exc}"
    return str(result)


@tool
def search_items(query: str | None = None, category: str | None = None) -> str:
    """샘플 상품 목록에서 키워드(query)나 카테고리(category)로 검색한다. 둘 다 생략하면 전체 목록을 반환한다."""
    items = json.loads(ITEMS_PATH.read_text(encoding="utf-8"))

    results = items
    if category:
        results = [item for item in results if item["category"] == category]
    if query:
        results = [
            item
            for item in results
            if query.lower() in item["name"].lower() or query.lower() in item["description"].lower()
        ]

    if not results:
        return "검색 결과가 없습니다."
    return json.dumps(results, ensure_ascii=False)


@tool
async def search_web(query: str) -> str:
    """실시간 웹 검색을 한다 (Tavily API). 최신 뉴스/시세처럼 저장소 안 데이터나 모델 지식만으로는
    답할 수 없는, 지금 인터넷에서 찾아봐야 하는 정보가 필요할 때만 사용한다."""
    client = AsyncTavilyClient(api_key=settings.tavily_api_key)
    try:
        response = await client.search(query, max_results=5)
    except Exception as exc:
        return f"웹 검색 실패: {exc}"

    results = response.get("results", [])
    if not results:
        return "검색 결과가 없습니다."

    lines = [f"- {r['title']}: {r['content'][:200]} ({r['url']})" for r in results]
    return "\n".join(lines)


@tool
def save_note(note: str) -> str:
    """메모를 로컬 파일(data/notes.jsonl)에 저장한다. 파일/설정 등을 바꾸는 작업이라 실행 전 사용자 승인이 필요하다."""
    entry = {"note": note, "saved_at": datetime.now().isoformat(timespec="seconds")}
    with NOTES_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return f"메모를 저장했습니다: {note}"


LOCAL_TOOLS = [get_current_datetime, calculate, search_items, search_web, save_note]
