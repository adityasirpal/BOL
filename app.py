import os
from services.node_service import NodeService
from routes.health import router as health_router
from routes.uploads import router as uploads_router
from routes.nodes import router as nodes_router
from routes.files import router as files_router
from routes.integrity import router as integrity_router
from routes.downloads import router as downloads_router
from routes.replicas import router as replicas_router
from fastapi import FastAPI, UploadFile, File, Depends, APIRouter
from fastapi.responses import FileResponse
from services.file_service import FileService
from pydantic import BaseModel
from config import (
    UPLOAD_DIR,
    CHUNK_DIR,
    DOWNLOAD_DIR,
    DECRYPTED_DIR
)
from database import conn, cursor
from models.schemas import (
    Node,
    Heartbeat,
    StorageRequest,
    FileRecord
)
from security import verify_api_key

router = APIRouter()

app = FastAPI(
    dependencies=[Depends(verify_api_key)],
    docs_url=None,
    redoc_url=None,
    openapi_url=None
)

app.include_router(nodes_router)
app.include_router(files_router)
app.include_router(integrity_router)
app.include_router(downloads_router)
app.include_router(replicas_router)
app.include_router(uploads_router)
app.include_router(health_router)

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(CHUNK_DIR, exist_ok=True)
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(DECRYPTED_DIR, exist_ok=True)

# Add last_seen column if the table already existed from older version

cursor.execute("""
CREATE TABLE IF NOT EXISTS allocations (
    allocation_id TEXT PRIMARY KEY,
    node_id TEXT,
    file_size_gb INTEGER,
    allocated_at TEXT,
    status TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS files (
    file_id TEXT PRIMARY KEY,
    filename TEXT,
    file_size_gb INTEGER,
    allocation_id TEXT,
    node_id TEXT,
    created_at TEXT,
    status TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS file_replicas (
    replica_id TEXT PRIMARY KEY,
    file_id TEXT,
    node_id TEXT,
    replica_number INTEGER,
    created_at TEXT,
    status TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    file_id TEXT NOT NULL,
    replica_id TEXT,
    chunk_number INTEGER,
    chunk_size_mb REAL,
    status TEXT,
    created_at TIMESTAMP
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS chunk_locations (
    location_id TEXT PRIMARY KEY,
    chunk_id TEXT,
    file_id TEXT,
    node_id TEXT,
    created_at TEXT,
    status TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS node_storage_usage (
    node_id TEXT PRIMARY KEY,
    total_storage_gb INTEGER,
    used_storage_gb INTEGER,
    available_storage_gb INTEGER,
    last_updated TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS file_replication (
    replication_id TEXT PRIMARY KEY,
    file_id TEXT,
    chunk_id TEXT,
    primary_node_id TEXT,
    replica_node_id TEXT,
    created_at TEXT,
    status TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS failover_events (
    failover_id TEXT PRIMARY KEY,
    chunk_id TEXT,
    file_id TEXT,
    failed_node_id TEXT,
    promoted_node_id TEXT,
    created_at TEXT,
    status TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS physical_chunks (
    chunk_id TEXT PRIMARY KEY,
    file_id TEXT NOT NULL,
    chunk_number INTEGER NOT NULL,
    chunk_path TEXT NOT NULL,
    chunk_size_bytes INTEGER,
    checksum TEXT,
    created_at TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS chunk_integrity (
    integrity_id TEXT PRIMARY KEY,
    file_id TEXT NOT NULL,
    chunk_id TEXT NOT NULL,
    sha256_hash TEXT NOT NULL,
    verified_at TEXT,
    status TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS file_encryption (
    encryption_id TEXT PRIMARY KEY,
    file_id TEXT NOT NULL,
    encryption_method TEXT NOT NULL,
    encryption_key TEXT NOT NULL,
    encrypted_file_path TEXT NOT NULL,
    encrypted_at TEXT NOT NULL,
    status TEXT NOT NULL
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS distributed_chunk_storage (
    storage_id TEXT PRIMARY KEY,
    file_id TEXT NOT NULL,
    chunk_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    chunk_path TEXT NOT NULL,
    chunk_size_bytes INTEGER,
    storage_type TEXT,
    status TEXT,
    created_at TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS distributed_chunk_replicas (
    replica_id TEXT PRIMARY KEY,
    file_id TEXT NOT NULL,
    chunk_id TEXT NOT NULL,
    primary_node_id TEXT NOT NULL,
    replica_node_id TEXT NOT NULL,
    chunk_path TEXT NOT NULL,
    chunk_size_bytes INTEGER,
    replica_number INTEGER,
    status TEXT,
    created_at TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS node_health_events (
    health_event_id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL,
    previous_status TEXT,
    new_status TEXT NOT NULL,
    event_type TEXT NOT NULL,
    created_at TEXT NOT NULL
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS recovery_events (
    recovery_id TEXT PRIMARY KEY,
    file_id TEXT NOT NULL,
    chunk_id TEXT NOT NULL,
    failed_node_id TEXT NOT NULL,
    promoted_node_id TEXT,
    recovery_action TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS distributed_rebuild_events (
    rebuild_id TEXT PRIMARY KEY,
    file_id TEXT NOT NULL,
    rebuilt_file_path TEXT NOT NULL,
    chunks_used INTEGER,
    status TEXT,
    created_at TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS integrity_events (
    integrity_id TEXT PRIMARY KEY,
    file_id TEXT,
    chunk_id TEXT,
    node_id TEXT,
    storage_role TEXT,
    expected_checksum TEXT,
    actual_checksum TEXT,
    verification_status TEXT,
    created_at TEXT
)
""")

