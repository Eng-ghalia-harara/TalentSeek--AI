import streamlit as st

from src.database import check_database, get_dashboard_stats, list_documents


def render() -> None:
    st.title("Dashboard")
    st.caption("Overview of the shared CV knowledge base.")
    try:
        stats = get_dashboard_stats()
        db_info = check_database()
    except Exception as exc:
        st.error(f"Could not load dashboard data: {exc}")
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("CV documents", stats["documents"])
    c2.metric("Ready for search", stats["ready"])
    c3.metric("Rejected · last 30 days", stats["rejected_30d"])

    st.subheader("Database connection")
    st.success(f"Connected to PostgreSQL database: {db_info['database']}")
    st.caption(f"Embedding column: {db_info['embedding_type'] or 'not found'}")

    st.subheader("Recently updated CVs")
    docs = list_documents()[:10]
    if docs:
        st.dataframe([
            {
                "ID": row["id"],
                "CV": row["title"],
                "Status": row["status"],
                "Chunks": row["chunk_count"],
                "Updated": row["updated_at"],
            }
            for row in docs
        ], use_container_width=True, hide_index=True)
    else:
        st.info("No CVs have been indexed yet. Open Upload CVs to add the first documents.")
