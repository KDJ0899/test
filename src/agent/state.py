# 그래프 전체에서 공유되는 State 정의.
# messages는 add_messages 리듀서로 누적되고, 나머지는 매 턴 classify 노드에서 덮어쓴다.

from typing import Annotated, Literal

from langchain_core.documents import Document
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    intent: Literal["chat", "rag", "tool"] | None
    retrieved_docs: list[Document]
    error: str | None