conn.commit()
node_service = NodeService(conn, cursor)
file_service = FileService(conn, cursor, node_service)

class StoreChunkRequest(BaseModel):
    file_id: str
    chunk_id: str
    node_id: str
    chunk_number: int
    data: str

class RoundtripChunkTestRequest(BaseModel):
    file_id: str
    chunk_id: str
    node_id: str
    chunk_number: int
    data: str

def record_node_health_event(node_id, previous_status, new_status, event_type):
    health_event_id = "HEALTH-" + str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    cursor.execute("""
        INSERT INTO node_health_events
        (health_event_id, node_id, previous_status, new_status, event_type, created_at)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (
        health_event_id,
        node_id,
        previous_status,
        new_status,
        event_type,
        created_at
    ))

    return health_event_id

@app.get("/")
def root():
    return {
        "project": "BOL",
        "status": "online",
        "message": "Building the future of Internet"
    }

@app.post("/recover-node/{node_id}")
def recover_node(node_id: str):
    return node_service.recover_node(node_id)

@app.get("/node/{node_id}")
def get_node(node_id: str):
    return node_service.get_node(node_id)

@app.post("/heartbeat")
def heartbeat(heartbeat: Heartbeat):
    return node_service.heartbeat(heartbeat)

@app.post("/scan-node-health")
def scan_node_health():
    return node_service.scan_node_health()


@app.get("/allocations")
def get_allocations():
    return node_service.get_allocations()


@app.post("/register-file")
def register_file(file: FileRecord):
    return file_service.register_file(file)

@app.get("/online-nodes")
def online_nodes():
    return node_service.get_online_nodes()

@app.get("/offline-nodes")
def offline_nodes():
    return node_service.get_offline_nodes()

@app.get("/network-capacity")
def network_capacity():
    return node_service.get_network_capacity()

@app.post("/allocate-storage")
def allocate_storage(request: StorageRequest):
    return node_service.allocate_storage(request)

@app.post("/create-replicas/{file_id}")
def create_replicas(file_id: str):
    return file_service.create_replicas(file_id)


@app.get("/file-health/{file_id}")
def file_health(file_id: str):
    return file_service.file_health(file_id)


@app.get("/chunk/{chunk_id}")
def get_chunk(chunk_id: str):
    return file_service.get_chunk(chunk_id)


@app.get("/failover-events")
def get_failover_events():
    return file_service.get_failover_events()

@app.get("/replicas/{file_id}")
def get_replicas(file_id: str):
    return file_service.get_replicas(file_id)

@app.post("/create-chunks/{file_id}")
def create_chunks(file_id: str):
    return file_service.create_chunks(file_id)

@app.get("/chunks/{file_id}")
def get_chunks(file_id: str):
    return file_service.get_chunks(file_id)

@app.post("/place-chunks/{file_id}")
def place_chunks(file_id: str):
    return file_service.place_chunks(file_id)

@app.get("/chunk-locations/{file_id}")
def get_chunk_locations(file_id: str):
    return file_service.get_chunk_locations(file_id)

@app.get("/chunk-location/{chunk_id}")
def chunk_location(chunk_id:str):
    return file_service.chunk_location(chunk_id)

@app.post("/initialize-storage-usage")
def initialize_storage_usage():
    return node_service.initialize_storage_usage()

@app.get("/storage-usage")
def get_storage_usage():
    return node_service.get_storage_usage()

@app.get("/storage-usage/{node_id}")
def get_node_storage_usage(node_id: str):
    return node_service.get_node_storage_usage(node_id)

@app.post("/replicate-file/{file_id}")
def replicate_file(file_id: str):
    return file_service.replicate_file(file_id)

@app.get("/file-replication/{file_id}")
def get_file_replication(file_id: str):
    return file_service.get_file_replication(file_id)

@app.post("/restore-node/{node_id}")
def restore_node(node_id: str):
    restored_at = datetime.now(timezone.utc).isoformat()

    cursor.execute("""
        UPDATE nodes
        SET status = 'online',
            last_seen = ?
        WHERE node_id = %s
    """, (restored_at, node_id))

    conn.commit()

    return {
        "success": True,
        "node_id": node_id,
        "status": "online",
        "restored_at": restored_at
    }

@app.post("/upload-file")
async def upload_file(file: UploadFile = File(...)):
    return await file_service.upload_file(file)

@app.post("/upload-and-chunk-file")
async def upload_and_chunk_file(file: UploadFile = File(...)):
    return await file_service.upload_and_chunk_file(file)

@app.get("/physical-chunks/{file_id}")
def physical_chunks(file_id:str):
    return file_service.physical_chunks(file_id)

@app.get("/download-file/{file_id}")
def download_file(file_id: str):
    return file_service.download_file(file_id)

@app.get("/recover-file/{file_id}")
def recover_file(file_id: str):
    return file_service.recover_file(file_id)

@app.post("/generate-checksums/{file_id}")
def generate_checksums(file_id: str):
    return file_service.generate_checksums(file_id)

@app.get("/chunk-integrity/{file_id}")
def get_chunk_integrity(file_id: str):
    return file_service.get_chunk_integrity(file_id)

@app.post("/verify-file-old/{file_id}")
def verify_file(file_id: str):
    return file_service.verify_file_old(file_id)

@app.post("/encrypt-upload-and-chunk-file")
async def encrypt_upload_and_chunk_file(file: UploadFile = File(...)):
    return await file_service.encrypt_upload_and_chunk_file(file)

@app.get("/file-encryption/{file_id}")
def get_file_encryption(file_id: str):
    return file_service.get_file_encryption(file_id)

@app.post("/rebuild-encrypted-file/{file_id}")
def rebuild_encrypted_file(file_id: str):
    return file_service.rebuild_encrypted_file(file_id)

@app.post("/decrypt-file/{file_id}")
def decrypt_file(file_id: str):
    return file_service.decrypt_file(file_id)

@app.get("/download-decrypted-file/{file_id}")
def download_decrypted_file(file_id: str):
    return file_service.download_decrypted_file(file_id)

@app.post("/distribute-physical-chunks/{file_id}")
def distribute_physical_chunks(file_id: str):
    return file_service.distribute_physical_chunks(file_id)

@app.get("/distributed-chunks/{file_id}")
def get_distributed_chunks(file_id: str):
    return file_service.get_distributed_chunks(file_id)

@app.get("/node-chunks/{node_id}")
def get_node_chunks(node_id: str):
    return node_service.get_node_chunks(node_id)

@app.get("/best-node")
def get_best_node():
    return node_service.select_best_node()

@app.post("/smart-distribute-physical-chunks/{file_id}")
def smart_distribute_physical_chunks(file_id: str):
    return file_service.smart_distribute_physical_chunks(file_id)

@app.post("/create-distributed-replicas/{file_id}")
def create_distributed_replicas(file_id: str, replica_count: int = 2):
    return file_service.create_distributed_replicas(file_id, replica_count)

@app.post("/mark-node-offline/{node_id}")
def mark_node_offline(node_id: str):
    return node_service.mark_node_offline(node_id)

@app.post("/mark-node-online/{node_id}")
def mark_node_online(node_id: str):
    return node_service.mark_node_online(node_id)

@app.get("/node-impact/{node_id}")
def get_node_impact(node_id: str):
    return node_service.get_node_impact(node_id)

@app.post("/rebuild-from-distributed-chunks/{file_id}")
def rebuild_from_distributed_chunks(file_id: str):
    return file_service.rebuild_from_distributed_chunks(file_id)

@app.post("/decrypt-distributed-file/{file_id}")
def decrypt_distributed_file(file_id: str):
    return file_service.decrypt_distributed_file(file_id)

@app.get("/distributed-download/{file_id}")
def distributed_download(file_id: str):
    return file_service.distributed_download(file_id)

@app.post("/verify-chunk/{chunk_id}")
def verify_chunk(chunk_id: str):
    return file_service.verify_chunk(chunk_id)

@app.post("/verify-file/{file_id}")
def verify_file(file_id: str):
    return file_service.verify_file(file_id)

@app.post("/self-heal/{file_id}")
def self_heal_file(file_id: str):
    return file_service.self_heal_file(file_id)

@app.post("/rebuild-corrupt-chunk/{file_id}/{chunk_id}")
def rebuild_corrupt_chunk(file_id: str, chunk_id: str):
    return file_service.rebuild_corrupt_chunk(file_id, chunk_id)

@app.post("/materialize-replicas/{file_id}")
def materialize_replicas(file_id: str):
    return file_service.materialize_replicas(file_id)

@app.post("/restore-corrupted-chunk/{file_id}/{chunk_id}")
def restore_corrupted_chunk(file_id:str,chunk_id:str):
    return file_service.restore_corrupted_chunk(file_id,chunk_id)

@app.post("/rebuild-file/{file_id}")
def rebuild_file(file_id: str):
    return file_service.rebuild_file(file_id)

@app.post("/integrity-scan/{file_id}")
def integrity_scan(file_id: str):
    return file_service.integrity_scan(file_id)

@app.post("/auto-heal-file/{file_id}")
def auto_heal_file(file_id: str):
    return file_service.auto_heal_file(file_id)

@app.post("/simulate-node-failure/{node_id}")
def simulate_node_failure(node_id: str):
    return node_service.simulate_node_failure(node_id)

@app.post("/automatic-failover/{node_id}")
def automatic_failover(node_id: str):
    return node_service.automatic_failover(node_id)

@app.get("/system-health")
def system_health():
    return node_service.system_health()

@app.get("/storage-report")
def storage_report():
    return file_service.storage_report()

@app.get("/network-summary")
def network_summary():
    return node_service.network_summary()

@app.post("/store-chunk")
def store_chunk(request: StoreChunkRequest):
    return file_service.store_chunk(request)

@app.post("/download-chunk/{chunk_id}")
def download_chunk(chunk_id: str):
    return file_service.download_chunk(chunk_id)

@app.post("/roundtrip-chunk-test")
def roundtrip_chunk_test(request: RoundtripChunkTestRequest):
    return file_service.roundtrip_chunk_test(request)

@app.get("/chunk-audit/{chunk_id}")
def chunk_audit(chunk_id: str):
    return file_service.chunk_audit(chunk_id)

@app.post("/simulate-chunk-corruption/{chunk_id}")
def simulate_chunk_corruption(chunk_id: str):
    return file_service.simulate_chunk_corruption(chunk_id)

@app.post("/materialize-chunk-replica/{file_id}/{chunk_id}")
def materialize_chunk_replica(file_id: str, chunk_id: str):
    return file_service.materialize_chunk_replica(file_id, chunk_id)

@app.post("/materialize-replicas-v2/{file_id}")
def materialize_replicas_v2(file_id: str):
    return file_service.materialize_replicas_v2(file_id)

@app.get("/node-report/{node_id}")
def node_report(node_id: str):
    return node_service.node_report(node_id)

@app.get("/file-report/{file_id}")
def file_report(file_id: str):
    return file_service.file_report(file_id)

@app.get("/storage-summary")
def storage_summary():
    return file_service.storage_summary()

@app.get("/replica-location/{chunk_id}")
def replica_location(chunk_id:str):
    return file_service.replica_location(chunk_id)

@app.get("/node-storage/{node_id}")
def node_storage(node_id:str):
    return node_service.node_storage(node_id)

@app.get("/replica-report/{file_id}")
def replica_report(file_id:str):
    return file_service.replica_report(file_id)

@app.get("/chunk-count")
def chunk_count():
    return file_service.chunk_count()

@app.get("/file-list/{file_id}")
def file_list(file_id: str):
    return file_service.file_list(file_id)

@app.get("/node-health-events")
def node_health_events():
    return node_service.node_health_events()

@app.get("/recovery-events")
def recovery_events():
    return file_service.recovery_events()

@app.get("/integrity-events")
def integrity_events():
    return file_service.integrity_events()

@app.get("/replica-health/{file_id}")
def replica_health(file_id:str):
    return file_service.replica_health(file_id)

@app.get("/allocation-report")
def allocation_report():
    return file_service.allocation_report()

@app.get("/capacity-report")
def capacity_report():
    return node_service.capacity_report()

@app.get("/cluster-summary")
def cluster_summary():
    return node_service.cluster_summary()
