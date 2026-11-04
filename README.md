# TalentSeek AI

TalentSeek AI helps recruiters search a shared set of CVs in Arabic or English. It retrieves CV evidence and uses Gemini to write a short summary. A human recruiter reviews the evidence and makes every hiring decision.

## Main features

- Upload and validate PDF CVs.
- Extract text with PyMuPDF and split it by CV sections.
- Search with both semantic vectors and PostgreSQL text search.
- Show the source file, page, section, and matching text.
- Compare candidates and refine a shortlist with follow-up questions.
- Use Admin and Recruiter roles.
- Replace or delete CVs while keeping the database and stored files in sync.

## Technology

- Python and Streamlit
- PostgreSQL and pgvector
- Google Gemini for embeddings and answer generation
- PyMuPDF for PDF text extraction

## Requirements

- Python 3.10 or newer
- PostgreSQL with the pgvector extension
- A Google Gemini API key
- Access to a PostgreSQL database

## Setup

1. Open the `rag_cv_product` folder in VS Code.
2. Create and select a Python virtual environment.
3. Install the packages:

   ```powershell
   python -m pip install -r requirements.txt
   ```

4. Copy `.env.example` to `.env` and set your database details, Gemini API key, and different passwords for the Admin and Recruiter roles.
5. Do not commit `.env` or share its secrets.

### Database setup

For a new database, run `sql/schema.sql` once. It creates the tables, indexes, and pgvector extension used by the app.

For an existing database that already has the `documents` and `chunks` tables with `VECTOR(768)` embeddings, run `sql/migrations/001_product_setup.sql` once. This migration adds product tables and indexes without deleting CV records.

Do not run an older migration that changes embedding dimensions or deletes existing rows.

Check the embedding column with:

```sql
SELECT format_type(a.atttypid, a.atttypmod) AS embedding_type
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
WHERE c.relname = 'chunks'
  AND a.attname = 'embedding'
  AND a.attnum > 0;
```

The expected type is `vector(768)`.

## Run the app

From the project folder, run:

```powershell
python run_app.py
```

You can also open `run_app.py` in VS Code and choose **Run Python File**. Do not run `app.py` as a regular Python script.

## Use the app

### Add CVs

1. Open **Upload CVs**.
2. Upload one or more PDF files.
3. Choose **Validate uploaded CVs** and review any warnings or rejections.
4. Choose **Index accepted CVs**.

The app extracts text, splits it into sections, creates embeddings, and stores the results in PostgreSQL. Rejected files are not added to the CV tables.

### Search and compare

1. Open **Candidate Search**.
2. Enter job requirements in Arabic or English.
3. Review the candidates and the CV evidence shown with each result.
4. Use follow-up questions to refine the shortlist.
5. Open **Compare Candidates** to compare two to five selected candidates.

The model only receives the evidence retrieved for the search. A missing result does not prove that a candidate lacks the skill; the relevant evidence may not have been retrieved. Always review the original CV before making a decision.

### Replace or delete a CV

Admins can replace or delete CVs from **CV Documents**. A replacement is processed before the existing CV is replaced. If processing fails, the old CV remains available. Previous versions are not kept.

## Evaluation

The evaluation questions and reference answers are in `reports/rag_evaluation_dataset_20.json` when available locally. Run the evaluation from the project folder with:

```powershell
python -m src.evaluate_rag --interval-seconds 10
```

The runner sends questions one at a time and waits ten seconds between them. It saves a readable JSON trace and a summary under `reports/rag_evaluation_runs/`. Two failure cases require manually withholding a CV or chunk, so the runner skips them. Generation grounding, answer completeness, ranking quality, and some safety checks still need human review. Gemini token use is recorded when available; cost is only estimated when model prices are provided.

## Export extracted text or chunks

These commands read the indexed CVs from PostgreSQL and write reports locally:

```powershell
python db/export_extraction.py
python db/export_chunks.py
```

To export one document, add its document ID:

```powershell
python db/export_extraction.py --document-id 12
python db/export_chunks.py --document-id 12
```

Reports may contain personal CV information. Keep them private and do not commit them.

## ATS validation limits

The current checks are internal file checks, not a certification for commercial ATS products. The app accepts PDFs with extractable text, checks file size and page limits, and looks for known section headings. OCR for image-only PDFs is not supported. Some issues appear as warnings rather than rejection.

## Privacy and security

- CV files, extracted text, reports, and embeddings may contain personal data.
- `.env`, local CV files, cache data, and reports are excluded by `.gitignore`.
- Do not add real CVs, secrets, or private reports to a public repository.
- Use HTTPS and review PostgreSQL access before making the app available on a network.
- Search results support human review; they are not automatic hiring decisions.

## Tests

Run the existing tests from the project folder with:

```powershell
python -m pytest
```

The current tests cover password checks, section chunking, and database connectivity.

## Project layout

```text
app.py                 Streamlit entry point
run_app.py             App launcher
src/                   Search, CV processing, and UI code
db/                    Database connection and export tools
sql/                   Database schema and migrations
tests/                 Automated tests
reports/               Local evaluation and export reports
storage/               Local CV storage
```
