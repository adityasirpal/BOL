from fastapi import APIRouter, Depends

from database import cursor
from security import verify_api_key

router = APIRouter()

@router.get("/nodes", dependencies=[Depends(verify_api_key)])
def get_nodes():
    cursor.execute("""
        SELECT node_id, country, storage_gb, status, last_seen
        FROM nodes
    """)

    rows = cursor.fetchall()

    node_list = []

    for row in rows:
        node_list.append({
            "node_id": row[0],
            "country": row[1],
            "storage_gb": row[2],
            "status": row[3],
            "last_seen": row[4]
        })

    return {
        "total_nodes": len(node_list),
        "nodes": node_list
    }
