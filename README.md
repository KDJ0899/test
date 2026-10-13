# LangGraph AI Agent 예제

LangGraph 기반 AI Agent workflow 레퍼런스 코드. 설계/구현 배경은 [`CLAUDE.md`](./CLAUDE.md) 참고.

## 설치

```bash
uv sync
cp .env.example .env
# .env에 OPENAI_API_KEY / OPENAI_BASE_URL / LLM_MODEL 등을 채운다
# (사내 모델이 OpenAI 호환 API라면 OPENAI_BASE_URL + LLM_MODEL만 바꾸면 됨)
# search_web 툴을 쓰려면 TAVILY_API_KEY도 채운다 (없으면 그 툴만 실패하고 나머지는 그대로 동작).
```

## 실행

FastAPI 없이 CLI로 workflow를 직접 테스트한다.

```bash
uv run python scripts/run_local.py
```

- 대화 이력은 서버가 기억하지 않는다. 이 스크립트가 실제 UI 역할(전체 히스토리를 들고 있다가 매 요청에 함께 보내는 것)을 흉내내서, 매 턴 누적된 히스토리를 통째로 보낸다. `thread_id`는 턴마다 새로 발급한다.
- `save_note` 같은 승인 대상 툴을 호출하면 콘솔에 `[승인 필요] ...` 메시지가 뜨고 `y`/`n`으로 승인/거절할 수 있다.

## 그래프 구조 PNG로 보기

```bash
uv run python scripts/export_graph.py            # graph.png로 저장
uv run python scripts/export_graph.py --out docs/graph.png
```

LangGraph 내장 기능(`graph.get_graph().draw_mermaid_png()`)으로 뽑는다. `build_graph()`가 RAG 인덱싱 때문에
실제로 임베딩 API를 호출하므로 `.env`에 유효한 키가 있어야 하고, PNG 렌더링 자체는 mermaid.ink API를 써서
인터넷 연결이 필요하다.

## 테스트

```bash
uv run pytest
```

실제 LLM/임베딩 API를 호출하지 않고, 가짜 모델/가짜 벡터스토어로 각 노드의 분기·예외 처리·HITL interrupt/resume 메커니즘만 검증한다.

## FastAPI 연결 방법 (CLAUDE.md 3장 계약)

이 저장소는 workflow(State 설계 + 노드 + 그래프 + 툴)까지만 만든다. FastAPI는 이미 구현되어 있다고 가정하고, 아래처럼 `build_graph()`만 가져다 쓴다.

```python
from agent.graph import build_graph
from langchain_core.messages import HumanMessage
from langgraph.types import Command

# 앱 시작 시 1회
graph = await build_graph()

# 대화 이력은 UI가 들고 있다가 매 요청마다 전체를 함께 보낸다 (서버는 이전 턴을 기억하지 않음).
# thread_id는 이 요청(턴) 하나를 위해 새로 발급한다.
config = {"configurable": {"thread_id": new_thread_id()}}

# 일반 질의 (messages = 지금까지의 전체 대화 이력 + 새 질문)
result = await graph.ainvoke({"messages": full_history + [HumanMessage(content=query)]}, config)

# 스트리밍 (FastAPI가 SSE로 변환)
async for event in graph.astream_events({"messages": [...]}, config, version="v2"):
    ...

# HITL 승인 후 재개 (같은 턴의 같은 thread_id로)
await graph.ainvoke(Command(resume={"approved": True}), config)
```

규칙:

- 그래프는 항상 async로 호출한다 (LLM 호출이 async이기 때문).
- 툴 로딩/RAG 인덱싱은 `build_graph()`에서 1회만 일어난다. 요청마다 다시 만들지 않는다.
- `thread_id`는 멀티턴 메모리용이 아니라 **HITL interrupt/resume**을 위한 턴 단위 식별자다. 같은 사용자의 이전 턴과 공유하면 안 된다 (공유하면 checkpointer에 쌓인 이전 메시지와 클라이언트가 다시 보낸 전체 히스토리가 중복됨). 대화 이력 자체는 UI가 관리하고 매 요청에 전체를 실어 보낸다.
- 분류(classify) 노드의 LLM 호출에는 `tags=["internal"]`이 붙어 있다. `astream_events`로 받을 때 이 태그로 필터링하면 사용자에게 보일 필요 없는 내부 분류 과정을 숨길 수 있다.

### Human-in-the-loop (승인 플로우)

`save_note`처럼 상태를 바꾸는 툴은 실행 전에 `interrupt()`로 멈춘다. `graph.ainvoke(...)` 결과에 `__interrupt__` 키가 있으면 승인이 필요하다는 뜻이고, payload 형식은 고정이다:

```python
{"type": "approval_request", "tool": "<툴 이름>", "args": {...}, "message": "<사용자에게 보여줄 설명>"}
```

FastAPI/UI는 이 payload로 승인 UI를 띄우고, 사용자 응답을 아래 형식으로 재개 호출에 넘긴다:

```python
await graph.ainvoke(Command(resume={"approved": True}), config)   # 승인
await graph.ainvoke(Command(resume={"approved": False}), config)  # 거절
```

## 디렉토리 구조

`CLAUDE.md` 4장 참고. 핵심만 요약:

- `src/agent/graph.py` — `build_graph()`. 노드/엣지 조립 지점.
- `src/agent/routing.py` — 조건부 엣지(분기) 함수 전부.
- `src/agent/nodes/` — classify / retrieve / agent / approval / respond / error 노드.
- `src/agent/tools/` — 로컬 샘플 툴 + 툴 레지스트리.
- `src/agent/rag/` — 문서 로딩 + 벡터스토어 검색.
- `data/docs/` — RAG 샘플 문서. `data/sample_items.json` — 툴 샘플 데이터.
- `scripts/run_local.py` — FastAPI 없이 CLI로 workflow 테스트.
