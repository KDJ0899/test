# 워크플로 전체 설정값을 모아둔 단일 지점. 테스트 용도라 .env 없이 이 파일의 값을 직접 고쳐 쓴다.
# 모델명/엔드포인트/k값 등은 다른 파일에 하드코딩하지 않고 전부 여기서만 읽는다.

# LLM (OpenAI 호환 클라이언트 사용, 사내 모델은 OPENAI_BASE_URL로 교체)
OPENAI_API_KEY: str = ""  # 여기에 직접 채운다. 키가 들어간 채로 커밋/공유하지 않는다.
OPENAI_BASE_URL: str | None = None
LLM_MODEL: str = "gpt-4o-mini"
LLM_TEMPERATURE: float = 0.0

# 임베딩 (RAG)
EMBEDDING_MODEL: str = "text-embedding-3-small"
RAG_TOP_K: int = 3

# Agent <-> Tool 루프 최대 반복
AGENT_MAX_ITERATIONS: int = 10

# 일정 작성 최대 시도 횟수 (초안 1회 + 검증 실패 시 위반 내용을 알려 다시 작성)
PLAN_MAX_ATTEMPTS: int = 3

# 상대 날짜("다음 달", "이번 주")의 기준일. None이면 오늘. 데모/테스트에서 "YYYY-MM-DD"로 고정한다.
# 샘플 경기가 2026-10~11월이므로 데모에서는 "2026-10-16" 등으로 고정하면 편하다.
TODAY_OVERRIDE: str | None = None
