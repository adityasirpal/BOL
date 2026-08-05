import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_NAME = os.path.join(BASE_DIR, "bol_nodes.db")

UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
CHUNK_DIR = os.path.join(BASE_DIR, "stored_chunks")
DECRYPTED_DIR = os.path.join(BASE_DIR, "decrypted_files")
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
PRIMARY_CHUNK_DIR = "stored_chunks/primary"
REPLICA_CHUNK_DIR = "stored_chunks/replicas"
INCOMING_UPLOAD_DIR = "uploads/incoming"
REBUILT_DOWNLOAD_DIR = "downloads/rebuilt"
TEMP_DIR = "temp"
