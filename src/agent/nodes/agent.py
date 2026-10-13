# agent 노드: 시스템 프롬프트 + (RAG면 검색 문서 컨텍스트) + 대화 이력으로 LLM을 호출한다.
# 툴은 build_graph()에서 1회 로딩해 bind_tools로 묶어두고 재사용한다 (요청마다 다시 만들지 않음).
# intent == "tool"일 때만 툴을 바인딩한 모델을 쓴다 (그 외에는 LLM이 괜히 툴을 부르지 않게).

from collections.abc import Callable
from typing import Awaitable

from agent.llm import get_llm
from agent.prompts import RAG_CONTEXT_TEMPLATE, SYSTEM_PROMPT
from agent.state import AgentState
from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool


def make_agent_node(tools: list[BaseTool] | None = None) -> Callable[[AgentState], Awaitable[dict]]:
    llm = get_llm()
    llm_with_tools = llm.bind_tools(tools) if tools else llm

    async def agent_node(state: AgentState) -> dict:
        model = llm_with_tools if state.get("intent") == "tool" else llm

        messages = [SystemMessage(content=SYSTEM_PROMPT)]
        docs = state.get("retrieved_docs") or []
        if docs:
            context = "\n\n".join(doc.page_content for doc in docs)
            messages.append(SystemMessage(content=RAG_CONTEXT_TEMPLATE.format(context=context)))
        messages.extend(state["messages"])

        try:
            response = await model.ainvoke(messages)
        except Exception as exc:
            return {"error": str(exc)}
        return {"messages": [response]}

    return agent_node
