# BOL Development Journal

## Date

July 29, 2026

## Development checkpoint

Primary storage metadata integration into the real upload-and-chunk workflow.

## Session objective

The purpose of today’s session was to continue validation of the Phase 4 storage workflow and make the upload-and-chunk endpoint create two related forms of metadata:

1. The physical chunk record representing the binary chunk created on disk.
2. The distributed primary storage record representing which BOL node owns the primary copy of that chunk.

The goal was not simply to make the endpoint return success. The goal was to verify that the binary chunk, physical metadata, node selection, and distributed storage metadata all represented the same file and chunk.

## Why the session started with validations

Recent development had changed the responsibilities of FileService, ChunkService, NodeService, and the new primary storage helper.

Because these components affect the most important part of BOL—the physical storage of customer data—we started by validating the existing workflow before moving to additional replication logic.

The validations were necessary because a successful HTTP response alone does not prove that:

- A physical chunk was actually created.
- The chunk metadata was inserted correctly.
- A primary node was selected.
- The primary storage record was created.
- The file ID and chunk ID matched across tables.
- The database transaction remained internally consistent.

The session therefore focused on endpoint testing, source-code inspection, PostgreSQL verification, error diagnosis, and repeated compilation before accepting the change.

## Initial files and components reviewed

The following files were inspected or modified:

- `routes/uploads.py`
- `services/file_service.py`
- `services/node_service.py`
- `services/primary_storage_service.py`
- `config.py`
- `database.py`
- `security.py`

The primary route under test was:

- `POST /upload-and-chunk-file`

The application remained protected by API-key authentication, and testing was performed using authenticated `curl` commands instead of Swagger.

## Existing architecture reviewed

### Upload route

The `/upload-and-chunk-file` route delegates the workflow to:

