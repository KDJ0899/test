# 로컬 툴 레지스트리. agent 노드는 이 레지스트리만 바라본다.

from agent.config import settings
from agent.tools.local_tools import LOCAL_TOOLS
from langchain_core.tools import BaseTool

# 실행 전 사용자 승인이 필요한 툴 이름. 기본은 save_trip_plan이고 .env의 APPROVAL_REQUIRED_TOOLS로 바꾼다.
REQUIRES_APPROVAL: set[str] = set(settings.approval_required_tools)


async def load_tools() -> list[BaseTool]:
    """build_graph()에서 1회 호출."""
    return list(LOCAL_TOOLS)


def get_tool(name: str) -> BaseTool | None:
    """이름으로 레지스트리의 툴을 찾는다. 승인된 실행(execute_approved_tool)이 허용된 툴만 호출하도록 검증하는 데 쓴다."""
    return next((t for t in LOCAL_TOOLS if t.name == name), None)
