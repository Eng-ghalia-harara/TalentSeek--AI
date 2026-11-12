import streamlit as st

from src.candidate_comparison import compare_candidates


def render() -> None:
    st.title("Compare Candidates")
    st.caption("Compare selected candidates using only evidence retrieved from their CVs.")
    candidates = st.session_state.get("comparison_candidates", [])
    if len(candidates) < 2:
        st.info("Run a candidate search first. At least two candidates are needed for comparison.")
        return

    by_id = {int(item["document_id"]): item for item in candidates}
    labels = {
        int(item["document_id"]): f"{item['candidate_label']} — {item['file_name']}"
        for item in candidates
    }
    selected_ids = st.multiselect(
        "Select 2–5 candidates",
        options=list(by_id),
        default=list(by_id)[:min(3, len(by_id))],
        format_func=lambda value: labels[value],
        max_selections=5,
    )
    question = st.text_area(
        "Comparison criteria",
        value=st.session_state.get("last_search_question", ""),
        height=100,
    )
    if st.button("Generate comparison", type="primary", disabled=len(selected_ids) < 2 or not question.strip()):
        selected = [by_id[item] for item in selected_ids]
        with st.spinner("Comparing the retrieved evidence..."):
            try:
                result = compare_candidates(question, selected)
                st.session_state["last_comparison"] = result
            except Exception as exc:
                st.error(f"Comparison failed: {exc}")
                return

    result = st.session_state.get("last_comparison")
    if result:
        st.subheader("Comparison summary")
        st.write(result.get("summary", "No summary returned."))
        follow_up_suggestions = result.get("follow_up_suggestions", [])
        if follow_up_suggestions:
            st.subheader("Optional follow-ups to refine this comparison")
            for item in follow_up_suggestions:
                st.markdown(f"- {item}")

    st.subheader("Retrieved evidence by candidate")
    columns = st.columns(len(selected_ids)) if selected_ids else []
    for column, candidate_id in zip(columns, selected_ids):
        candidate = by_id[candidate_id]
        with column:
            st.markdown(f"**{candidate['candidate_label']}**")
            st.caption(candidate["file_name"])
            for evidence in candidate["evidence"]:
                pages = evidence.get("page_nums") or [evidence.get("page_num") or "—"]
                with st.expander(f"{evidence.get('section')} · p. {pages}"):
                    st.write(evidence["content"])
