from fastapi import APIRouter, Depends

from database import cursor
from security import verify_api_key

router = APIRouter(
    dependencies=[Depends(verify_api_key)]
)


@router.get("/files")
def get_files():
    cursor.execute("""
        SELECT file_id, filename, file_size_gb, allocation_id, node_id, created_at, status
        FROM files
    """)

    rows = cursor.fetchall()

    file_list = []

    for row in rows:
        file_list.append({
            "file_id": row[0],
            "filename": row[1],
            "file_size_gb": row[2],
            "allocation_id": row[3],
            "node_id": row[4],
            "created_at": row[5],
            "status": row[6]
        })

    return {
        "total_files": len(file_list),
        "files": file_list
    }


@router.get("/file/{file_id}")
def get_file(file_id: str):
    cursor.execute("""
        SELECT file_id, filename, file_size_gb, allocation_id, node_id, created_at, status
        FROM files
        WHERE file_id = ?
    """, (file_id,))

    row = cursor.fetchone()

    if row is None:
        return {"error": "File not found"}

    return {
        "file_id": row[0],
        "filename": row[1],
        "file_size_gb": row[2],
        "allocation_id": row[3],
        "node_id": row[4],
        "created_at": row[5],
        "status": row[6]
    }
