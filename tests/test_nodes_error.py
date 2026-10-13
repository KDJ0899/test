# error 노드 단위 테스트.

from agent.nodes.error import error_node


async def test_error_node_formats_message():
    state = {"messages": [], "error": "something went wrong"}
    result = await error_node(state)
    assert "something went wrong" in result["messages"][0].content
