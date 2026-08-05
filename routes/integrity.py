from datetime import datetime, timezone
import hashlib
import os
import uuid

from fastapi import APIRouter, Depends

from database import conn, cursor
from security import verify_api_key

router = APIRouter(
    dependencies=[Depends(verify_api_key)]
)


@router.get("/integrity-events")
def get_integrity_events():
    cursor.execute("""
        SELECT integrity_id, file_id, chunk_id, chunk_path, verification_status, created_at
        FROM integrity_events
        ORDER BY created_at DESC
    """)

    rows = cursor.fetchall()
    events = []

    for row in rows:
        events.append({
            "integrity_id": row[0],
            "file_id": row[1],
            "chunk_id": row[2],
            "chunk_path": row[3],
            "verification_status": row[4],
            "created_at": row[5]
        })

    return {
        "success": True,
        "total_events": len(events),
        "events": events
    }


@router.get("/corrupted-chunks")
def get_corrupted_chunks():
    cursor.execute("""
        SELECT integrity_id, file_id, chunk_id, node_id, storage_role,
               expected_checksum, actual_checksum, verification_status, created_at
        FROM integrity_events
        WHERE verification_status IN ('corrupted', 'missing')
        ORDER BY created_at DESC
    """)

    rows = cursor.fetchall()
    corrupted = []

    for row in rows:
        corrupted.append({
            "integrity_id": row[0],
            "file_id": row[1],
            "chunk_id": row[2],
            "node_id": row[3],
            "storage_role": row[4],
            "expected_checksum": row[5],
            "actual_checksum": row[6],
            "verification_status": row[7],
            "created_at": row[8]
        })

    return {
        "total_corrupted_or_missing": len(corrupted),
        "chunks": corrupted
    }


@router.post("/verify-file/{file_id}")
def verify_file(file_id: str):
    created_at = datetime.now(timezone.utc).isoformat()

    cursor.execute("""
        SELECT chunk_id, chunk_path, checksum
        FROM physical_chunks
        WHERE file_id = %s
        ORDER BY chunk_number
    """, (file_id,))

    chunks = cursor.fetchall()

    if not chunks:
        return {
            "success": False,
            "message": "No chunks found for this file"
        }

    results = []
    healthy = 0
    corrupted = 0
    missing = 0

    for chunk in chunks:
        chunk_id = chunk[0]
        chunk_path = chunk[1]
        expected_checksum = chunk[2]

        if not os.path.exists(chunk_path):
            actual_checksum = None
            verification_status = "missing"
            missing += 1
        else:
            with open(chunk_path, "rb") as f:
                data = f.read()

            actual_checksum = hashlib.sha256(data).hexdigest()

            if actual_checksum == expected_checksum:
                verification_status = "healthy"
                healthy += 1
            else:
                verification_status = "corrupted"
                corrupted += 1

        integrity_id = "INTEGRITY-" + str(uuid.uuid4())

        cursor.execute("""
            INSERT INTO integrity_events
            (integrity_id, file_id, chunk_id, chunk_path, verification_status, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            integrity_id,
            file_id,
            chunk_id,
            chunk_path,
            verification_status,
            created_at
        ))

        results.append({
            "integrity_id": integrity_id,
            "chunk_id": chunk_id,
            "verification_status": verification_status
        })

    conn.commit()

    return {
        "success": True,
        "file_id": file_id,
        "total_checked": len(results),
        "healthy": healthy,
        "corrupted": corrupted,
        "missing": missing,
        "results": results
    }
