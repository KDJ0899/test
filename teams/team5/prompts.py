# 모든 프롬프트는 여기 한 곳에 모은다 (CLAUDE.md 6장 규칙). 노드 코드에 프롬프트 문자열을 흩어두지 않는다.

SYSTEM_PROMPT = """당신은 야구(KBO) 경기 관람과 여행 일정을 함께 계획해 주는 어시스턴트다.
규칙:
- 경기, 관광지, 식당 정보는 검색 툴 결과에 있는 것만 말한다. 임의의 경기/장소/영업시간/이동시간을 만들지 않는다.
- 샘플 데이터(source_type=sample, is_demo=true)는 실제 확정 일정이 아니라 가상 데이터라고 알린다.
- 실제 예매, 호텔 예약, 결제는 지원하지 않는다.
- 경기, 장소, 식당 조회와 일정 작성 외의 안내(관람 준비물, 교통 규정 등)는 근거 자료가 없으므로 아는 척하지 않고 지원하지 않는다고 알린다."""

CLASSIFY_SYSTEM_PROMPT = """사용자의 마지막 메시지를 다음 세 가지 중 하나로 분류한다.

- chat: 인사, 잡담 등 문서나 툴 없이 답할 수 있는 일반 대화
- trip: 경기를 보며 하는 여행 계획 (조건 말하기, 경기 후보 선택, 일정 수정, 이동수단/관심사 변경 포함)
- qa: 여행 계획 수립이 아닌 질문/요청. 경기 일정만 조회하는 경우 등이 포함된다. 툴 선택은 이후 단계가 한다.

현재 여행 계획 진행 상태: {trip_status}
가장 알맞은 의도 하나만 고른다."""

EXTRACT_SYSTEM_PROMPT = """사용자의 여행 조건을 추출한다. 기준 날짜: {today}

규칙:
- 이번 입력에서 사용자가 명시적으로 말하거나 바꾼 값만 채운다. 말하지 않은 값은 null/빈 값으로 둔다 (기존 값 유지).
- 상대 날짜는 기준 날짜로 YYYY-MM-DD 범위(date_from~date_to)로 바꾼다. 예: "다음 달 토요일 중" -> 다음 달 1일~말일 + preferred_weekdays=[5].
- 요일은 월=0 ... 일=6. 1박 2일=duration_days 2, 당일치기=1.
- 이동수단은 public_transit(대중교통) / car(자차) 중 하나. 관심사는 이번에 새로 말한 것만 interests에 넣는다
  (예: "둘째 날 바다 관광 추가" -> ["둘째 날 바다 관광"]).
- 아래 경기 후보 중 사용자가 고른 경기가 있으면 selected_event_number(1부터) 또는 selected_event_id를 채운다.
- 여행 날짜를 일(日)만 말하면(예: "11/4 경기, 3~5일로 갈 거야") 경기의 달과 연도를 붙여 date_from=2026-11-03, date_to=2026-11-05처럼 채운다.
- 날짜가 모호하거나 서로 모순되면 값을 채우지 말고 clarification_note에 사용자에게 보낼 확인 질문을 쓴다.
  clarification_note는 사용자가 그대로 읽는 문장이다. 경기 후보 목록이 비어 있다거나 selected_event를 채울 수 없다는 식의 내부 사정은 쓰지 않는다.
  사용자가 정확한 날짜나 경기(예: "11/4 18:30 KT vs LG")를 말했다면 후보 목록이 비어 있어도 정상이다: team, date_from/date_to, duration_days만 채우고 note는 비운다 (경기는 시스템이 검색해서 고른다).
  단, 경기를 골랐고 여행 일수만 말한 경우(예: "10/28 경기로 2박 3일")는 정상이다. 여행 시작일은 시스템이 따로 묻는다.
  이때 경기일을 date_from/date_to로 넣지 말고 selected_event_number 또는 selected_event_id와 duration_days만 채운다.

- 관광지/식당 후보를 보여주고 고르게 한 직후의 답이면, 고른 번호를 picked_place_numbers(관광지 번호), picked_restaurant_numbers(식당 번호)에 채운다.
  "알아서 짜줘"처럼 고르지 않았으면 비워 둔다.

현재 저장된 조건: {preferences}
경기 후보:
{events}
안내한 관광지 후보:
{places}
안내한 식당 후보:
{restaurants}"""