```python
file_service.upload_and_chunk_file(file)
The route is intended to remain thin. Business logic belongs in service modules.

FileService

FileService is responsible for coordinating:

Incoming file persistence.
File metadata insertion.
Calling ChunkService.
Physical chunk metadata insertion.
Node selection through NodeService.
Primary distributed-storage metadata creation.
Database transaction commit or rollback.
Cleanup of files created during failed transactions.
ChunkService

ChunkService owns binary chunk creation and hashing.

It returns chunk information including:

chunk_id
chunk_number
chunk_path
size_bytes
sha256

This separation prevents FileService from duplicating chunk-splitting and hashing logic.

NodeService

NodeService owns node-related logic and database operations.

For the upload workflow, FileService now depends on NodeService to select the best available node for primary storage.

Primary storage helper

The canonical primary storage helper creates a record in the distributed storage metadata table.

The helper records information such as:

Storage ID.
File ID.
Chunk ID.
Node ID.
Storage type.
Chunk path.
Chunk size.
Status.
Creation time.

For this workflow, the storage type is primary and the status is stored.

Main development work completed
1. Upload route responsibility reviewed

The upload route was reviewed to ensure the endpoint calls FileService rather than duplicating the full workflow inside the route.

The intended route wiring is:

return await file_service.upload_and_chunk_file(file)
2. Upload streaming behavior retained

The upload-and-chunk method saves the incoming file incrementally rather than loading an arbitrarily large file completely into memory.

The file is read in blocks and written to the incoming upload directory.

This is important for future large-file handling.

3. File metadata creation validated

The uploaded file receives:

A generated FILE-... identifier.
The original filename.
Calculated file size.
UTC creation timestamp.
Upload-and-chunk status.
4. ChunkService ownership clarified

ChunkService remains responsible for:

Splitting the uploaded file.
Writing binary chunks.
Generating chunk IDs.
Calculating SHA-256 hashes.
Returning chunk metadata to FileService.
5. Physical chunk identifier problem diagnosed

The first upload attempt failed because PostgreSQL rejected a null value for:

physical_chunks.physical_chunk_id

The physical chunks table requires a non-null physical chunk identifier.

The upload workflow was updated to generate a unique value in the form:

PHYSICAL-<UUID>

before inserting the physical chunk record.

6. Physical chunk metadata insertion repaired

The insertion into physical_chunks was aligned with the actual schema.

The record contains:

physical_chunk_id
chunk_id
file_id
chunk_number
chunk_path
chunk_size_bytes
checksum
created_at
status

The status used for the successfully written chunk is:

stored
7. NodeService dependency introduced

FileService needs NodeService in order to assign each primary chunk to a node.

The FileService constructor supports receiving a NodeService dependency.

The uploads route was updated so it can construct:

node_service = NodeService(conn, cursor)
file_service = FileService(conn, cursor, node_service)
8. NodeService availability validation added

A defensive check was introduced so the upload workflow does not silently create physical metadata without being able to assign distributed primary storage.

When NodeService is unavailable, the workflow returns a controlled failure rather than creating incomplete distributed metadata.

9. Best-node selection integrated

After the physical chunk record is created, FileService calls NodeService to select the best available node.

If no suitable online node is available, the transaction must fail and roll back rather than create an incomplete storage assignment.

10. Canonical primary storage helper integrated

After node selection, FileService calls the canonical primary-storage helper.

The helper receives:

Database cursor.
File ID.
Chunk ID.
Selected node ID.
Chunk path.
Chunk size.
Creation timestamp.

This creates the primary entry in the distributed storage metadata table.

11. Transaction handling retained

The upload workflow uses a database transaction.

On success:

File metadata is retained.
Physical chunk metadata is retained.
Primary distributed-storage metadata is retained.
The transaction is committed.

On failure:

The database transaction is rolled back.
Created chunk files are removed where possible.
The incoming uploaded file is removed where appropriate.
A structured error response is returned.
Problems encountered during development
Physical chunk NOT NULL violation

Error:

null value in column "physical_chunk_id" of relation "physical_chunks"
violates not-null constraint

Cause:

The newly refactored insertion populated chunk_id but did not generate and insert the required physical_chunk_id.

Resolution:

Generate a separate PHYSICAL-<UUID> value and insert it into the correct column.

Missing primary storage record

After the physical chunk insert succeeded, database validation initially showed:

One physical chunk.
Zero active primary storage records.

Cause:

The workflow created the physical chunk but had not yet successfully executed the canonical primary-storage helper.

Resolution:

Wire NodeService into FileService, select the best node, and call the primary-storage helper for every successfully created chunk.

Indentation errors

Several edits caused Python indentation failures in the try block and chunk-processing section.

Errors included:

IndentationError: expected an indented block
IndentationError: unexpected indent
SyntaxError: expected 'except' or 'finally' block

Cause:

Code inserted into the upload method was not consistently nested inside:

The method.
The try block.
The for chunk in chunks loop.

Resolution:

The damaged upload metadata section was reconstructed and indentation was checked programmatically.

Unterminated triple-quoted SQL string

An intermediate edit resulted in:

SyntaxError: unterminated triple-quoted string literal

Cause:

A SQL string in the modified section was opened but not correctly closed after manual changes.

Resolution:

The relevant SQL block was inspected, reconstructed, and compiled again.

Uvicorn server confusion

An attempt was made to start Uvicorn while port 8000 was already occupied.

Error:

[Errno 98] address already in use

Further investigation showed that Uvicorn was already running as a manually launched process rather than as a bol.service systemd unit.

The server process was later intentionally restarted using:

pkill -f "/root/bol/venv/bin/uvicorn app:app"

followed by a nohup Uvicorn command.

Systemd service not found

The command:

systemctl restart bol

failed because no bol.service unit currently exists.

This confirmed that the present prototype is being run manually through Uvicorn.

A permanent systemd unit remains future infrastructure work.

FileService initially received no NodeService

An upload test returned:

{
    "success": false,
    "message": "Upload and chunk workflow failed",
    "error": "NodeService is unavailable"
}

Cause:

routes/uploads.py was still constructing FileService without providing a NodeService instance.

Resolution:

NodeService was imported and passed into FileService during route wiring.

Validation commands used
API key loading

The API key was loaded from the existing security module:

API_KEY=$(python -c 'from security import API_KEY; print(API_KEY)')
Root endpoint validation

The root endpoint was tested with API-key authentication.

Successful result:

{
    "project": "BOL",
    "status": "online",
    "message": "Building the future of Internet"
}
Upload-and-chunk validation

A small timestamped test file was created and sent to:

POST /upload-and-chunk-file

The final successful response confirmed:

success: true
A generated file ID.
Original filename.
Incoming file path.
File size.
One physical chunk.
Chunk ID.
Chunk number.
Chunk path.
Chunk size.
SHA-256 checksum.
PostgreSQL physical chunk validation

The physical_chunks table was queried using the uploaded file ID.

The final query confirmed one stored physical chunk containing:

A non-null physical chunk ID.
The correct file ID.
The correct chunk ID.
Chunk number 1.
The expected chunk path.
The expected byte size.
Status stored.
A UTC creation timestamp.
PostgreSQL primary storage validation

The distributed storage table was queried using the same file ID.

The final query confirmed one primary storage record containing:

A generated distributed storage ID.
The correct file ID.
The same chunk ID as the physical chunk record.
Node USA002.
Storage type primary.
The same stored chunk path.
The same byte size.
Status stored.
A UTC creation timestamp.
Final validated example

The final successful upload produced:

One file record.
One binary chunk on disk.
One physical chunk metadata record.
One primary distributed-storage metadata record.
One selected primary node.

The physical chunk and distributed storage records matched on:

File ID.
Chunk ID.
Chunk path.
Chunk size.
Status.
Creation time.

This proved that the primary-storage helper is now participating in the real upload-and-chunk workflow.

Current architecture after today’s work

The upload flow now follows this sequence:

Authenticated API request
        |
        v
routes/uploads.py
        |
        v
FileService.upload_and_chunk_file
        |
        +--> Persist incoming file
        |
        +--> Insert file metadata
        |
        +--> ChunkService.split_file
        |       |
        |       +--> Create binary chunk
        |       +--> Generate chunk ID
        |       +--> Calculate SHA-256
        |
        +--> Insert physical_chunks metadata
        |
        +--> NodeService.select_best_node
        |
        +--> create_primary_storage_record
        |
        +--> Commit transaction
        |
        v
Return file and chunk information
Confirmed working at checkpoint

The following functionality was confirmed working:

API-key authenticated root request.
Uvicorn application startup.
Incoming file persistence.
Real binary chunk creation.
Chunk hashing.
File metadata insertion.
Non-null physical chunk identifier generation.
Physical chunk metadata insertion.
NodeService dependency wiring.
Best-node selection.
Canonical primary-storage metadata creation.
Transaction commit.
PostgreSQL verification across both storage tables.
Important technical observations
Physical and logical identifiers must remain separate

The system currently has distinct concepts:

chunk_id: logical identity of the chunk.
physical_chunk_id: identity of a physical stored instance.
storage_id: identity of the distributed storage assignment.

These should not be merged. One logical chunk may eventually have multiple physical copies and multiple storage assignments.

Route logic should be reduced further

routes/uploads.py still contains older direct database logic for some endpoints.

Long-term direction remains:

Routes should receive requests and return responses.
Services should contain business logic.
Storage helpers should own canonical storage record creation.
Database access should not be duplicated across routes and services.
Current Uvicorn process is not managed by systemd

The BOL application is currently running manually with Uvicorn.

Before production or unattended operation, a proper service manager should be configured so BOL:

Starts automatically after reboot.
Restarts after failure.
Writes predictable logs.
Runs under a dedicated non-root Linux user.
Files changed or created during the session

Primary source files:

routes/uploads.py
services/file_service.py
services/node_service.py
services/primary_storage_service.py
config.py

Development artifacts and temporary backup files were also generated while repairing indentation and SQL blocks.

These temporary files should remain outside the Git commit unless deliberately required.

Freeze decision

The July 29 session ends at a stable primary-storage checkpoint.

No additional replica, recovery, encryption, or cleanup development should be started before this state is committed, tagged, and backed up.

Next development session

The recommended next sequence is:

Reconfirm the tagged checkpoint.
Run one clean regression upload.
Verify the physical chunks endpoint.
Add canonical replica-storage creation.
Verify primary and replica metadata separately.
Test behavior when no nodes are available.
Test rollback behavior after an intentional failure.
Create the next Git commit and tag before continuing.
Checkpoint name
checkpoint-2026-07-29-primary-storage-wiring
Session conclusion

The important accomplishment today was not merely fixing an upload error.

The upload-and-chunk workflow now connects real file ingestion, binary chunk creation, physical metadata, node selection, and canonical distributed primary-storage metadata.

This is a meaningful Phase 4 foundation for later replication, recovery, integrity checking, and node-based storage orchestration.
JOURNAL

echo "Daily journal created:"
echo "$JOURNAL_FILE"

--------------------------------------------------
3. Remove Python cache files from the working tree
--------------------------------------------------

find /root/bol
-type d -name "pycache"
-prune -exec rm -rf {} +

find /root/bol
-type f −name"∗.pyc"−o−name"∗.pyo"
-delete

--------------------------------------------------
4. Validate source code before committing
--------------------------------------------------

python -m py_compile
app.py
routes/uploads.py
services/file_service.py
services/node_service.py
services/primary_storage_service.py

git diff --check

echo "Python compilation and Git whitespace checks passed."

--------------------------------------------------
5. Create PostgreSQL backups
--------------------------------------------------

sudo -u postgres pg_dump
--format=custom
--no-owner
--no-privileges
--file="$BACKUP_DIR/bol_database_${TIMESTAMP}.dump"
bol

sudo -u postgres pg_dump
--format=plain
--no-owner
--no-privileges
bol
> "$BACKUP_DIR/bol_database_${TIMESTAMP}.sql"

sudo -u postgres psql
-P pager=off
-d bol
-c '\dt'
> "$BACKUP_DIR/postgresql_tables.txt"

sudo -u postgres psql
-P pager=off
-d bol
-c '\d+ physical_chunks'
> "$BACKUP_DIR/physical_chunks_schema.txt"

sudo -u postgres psql
-P pager=off
-d bol
-c '\d+ distributed_chunk_storage'
> "$BACKUP_DIR/distributed_chunk_storage_schema.txt"

echo "PostgreSQL database backups created."

--------------------------------------------------
6. Create a full filesystem backup of BOL
--------------------------------------------------

tar
--exclude='/root/bol/venv'
--exclude='/root/bol/.git'
--exclude='/pycache'
--exclude='.pyc'
--exclude='*.pyo'
-czf "$BACKUP_DIR/bol_full_project_${TIMESTAMP}.tar.gz"
-C /root bol

Preserve Git repository separately, including history and tags.

git bundle create
"$BACKUP_DIR/bol_git_repository_${TIMESTAMP}.bundle"
--all

echo "Full project archive and Git repository bundle created."

--------------------------------------------------
7. Save environment and runtime information
--------------------------------------------------

python --version > "$BACKUP_DIR/python_version.txt"
pip freeze > "$BACKUP_DIR/python_requirements_freeze.txt"

ps -ef | grep '[u]vicorn'
> "$BACKUP_DIR/uvicorn_process.txt" || true

ss -ltnp
> "$BACKUP_DIR/listening_ports.txt" || true

Save endpoint inventory from the FastAPI application.

python - <<'PY' > "$BACKUP_DIR/endpoint_inventory.txt"
from app import app

routes = []
for route in app.routes:
methods = ",".join(sorted(getattr(route, "methods", []) or []))
path = getattr(route, "path", "")
name = getattr(route, "name", "")
routes.append((path, methods, name))

for path, methods, name in sorted(routes):
print(f"{methods:20} {path:55} {name}")
PY

--------------------------------------------------
8. Stage only project source and documentation
--------------------------------------------------

git add -A --
app.py
config.py
database.py
security.py
routes
services
docs

echo
echo "Files staged for checkpoint:"
git status --short

--------------------------------------------------
9. Commit the checkpoint
--------------------------------------------------

git commit -m "Checkpoint July 29 2026: wire canonical primary storage into upload flow"
-m "Validated authenticated upload-and-chunk workflow, physical chunk metadata, NodeService dependency injection, best-node selection, and canonical primary distributed storage record creation."
-m "Verified matching file IDs, chunk IDs, paths, byte sizes and stored statuses directly in PostgreSQL."

COMMIT_HASH="$(git rev-parse HEAD)"

--------------------------------------------------
10. Create annotated Git tag
--------------------------------------------------

if git rev-parse "$TAG_NAME" >/dev/null 2>&1; then
echo "ERROR: Git tag already exists: $TAG_NAME"
echo "Commit was created, but no tag was overwritten."
exit 1
fi

git tag -a "$TAG_NAME"
-m "BOL July 29 2026 stable checkpoint

Validated:

API-key authenticated upload-and-chunk
Real physical chunk creation
Physical chunk metadata insertion
NodeService wiring
Best-node selection
Canonical primary storage record creation
PostgreSQL consistency across physical_chunks and distributed_chunk_storage

Commit: $COMMIT_HASH"

--------------------------------------------------
11. Save final Git checkpoint details
--------------------------------------------------

git status > "$BACKUP_DIR/git_status_after_commit.txt"
git log -1 --stat --decorate > "$BACKUP_DIR/checkpoint_commit.txt"
git show "$TAG_NAME" --no-patch > "$BACKUP_DIR/checkpoint_tag.txt"

cat > "$BACKUP_DIR/CHECKPOINT_SUMMARY.txt" <<EOF
BOL CHECKPOINT SUMMARY

Date:
$CHECKPOINT_DATE

Checkpoint:
$CHECKPOINT_NAME

Git commit:
$COMMIT_HASH

Git tag:
$TAG_NAME

Daily journal:
$JOURNAL_FILE

Full project archive:
$BACKUP_DIR/bol_full_project_${TIMESTAMP}.tar.gz

PostgreSQL custom dump:
$BACKUP_DIR/bol_database_${TIMESTAMP}.dump

PostgreSQL SQL dump:
$BACKUP_DIR/bol_database_${TIMESTAMP}.sql

Git repository bundle:
$BACKUP_DIR/bol_git_repository_${TIMESTAMP}.bundle

Checkpoint status:
Upload-and-chunk creates matching physical chunk and primary distributed
storage metadata, using NodeService for primary-node selection.
EOF

--------------------------------------------------
12. Generate backup checksums
--------------------------------------------------

cd "$BACKUP_DIR"

find . -maxdepth 1 -type f
! -name "SHA256SUMS.txt"
-print0
| sort -z
| xargs -0 sha256sum
> SHA256SUMS.txt

cd /root/bol

--------------------------------------------------
13. Final checkpoint verification
--------------------------------------------------

echo
echo "=================================================="
echo "CHECKPOINT COMPLETE"
echo "=================================================="
echo "Commit: $COMMIT_HASH"
echo "Tag: $TAG_NAME"
echo "Backup: $BACKUP_DIR"
echo "Journal: $JOURNAL_FILE"
echo

git status
git log -1 --oneline --decorate
git tag -n20 "$TAG_NAME"

echo
echo "Backup contents:"
du -sh "$BACKUP_DIR"
find "$BACKUP_DIR" -maxdepth 2 -type f | sort

echo
echo "SHA-256 verification:"
cd "$BACKUP_DIR"
sha256sum -c SHA256SUMS.txt
cd /root/bol


## 2. Confirm the server still responds after the checkpoint

The server is already running, so do **not** launch another Uvicorn process. Run:

```bash
cd /root/bol
source venv/bin/activate

API_KEY="$(python -c 'from security import API_KEY; print(API_KEY)')"
BASE_URL="http://127.0.0.1:8000"

curl -sS \
  -H "X-API-Key: $API_KEY" \
  "$BASE_URL/" \
  | python -m json.tool

Expected result:

{
    "project": "BOL",
    "status": "online",
    "message": "Building the future of Internet"
}
