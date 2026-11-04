-- Non-destructive index for filtering CVs by job fields stored in documents.metadata.
BEGIN;

CREATE INDEX IF NOT EXISTS idx_documents_job_fields_gin
    ON documents USING GIN ((metadata->'job_fields'));

COMMIT;
