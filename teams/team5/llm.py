# LLM/임베딩 모델 생성부. 공급자를 코드에 하드코딩하지 않고 openai 호환 클라이언트를 쓰되,
# 실제 모델명/엔드포인트는 config.py에서만 주입한다 (사내 모델 전환 시 config.py만 변경).

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import OpenAIEmbeddings

from teams.team5 import config


def get_llm(**kwargs) -> BaseChatModel:
    """채팅 LLM 인스턴스 생성. tags 등은 호출부에서 kwargs로 덧붙인다 (예: 분류 노드의 internal 태그)."""
    return init_chat_model(
        config.LLM_MODEL,
        model_provider="openai",
        temperature=config.LLM_TEMPERATURE,
        api_key=config.OPENAI_API_KEY,
        base_url=config.OPENAI_BASE_URL,
        **kwargs,
    )


def get_embeddings() -> OpenAIEmbeddings:
    """RAG 벡터스토어용 임베딩 모델 생성."""
    return OpenAIEmbeddings(
        model=config.EMBEDDING_MODEL,
        api_key=config.OPENAI_API_KEY,
        base_url=config.OPENAI_BASE_URL,
    )
