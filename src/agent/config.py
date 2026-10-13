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

    # Tavily 검색 (search_web 툴, 유일하게 허용된 외부 API 호출)
    tavily_api_key: str = ""


settings = Settings()
