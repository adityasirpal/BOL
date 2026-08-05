from datetime import datetime, timezone
import uuid
import os
import hashlib

from fastapi import APIRouter, UploadFile, File

from database import conn, cursor
from config import UPLOAD_DIR, CHUNK_DIR
from services.file_service import FileService
from services.node_service import NodeService
from services.upload_service import UploadService

router = APIRouter()

node_service = NodeService(conn, cursor)
file_service = FileService(conn, cursor, node_service)
upload_service = UploadService(file_service)

@router.post("/upload-file")
async def upload_file(file: UploadFile = File(...)):

    file_id = "FILE-" + str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    file_content = await file.read()

    file_size_bytes = len(file_content)
    file_size_gb = round(file_size_bytes / (1024 * 1024 * 1024), 6)

    if file_size_gb == 0:
        file_size_gb = 0.001

    cursor.execute("""
        INSERT INTO files
        (file_id, filename, file_size_gb, created_at, status)
        VALUES (%s, %s, %s, %s, %s)
    """, (
        file_id,
        file.filename,
        file_size_gb,
        created_at,
        "uploaded"
    ))

    conn.commit()

    return {
        "success": True,
        "file_id": file_id,
        "filename": file.filename,
        "file_size_bytes": file_size_bytes,
        "file_size_gb": file_size_gb,
        "status": "uploaded"
    }

@router.post("/upload-and-chunk-file")
async def upload_and_chunk_file(file: UploadFile = File(...)):
    return await upload_service.upload_and_chunk_file(file)

@router.get("/physical-chunks/{file_id}")
def get_physical_chunks(file_id: str):

    cursor.execute("""
        SELECT chunk_id,
               file_id,
               chunk_number,
               chunk_path,
               chunk_size_bytes,
               checksum,
               created_at
        FROM physical_chunks
        WHERE file_id = %s
        ORDER BY chunk_number
    """, (file_id,))

    rows = cursor.fetchall()

    chunks = []

    for row in rows:
        chunks.append({
            "chunk_id": row[0],
            "file_id": row[1],
            "chunk_number": row[2],
            "chunk_path": row[3],
            "chunk_size_bytes": row[4],
            "checksum": row[5],
            "created_at": row[6]
        })

    return {
        "file_id": file_id,
        "total_chunks": len(chunks),
        "chunks": chunks
    }
