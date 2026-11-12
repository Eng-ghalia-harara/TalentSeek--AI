# TalentSeek AI
## Project Overview and Review Plan

- **Project type:** AI-assisted CV search and early candidate review
- **Main users:** Recruiters and system admins
- **Status:** Working product prototype
- **Main tools:** Python, Streamlit, PostgreSQL, pgvector, and Google Gemini

## 1. Executive summary

TalentSeek AI helps recruiters search a shared set of CVs using a job description or natural-language question in Arabic or English. The system extracts and splits CV text, then searches it by meaning and by keywords. It shows likely matches with short source excerpts, page numbers, and section names.

The goal is to help recruiters find useful evidence faster. The system supports human review. It does not make final hiring decisions.

## 2. Problem

CVs contain a lot of information and use different layouts and wording. When there are many CVs, recruiters may need to open and read several files to find relevant skills and experience. A keyword-only search can also miss a match when the CV uses different words from the search question.

TalentSeek AI addresses this by:

- Keeping indexed CVs in one database.
- Searching by meaning and by exact words.
- Showing source evidence with each result.
- Letting recruiters refine a shortlist with follow-up questions.

## 3. Project goals

1. Provide a clear interface for uploading and managing PDF CVs.
2. Extract and check CV text before indexing it.
3. Split text into sections to help find relevant evidence.
4. Support natural-language search in Arabic and English.
5. Show the source of each result where available.
6. Let recruiters refine and compare candidates.
7. Provide separate Admin and Recruiter roles.

## 4. Users

### Recruiter

- Upload, check, and index CVs.
- Search candidates by job requirements.
- Review source excerpts and refine a shortlist.
- Compare selected candidates.
- Manage CVs allowed by the app's role permissions.

### Admin

- Use the recruiter features.
- Open the user management page.
- Replace or delete CVs where the interface allows it.

The current prototype uses one shared local password for each role. It does not use individual company accounts or an external identity provider.

## 5. Main features

### CV processing

- Accept PDF files and check file health, size, and page count.
- Extract text page by page with PyMuPDF.
- Show rejection reasons and warnings, including low text or possible multi-column layouts.
- Detect common section headings and group text by section.
- Keep text before the first known heading in a `Header` section.
- Detect exact duplicate files by content hash.
- Record upload, processing, replacement, and deletion events.

### Search

- Accept job requirements in Arabic or English.
- Combine semantic vector search with PostgreSQL text search.
- Merge and rank results from both search methods.
- Group retrieved chunks by CV so one candidate is not shown multiple times.
- Send up to four retrieved evidence chunks per candidate by default to Gemini for a summary and initial assessment (from up to 40 retrieved chunks overall).
- Classify fit as meets, partial, unclear, or does not meet, and make clear that the assessment is limited to retrieved evidence.
- Show the supporting excerpt, section, and page.
- Stream the summary to the interface as it is generated.
- Allow Admins and Recruiters to explicitly request contact details for displayed candidates assessed as meeting the criteria. Contact details are kept out of Gemini; database-wide contact exports are blocked.
- Filter known boilerplate and high-confidence ranking directives from CV text, and omit hidden or tiny PDF text spans. These are targeted mitigations, not a guarantee of detecting every misleading instruction.

### Shortlists and comparison

- Suggest follow-up questions based on the search request.
- Let the recruiter answer a suggested question or enter another requirement.
- Refine results within the current shortlist.
- Compare selected candidates using retrieved evidence.

### Roles and administration

- Provide Admin and Recruiter roles.
- Show admin pages only to the Admin role.
- Keep a record of CV uploads, rejections, processing, replacements, and duplicates.

## 6. How the system works

### CV upload

1. The user uploads a PDF.
2. The app checks the file and extracts text with PyMuPDF.
3. It checks page count, text content, and known section headings.
4. It splits text by section. Long sections may use more than one chunk.
5. Gemini creates a vector embedding for each chunk.
6. PostgreSQL and pgvector store the document, text chunks, metadata, and vectors.
7. The app stores the PDF and an ingestion event.

### Candidate search

1. The recruiter enters job requirements.
2. The app creates an embedding for the question.
3. PostgreSQL finds similar chunks and keyword matches, then combines their rankings.
4. The app groups evidence by CV and selects the best chunks for each candidate.
5. Gemini receives the question and the limited evidence and creates a summary, candidate assessments, and follow-up questions.
6. The interface shows the answer, candidates, and evidence.
7. The recruiter can refine the search within the current shortlist.

## 7. Technical design

