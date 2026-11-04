import streamlit as st

from src.config import EMBEDDING_MODEL, EMBEDDING_DIM, GENERATION_MODEL, EXTRACTION_METHOD, CHUNKING_STRATEGY
from src.database import check_database


def render() -> None:
    st.title("System Settings")
    st.caption("Read-only configuration of this product deployment.")
    st.subheader("AI configuration")
    st.write({
        "Extraction method": EXTRACTION_METHOD,
        "Chunking strategy": CHUNKING_STRATEGY,
        "Embedding model": EMBEDDING_MODEL,
        "Embedding dimensions": EMBEDDING_DIM,
        "Generation model": GENERATION_MODEL,
    })
    st.subheader("PostgreSQL")
    try:
        info = check_database()
        st.success(f"Connected to {info['database']}")
        st.write({"Embedding column": info["embedding_type"], "Detected tables": info["tables"]})
        if info["embedding_type"] != f"vector({EMBEDDING_DIM})":
            st.error("Database embedding dimension does not match EMBEDDING_DIM. Run the product migration before indexing CVs.")
    except Exception as exc:
        st.error(str(exc))
    st.info("API keys and database passwords are intentionally not displayed in the interface.")
