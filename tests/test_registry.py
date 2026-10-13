# 툴 레지스트리 테스트.

from agent.tools.registry import REQUIRES_APPROVAL, load_tools


async def test_load_tools_returns_local_tools():
    tools = await load_tools()
    names = {t.name for t in tools}
    assert names == {"get_current_datetime", "calculate", "search_items", "search_web", "save_note"}


def test_requires_approval_contains_save_note_and_search_web():
    assert REQUIRES_APPROVAL == {"save_note", "search_web"}
