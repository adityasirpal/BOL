import os
import shutil
import uuid

from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from database import conn, cursor
from security import verify_api_key

router = APIRouter(
    dependencies=[Depends(verify_api_key)]
)


@router.get("/distributed-replicas/{file_id}")
def get_distributed_replicas(file_id: str):
    cursor.execute("""
        SELECT replica_id, file_id, chunk_id, primary_node_id, replica_node_id,
               chunk_path, chunk_size_bytes, replica_number, status, created_at
        FROM distributed_chunk_replicas
        WHERE file_id = ?
        ORDER BY chunk_id, replica_number
    """, (file_id,))

    rows = cursor.fetchall()
    replicas = []

    for row in rows:
        replicas.append({
            "replica_id": row[0],
            "file_id": row[1],
            "chunk_id": row[2],
            "primary_node_id": row[3],
            "replica_node_id": row[4],
            "chunk_path": row[5],
            "chunk_size_bytes": row[6],
            "replica_number": row[7],
            "status": row[8],
            "created_at": row[9]
        })

    return {
        "file_id": file_id,
        "total_replicas": len(replicas),
        "replicas": replicas
    }


@router.get("/node-replicas/{node_id}")
def get_node_replicas(node_id: str):
    cursor.execute("""
        SELECT replica_id, file_id, chunk_id, primary_node_id, replica_node_id,
               chunk_path, chunk_size_bytes, replica_number, status, created_at
        FROM distributed_chunk_replicas
        WHERE replica_node_id = ?
        ORDER BY created_at
    """, (node_id,))

    rows = cursor.fetchall()
    replicas = []

    for row in rows:
        replicas.append({
            "replica_id": row[0],
            "file_id": row[1],
            "chunk_id": row[2],
            "primary_node_id": row[3],
            "replica_node_id": row[4],
            "chunk_path": row[5],
            "chunk_size_bytes": row[6],
            "replica_number": row[7],
            "status": row[8],
            "created_at": row[9]
        })

    return {
        "node_id": node_id,
        "total_replicas": len(replicas),
        "replicas": replicas
    }
@router.post("/heal-missing-primary-chunks")
def heal_missing_primary_chunks():
    scan_time = datetime.now(timezone.utc).isoformat()

    cursor.execute("""
        SELECT file_id, chunk_id, chunk_path
        FROM physical_chunks
        ORDER BY file_id, chunk_number
    """)

    primary_chunks = cursor.fetchall()

    healed = []
    failed = []
    healthy = 0

    for row in primary_chunks:
        file_id = row[0]
        chunk_id = row[1]
        primary_path = row[2]

        if os.path.exists(primary_path):
            healthy += 1
            continue

        cursor.execute("""
            SELECT chunk_path
            FROM distributed_chunk_replicas
            WHERE file_id = ?
              AND chunk_id = ?
              AND status = 'replicated'
            ORDER BY replica_number
        """, (file_id, chunk_id))

        replica_rows = cursor.fetchall()
        usable_replica = None

        for replica_row in replica_rows:
            replica_path = replica_row[0]

            if replica_path != primary_path and os.path.exists(replica_path):
                usable_replica = replica_path
                break

        if usable_replica is None:
            recovery_id = "RECOVERY-" + str(uuid.uuid4())

            cursor.execute("""
                INSERT INTO recovery_events
                (recovery_id, file_id, chunk_id, failed_node_id, promoted_node_id,
                 recovery_action, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                recovery_id,
                file_id,
                chunk_id,
                "UNKNOWN",
                None,
                "AUTO_HEAL_PRIMARY_CHUNK",
                "FAILED_NO_REPLICA",
                scan_time
            ))

            failed.append({
                "file_id": file_id,
                "chunk_id": chunk_id,
                "primary_path": primary_path,
                "message": "No usable replica found"
            })

            continue

        os.makedirs(os.path.dirname(primary_path), exist_ok=True)
        shutil.copy2(usable_replica, primary_path)

        recovery_id = "RECOVERY-" + str(uuid.uuid4())

        cursor.execute("""
            INSERT INTO recovery_events
            (recovery_id, file_id, chunk_id, failed_node_id, promoted_node_id,
             recovery_action, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            recovery_id,
            file_id,
            chunk_id,
            "PRIMARY_CHUNK",
            "REPLICA_CHUNK",
            "AUTO_HEAL_PRIMARY_CHUNK",
            "HEALED",
            scan_time
        ))

        healed.append({
            "file_id": file_id,
            "chunk_id": chunk_id,
            "restored_primary_path": primary_path,
            "recovered_from_replica": usable_replica
        })

    conn.commit()

    return {
        "success": True,
        "healthy_chunks": healthy,
        "healed_chunks": len(healed),
        "failed_chunks": len(failed),
        "scan_time": scan_time
    }
