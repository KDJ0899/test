# 로컬 샘플 툴 단위 테스트.

import json

from agent.tools import local_tools


def test_calculate_valid_expression():
    assert local_tools.calculate.invoke({"expression": "(3 + 5) * 2"}) == "16"


def test_calculate_rejects_unsafe_expression():
    result = local_tools.calculate.invoke({"expression": "__import__('os').system('echo hi')"})
    assert "계산 실패" in result


def test_get_current_datetime_returns_iso_format():
    result = local_tools.get_current_datetime.invoke({})
    # ISO 8601 형식인지만 확인 (실제 시각 값은 테스트하지 않음)
    assert "T" in result


def test_search_items_by_query():
    result = json.loads(local_tools.search_items.invoke({"query": "마우스"}))
    assert len(result) == 1
    assert result[0]["name"] == "무선 마우스"


def test_search_items_by_category():
    result = json.loads(local_tools.search_items.invoke({"category": "사무용품"}))
    assert all(item["category"] == "사무용품" for item in result)
    assert len(result) >= 1


def test_search_items_no_match():
    result = local_tools.search_items.invoke({"query": "존재하지않는상품이름"})
    assert result == "검색 결과가 없습니다."


async def test_search_web_returns_formatted_results(monkeypatch):
    class FakeTavilyClient:
        def __init__(self, api_key):
            self.api_key = api_key

        async def search(self, query, max_results=5):
            return {
                "results": [
                    {"title": "결과1", "content": "내용1", "url": "https://example.test/1"},
                ]
            }

    monkeypatch.setattr(local_tools, "AsyncTavilyClient", FakeTavilyClient)

    result = await local_tools.search_web.ainvoke({"query": "테스트 질문"})

    assert "결과1" in result
    assert "https://example.test/1" in result


async def test_search_web_handles_no_results(monkeypatch):
    class FakeTavilyClient:
        def __init__(self, api_key):
            pass

        async def search(self, query, max_results=5):
            return {"results": []}

    monkeypatch.setattr(local_tools, "AsyncTavilyClient", FakeTavilyClient)

    result = await local_tools.search_web.ainvoke({"query": "테스트 질문"})

    assert result == "검색 결과가 없습니다."


async def test_search_web_handles_exception(monkeypatch):
    class FakeTavilyClient:
        def __init__(self, api_key):
            pass

        async def search(self, query, max_results=5):
            raise RuntimeError("api down")

    monkeypatch.setattr(local_tools, "AsyncTavilyClient", FakeTavilyClient)

    result = await local_tools.search_web.ainvoke({"query": "테스트 질문"})

    assert "웹 검색 실패" in result


def test_save_note_writes_jsonl(monkeypatch, tmp_path):
    notes_path = tmp_path / "notes.jsonl"
    monkeypatch.setattr(local_tools, "NOTES_PATH", notes_path)

    result = local_tools.save_note.invoke({"note": "테스트 메모"})

    assert "테스트 메모" in result
    lines = notes_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["note"] == "테스트 메모"
