from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

import os
import sqlite3

from security import verify_api_key
from database import conn, cursor
from services.node_service import NodeService
from services.file_service import FileService
from database import conn, cursor

node_service = NodeService(conn, cursor)
file_service = FileService(conn, cursor, node_service)

router = APIRouter(
    dependencies=[Depends(verify_api_key)]
)

@router.get("/download-file-metadata/{file_id}")
def download_file(file_id: str):
    cursor.execute("""
        SELECT filename
        FROM files
        WHERE file_id = %s
    """, (file_id,))

    file_row = cursor.fetchone()

    if file_row is None:
        return {
            "success": False,
            "message": "File not found"
        }

    filename = file_row[0]

    cursor.execute("""
        SELECT chunk_id, chunk_path, chunk_number
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

    return {
        "success": True,
        "file_id": file_id,
        "filename": filename,
        "total_chunks": len(chunks),
        "chunks": [
            {
                "chunk_id": row[0],
                "chunk_path": row[1],
                "chunk_number": row[2]
            }
            for row in chunks
        ]
    }

@router.post("/rebuild-file/{file_id}")
def rebuild_file(file_id: str):
    return file_service.recover_file(file_id)
    cursor.execute("""
        SELECT filename
        FROM files
        WHERE file_id = %s
    """, (file_id,))

    file_row = cursor.fetchone()

    if file_row is None:
        return {
            "success": False,
            "message": "File not found"
        }

    filename = file_row[0]

    cursor.execute("""
        SELECT chunk_path, chunk_id, chunk_number
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

    output_path = os.path.join("downloads", filename)
    os.makedirs("downloads", exist_ok=True)

    recovered_from_replicas = 0

    with open(output_path, "wb") as output_file:
        for row in chunks:
            chunk_path = row[0]
            chunk_id = row[1]

            if not os.path.exists(chunk_path):
                cursor.execute("""
                    SELECT chunk_path
                    FROM distributed_chunk_replicas
                    WHERE file_id = %s
                      AND chunk_id = %s
                      AND status = 'replicated'
                    ORDER BY replica_number
                    LIMIT 1
                """, (file_id, chunk_id))

                replica_row = cursor.fetchone()

                if replica_row is None or not os.path.exists(replica_row[0]):
                    return {
                        "success": False,
                        "message": "Missing chunk during rebuild and no replica available",
                        "missing_chunk_path": chunk_path,
                        "chunk_id": chunk_id
                    }

                chunk_path = replica_row[0]
                recovered_from_replicas += 1

            with open(chunk_path, "rb") as chunk_file:
                output_file.write(chunk_file.read())

    return {
        "success": True,
        "file_id": file_id,
        "filename": filename,
        "chunks_rebuilt": len(chunks),
        "recovered_from_replicas": recovered_from_replicas,
        "download_path": output_path
    }