| Tool | Role |
|---|---|
| Streamlit | User interface for search, upload, and administration. |
| PyMuPDF | Extracts text from text-based PDF files. |
| Google Gemini Embedding | Creates vectors for CV chunks and search questions. |
| Google Gemini Generation | Summarizes evidence and suggests candidate assessments and follow-up questions. |
| PostgreSQL | Stores documents, chunks, users, and processing events. |
| pgvector | Stores embeddings and supports vector search. |
| Python | Runs validation, chunking, retrieval, and app logic. |

The generation model is configured through `GENERATION_MODEL`; its code default is `gemini-3.1-flash-lite`. The effective model can differ when `.env` overrides that value.

## 8. Data and evidence

The `documents` table stores CV records. The `chunks` table stores text, page and section metadata, and embeddings. The app also uses `app_users` for local roles and `ingestion_events` for processing history.

Search results include source excerpts so recruiters can check why a result appeared. Gemini's summary is only support for review. Recruiters should check the original CV before taking action.

## 9. Current scope and limits

### Supported now

- PDF files with extractable text.
- Section-based chunking using known headings.
- Hybrid semantic and keyword search.
- PostgreSQL and pgvector storage.
- A short candidate list and an initial Gemini assessment.
- Follow-up questions that refine the current shortlist.
- Streamlit interface with Admin and Recruiter roles.
- Explicit contact-detail requests for matching candidates, with no contact data sent to Gemini and no database-wide contact exports.
- Targeted filtering of known boilerplate and high-confidence ranking instructions in CV text.

### Limits to consider

- Gemini only receives retrieved evidence, not every CV or every chunk.
- A candidate missing from the shortlist may not have reached the generation step.
- New section headings must be added to `src/chunking.py` to be recognized.
- Image-only PDFs are not supported because OCR is not included.
- Missing evidence in retrieved text does not prove a person lacks a skill.
- Gemini may be unavailable or slow. In that case, the app can show retrieval results without a completed AI assessment.
- Contact details are disclosed only after a successful assessment, for displayed candidates marked `meets`, and only on explicit request. Bulk contact exports are blocked.
- CV sanitization targets known patterns and is not a guarantee that every misleading or malicious instruction will be detected.
- The recruiter remains responsible for checking qualifications and making the final decision.

## 10. Expected value

The project aims to reduce the time needed to find relevant CVs, make source evidence easier to review, and support searches that use wording different from the CV. It also provides a shared process for indexing and managing CVs.

These are expected benefits. Their real impact should be measured with representative CVs and questions.

## 11. Suggested evaluation measures

The prototype can be evaluated with recruiters using measures such as:

- Precision@3 for reference questions.
- Whether source excerpts and citations match the CV, page, and section.
- Whether unsupported PDFs are rejected correctly.
- Search time, split between retrieval and Gemini generation.
- Recruiter usability and satisfaction after set tasks.
- How often recruiters need to open the original CV to verify an answer.

Human reviewers should create the reference answers before these measures are treated as final performance results.

## 12. Future work

These are possible improvements, not all current features:

1. **Improve retrieval:** evaluate real questions and tune candidate count, chunk count, and semantic/keyword balance.
2. **Support more documents:** study OCR and better handling of multi-column layouts.
3. **Recognize more headings:** add aliases based on real CVs and test Arabic and English headings.
4. **Strengthen evaluation:** automatically validate citations, distinguish explicit facts from estimates, and add runnable withheld-CV/chunk cases instead of skipping them.
5. **Improve user accounts:** replace shared role passwords with individual accounts or a company sign-in provider.
6. **Improve operations:** strengthen monitoring for external service availability, connection errors, timeouts, and cost, and set backup and data-retention rules.
7. **Test with recruiters:** run structured user sessions and prioritize changes based on the results.

## 13. Main files for technical review

- App entry and access roles: `app.py`, `src/auth.py`
- User interface: `src/ui/pages/`
- CV import: `src/ingestion.py`, `src/ats_validator.py`, `src/extraction.py`
- Chunking: `src/chunking.py`
- Embeddings: `src/embeddings.py`
- Search: `src/search.py`, `src/database.py`, `src/candidate_matching.py`
- Gemini prompts and generation: `src/prompts.py`, `src/generation.py`
- Database structure: `sql/schema.sql`, `sql/migrations/001_product_setup.sql`

---

**Summary:** TalentSeek AI helps recruiters search CVs and review source evidence. It helps people find relevant information faster, while keeping verification and hiring decisions with the recruiter.
