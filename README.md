# 스포츠 여행 Agent (LangGraph 레퍼런스)

야구(KBO) 경기 관람과 여행 일정을 함께 계획하는 LangGraph Agent 예제. 구현 명세는 [`SPORTS_TRIP_AGENT_IMPLEMENTATION.md`](./SPORTS_TRIP_AGENT_IMPLEMENTATION.md),
공통 규칙은 [`CLAUDE.md`](./CLAUDE.md)를 따른다. UI와 FastAPI는 이 저장소 범위가 아니다.

## 설치

```bash
uv sync
# teams/team5/config.py 의 OPENAI_API_KEY / OPENAI_BASE_URL / LLM_MODEL / EMBEDDING_MODEL 을 직접 채운다 (OpenAI 호환 API)
# 샘플 경기가 2026-10~11월이므로 데모에서는 config.py 의 TODAY_OVERRIDE = "2026-10-16" 으로 기준 날짜를 고정한다
```

## 실행 (멀티턴 CLI)

```bash
uv run python scripts/run_local.py
```

- 체크포인터 없이, 스크립트가 `graph.invoke`가 돌려준 전체 State를 들고 있다가 다음 턴에 `user_input`과 함께 다시 넘긴다 (프로세스를 끝내면 사라짐).
- CLI 명령: `state`(현재 State 요약), `reset`(State를 비우고 새 대화), `exit`.
- 데모 대화 예시 (`TODAY_OVERRIDE = "2026-10-16"`):

```
you> 롯데 경기 보고 여행 가고 싶어          -> 날짜 범위/여행 기간을 한 번에 질문
you> 다음 달 토요일 중 1박 2일               -> 팀 조건 유지 + 11월 토요일 경기 후보 3개 제시
you> 두 번째 경기로                          -> event_id 선택, 관광지/식당 검색 후 후보 목록을 보여주고 선택을 기다림
you> 관광지 1, 3 / 식당 2                    -> 고른 곳을 꼭 포함해 상세 타임테이블(이동·식사·휴식 포함) 작성 ("알아서 짜줘"도 가능)
you> 차 없이 갈 거고 둘째 날 바다 관광 추가해 줘 -> 선택 경기 유지, 일정 수정
you> 야구장 준비물은?                        -> 가이드 문서 기반 답변 + 출처 표시
you> 이번 주 롯데 경기만 알려줘              -> 여행 기간을 묻지 않고 경기만 조회
you> 11/4 18:30 KT 위즈 vs LG 트윈스 경기로 2박 3일, 3~5일로 갈 거야 -> 후보 목록 없이 바로 그 경기를 선택 (여행 11/3~11/5)
you> 11/4 21:00 롯데 vs 삼성 경기로 1박 2일  -> 그런 경기가 없다고 알리고, 같은 날짜/비슷한 시각/언급한 팀의 경기를 후보로 제시
```

## Workflow

그래프 도식은 [`docs/graph.mmd`](./docs/graph.mmd) (`uv run python scripts/draw_workflow.py`로 재생성).

```
classify ─ trip ─> extract_preferences -> validate_preferences ─ 부족 ─> ask_clarification -> END
        │                                                      └ 충분 ─> agent
        ├ chat / qa ─> agent  (qa: 안내 질문, 경기 일정 조회 등)
        └ needs_guide ─> retrieve -> agent   (가이드 문서가 필요한 질문은 검색을 코드가 강제)
agent ─ Tool 호출 ─> tools -> ingest_tool_results -> agent   (최대 반복 AGENT_MAX_ITERATIONS)
      ├ 일정 작성 단계 ─> (경기당 1회) present_candidates(관광지/식당 후보 안내, 선택을 받고 END)
      │                 └ 선택 후 ─> retrieve_for_plan(고정 질의 검색 강제) -> plan_trip -> respond   (validate_trip_plan 검증, 실패 시 재작성)
      └ 최종 답 ─> respond -> END          (어느 노드든 예외는 handle_error 노드로)
```

| 파일 | 역할 |
|---|---|
| `state.py` | `MyState`(대화 + 여행 상태) |
| `routing.py` | 조건부 엣지 함수 전부 |
| `nodes/` | classify, extract_preferences, validate_preferences, ask_clarification, retrieve, agent, ingest_tool_results, present_candidates, plan_trip, respond, error, save_session |
| `trip_state.py`, `trip_validation.py` | State 파생 계산, 일정 검증(`validate_trip_plan`) |
| `tools/` | 로컬 조회 Tool 4개와 레지스트리 |
| `rag/` | 문서 로딩/벡터스토어, `search_guide_docs` 툴(강제 검색 뒤 추가로 찾을 때 Agent가 쓰는 보충용) |
| `clock.py` | 기준 날짜 (`TODAY_OVERRIDE`) |

