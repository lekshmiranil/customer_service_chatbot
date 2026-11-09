from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())
import csv
import os
from pathlib import Path
from langchain_community.document_loaders import CSVLoader, TextLoader
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_classic.chains import RetrievalQA

# Paths are resolved from the project root, so the pipeline and the chatbot
# always use the same index no matter which folder they are started from.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = str(PROJECT_ROOT / "faiss_index")
STAGING_DIR = PROJECT_ROOT / "dataset" / "staging"
EMBEDDING_MODEL = "hkunlp/instructor-large"


def _load_staged_documents():
    """Loads every supported document in the staging folder (CSV, TXT, MD)."""
    docs = []
    for file_path in sorted(STAGING_DIR.glob("*.*")):
        suffix = file_path.suffix.lower()
        if suffix == ".csv":
            with open(file_path, newline="") as f:
                header = next(csv.reader(f), [])
            if "prompt" in header:
                loader = CSVLoader(file_path=str(file_path), source_column="prompt")
            else:
                loader = CSVLoader(file_path=str(file_path))
        elif suffix in (".txt", ".md"):
            loader = TextLoader(str(file_path))
        else:
            continue
        docs.extend(loader.load())
    return docs


def create_vector_db(target_path=INDEX_PATH):
    """Builds the FAISS index from every supported document in staging."""
    docs = _load_staged_documents()
    if not docs:
        raise FileNotFoundError(
            "No supported documents found in dataset/staging. Ensure ingestion ran successfully."
        )

    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    vectordb = FAISS.from_documents(docs, embeddings)
    vectordb.save_local(target_path)
    print(f"Vector database successfully built from {len(docs)} entries and saved to '{Path(target_path).name}'.")
    return vectordb


def get_vectordb(index_path=INDEX_PATH):
    """Loads the saved FAISS index."""
    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    return FAISS.load_local(index_path, embeddings, allow_dangerous_deserialization=True)


def get_index_version():
    """Changes whenever the pipeline replaces or rolls back the index,
    so a long-running app can tell it needs to reload."""
    index_file = Path(INDEX_PATH) / "index.faiss"
    return index_file.stat().st_mtime_ns if index_file.exists() else 0


def retrieval_confidence(vectordb, question):
    """Confidence proxy between 0 and 1, based on how close the best matching
    entry is to the question (higher means a closer match). Gemini returns no
    confidence score, so this is a retrieval-based stand-in."""
    results = vectordb.similarity_search_with_score(question, k=1)
    if not results:
        return 0.0
    _, distance = results[0]
    return round(1.0 / (1.0 + float(distance)), 3)


class _MockChain:
    """Fake chain for testing pipeline logic without hitting the real LLM API.
    Answers from the top retrieved documents so quality checks exercise the real index."""

    def __init__(self, vectordb=None):
        self.vectordb = vectordb

    def invoke(self, inputs):
        query = inputs.get("query", "") if isinstance(inputs, dict) else str(inputs)
        if self.vectordb is None:
            return {"result": "This is a mock response for pipeline testing."}
        docs = self.vectordb.similarity_search(query, k=3)
        text = "\n".join(doc.page_content for doc in docs)
        return {"result": text or "No relevant documents found."}

    def __call__(self, inputs):
        return self.invoke(inputs)


def get_qa_chain(vectordb=None):
    """Returns a retrieval-based QA chain using Gemini, or a mock chain when
    DRY_RUN_LLM=true. Pass an already loaded vectordb to avoid loading it twice."""
    if os.getenv("DRY_RUN_LLM", "false").lower() == "true":
        if vectordb is None:
            vectordb = get_vectordb()
        return _MockChain(vectordb)
    if vectordb is None:
        vectordb = get_vectordb()
    llm = ChatGoogleGenerativeAI(
        model="gemini-3.6-flash",
        api_key=os.getenv("GOOGLE_API_KEY"),
        temperature=0.2,
    )

    return RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=vectordb.as_retriever()
    )
