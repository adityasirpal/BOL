from fastapi import APIRouter
from datetime import datetime, timezone

router = APIRouter(tags=["health"])


@router.get("/api-health")
def api_health():
    return {
        "success": True,
        "service": "BOL API",
        "status": "running",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
