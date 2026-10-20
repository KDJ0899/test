# 워크플로 전체 설정값을 .env에서 읽어 들이는 단일 지점.
# 모델명/엔드포인트/k값 등은 하드코딩하지 않고 전부 여기서만 읽는다 (CLAUDE.md 6장 규칙).

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM (OpenAI 호환 클라이언트 사용, 사내 모델은 base_url로 교체)
    openai_api_key: str = ""
    openai_base_url: str | None = None
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.0

    # 임베딩 (RAG)
    embedding_model: str = "text-embedding-3-small"
    rag_top_k: int = 3

    # Agent <-> Tool 루프 최대 반복
    agent_max_iterations: int = 10

    # 승인이 필요한 툴 이름 (JSON 배열로 .env에서 변경 가능). 승인이 필요 없으면 []로 둔다.
    approval_required_tools: list[str] = ["save_trip_plan"]

    # 상대 날짜("다음 달", "이번 주")의 기준일. 비우면 오늘. 데모/테스트에서 YYYY-MM-DD로 고정한다.
    today_override: str | None = None

    # 로컬 CLI의 고정 thread_id (InMemorySaver가 이 id로 State를 이어 준다)
    thread_id: str = "local-demo"


settings = Settings()