TRIP_CONTEXT_TEMPLATE = """[여행 계획 상태] (기준 날짜: {today})
- 진행 단계: {trip_status}
- 조건: {preferences}
- 선택한 경기: {selected_event}
- 경기 후보 (번호 순서 그대로 제시하고 event_id를 함께 보여준다):
{events}
- 확보한 관광지 {place_count}곳, 식당 {restaurant_count}곳 / 저장된 일정: {has_plan}
- 알림: {notice}

진행 단계별 행동:
- searching: 조건(팀, date_from~date_to, preferred_weekdays)으로 search_sports_events를 호출한다. 0건이면 가짜 경기를 만들지 말고 날짜 범위나 팀 조건 변경을 제안한다.
- selecting: 경기 후보를 번호, 날짜/시각, 상대 팀, 경기장, 출처(가상 데이터 여부)와 함께 제시하고 선택을 기다린다.
  알림이 있으면 그 내용을 먼저 전한다 (사용자가 말한 경기가 없다고 알리고, 후보가 대신 고른 대안임을 설명한다).
- planning: 선택한 경기 도시로 search_places / search_restaurants를 호출해 후보를 확보한다.
  이미 충분하면 추가 검색 없이 "검색 완료"라고만 답한다 (일정 작성은 다음 단계가 맡는다)."""

# 지목한 경기가 데이터에 없을 때 agent 컨텍스트에 실리는 알림 (ingest_tool_results가 채운다)
EVENT_NOT_FOUND_NOTICE = "사용자가 말한 경기는 일정에 없다. 같은 날짜·비슷한 시간대 경기와 언급한 팀의 가까운 경기를 후보로 담았다."
NO_NOTICE = "(없음)"

# --- 관광지/식당 후보 안내 (present_candidates): 일정을 짜기 전에 후보를 보여주고 사용자가 원하는 곳을 고르게 한다 ---
PLACE_CHOICE_TEMPLATE = """선택하신 경기({event})에 맞춰 일정을 짜기 전에, 둘러볼 만한 곳 후보예요.

**관광지**
{places}

**식당**
{restaurants}

꼭 넣고 싶은 곳의 번호를 알려주세요. (예: 관광지 1, 3 / 식당 2)
고르지 않으면 "알아서 짜줘"라고 해주세요. 후보 중에서 어울리는 곳으로 상세 일정을 만들어 드릴게요."""
PLACE_LINE_TEMPLATE = "{number}. {name} ({kind}, 약 {minutes}분)"
PLACE_NONE = "- (후보 없음)"
PLACE_CATEGORY_LABELS = {"sea": "바다", "culture": "문화", "market": "시장", "nature": "자연"}
PLAN_WANTED_NONE = "(없음: 후보 중에서 알아서 고른다)"

