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

- 같은 그래프 인스턴스와 고정 `thread_id`로 호출하고, 첫 턴부터 `user_input`만 보낸다. 대화와 여행 상태는 `InMemorySaver`가 기억한다 (프로세스를 끝내면 사라짐).
- CLI 명령: `state`(현재 State 요약), `reset`(새 thread_id로 새 대화), `exit`.
- 데모 대화 예시 (`TODAY_OVERRIDE = "2026-10-16"`):

```
you> 롯데 경기 보고 여행 가고 싶어          -> 날짜 범위/여행 기간을 한 번에 질문
you> 다음 달 토요일 중 1박 2일               -> 팀 조건 유지 + 11월 토요일 경기 후보 3개 제시
you> 두 번째 경기로                          -> event_id 선택, 관광지/식당 검색 후 일정 작성
you> 차 없이 갈 거고 둘째 날 바다 관광 추가해 줘 -> 선택 경기 유지, 일정 수정
you> 일정 저장해 줘                          -> [승인 요청] ...
you> 승인                                    -> teams/team5/data/saved_trips.json 에 저장 (거절이면 저장 안 함)
you> 야구장 준비물은?                        -> 가이드 문서 기반 답변 + 출처 표시
you> 이번 주 롯데 경기만 알려줘              -> 여행 기간을 묻지 않고 경기만 조회
```

## Workflow

그래프 도식은 [`docs/graph.mmd`](./docs/graph.mmd) (`uv run python scripts/draw_workflow.py`로 재생성).

```
classify ─ trip ─> extract_preferences -> validate_preferences ─ 부족 ─> ask_clarification -> END
        │                                                      └ 충분 ─> agent
        ├ 승인 대기 ─> resolve_approval ─ 승인 ─> execute_approved_tool ─> respond / ingest -> agent
        │                              ├ 거절 ─> respond
        │                              └ 모호 ─> ask_approval_again -> END
        ├ chat / qa ─> agent  (qa: 안내 질문, 일정 조회, 저장 등)
        └ needs_guide ─> retrieve -> agent   (가이드 문서가 필요한 질문은 검색을 코드가 강제)
agent ─ 승인 대상 Tool ─> request_approval -> END
      ├ 일반 Tool ─> tools -> ingest_tool_results -> agent   (최대 반복 AGENT_MAX_ITERATIONS)
      ├ 일정 작성 단계 ─> retrieve_for_plan(고정 질의 검색 강제) -> plan_trip -> respond   (validate_trip_plan 검증, 실패 시 1회 재작성)
      └ 최종 답 ─> respond -> END          (어느 노드든 예외는 error 노드로)
```

| 파일 | 역할 |
|---|---|
| `state.py` | `MyState`(대화 + 여행 상태), `InputState`, `OutputState` |
| `routing.py` | 조건부 엣지 함수 전부 |
| `nodes/` | classify, extract_preferences, validate_preferences, ask_clarification, retrieve, agent, ingest_tool_results, plan_trip, approval(4개 노드), respond, error |
| `trip_state.py`, `trip_validation.py` | State 파생 계산, 일정 검증(`validate_trip_plan`) |
| `tools/` | 로컬 Tool 5개와 레지스트리(`REQUIRES_APPROVAL`) |
| `rag/` | 문서 로딩/벡터스토어, `search_guide_docs` 툴(강제 검색 뒤 추가로 찾을 때 Agent가 쓰는 보충용) |
| `clock.py` | 기준 날짜 (`TODAY_OVERRIDE`) |

State 관리 요점:
- 턴 단위 값(`intent`, `missing_fields`, `retrieved_docs`, `error`, `answer`)은 `classify`가 매 턴 초기화하고, 여행 상태(`trip_preferences`, `sports_events`, `selected_event_id`, `trip_plan`, `pending_approval` ...)는 유지한다.
- 팀/날짜/요일이 바뀌면 후보·선택·일정을 무효화하고, 인원/이동수단/관심사만 바뀌면 선택 경기는 유지한 채 일정만 다시 만든다.
- 승인은 `interrupt()` 없이 `pending_approval`을 State에 저장하고 다음 턴 "승인/거절"로 처리한다. 승인 시 저장된 인자 그대로 실행하며, 대기 중 다른 요청이 오면 실행하지 않고 다시 묻는다.

## 테스트

```bash
uv run pytest
```

실제 LLM/임베딩을 호출하지 않는다. `tests/conftest.py`의 대본형 가짜 LLM으로 그래프 전체(멀티턴, 승인, 검증, 라우팅)를 돌린다.
명세서 11장 시나리오(웹 검색 제거로 T11 제외)는 `test_multiturn.py`(T01~T07, T10, T14), `test_approval.py`(T08, T09, T12), `test_trip_validation.py`(T13)에 대응한다.

## CLAUDE.md 계약과 달라진 점

| 항목 | CLAUDE.md (기존) | 이 구현 (명세서 0장) |
|---|---|---|
| 대화 이력 | UI가 `messages`로 매번 전달, 서버는 기억 안 함 | 로컬 `InMemorySaver` + 고정 `thread_id`, 첫 호출 이후 `user_input`만 전달 |
| 체크포인터 | 불필요 | `build_graph()`가 기본으로 `InMemorySaver` 부착 |
| 승인 | 이력 속 승인 요청 문구로 판정 | State의 `pending_approval`로 판정 |
| 툴 | 범용 샘플 툴 | 경기/관광지/식당 검색, 일정 저장 (`calculate`, `search_items`, `save_note` 제거) |

`build_graph()`, `ainvoke`, `result["answer"]` 개념은 유지한다. 기존 FastAPI가 "매 요청에 전체 `messages`를 보내는" 방식이면 `thread_id`를 넘기도록 어댑터 수정이 필요하다.
**이 저장소에서 FastAPI 코드는 수정하지 않았다.**

## 남은 제약

- 실제 OpenAI 호환 API 키로 end-to-end 실행은 아직 검증하지 못했다. 테스트는 모두 가짜 LLM이라 프롬프트 품질(조건 추출, 일정 작성)은 실모델로 확인해야 한다.
- 경기/관광지/식당은 **가상 샘플 데이터**(`is_demo: true`)다. 영업시간·이동시간·예매 가능 여부는 만들지 않고 "확인 필요"로 표시한다. 예매·결제는 지원하지 않는다.
- 웹 검색(Tavily)은 제거했다. 외부 API는 호출하지 않고, 경기가 없으면 조건 변경을 안내한다.
- 승인 요청 한 번에 Tool 하나만 처리한다. 한 응답에 승인 대상 Tool이 여러 개면 첫 번째만 묻고 나머지는 실행하지 않는다.
- 일정은 경기일을 Day 1로 가정한다 (경기 전날 도착 일정 미지원). 골프 등 다른 종목은 `sport_type`만 유지하고 미구현.
- State는 프로세스 메모리에만 있다. 재시작하면 사라진다.
