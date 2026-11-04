from __future__ import annotations

import streamlit as st

from src.auth import current_user
from src.database import record_ingestion_event
from src.extraction import sha256_bytes
from src.ingestion import validate_uploaded_cv, ingest_uploaded_cv


def render() -> None:
    st.title("Upload CVs")
    st.caption("Upload PDF resumes, review ATS compatibility, then index accepted files.")
    user = current_user()
    files = st.file_uploader(
        "Choose PDF CV files",
        type=["pdf"],
        accept_multiple_files=True,
        help="PDF only. Image-only scanned CVs are not supported in this release.",
    )

    if "validated_uploads" not in st.session_state:
        st.session_state["validated_uploads"] = {}

    if st.button("Validate uploaded CVs", type="primary", disabled=not files):
        for uploaded in files or []:
            data = uploaded.getvalue()
            digest = sha256_bytes(data)
            key = f"{uploaded.name}:{digest}"
            try:
                result = validate_uploaded_cv(uploaded.name, data)
                st.session_state["validated_uploads"][key] = {
                    "file_name": uploaded.name,
                    "data": data if result.get("accepted") else None,
                    "validation": result,
                }
                if not result.get("accepted"):
                    record_ingestion_event(
                        int(user["id"]), uploaded.name, digest, "upload", "rejected",
                        result.get("errors", []), {"warnings": result.get("warnings", [])},
                    )
            except Exception as exc:
                st.error(f"Validation failed for {uploaded.name}: {exc}")

    pending = st.session_state["validated_uploads"]
    if pending:
        st.subheader("Validation results")
        accepted_keys = []
        for key, item in list(pending.items()):
            result = item["validation"]
            with st.expander(item["file_name"], expanded=True):
                if result.get("accepted"):
                    st.success("Accepted by the system's ATS compatibility checks")
                    accepted_keys.append(key)
                    st.write(f"Pages: {result.get('page_count')} · Extracted pages: {result.get('pages_with_text')} · Characters: {result.get('character_count')}")
                    st.write("Recognized sections: " + ", ".join(result.get("recognized_sections", [])))
                else:
                    st.error("Rejected")
                    for reason in result.get("errors", []):
                        st.write(f"- {reason}")
                for warning in result.get("warnings", []):
                    st.warning(warning)

        st.caption("Rejected files are not sent to embeddings or stored in the CV knowledge base.")
        if accepted_keys and st.button("Index accepted CVs", type="primary"):
            progress = st.progress(0)
            statuses = []
            for index, key in enumerate(accepted_keys, start=1):
                item = pending[key]
                try:
                    result = ingest_uploaded_cv(
                        file_name=item["file_name"],
                        data=item["data"],
                        user_id=int(user["id"]),
                        validation=item["validation"],
                    )
                    statuses.append((item["file_name"], result))
                    pending.pop(key, None)
                except Exception as exc:
                    statuses.append((item["file_name"], {"status": "failed", "message": str(exc)}))
                progress.progress(index / len(accepted_keys))

            st.subheader("Indexing results")
            for name, result in statuses:
                if result["status"] == "succeeded":
                    st.success(f"{name}: indexed {result['chunks_created']} chunks (document ID {result['document_id']}).")
                elif result["status"] in {"duplicate", "unchanged"}:
                    st.info(f"{name}: {result['message']}")
                else:
                    st.error(f"{name}: {result.get('message') or result.get('errors')}")
                for warning in result.get("warnings", []):
                    st.warning(warning)