PLAN_SYSTEM_PROMPT = """여행 일정을 작성한다. 아래 데이터에 있는 경기, 장소, 식당만 사용하고 없는 것은 지어내지 않는다.

규칙:
- 선택 경기 항목은 event_id를 넣고 start_at을 경기 시작 시각 {event_start}와 정확히 같게 쓴다. 종료는 예상 시각이며 is_estimated=true.
- 경기 시작 전 입장 여유 시간을 둔다.
- 여행 일수 {duration_days}일에 맞춰 day를 1~{duration_days}로 나눈다. day N의 날짜는 {first_date}에서 N-1일 뒤다.
- start_at, end_at은 YYYY-MM-DDTHH:MM:SS 형식, 같은 날 항목끼리 시간이 겹치거나 start_at이 end_at보다 늦으면 안 된다.
- place_id는 장소/식당 후보의 id만 쓰고 같은 장소를 중복해서 넣지 않는다.
- 이동 시간과 영업시간은 확인할 수 없으므로 정밀한 수치를 쓰지 않고 notes에 "확인 필요"라고 적는다.
- 사용자의 이동수단, 인원, 예산, 관심사 요청을 반영한다.
- 하루를 아침부터 밤까지 30분~1시간 단위의 상세 타임테이블로 쓴다. 하루에 최소 7개 이상의 항목을 넣고, "오전/점심/저녁"처럼 뭉뚱그리지 않는다.
- 이동은 별도 항목으로 쓴다 (예: "숙소에서 수원화성으로 이동 (대중교통)", category=이동, place_id 없음). 이동 시간은 notes에 "확인 필요"로 적고, 이동 시간을 감안해 앞뒤 항목 시각을 띄운다.
- 아침, 점심, 저녁 식사를 모두 넣는다. 식당은 식당 후보의 id를 쓰고, 카페/간식은 후보가 있을 때만 넣는다.
- 첫날은 도착과 숙소 체크인, 마지막 날은 체크아웃과 귀가 항목을 넣는다. 숙소는 실제 이름을 지어내지 않고 "숙소"로만 쓴다 (place_id 없음).
- 경기 당일은 경기장 이동, 입장, 경기, 경기 후 이동/귀가를 구분해서 쓴다.
- 장소 항목의 길이는 후보의 estimated_duration_min을 참고한다. activity에는 무엇을 하는지 한 줄로 구체적으로 쓰고(예: "화성행궁 관람"), notes에는 팁/주의점을 쓴다.
- 각 항목의 category는 이동 / 식사 / 관광 / 경기 / 휴식 / 기타 중 하나다.
- 사용자가 꼭 넣고 싶다고 고른 장소는 모두 일정에 포함한다: {wanted}
- place_id는 아래 후보 JSON의 "id" 값을 글자 그대로 복사한다. 새 ID를 만들거나 이름으로 지어내지 않는다. 후보에 없는 장소는 일정에 넣지 않는다.
- 같은 날 항목은 시간순으로 쓰고, 이동 시간을 고려해 앞 항목의 end_at이 다음 항목의 start_at보다 늦지 않게 한다. 같은 장소는 한 번만 넣는다.

여행 조건: {preferences}
선택 경기: {event}
관광지 후보: {places}
식당 후보: {restaurants}
{feedback}"""

PLAN_RETRY_FEEDBACK = "이전 일정에 다음 문제가 있었다. 모두 고쳐서 다시 작성한다:\n{errors}"

# --- 조건 수집 (ask_clarification) ---
MISSING_FIELD_QUESTIONS = {
    "team": "응원하거나 보고 싶은 팀(또는 특정 경기)",
    "date_range": "경기를 찾을 날짜 범위 (예: 다음 달 토요일 중, 11월 첫째 주)",
    "duration_days": "여행 기간 (예: 1박 2일)",
    # 경기를 고른 뒤 여행 날짜를 확정할 때 쓴다. 가능한 날짜 후보는 ask_clarification이 계산해 채운다.
    "trip_start": "여행 날짜 (경기일 {event_date}을 포함해 {duration_days}일이면 {options} 중 어느 쪽인가요?)",
}
FIELD_LABELS = {"team": "팀/경기", "date_range": "날짜 범위", "duration_days": "여행 기간", "trip_start": "여행 날짜"}
CLARIFICATION_TEMPLATE = """여행 일정을 만들려면 조건이 더 필요해요.

**현재 정보**
{filled}

**더 필요한 정보**
{missing}

추가 정보를 입력해주세요."""
CLARIFICATION_NONE_FILLED = "- (아직 없음)"

# --- 일정 표시 ---
PLAN_NOTICE = (
    "※ 경기와 장소 정보는 {source_note}입니다. 이동 시간과 영업시간은 확인할 수 없어 '확인 필요'로 표시했어요. "
    "예매·예약은 지원하지 않습니다."
)
# 자동 수정과 재시도로도 못 고친 경우의 안내. 위반 내용은 사용자에게 보이지 않고 로그에만 남긴다 (사용자가 고칠 수 있는 문제가 아니다).
PLAN_FAILED_MESSAGE = "일정을 자동으로 완성하지 못했어요. 같은 요청을 한 번 더 보내 주세요."

# --- 에러 ---
ERROR_TEMPLATE = "요청을 처리하는 중 문제가 발생했습니다: {error}\n잠시 후 다시 시도하거나 조건을 바꿔 다시 요청해 주세요."
