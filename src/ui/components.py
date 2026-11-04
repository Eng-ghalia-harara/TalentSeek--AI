from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st


def render_candidate_card(candidate: dict[str, Any], rank: int) -> None:
    st.markdown(f"### {rank}. {candidate['candidate_label']}")
    st.caption(f"{candidate['file_name']} · Retrieval score: {candidate['score']:.5f}")
    for index, evidence in enumerate(candidate.get("evidence", []), start=1):
        pages = evidence.get("page_nums") or [evidence.get("page_num") or "—"]
        with st.expander(
            f"Evidence {index} · {evidence.get('section', 'Unclassified')} · Page(s): {', '.join(map(str, pages))}"
        ):
            st.write(evidence.get("content", ""))
            st.caption(f"Source: {candidate['file_name']} | Section: {evidence.get('section')} | Pages: {pages}")
    source = candidate.get("source_uri")
    if source and Path(source).is_file():
        with open(source, "rb") as file:
            st.download_button(
                "Download original CV",
                data=file.read(),
                file_name=candidate["file_name"],
                mime="application/pdf",
                key=f"download_{candidate['document_id']}_{rank}",
            )
    st.divider()
