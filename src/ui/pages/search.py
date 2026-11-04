import re

import streamlit as st

from src.auth import current_user
from src.database import list_job_fields
from src.job_classification import JOB_FIELD_LABELS
from src.search import search_candidates
from src.ui.components import render_candidate_card


def _clear_search_on_field_change() -> None:
    for key in (
        "last_search_result",
        "last_search_question",
        "last_search_job_field",
        "initial_search_question",
        "initial_shortlist_ids",
        "refinement_scope_ids",
        "refinement_history",
        "refinement_count",
        "active_clarification",
        "comparison_candidates",
    ):
        st.session_state.pop(key, None)


def render() -> None:
    st.title("Candidate Search")
    st.caption("Search the shared CV knowledge base in Arabic or English.")
    available_fields = ["All fields", *list_job_fields()]
    filter_key = "candidate_search_job_field"
    if st.session_state.get(filter_key) not in available_fields:
        st.session_state[filter_key] = "All fields"
    selected_job_field = st.selectbox(
        "Filter by candidate field",
        options=available_fields,
        format_func=lambda value: (
            value if value == "All fields" else JOB_FIELD_LABELS.get(value, value)
        ),
        key=filter_key,
        on_change=_clear_search_on_field_change,
        help="Fields are detected from CV headers and work-experience job titles.",
    )
    question = st.text_area(
        "Recruitment requirements",
        placeholder="مثال: أحتاج مهندس تعلم آلي لديه خبرة في Python وFastAPI ونشر النماذج باستخدام Docker.",
        height=120,
    )
    search_clicked = st.button("Search candidates", type="primary", disabled=not question.strip())
    existing_result = st.session_state.get("last_search_result")
    summary_placeholder = None
    if search_clicked or existing_result:
        st.subheader("Search summary")
        summary_placeholder = st.empty()

    if search_clicked:
        with st.spinner("Searching CV evidence and preparing the shortlist..."):
            try:
                result = search_candidates(
                    question,
                    job_field=None if selected_job_field == "All fields" else selected_job_field,
                    on_summary_update=lambda text: summary_placeholder.markdown(text),
                )
                st.session_state["last_search_result"] = result
                st.session_state["last_search_question"] = question
                st.session_state["last_search_job_field"] = selected_job_field
                st.session_state["initial_search_question"] = question
                st.session_state["initial_shortlist_ids"] = result.get(
                    "candidate_pool_ids",
                    [int(candidate["document_id"]) for candidate in result.get("candidates", [])],
                )
                st.session_state["refinement_scope_ids"] = list(
                    st.session_state["initial_shortlist_ids"]
                )
                st.session_state["refinement_history"] = []
                st.session_state["refinement_count"] = 0
                st.session_state.pop("active_clarification", None)
            except Exception as exc:
                st.error(f"Search failed: {exc}")
                return

    result = st.session_state.get("last_search_result")
    if not result:
        st.info("Enter recruitment requirements to search the CV knowledge base.")
        return

    final_summary = result.get("summary") or "No generated summary is available."
    if summary_placeholder is not None:
        summary_placeholder.markdown(final_summary)
    last_question = st.session_state.get("last_search_question", question)
    is_arabic_search = bool(re.search(r"[\u0600-\u06FF]", last_question))
    generation_failed = bool(result.get("generation_warning"))
    stage_timings = result.get("stage_timings", {})
    elapsed_seconds = stage_timings.get("total_seconds") if isinstance(stage_timings, dict) else None
    if isinstance(elapsed_seconds, (int, float)):
        elapsed_label = (
            "اكتمل الاسترجاع خلال" if is_arabic_search and generation_failed
            else "اكتملت الإجابة خلال" if is_arabic_search
            else "Retrieval completed in" if generation_failed
            else "Answered in"
        )
        st.markdown(
            f"<div dir='rtl' style='text-align: right; color: #808495; font-size: 0.875rem;'>"
            f"{elapsed_label} {elapsed_seconds:.2f} {'ثانية' if is_arabic_search else 'seconds'}</div>",
            unsafe_allow_html=True,
        )
    candidates = result.get("candidates", [])
    requested_count = max(1, min(int(result.get("requested_count", 1)), 3))
    displayed_candidates = candidates[:requested_count]
    assessments = result.get("candidate_assessments", {})
    if result.get("generation_warning"):
        if is_arabic_search:
            st.warning("تعذر تقييم المرشحين باستخدام Gemini؛ المعروض هو أفضل ما وجده البحث. يُرجى مراجعة الأدلة يدويًا.")
            st.subheader("أفضل نتائج الاسترجاع")
        else:
            st.warning("AI assessment was unavailable; these are the highest-ranked retrieval matches. Review their evidence manually.")
            st.subheader("Top retrieval matches")
        generation_error = result.get("generation_error")
        if current_user().get("role") == "admin" and generation_error:
            expander_label = "تفاصيل تقنية للمسؤول" if is_arabic_search else "Technical details (admin only)"
            with st.expander(expander_label):
                st.code(generation_error)
    elif not result.get("privacy_blocked"):
        if requested_count == 1:
            st.subheader("Recommended candidate")
        else:
            st.subheader("Relevant candidates")
    initial_ids = st.session_state.get("initial_shortlist_ids", [])
    if st.session_state.get("refinement_count", 0):
        st.caption(f"Refined within the original shortlist of {len(initial_ids)} candidates.")
    if not candidates:
        if result.get("privacy_blocked"):
            st.info("Privacy protection is active for this request.")
        elif st.session_state.get("refinement_count", 0):
            st.warning("No candidates in the original shortlist matched this refinement. Try a broader follow-up or start a new search.")
        else:
            st.warning("No relevant CV evidence was found. Try broader or more specific requirements.")
    if displayed_candidates:
        for rank, candidate in enumerate(displayed_candidates, start=1):
            assessment = assessments.get(int(candidate["document_id"]))
            if assessment:
                status = assessment["fit_status"].replace("_", " ").title()
                st.markdown(f"**Evidence fit: {status}.** {assessment.get('reason', '')}")
            render_candidate_card(candidate, rank)

    questions = result.get("clarification_questions", [])
    if candidates:
        st.subheader("Refine this shortlist or ask a follow-up")
        if questions:
            st.caption("Choose a suggested clarification, or write your own follow-up below.")
            for index, question_text in enumerate(questions):
                if st.button(question_text, key=f"clarification_{index}"):
                    st.session_state["active_clarification"] = question_text
                    st.rerun()

        active_clarification = st.session_state.get("active_clarification")
        if active_clarification:
            st.info(f"Clarification selected: {active_clarification}")

        refinement_count = int(st.session_state.get("refinement_count", 0))
        with st.form(f"shortlist_refinement_{refinement_count}"):
            response = st.text_area(
                "Your answer or follow-up question",
                placeholder=(
                    "For example: A master's degree in progress is acceptable, and remote training is fine."
                    if active_clarification
                    else "For example: Does this candidate's CV show training experience?"
                ),
                key=f"shortlist_refinement_text_{refinement_count}",
            )
            refine_submitted = st.form_submit_button(
                "Apply to this shortlist",
                type="primary",
                disabled=not bool(initial_ids),
            )

        if refine_submitted:
            if not response.strip():
                st.warning("Enter an answer or follow-up question first.")
            else:
                original_question = st.session_state.get("initial_search_question", "")
                if active_clarification:
                    refinement_item = (
                        f"Clarification: {active_clarification}\n"
                        f"Recruiter's answer: {response.strip()}"
                    )
                else:
                    refinement_item = f"Follow-up about the shortlisted candidates: {response.strip()}"
                refinement_history = [
                    *st.session_state.get("refinement_history", []),
                    refinement_item,
                ]
                refinement_query = "\n".join([
                    f"Original recruitment request: {original_question}",
                    *refinement_history,
                ])
                current_scope_ids = st.session_state.get("refinement_scope_ids", initial_ids)
                with st.spinner("Refining the original shortlist..."):
                    try:
                        refined_result = search_candidates(
                            refinement_query,
                            candidate_ids=current_scope_ids,
                            job_field=(
                                None
                                if st.session_state.get("last_search_job_field", "All fields") == "All fields"
                                else st.session_state["last_search_job_field"]
                            ),
                            on_summary_update=lambda text: summary_placeholder.markdown(text),
                        )
                        st.session_state["last_search_result"] = refined_result
                        st.session_state["last_search_question"] = refinement_query
                        st.session_state["refinement_history"] = refinement_history
                        st.session_state["refinement_scope_ids"] = refined_result.get(
                            "candidate_pool_ids",
                            [int(candidate["document_id"]) for candidate in refined_result.get("candidates", [])],
                        )
                        st.session_state["refinement_count"] = refinement_count + 1
                        st.session_state.pop("active_clarification", None)
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Could not refine the shortlist: {exc}")

    if candidates:
        st.session_state["comparison_candidates"] = candidates
        st.caption("You can open Compare Candidates to compare 2–5 candidates from this search.")
