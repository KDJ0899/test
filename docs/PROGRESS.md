# 진행 기록 (스포츠 여행 Agent)

최종 갱신: 2026-10-27. 다음 세션은 이 문서부터 읽고 이어간다.

## 현재 상태
- `SPORTS_TRIP_AGENT_IMPLEMENTATION.md` 12장 1~9단계 구현 완료. `uv run pytest` 68개 통과 (일정 저장/승인 제거 후) (전부 가짜 LLM).
- **실제 LLM/API 키로 end-to-end는 아직 한 번도 돌려보지 않음.** 프롬프트 품질, 분류 정확도는 미검증.
- UI/FastAPI는 만들지 않음 (요청 범위 밖). `scripts/run_local.py`로 멀티턴 확인.

## 확정된 설계 결정 (사용자 지시)
1. 상태 관리: 체크포인터 없음. 호출자가 invoke 결과(전체 State)를 보관했다가 다음 턴에 `user_input`과 함께 다시 전달. 명세서가 CLAUDE.md보다 우선. 서버 연동 설명과 차이는 README에 명시.
2. Tavily/웹 검색 완전 제거 (코드·설정·의존성·테스트·문서).
3. 의도는 `chat / trip / qa` 3개. RAG는 별도 의도가 아니라 문서 검색 기능.
4. 문서 검색은 하이브리드(C안):
   - classify가 `needs_guide`를 같이 판단 -> True면 `retrieve -> agent` 강제 검색
   - 일정 작성 전 `retrieve_for_plan`(조건으로 만든 고정 질의) 항상 실행
   - `search_guide_docs` 툴은 agent의 보충 검색용으로만 유지
5. 일정 저장(`save_trip_plan`)과 사용자 승인(HITL) 흐름은 제거했다 (2026-10-27, 사용자 지시). 가이드 RAG와 후보 선택(`present_candidates`)은 유지.
6. FastAPI 코드는 수정하지 않는다.

## 그래프
classify -> (error | extract_preferences | retrieve | agent)
extract_preferences -> validate_preferences -> (ask_clarification | agent)
agent -> (error | tools | present_candidates | retrieve_for_plan | respond)
tools -> ingest_tool_results -> agent
retrieve_for_plan -> plan_trip -> respond
다이어그램: `docs/graph.mmd`, `docs/graph.png` (`scripts/draw_graph.py`로 재생성). 상세 설계는 `docs/WORKFLOW_DESIGN.md`.

## 주요 파일
- `teams/team5/`: graph, routing, state, prompts, config, clock, trip_state, trip_validation
- `teams/team5/nodes/`: classify, extract_preferences, validate_preferences, ask_clarification, retrieve, agent, ingest_tool_results, present_candidates, plan_trip, respond, error, save_session
- `teams/team5/tools/local_tools.py`: get_current_datetime, search_sports_events, search_places, search_restaurants
- `teams/team5/rag/`: loader, retriever, guide_tool
- `teams/team5/data/`: sports_events.json(7, 가상), tourist_places.json(10), restaurants.json(8), docs/{baseball,travel,transport}_guide.md
- `tests/`: conftest(ScriptedLLM 등), test_tools/routing/preferences/nodes/multiturn/trip_validation

## 알려진 위험 / 미검증
- `needs_guide`는 분류 LLM 판단. 안내 질문을 False로 내면 검색 누락.
- 여행 계획 중 나온 안내 질문(예: 일정 도중 "준비물은?")이 `trip`으로 분류되면 강제 검색을 안 탄다. `qa`로 보낼지 분류 프롬프트로 유도 필요.
- 실모델에서 구조화 출력(classify, extract, plan_trip) 안정성, 일정 검증 후 1회 재작성 동작 확인 필요.

## 다음 후보 (사용자 미요청)
1. `teams/team5/config.py`에 실제 모델/키 설정 후 `scripts/run_local.py`로 명세 11장 시나리오(T01~T14) 수동 검증, 프롬프트 튜닝
2. (제거됨) 일정 저장/불러오기
3. 영구 체크포인터(SQLite 등)
4. 데이터 확장 (팀/구장/날짜)

## 작업 시 주의 (Windows)
- Bash heredoc에 한글+따옴표 섞이면 파싱 실패 가능. 파일은 Write/Edit 도구 사용.
- 사용자 소유 파일: `requirements*.txt`, `scripts/draw_workflow.py`.
- git 커밋 안 함 (사용자 요청 시에만). 변경은 working tree에 있음.
