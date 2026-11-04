from __future__ import annotations

from pathlib import Path

import streamlit as st

from src.auth import current_user
from src.database import delete_document, get_document, list_documents, record_ingestion_event
from src.ingestion import validate_uploaded_cv, ingest_uploaded_cv
from src.extraction import sha256_bytes
from src.storage import remove_file


def render() -> None:
    st.title("CV Documents")
    st.caption("Manage the current CV files in the shared knowledge base.")
    user = current_user()
    if user.get("role") != "admin":
        st.info("Only administrators can replace or delete CV documents. Recruiters can search and compare them.")
        docs = list_documents()
        if docs:
            st.dataframe([{"ID": d["id"], "CV": d["title"], "Status": d["status"], "Chunks": d["chunk_count"], "Updated": d["updated_at"]} for d in docs], use_container_width=True, hide_index=True)
        return

    docs = list_documents()
    if docs:
        st.dataframe([
            {"ID": d["id"], "CV": d["title"], "Status": d["status"], "Chunks": d["chunk_count"], "Updated": d["updated_at"]}
            for d in docs
        ], use_container_width=True, hide_index=True)
    else:
        st.info("No CV documents are indexed yet.")
        return

    labels = {int(d["id"]): f"{d['title']} (ID {d['id']})" for d in docs}
    selected_id = st.selectbox("Select a CV to manage", options=list(labels), format_func=lambda value: labels[value])
    selected = get_document(int(selected_id))

    with st.expander("Replace this CV", expanded=False):
        uploaded = st.file_uploader("Choose the new PDF", type=["pdf"], key=f"replace_upload_{selected_id}")
        if uploaded and st.button("Validate replacement", key=f"validate_replace_{selected_id}"):
            data = uploaded.getvalue()
            validation = validate_uploaded_cv(uploaded.name, data)
            if not validation.get("accepted"):
                record_ingestion_event(
                    int(user["id"]), uploaded.name, sha256_bytes(data),
                    "replace", "rejected", validation.get("errors", []),
                    {"warnings": validation.get("warnings", [])}, int(selected_id),
                )
            st.session_state[f"replacement_{selected_id}"] = {
                "file_name": uploaded.name,
                "data": data,
                "validation": validation,
            }
        replacement = st.session_state.get(f"replacement_{selected_id}")
        if replacement:
            validation = replacement["validation"]
            if validation.get("accepted"):
                st.success("Replacement passed the system's ATS checks.")
                for warning in validation.get("warnings", []):
                    st.warning(warning)
                st.write(f"Recognized sections: {', '.join(validation.get('recognized_sections', []))}")
                st.warning("The current CV remains active until the new file is fully embedded and committed.")
                if st.button("Process and replace current CV", type="primary", key=f"commit_replace_{selected_id}"):
                    try:
                        result = ingest_uploaded_cv(
                            file_name=replacement["file_name"],
                            data=replacement["data"],
                            user_id=int(user["id"]),
                            validation=validation,
                            replace_document_id=int(selected_id),
                        )
                        if result["status"] == "succeeded":
                            st.success(f"CV replaced successfully. {result['chunks_created']} chunks indexed.")
                            st.session_state.pop(f"replacement_{selected_id}", None)
                            st.rerun()
                        else:
                            st.info(result.get("message", result["status"]))
                    except Exception as exc:
                        st.error(f"Replacement failed. The previous CV remains unchanged. Details: {exc}")
            else:
                st.error("The replacement was rejected.")
                for reason in validation.get("errors", []):
                    st.write(f"- {reason}")

    with st.expander("Delete this CV", expanded=False):
        confirm = st.checkbox("I understand that deleting this CV also deletes all its chunks and embeddings.", key=f"confirm_delete_{selected_id}")
        if st.button("Delete CV", type="secondary", disabled=not confirm, key=f"delete_{selected_id}"):
            source = delete_document(int(selected_id))
            remove_file(source)
            try:
                record_ingestion_event(
                    int(user["id"]), Path(source).name if source else labels[int(selected_id)],
                    None, "delete", "succeeded", [], {}, None,
                )
            except Exception:
                pass
            st.session_state.pop(f"replacement_{selected_id}", None)
            st.success("CV and its indexed chunks were deleted.")
            st.rerun()
