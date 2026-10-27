# data/docs의 샘플 문서를 읽어 청크로 분할한다. build_graph()에서 1회만 호출된다.

from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

DOCS_DIR = Path(__file__).resolve().parents[1] / "data" / "docs"


def load_and_split_docs() -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)

    raw_docs = [
        Document(page_content=path.read_text(encoding="utf-8"), metadata={"source": path.name})
        for path in sorted(DOCS_DIR.glob("*.md"))
    ]
    return splitter.split_documents(raw_docs)