State 관리 요점:
- 턴 단위 값(`intent`, `missing_fields`, `event_notice`, `retrieved_docs`, `error`, `answer`)은 `classify`가 매 턴 초기화하고, 여행 상태(`trip_preferences`, `sports_events`, `selected_event_id`, `trip_plan` ...)는 유지한다.
- 경기를 직접 지목하면("11/4 18:30 KT vs LG", 날짜 형식은 2026-11-04 / 11/4 / 11월 4일) 후보 목록 없이도 `ingest_tool_results`가 검색 결과에서 그 경기를 바로 고른다. 검색 결과에 없으면 전체 일정에서 다시 찾고, 그래도 없으면 같은 날짜·비슷한 시각 경기와 언급한 팀의 경기를 후보로 담아 `event_notice`로 "요청한 경기가 없다"고 알린다. 시각을 말하면 정확히 일치해야 한다.
- 여행 날짜를 일(日)만 말하면("3~5일로 갈 거야") 경기의 달에 붙여 11/3~11/5로 해석하고, 경기일만 말하면 그 하루를 검색 범위로 쓴다. 경기를 고른 2일 이상 여행에 날짜 범위가 여행 기간과 맞지 않으면 `trip_start`(여행 날짜)를 묻는다.
- 경기를 고르면 일정을 짜기 전에 `present_candidates`가 관광지·식당 후보를 번호로 보여주고 턴을 끝낸다 (`place_choice`: asked -> done). 다음 턴의 답(번호 또는 "알아서")이 오면 `plan_trip`이 고른 장소를 반드시 포함해 이동·식사·체크인까지 나눈 상세 일정을 만든다. 경기가 바뀌면 다시 묻고, 일정 수정은 다시 묻지 않는다.
- 팀/날짜/요일이 바뀌면 후보·선택·일정을 무효화하고, 인원/이동수단/관심사만 바뀌면 선택 경기는 유지한 채 일정만 다시 만든다.

## 테스트

```bash
uv run pytest
```

실제 LLM/임베딩을 호출하지 않는다. `tests/conftest.py`의 대본형 가짜 LLM으로 그래프 전체(멀티턴, 검증, 라우팅)를 돌린다.
명세서 11장 시나리오 중 일정 저장·승인(T08, T09, T12)은 기능을 제거해 테스트도 없고, 웹 검색(T11)도 제외했다. 나머지는 `test_multiturn.py`(T01~T07, T10, T14), `test_trip_validation.py`(T13)에 대응한다.

## CLAUDE.md 계약과 달라진 점

| 항목 | CLAUDE.md (기존) | 이 구현 (명세서 0장) |
|---|---|---|
| 대화 이력 | UI가 `messages`로 매번 전달, 서버는 기억 안 함 | 호출자는 CLAUDE.md 계약대로 `messages`와 `user_input`만 전달. 이력에 없는 여행 상태는 `session.py`의 프로세스 내 보관소가 이어줌 (1명 사용 로컬 환경 전용) |
| 체크포인터 | 불필요 | 불필요 (체크포인터 없음) |
| 툴 | 범용 샘플 툴 | 경기/관광지/식당 검색, 가이드 문서 검색 (`calculate`, `search_items`, `save_note` 제거, 일정 저장·승인 기능 없음) |

`build_graph()`와 `await graph.ainvoke({"messages": history, "user_input": query})`로 호출하며 (LLM 노드가 async라 동기 `invoke`는 쓸 수 없다), `result["answer"]`로 답을 꺼낸다. 호출자는 결과 State를 되돌려 보낼 필요가 없고, UI가 가진 이전 대화 이력만 `messages`로 보내면 된다.

여행 상태(`trip_preferences`, `sports_events`, `selected_event_id`, `place_choice`, `places`, `restaurants`, `trip_plan`, `trip_status`)는 턴이 끝날 때 `save_session` 노드가 `teams/team5/session.py`의 보관소에 저장하고, 다음 턴 `classify`가 복원한다.
UI의 "새 대화"처럼 `messages`가 비어 있으면 새 대화로 보고 보관소를 초기화한다. 대화 ID가 없어서 사용자 1명만 가정하며, 호출자가 State 값을 직접 넘기면 그 값이 보관소보다 우선한다.
**이 저장소에서 FastAPI 코드는 수정하지 않았다.**

## 남은 제약

- 실제 OpenAI 호환 API 키로 end-to-end 실행은 아직 검증하지 못했다. 테스트는 모두 가짜 LLM이라 프롬프트 품질(조건 추출, 일정 작성)은 실모델로 확인해야 한다.
- 경기/관광지/식당은 **가상 샘플 데이터**(`is_demo: true`)다. 영업시간·이동시간·예매 가능 여부는 만들지 않고 "확인 필요"로 표시한다. 예매·결제는 지원하지 않는다.
- 웹 검색(Tavily)은 제거했다. 외부 API는 호출하지 않고, 경기가 없으면 조건 변경을 안내한다.
- 일정 저장(파일 쓰기)과 사용자 승인 흐름(HITL)은 지원하지 않는다.
- 여행 시작일이 정해지지 않은 1일 일정이나 넓은 검색 범위만 있을 때는 경기일을 Day 1로 본다 (2일 이상이면 `trip_start`로 시작일을 확정한다). 골프 등 다른 종목은 `sport_type`만 유지하고 미구현.
- 여행 상태 보관소는 프로세스 메모리에만 있고 대화를 구분하지 않는다. 서버를 재시작하면 사라지고, 브라우저 탭을 여러 개 열어 동시에 대화하면 상태가 섞인다. UI에서 마지막 턴을 지우거나 다시 생성하면 보관소가 한 턴 앞서게 된다.
