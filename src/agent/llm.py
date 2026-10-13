# LLM/임베딩 모델 생성부. 공급자를 코드에 하드코딩하지 않고 openai 호환 클라이언트를 쓰되,
# 실제 모델명/엔드포인트는 config(.env)에서만 주입한다 (사내 모델 전환 시 .env만 변경).

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import OpenAIEmbeddings

from agent.config import settings


def get_llm(**kwargs) -> BaseChatModel:
    """채팅 LLM 인스턴스 생성. tags 등은 호출부에서 kwargs로 덧붙인다 (예: 분류 노드의 internal 태그)."""
    return init_chat_model(
        settings.llm_model,
        model_provider="openai",
        temperature=settings.llm_temperature,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        **kwargs,
    )


def get_embeddings() -> OpenAIEmbeddings:
    """RAG 벡터스토어용 임베딩 모델 생성."""
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )
