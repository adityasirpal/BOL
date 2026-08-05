from pydantic import BaseModel


class Node(BaseModel):
    node_id: str
    country: str
    storage_gb: int
    status: str


class Heartbeat(BaseModel):
    node_id: str
    status: str


class StorageRequest(BaseModel):
    file_size_gb: int


class FileRecord(BaseModel):
    filename: str
    file_size_gb: int
