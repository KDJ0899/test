# 로컬 툴 레지스트리. workflow는 이 레지스트리만 바라본다.

from teams.team5.tools.local_tools import LOCAL_TOOLS
from langchain_core.tools import BaseTool


def load_tools() -> list[BaseTool]:
    """build_graph()에서 1회 호출."""
    return list(LOCAL_TOOLS)
