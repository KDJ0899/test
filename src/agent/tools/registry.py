# 로컬 툴 레지스트리. agent 노드는 이 레지스트리만 바라본다.

from langchain_core.tools import BaseTool

from agent.tools.local_tools import LOCAL_TOOLS

# 실행 전 사용자 승인이 필요한 툴 이름 (approval 노드가 참조)
REQUIRES_APPROVAL: set[str] = {"save_note", "search_web"}


async def load_tools() -> list[BaseTool]:
    """build_graph()에서 1회 호출."""
    return list(LOCAL_TOOLS)
