import uuid
import os
import hashlib
import shutil
import base64

from cryptography.fernet import Fernet
from datetime import datetime, timezone
from config import UPLOAD_DIR, CHUNK_DIR, DOWNLOAD_DIR, DECRYPTED_DIR, INCOMING_UPLOAD_DIR, PRIMARY_CHUNK_DIR
from fastapi.responses import FileResponse
from services.chunk_service import ChunkService
from services.primary_storage_service import create_primary_storage_record
from services.upload_service import UploadService

class FileService:
    def __init__(self, conn, cursor, node_service=None):
        self.conn = conn
        self.cursor = cursor
        self.node_service = node_service
        self.chunk_service = ChunkService()
        self.upload_service = UploadService()

    def split_uploaded_file(self, file_path: str):

        return self.chunl_service.split_file(
            input_file=file_path,
            output_directory="stored_chunks/primary"
        )

    async def upload_file(self, file):
        created_at = datetime.now(timezone.utc).isoformat()
        chunks = []

        try:
            # UploadService owns incoming filesystem persistence.
            upload_result = await self.upload_service.save_incoming_upload(
                file=file,
                incoming_upload_dir=INCOMING_UPLOAD_DIR,
            )

            file_id = upload_result["upload_id"]
            original_filename = upload_result["original_filename"]
            original_file_path = upload_result["original_file_path"]
            file_size_bytes = upload_result["file_size_bytes"]
            file_size_gb = round(file_size_bytes / (1024 ** 3), 9)

            # ChunkService still owns chunk-output directory usage.
            os.makedirs(PRIMARY_CHUNK_DIR, exist_ok=True)

            # Create the file metadata record.
            self.upload_service.create_file_metadata(
                cursor=self.cursor,
                file_id=file_id,
                filename=original_filename,
                file_size_gb=file_size_gb,
                created_at=created_at,
            )
            # ChunkService owns all binary chunk creation and hashing.
            chunks = self.chunk_service.split_file(
                input_file=original_file_path,
                output_directory=PRIMARY_CHUNK_DIR
            )

            # FileService owns PostgreSQL metadata.
            if self.node_service is None:
                raise RuntimeError("NodeService is unavailable")

            # UploadService owns physical chunk metadata.
            self.upload_service.create_physical_chunk_metadata(
                cursor=self.cursor,
                file_id=file_id,
                chunks=chunks,
                created_at=created_at,
            )

            # Create one primary-storage record for every physical chunk.
            for chunk in chunks:
                best_node = self.node_service.select_best_node()

                if not best_node:
                    raise RuntimeError("No online node available")

                create_primary_storage_record(
                    self.cursor,
                    file_id=file_id,
                    chunk_id=chunk["chunk_id"],
                    node_id=best_node["node_id"],
                    chunk_path=chunk["chunk_path"],
                    chunk_size_bytes=chunk["size_bytes"],
                    created_at=created_at,
                )

            self.conn.commit()

            return {
                "success": True,
                "file_id": file_id,
                "filename": original_filename,
                "original_file_path": original_file_path,
                "file_size_bytes": file_size_bytes,
                "total_chunks": len(chunks),
                "chunks": chunks,
            }

        except Exception as exc:
            self.conn.rollback()

            # Remove chunk files created during a failed transaction.
            for chunk in chunks:
                chunk_path = chunk.get("chunk_path")

                if chunk_path and os.path.exists(chunk_path):
                    os.remove(chunk_path)

            # Remove the incoming upload when the workflow fails.
            if os.path.exists(original_file_path):
                os.remove(original_file_path)

            return {
                "success": False,
                "message": "Upload and chunk workflow failed",
                "error": str(exc)
            }

    def get_physical_chunks(self, file_id):
        self.cursor.execute("""
            SELECT chunk_id, file_id, chunk_number, chunk_path,
                   chunk_size_bytes, checksum, created_at
            FROM physical_chunks
            WHERE file_id = %s
            ORDER BY chunk_number
        """, (file_id,))

        rows = self.cursor.fetchall()

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

    def download_file(self, file_id):
        self.cursor.execute("""
            SELECT filename
            FROM files
            WHERE file_id = %s
        """, (file_id,))

        file_row = self.cursor.fetchone()

        if not file_row:
            return {
                "success": False,
                "message": "File not found"
            }

        original_filename = file_row[0]

        self.cursor.execute("""
            SELECT chunk_path, checksum
            FROM physical_chunks
            WHERE file_id = %s
            ORDER BY chunk_number
        """, (file_id,))

        chunks = self.cursor.fetchall()

        if not chunks:
            return {
                "success": False,
                "message": "No physical chunks found for this file"
            }

        reconstructed_path = os.path.join(
            DOWNLOAD_DIR,
            "reconstructed_" + original_filename
        )
        chunk_records = [
            {
                "chunk_path": row[0],
                "checksum": row[1]
            }
            for row in chunks
        ]

        rebuild_result = self.chunk_service.rebuild_file(
            chunks=chunk_records,
            output_path=reconstructed_path
        )

        if not rebuild_result["success"]:
            return {
                "success": False,
                "message": rebuild_result.get(
                "message",
                "File reconstruction failed"
                ),
                "error": rebuild_result.get("error")
            }
        return FileResponse(
            path=reconstructed_path,
            filename=original_filename,
            media_type="application/octet-stream"
        )

    def recover_file(self, file_id):
        self.cursor.execute(
            """
            SELECT filename
            FROM files
            WHERE file_id = %s
            """,
            (file_id,),
        )

        file_row = self.cursor.fetchone()

        if not file_row:
            return {
                "success": False,
                "message": "File not found",
            }

        original_filename = file_row[0]

        self.cursor.execute(
            """
            SELECT
                dcs.chunk_id,
                dcs.node_id,
                dcs.chunk_path,
                pc.checksum
            FROM distributed_chunk_storage dcs
            JOIN physical_chunks pc
                ON dcs.chunk_id = pc.chunk_id
            WHERE dcs.file_id = %s
              AND dcs.storage_type = 'primary'
              AND dcs.status = 'stored'
            ORDER BY pc.chunk_number
            """,
            (file_id,),
        )

        chunks = self.cursor.fetchall()

        if not chunks:
            return {
                "success": False,
                "message": "No distributed primary chunks found for this file",
            }

        recovered_path = os.path.join(
            DOWNLOAD_DIR,
            "recovered_" + original_filename,
        )

        chunk_records = [
            {
                "chunk_path": row[2],
                "checksum": row[3],
            }
            for row in chunks
        ]

        rebuild_result = self.chunk_service.rebuild_file(
            chunks=chunk_records,
            output_path=recovered_path,
        )

        if not rebuild_result["success"]:
            return rebuild_result

        return FileResponse(
            path=recovered_path,
            filename="recovered_" + original_filename,
            media_type="application/octet-stream",
        )

    def generate_checksums(self, file_id):
        self.cursor.execute("""
            SELECT chunk_id, chunk_path
            FROM physical_chunks
            WHERE file_id = %s
            ORDER BY chunk_number
        """, (file_id,))

        chunks = self.cursor.fetchall()

        if not chunks:
            return {
                "success": False,
                "message": "No physical chunks found for this file"
            }

        verified_at = datetime.now(timezone.utc).isoformat()
        checksum_records = []

        for chunk in chunks:
            chunk_id = chunk[0]
            chunk_path = chunk[1]

            if not os.path.exists(chunk_path):
                checksum_records.append({
                    "chunk_id": chunk_id,
                    "status": "missing_chunk_file"
                })
                continue

            with open(chunk_path, "rb") as f:
                chunk_data = f.read()

            sha256_hash = hashlib.sha256(chunk_data).hexdigest()
            integrity_id = "INTEGRITY-" + str(uuid.uuid4())

            self.cursor.execute("""
                INSERT INTO chunk_integrity
                (integrity_id, file_id, chunk_id, sha256_hash, verified_at, status)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                integrity_id,
                file_id,
                chunk_id,
                sha256_hash,
                verified_at,
                "checksum_generated"
            ))

            checksum_records.append({
                "integrity_id": integrity_id,
                "chunk_id": chunk_id,
                "sha256_hash": sha256_hash,
                "status": "checksum_generated"
            })

        self.conn.commit()

        return {
            "success": True,
            "file_id": file_id,
            "chunks_processed": len(chunks),
            "checksums_created": len(checksum_records),
            "checksums": checksum_records
        }

    def get_chunk_integrity(self, file_id):
        self.cursor.execute("""
            SELECT integrity_id, file_id, chunk_id,
                   sha256_hash, verified_at, status
            FROM chunk_integrity
            WHERE file_id = %s
        """, (file_id,))

        rows = self.cursor.fetchall()

        records = []

        for row in rows:
            records.append({
                "integrity_id": row[0],
                "file_id": row[1],
                "chunk_id": row[2],
                "sha256_hash": row[3],
                "verified_at": row[4],
                "status": row[5]
            })

        return {
            "file_id": file_id,
            "total_integrity_records": len(records),
            "integrity_records": records
        }

    def verify_file_old(self, file_id):
        self.cursor.execute("""
            SELECT pc.chunk_id, pc.chunk_path, ci.sha256_hash
            FROM physical_chunks pc
            JOIN chunk_integrity ci
                ON pc.chunk_id = ci.chunk_id
            WHERE pc.file_id = %s
        """, (file_id,))

        rows = self.cursor.fetchall()

        if not rows:
            return {
                "success": False,
                "message": "No checksum records found. Run /generate-checksums first."
            }

        verified_at = datetime.now(timezone.utc).isoformat()

        healthy_chunks = []
        corrupted_chunks = []
        missing_chunks = []

        for row in rows:
            chunk_id = row[0]
            chunk_path = row[1]
            expected_hash = row[2]

            if not os.path.exists(chunk_path):
                missing_chunks.append(chunk_id)
                continue

            with open(chunk_path, "rb") as f:
                chunk_data = f.read()

            actual_hash = hashlib.sha256(chunk_data).hexdigest()

            if actual_hash == expected_hash:
                healthy_chunks.append(chunk_id)
            else:
                corrupted_chunks.append({
                    "chunk_id": chunk_id,
                    "expected_hash": expected_hash,
                    "actual_hash": actual_hash
                })

        if corrupted_chunks or missing_chunks:
            status = "unhealthy"
        else:
            status = "healthy"

        return {
            "success": True,
            "file_id": file_id,
            "verified_at": verified_at,
            "total_checked": len(rows),
            "healthy_chunks": len(healthy_chunks),
            "corrupted_chunks": len(corrupted_chunks),
            "missing_chunks": len(missing_chunks),
            "status": status,
            "corrupted_details": corrupted_chunks,
            "missing_details": missing_chunks
        }

    async def encrypt_upload_and_chunk_file(self, file):
        file_id = "FILE-" + str(uuid.uuid4())
        encryption_id = "ENC-" + str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()

        file_content = await file.read()
        original_size_bytes = len(file_content)
        file_size_gb = round(original_size_bytes / (1024 * 1024 * 1024), 6)

        key = Fernet.generate_key()
        cipher = Fernet(key)

        encrypted_data = cipher.encrypt(file_content)

        encrypted_filename = file_id + "_" + file.filename + ".enc"
        encrypted_path = os.path.join(UPLOAD_DIR, encrypted_filename)

        with open(encrypted_path, "wb") as encrypted_file:
            encrypted_file.write(encrypted_data)

        self.cursor.execute("""
            INSERT INTO files
            (file_id, filename, file_size_gb, created_at, status)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            file_id,
            file.filename,
            file_size_gb,
            created_at,
            "encrypted_uploaded_and_chunked"
        ))

        self.cursor.execute("""
            INSERT INTO file_encryption
            (encryption_id, file_id, encryption_method, encryption_key,
             encrypted_file_path, encrypted_at, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            encryption_id,
            file_id,
            "FERNET",
            key.decode(),
            encrypted_path,
            created_at,
            "encrypted"
        ))

        chunk_size_bytes = 1024 * 25
        chunks = []
        chunk_number = 1

        for i in range(0, len(encrypted_data), chunk_size_bytes):
            chunk_data = encrypted_data[i:i + chunk_size_bytes]

            physical_chunk_id = "PHYS-" + str(uuid.uuid4())
            chunk_id = "PCHUNK-" + str(uuid.uuid4())

            chunk_filename = chunk_id + ".bin"
            chunk_path = os.path.join(CHUNK_DIR, chunk_filename)

            with open(chunk_path, "wb") as chunk_file:
                chunk_file.write(chunk_data)

            checksum = hashlib.sha256(chunk_data).hexdigest()

            self.cursor.execute("""
                INSERT INTO physical_chunks
                (physical_chunk_id, file_id, chunk_id, chunk_number, chunk_path,
                 chunk_size_bytes, checksum, created_at, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                physical_chunk_id,
                file_id,
		chunk_id,
                chunk_number,
                chunk_path,
                len(chunk_data),
                checksum,
                created_at,
		"stored"
            ))

            chunks.append({
                "chunk_id": chunk_id,
                "chunk_number": chunk_number,
                "chunk_path": chunk_path,
                "chunk_size_bytes": len(chunk_data),
                "checksum": checksum
            })

            chunk_number += 1

        self.conn.commit()

        return {
            "success": True,
            "file_id": file_id,
            "encryption_id": encryption_id,
            "filename": file.filename,
            "original_size_bytes": original_size_bytes,
            "encrypted_size_bytes": len(encrypted_data),
            "total_chunks": len(chunks),
            "status": "encrypted_uploaded_and_chunked",
            "chunks": chunks
        }

    def get_file_encryption(self, file_id):
        self.cursor.execute("""
            SELECT encryption_id,
                   file_id,
                   encryption_method,
                   encrypted_file_path,
                   encrypted_at,
                   status
            FROM file_encryption
            WHERE file_id = %s
        """, (file_id,))

        row = self.cursor.fetchone()

        if not row:
            return {
                "success": False,
                "message": "No encryption record found"
            }

        return {
            "encryption_id": row[0],
            "file_id": row[1],
            "encryption_method": row[2],
            "encrypted_file_path": row[3],
            "encrypted_at": row[4],
            "status": row[5]
        }

    def rebuild_encrypted_file(self, file_id):
        self.cursor.execute("""
            SELECT filename
            FROM files
            WHERE file_id = %s
        """, (file_id,))

        file_row = self.cursor.fetchone()

        if not file_row:
            return {
                "success": False,
                "message": "File not found"
            }

        original_filename = file_row[0]

        self.cursor.execute("""
            SELECT chunk_path, checksum
            FROM physical_chunks
            WHERE file_id = %s
            ORDER BY chunk_number
        """, (file_id,))

        chunks = self.cursor.fetchall()

        if not chunks:
            return {
                "success": False,
                "message": "No chunks found for this file"
            }

        rebuilt_encrypted_path = os.path.join(
            DOWNLOAD_DIR,
            "rebuilt_encrypted_" + file_id + "_" + original_filename + ".enc"
        )

        with open(rebuilt_encrypted_path, "wb") as output_file:

            for chunk in chunks:

                chunk_path = chunk[0]
                expected_checksum = chunk[1]

                if not os.path.exists(chunk_path):
                    return {
                        "success": False,
                        "message": "Missing chunk file",
                        "missing_chunk_path": chunk_path
                    }

                with open(chunk_path, "rb") as chunk_file:
                    chunk_data = chunk_file.read()

                actual_checksum = hashlib.sha256(chunk_data).hexdigest()

                if actual_checksum != expected_checksum:
                    return {
                        "success": False,
                        "message": "Checksum mismatch",
                        "chunk_path": chunk_path,
                        "expected_checksum": expected_checksum,
                        "actual_checksum": actual_checksum
                    }

                output_file.write(chunk_data)

        return {
            "success": True,
            "file_id": file_id,
            "rebuilt_encrypted_path": rebuilt_encrypted_path,
            "chunks_used": len(chunks),
            "status": "encrypted_file_rebuilt"
        }

    def decrypt_file(self, file_id):
        self.cursor.execute("""
            SELECT filename
            FROM files
            WHERE file_id = %s
        """, (file_id,))

        file_row = self.cursor.fetchone()

        if not file_row:
            return {
                "success": False,
                "message": "File not found"
            }

        original_filename = file_row[0]

        self.cursor.execute("""
            SELECT encryption_key
            FROM file_encryption
            WHERE file_id = %s
        """, (file_id,))

        encryption_row = self.cursor.fetchone()

        if not encryption_row:
            return {
                "success": False,
                "message": "Encryption key not found"
            }

        encryption_key = encryption_row[0].encode()
        cipher = Fernet(encryption_key)

        rebuilt_encrypted_path = os.path.join(
            DOWNLOAD_DIR,
            "rebuilt_encrypted_" + file_id + "_" + original_filename + ".enc"
        )

        if not os.path.exists(rebuilt_encrypted_path):
            return {
                "success": False,
                "message": "Rebuilt encrypted file not found. Run /rebuild-encrypted-file first.",
                "expected_path": rebuilt_encrypted_path
            }

        with open(rebuilt_encrypted_path, "rb") as encrypted_file:
            encrypted_data = encrypted_file.read()

        try:
            decrypted_data = cipher.decrypt(encrypted_data)
        except Exception as e:
            return {
                "success": False,
                "message": "Decryption failed",
                "error": str(e)
            }

        decrypted_path = os.path.join(
            DECRYPTED_DIR,
            "decrypted_" + file_id + "_" + original_filename
        )

        with open(decrypted_path, "wb") as decrypted_file:
            decrypted_file.write(decrypted_data)

        return {
            "success": True,
            "file_id": file_id,
            "decrypted_path": decrypted_path,
            "status": "decrypted"
        }

    def download_decrypted_file(self, file_id):
        self.cursor.execute("""
            SELECT filename
            FROM files
            WHERE file_id = %s
        """, (file_id,))

        file_row = self.cursor.fetchone()

        if not file_row:
            return {
                "success": False,
                "message": "File not found"
            }

        original_filename = file_row[0]

        decrypted_path = os.path.join(
            DECRYPTED_DIR,
            "decrypted_" + file_id + "_" + original_filename
        )

        if not os.path.exists(decrypted_path):
            return {
                "success": False,
                "message": "Decrypted file not found. Run /decrypt-file first.",
                "expected_path": decrypted_path
            }

        return FileResponse(
            path=decrypted_path,
            filename=original_filename,
            media_type="application/octet-stream"
        )

    def smart_distribute_physical_chunks(self, file_id):
        created_at = datetime.now(timezone.utc).isoformat()

        self.cursor.execute("""
            SELECT chunk_id, chunk_path, chunk_size_bytes
            FROM physical_chunks
            WHERE file_id = %s
            ORDER BY chunk_number
        """, (file_id,))

        chunks = self.cursor.fetchall()

        if not chunks:
            return {
                "success": False,
                "message": "No physical chunks found for this file"
            }

        distributed_records = []

        for chunk in chunks:

            chunk_id = chunk[0]
            chunk_path = chunk[1]
            chunk_size_bytes = chunk[2]

            chunk_size_gb = chunk_size_bytes / (1024 * 1024 * 1024)

            best_node = self.node_service.select_best_node()

            if not best_node:
                return {
                    "success": False,
                    "message": "No online node available"
                }

            selected_node = best_node["node_id"]

            storage_id = create_primary_storage_record(
                self.cursor,
                file_id=file_id,
                chunk_id=chunk_id,
                node_id=selected_node,
                chunk_path=chunk_path,
                chunk_size_bytes=chunk_size_bytes,
                created_at=created_at,
            )

            self.cursor.execute("""
                UPDATE node_storage_usage
                SET used_storage_gb = used_storage_gb + %s,
                    available_storage_gb = available_storage_gb - %s,
                    last_updated = %s
                WHERE node_id = %s
            """, (
                chunk_size_gb,
                chunk_size_gb,
                created_at,
                selected_node
            ))

            distributed_records.append({
                "storage_id": storage_id,
                "chunk_id": chunk_id,
                "node_id": selected_node,
                "chunk_size_bytes": chunk_size_bytes,
                "storage_type": "primary",
                "status": "stored"
            })

        self.conn.commit()

        return {
            "success": True,
            "file_id": file_id,
            "total_chunks_distributed": len(distributed_records),
            "distribution_method": "best_available_storage",
            "distributed_chunks": distributed_records
        }

    def create_distributed_replicas(self, file_id, replica_count=2):
        created_at = datetime.now(timezone.utc).isoformat()

        self.cursor.execute("""
            SELECT chunk_id, node_id, chunk_path, chunk_size_bytes
            FROM distributed_chunk_storage
            WHERE file_id = %s
              AND storage_type = 'primary'
              AND status = 'stored'
        """, (file_id,))

        primary_chunks = self.cursor.fetchall()

        if not primary_chunks:
            return {
                "success": False,
                "message": "No distributed primary chunks found for this file"
            }

        replica_records = []

        for chunk in primary_chunks:
            chunk_id = chunk[0]
            primary_node_id = chunk[1]
            chunk_path = chunk[2]
            chunk_size_bytes = chunk[3]
            chunk_size_gb = chunk_size_bytes / (1024 * 1024 * 1024)

            replica_nodes = self.node_service.select_replica_nodes(
                primary_node_id,
                replica_count
            )

            if not replica_nodes:
                replica_records.append({
                    "chunk_id": chunk_id,
                    "primary_node_id": primary_node_id,
                    "status": "no_replica_nodes_available"
                })
                continue

            replica_number = 1

            for replica_node in replica_nodes:
                replica_node_id = replica_node["node_id"]
                replica_id = "DREPLICA-" + str(uuid.uuid4())

                self.cursor.execute("""
                    INSERT INTO distributed_chunk_replicas
                    (replica_id, file_id, chunk_id, primary_node_id,
                     replica_node_id, chunk_path, chunk_size_bytes,
                     replica_number, status, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    replica_id,
                    file_id,
                    chunk_id,
                    primary_node_id,
                    replica_node_id,
                    chunk_path,
                    chunk_size_bytes,
                    replica_number,
                    "replicated",
                    created_at
                ))

                self.cursor.execute("""
                    UPDATE node_storage_usage
                    SET used_storage_gb = used_storage_gb + %s,
                        available_storage_gb = available_storage_gb - %s,
                        last_updated = %s
                    WHERE node_id = %s
                """, (
                    chunk_size_gb,
                    chunk_size_gb,
                    created_at,
                    replica_node_id
                ))

                replica_records.append({
                    "replica_id": replica_id,
                    "file_id": file_id,
                    "chunk_id": chunk_id,
                    "primary_node_id": primary_node_id,
                    "replica_node_id": replica_node_id,
                    "replica_number": replica_number,
                    "status": "replicated"
                })

                replica_number += 1

        self.conn.commit()

        return {
            "success": True,
            "file_id": file_id,
            "replica_count_requested": replica_count,
            "primary_chunks_found": len(primary_chunks),
            "replicas_created": len(replica_records),
            "replicas": replica_records
        }

    def get_recovery_events(self):

        self.cursor.execute("""
            SELECT recovery_id,
                   file_id,
                   chunk_id,
                   failed_node_id,
                   promoted_node_id,
                   recovery_action,
                   status,
                   created_at
            FROM recovery_events
            ORDER BY created_at DESC
        """)

        rows = self.cursor.fetchall()

        events = []

        for row in rows:
            events.append({
                "recovery_id": row[0],
                "file_id": row[1],
                "chunk_id": row[2],
                "failed_node_id": row[3],
                "promoted_node_id": row[4],
                "recovery_action": row[5],
                "status": row[6],
                "created_at": row[7]
            })

        return {
            "total_recovery_events": len(events),
            "recovery_events": events
        }

    def rebuild_from_distributed_chunks(self, file_id):

        self.cursor.execute("""
            SELECT filename
            FROM files
            WHERE file_id = %s
        """, (file_id,))

        row = self.cursor.fetchone()

        if not row:
            return {
                "success": False,
                "message": "File not found"
            }

        filename = row[0]

        self.cursor.execute("""
        SELECT
            dcs.chunk_path,
            dcs.chunk_id
        FROM distributed_chunk_storage dcs
        JOIN physical_chunks pc
            ON pc.chunk_id = dcs.chunk_id
        WHERE dcs.file_id = %s
          AND dcs.storage_type = 'primary'
          AND dcs.status = 'stored'
        ORDER BY pc.chunk_number
    """, (file_id,))

        chunks = self.cursor.fetchall()

        if not chunks:
            return {
                "success": False,
                "message": "No distributed chunks found"
            }

        rebuilt_path = os.path.join(
            DOWNLOAD_DIR,
            "rebuilt_distributed_" + filename
        )

        with open(rebuilt_path, "wb") as output_file:

            for chunk in chunks:

                chunk_path = chunk[0]

                if not os.path.exists(chunk_path):
                    return {
                        "success": False,
                        "missing_chunk": chunk[1],
                        "missing_path": chunk_path
                    }

                with open(chunk_path, "rb") as chunk_file:
                    output_file.write(chunk_file.read())

        return {
            "success": True,
            "file_id": file_id,
            "rebuilt_file": rebuilt_path,
            "chunks_used": len(chunks),
            "status": "rebuilt_from_distributed_chunks"
        }

    def decrypt_distributed_file(self, file_id):
        self.cursor.execute("""
            SELECT filename
            FROM files
            WHERE file_id = %s
        """, (file_id,))

        file_row = self.cursor.fetchone()

        if not file_row:
            return {
                "success": False,
                "message": "File not found"
            }

        original_filename = file_row[0]

        self.cursor.execute("""
            SELECT encryption_key
            FROM file_encryption
            WHERE file_id = %s
        """, (file_id,))

        encryption_row = self.cursor.fetchone()

        if not encryption_row:
            return {
                "success": False,
                "message": "Encryption key not found"
            }

        encryption_key = encryption_row[0].encode()
        cipher = Fernet(encryption_key)

        rebuilt_encrypted_path = os.path.join(
            DOWNLOAD_DIR,
            "rebuilt_distributed_" + original_filename
        )

        if not os.path.exists(rebuilt_encrypted_path):
            return {
                "success": False,
                "message": "Rebuilt distributed encrypted file not found. Run /rebuild-from-distributed-chunks first.",
                "expected_path": rebuilt_encrypted_path
            }

        with open(rebuilt_encrypted_path, "rb") as encrypted_file:
            encrypted_data = encrypted_file.read()

        try:
            decrypted_data = cipher.decrypt(encrypted_data)
        except Exception as e:
            return {
                "success": False,
                "message": "Decryption failed",
                "error": str(e)
            }

        decrypted_path = os.path.join(
            DECRYPTED_DIR,
            "distributed_decrypted_" + file_id + "_" + original_filename
        )

        with open(decrypted_path, "wb") as decrypted_file:
            decrypted_file.write(decrypted_data)

        return {
            "success": True,
            "file_id": file_id,
            "decrypted_path": decrypted_path,
            "status": "distributed_file_decrypted"
        }

    def distributed_download(self, file_id):
        self.cursor.execute("""
            SELECT filename
            FROM files
            WHERE file_id = %s
        """, (file_id,))

        row = self.cursor.fetchone()

        if not row:
            return {"success": False, "message": "File not found"}

        filename = row[0]

        decrypted_path = os.path.join(
            DECRYPTED_DIR,
            "distributed_decrypted_" + file_id + "_" + filename
        )

        if not os.path.exists(decrypted_path):
            return {
                "success": False,
                "message": "Distributed decrypted file not found. Run /decrypt-distributed-file first.",
                "expected_path": decrypted_path
            }

        return FileResponse(
            path=decrypted_path,
            filename=filename,
            media_type="application/octet-stream"
        )

    def get_distributed_chunks(self, file_id):
        self.cursor.execute("""
            SELECT storage_id,
                   file_id,
                   chunk_id,
                   node_id,
                   chunk_path,
                   chunk_size_bytes,
                   storage_type,
                   status,
                   created_at
            FROM distributed_chunk_storage
            WHERE file_id = %s
            ORDER BY created_at DESC
        """, (file_id,))

        rows = self.cursor.fetchall()

        records = []

        for row in rows:
            records.append({
                "storage_id": row[0],
                "file_id": row[1],
                "chunk_id": row[2],
                "node_id": row[3],
                "chunk_path": row[4],
                "chunk_size_bytes": row[5],
                "storage_type": row[6],
                "status": row[7],
                "created_at": row[8]
            })

        return {
            "file_id": file_id,
            "total_distributed_chunks": len(records),
            "distributed_chunks": records
        }

    def verify_chunk(self, chunk_id):
        self.cursor.execute("""
            SELECT chunk_id, chunk_path, checksum, file_id
            FROM physical_chunks
            WHERE chunk_id = %s
        """, (chunk_id,))

        row = self.cursor.fetchone()

        if not row:
            return {
                "success": False,
                "message": "Chunk not found",
                "chunk_id": chunk_id
            }

        chunk_id = row[0]
        chunk_path = row[1]
        expected_checksum = row[2]
        file_id = row[3]

        if not os.path.exists(chunk_path):
            return {
                "success": False,
                "chunk_id": chunk_id,
                "file_id": file_id,
                "status": "missing",
                "message": "Chunk file missing",
                "chunk_path": chunk_path
            }

        with open(chunk_path, "rb") as chunk_file:
            chunk_data = chunk_file.read()

        actual_checksum = hashlib.sha256(chunk_data).hexdigest()

        if actual_checksum == expected_checksum:
            status = "healthy"
        else:
            status = "corrupt"

        return {
            "success": True,
            "chunk_id": chunk_id,
            "file_id": file_id,
            "chunk_path": chunk_path,
            "expected_checksum": expected_checksum,
            "actual_checksum": actual_checksum,
            "status": status
        }

    def verify_file(self, file_id):
        self.cursor.execute("""
            SELECT chunk_id, chunk_path, checksum
            FROM physical_chunks
            WHERE file_id = %s
            ORDER BY chunk_number
        """, (file_id,))

        rows = self.cursor.fetchall()

        if not rows:
            return {
                "success": False,
                "message": "No chunks found for this file",
                "file_id": file_id
            }

        healthy_chunks = []
        corrupt_chunks = []
        missing_chunks = []

        for row in rows:
            chunk_id = row[0]
            chunk_path = row[1]
            expected_checksum = row[2]

            if not os.path.exists(chunk_path):
                missing_chunks.append({
                    "chunk_id": chunk_id,
                    "chunk_path": chunk_path
                })
                continue

            with open(chunk_path, "rb") as chunk_file:
                chunk_data = chunk_file.read()

            actual_checksum = hashlib.sha256(chunk_data).hexdigest()

            if actual_checksum == expected_checksum:
                healthy_chunks.append(chunk_id)
            else:
                corrupt_chunks.append({
                    "chunk_id": chunk_id,
                    "expected_checksum": expected_checksum,
                    "actual_checksum": actual_checksum
                })

        if corrupt_chunks or missing_chunks:
            status = "unhealthy"
        else:
            status = "healthy"

        return {
            "success": True,
            "file_id": file_id,
            "total_checked": len(rows),
            "healthy_chunks": len(healthy_chunks),
            "corrupt_chunks": len(corrupt_chunks),
            "missing_chunks": len(missing_chunks),
            "status": status,
            "corrupt_details": corrupt_chunks,
            "missing_details": missing_chunks
        }

    def self_heal_file(self, file_id):
        verify_result = self.verify_file(file_id)

        if not verify_result.get("success"):
            return verify_result

        if verify_result.get("status") == "healthy":
            return {
                "success": True,
                "file_id": file_id,
                "status": "healthy",
                "message": "No healing needed"
            }

        return {
            "success": True,
            "file_id": file_id,
            "status": "healing_required",
            "corrupt_chunks": verify_result.get("corrupt_details", []),
            "missing_chunks": verify_result.get("missing_details", []),
            "message": "Corrupt or missing chunks detected"
        }

    def rebuild_corrupt_chunk(self, file_id, chunk_id):
        self.cursor.execute("""
            SELECT chunk_path, checksum
            FROM physical_chunks
            WHERE file_id = %s
              AND chunk_id = %s
        """, (file_id, chunk_id))

        row = self.cursor.fetchone()

        if not row:
            return {
                "success": False,
                "message": "Physical chunk not found",
                "file_id": file_id,
                "chunk_id": chunk_id
            }

        chunk_path = row[0]
        expected_checksum = row[1]

        self.cursor.execute("""
            SELECT chunk_path
            FROM distributed_chunk_replicas
            WHERE file_id = %s
              AND chunk_id = %s
              AND status IN ('replicated', 'promoted_to_primary')
            ORDER BY replica_number ASC
            LIMIT 1
        """, (file_id, chunk_id))

        replica_row = self.cursor.fetchone()

        if not replica_row:
            return {
                "success": False,
                "message": "No healthy replica available to rebuild chunk",
                "file_id": file_id,
                "chunk_id": chunk_id
            }

        replica_path = replica_row[0]

        if not os.path.exists(replica_path):
            return {
                "success": False,
                "message": "Replica file path does not exist",
                "replica_path": replica_path
            }

        with open(replica_path, "rb") as replica_file:
            replica_data = replica_file.read()

        actual_checksum = hashlib.sha256(replica_data).hexdigest()

        if actual_checksum != expected_checksum:
            return {
                "success": False,
                "message": "Replica checksum does not match expected checksum",
                "expected_checksum": expected_checksum,
                "actual_checksum": actual_checksum
            }

        with open(chunk_path, "wb") as chunk_file:
            chunk_file.write(replica_data)

        return {
            "success": True,
            "file_id": file_id,
            "chunk_id": chunk_id,
            "rebuilt_chunk_path": chunk_path,
            "source_replica_path": replica_path,
            "status": "corrupt_chunk_rebuilt"
        }

    def materialize_replicas(self, file_id):
        self.cursor.execute("""
            SELECT replica_id,
                   chunk_id,
                   replica_node_id,
                   chunk_path,
                   replica_number,
                   status
            FROM distributed_chunk_replicas
            WHERE file_id = %s
            ORDER BY replica_number
        """, (file_id,))

        rows = self.cursor.fetchall()

        if not rows:
            return {
                "success": False,
                "message": "No replicas found",
                "file_id": file_id
            }

        replicas = []

        for row in rows:
            replicas.append({
                "replica_id": row[0],
                "chunk_id": row[1],
                "replica_node": row[2],
                "chunk_path": row[3],
                "replica_number": row[4],
                "status": row[5]
            })

        return {
            "success": True,
            "file_id": file_id,
            "replica_count": len(replicas),
            "replicas": replicas
        }

    def restore_corrupted_chunk(self, file_id, chunk_id):

        self.cursor.execute("""
            SELECT chunk_path
            FROM distributed_chunk_replicas
            WHERE file_id=%s
              AND chunk_id=%s
              AND status IN ('replicated','promoted_to_primary')
            ORDER BY replica_number
            LIMIT 1
        """,(file_id,chunk_id))

        row=self.cursor.fetchone()

        if not row:
            return {
                "success":False,
                "message":"No healthy replica found"
            }

        replica_path=row[0]

        self.cursor.execute("""
            SELECT chunk_path
            FROM physical_chunks
            WHERE file_id=%s
              AND chunk_id=%s
        """,(file_id,chunk_id))

        physical=self.cursor.fetchone()

        if not physical:
            return {
                "success":False,
                "message":"Physical chunk missing"
            }

        physical_path=physical[0]

        if os.path.abspath(replica_path) == os.path.abspath(physical_path):
            return {
                "success": True,
                "file_id": file_id,
                "chunk_id": chunk_id,
                "replica_source": replica_path,
                "restored_chunk": physical_path,
                "status": "already_restored",
                "message": "Replica and Physical Chunk path are the same; no copy needed."
            }

        shutil.copy2(replica_path,physical_path)

        return{
            "success":True,
            "file_id":file_id,
            "chunk_id":chunk_id,
            "replica_source":replica_path,
            "restored_chunk":physical_path,
            "status":"restored"
        }

    def integrity_scan(self, file_id):
        return self.verify_file(file_id)

    def auto_heal_file(self, file_id):
        scan = self.verify_file(file_id)

        if not scan.get("success"):
            return scan

        if scan.get("status") == "healthy":
            return {
                "success": True,
                "file_id": file_id,
                "status": "healthy",
                "message": "No healing needed"
            }

        healed_chunks = []

        for chunk in scan.get("corrupt_details", []):
            chunk_id = chunk["chunk_id"]
            heal_result = self.restore_corrupted_chunk(file_id, chunk_id)
            healed_chunks.append(heal_result)

        final_scan = self.verify_file(file_id)

        return {
            "success": True,
            "file_id": file_id,
            "initial_status": scan.get("status"),
            "healed_chunks": healed_chunks,
            "final_scan": final_scan,
            "status": final_scan.get("status")
        }

    def rebuild_file(self, file_id):
        return self.rebuild_from_distributed_chunks(file_id)

    def download_chunk(self, chunk_id):
        self.cursor.execute("""
            SELECT chunk_id, file_id, chunk_path, chunk_size_bytes, status
            FROM physical_chunks
            WHERE chunk_id = %s
        """, (chunk_id,))

        row = self.cursor.fetchone()

        if not row:
            return {
                "success": False,
                "message": "Chunk not found",
                "chunk_id": chunk_id
            }

        chunk_path = row[2]

        if not os.path.exists(chunk_path):
            return {
                "success": False,
                "message": "Chunk file missing on disk",
                "chunk_id": chunk_id,
                "chunk_path": chunk_path
            }

        return FileResponse(
            path=chunk_path,
            filename=row[0] + ".bin",
            media_type="application/octet-stream"
        )

    def store_chunk(self, request):
        created_at = datetime.now(timezone.utc).isoformat()

        chunk_path = os.path.join(
            CHUNK_DIR,
            request.chunk_id + ".bin"
        )

        chunk_data = request.data.encode()

        with open(chunk_path, "wb") as chunk_file:
            chunk_file.write(chunk_data)

        checksum = hashlib.sha256(chunk_data).hexdigest()
        chunk_size_bytes = len(chunk_data)

        physical_chunk_id = "PHYSICAL-" + str(uuid.uuid4())

        self.cursor.execute("""
            INSERT INTO physical_chunks
            (physical_chunk_id, file_id, chunk_id, chunk_number, chunk_path, chunk_size_bytes, checksum, created_at, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            physical_chunk_id,
            request.file_id,
            request.chunk_id,
            request.chunk_number,
            chunk_path,
            chunk_size_bytes,
            checksum,
            created_at,
            "stored"
        ))

        self.conn.commit()

        return {
            "success": True,
            "message": "Chunk stored successfully",
            "file_id": request.file_id,
            "chunk_id": request.chunk_id,
            "chunk_path": chunk_path,
            "chunk_size_bytes": chunk_size_bytes,
            "checksum": checksum,
            "physical_chunk_id": physical_chunk_id
        }

    def roundtrip_chunk_test(self, request):
        created_at = datetime.now(timezone.utc).isoformat()

        try:
            original_bytes = base64.b64decode(request.data)
        except Exception:
            return {
                "success": False,
                "message": "Invalid base64 data"
            }

        original_checksum = hashlib.sha256(original_bytes).hexdigest()

        self.cursor.execute("""
            SELECT node_id, status
            FROM nodes
            WHERE node_id = %s
        """, (request.node_id,))

        node = self.cursor.fetchone()

        if not node:
            return {
                "success": False,
                "message": "Node not found",
                "node_id": request.node_id
            }

        chunk_path = os.path.join(
            CHUNK_DIR,
            request.chunk_id + ".bin"
        )

        with open(chunk_path, "wb") as chunk_file:
            chunk_file.write(original_bytes)

        chunk_size_bytes = len(original_bytes)
        physical_chunk_id = "PHYSICAL-" + str(uuid.uuid4())

        self.cursor.execute("""
            INSERT INTO physical_chunks
            (physical_chunk_id, file_id, chunk_id, chunk_number, chunk_path, chunk_size_bytes, checksum, created_at, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            physical_chunk_id,
            request.file_id,
            request.chunk_id,
            request.chunk_number,
            chunk_path,
            chunk_size_bytes,
            original_checksum,
            created_at,
            "stored"
        ))

        self.conn.commit()

        with open(chunk_path, "rb") as chunk_file:
            downloaded_bytes = chunk_file.read()

        downloaded_checksum = hashlib.sha256(downloaded_bytes).hexdigest()

        return {
            "success": original_checksum == downloaded_checksum,
            "file_id": request.file_id,
            "chunk_id": request.chunk_id,
            "node_id": request.node_id,
            "chunk_path": chunk_path,
            "chunk_size_bytes": chunk_size_bytes,
            "original_checksum": original_checksum,
            "downloaded_checksum": downloaded_checksum,
            "status": "roundtrip_passed" if original_checksum == downloaded_checksum else "roundtrip_failed"
        }

    def chunk_audit(self, chunk_id):
        self.cursor.execute("""
            SELECT physical_chunk_id, file_id, chunk_id, chunk_number,
                   chunk_path, chunk_size_bytes, checksum, created_at, status
            FROM physical_chunks
            WHERE chunk_id = %s
            ORDER BY created_at DESC
            LIMIT 10
        """, (chunk_id,))

        rows = self.cursor.fetchall()

        audits = []
        for row in rows:
            audits.append({
                "physical_chunk_id": row[0],
                "file_id": row[1],
                "chunk_id": row[2],
                "chunk_number": row[3],
                "chunk_path": row[4],
                "chunk_size_bytes": row[5],
                "checksum": row[6],
                "created_at": row[7],
                "status": row[8]
            })

        return {
            "success": True,
            "chunk_id": chunk_id,
            "records_found": len(audits),
            "audit_records": audits
        }

    def simulate_chunk_corruption(self, chunk_id):
        self.cursor.execute("""
            SELECT physical_chunk_id, file_id, chunk_path, status
            FROM physical_chunks
            WHERE chunk_id = %s
            ORDER BY created_at DESC
            LIMIT 1
        """, (chunk_id,))

        row = self.cursor.fetchone()

        if not row:
            return {
                "success": False,
                "message": "Chunk not found",
                "chunk_id": chunk_id
            }

        physical_chunk_id = row[0]
        file_id = row[1]
        chunk_path = row[2]

        if not os.path.exists(chunk_path):
            return {
                "success": False,
                "message": "Chunk file missing on disk",
                "chunk_id": chunk_id,
                "chunk_path": chunk_path
            }

        with open(chunk_path, "ab") as chunk_file:
            chunk_file.write(b"CORRUPTED")

        self.cursor.execute("""
            UPDATE physical_chunks
            SET status = %s
            WHERE physical_chunk_id = %s
        """, ("corrupted", physical_chunk_id))

        self.conn.commit()

        return {
            "success": True,
            "file_id": file_id,
            "chunk_id": chunk_id,
            "physical_chunk_id": physical_chunk_id,
            "chunk_path": chunk_path,
            "status": "corrupted",
            "message": "Chunk corruption simulated successfully"
        }

    def materialize_chunk_replica(self, file_id, chunk_id):
        self.cursor.execute("""
            SELECT chunk_path, checksum
            FROM physical_chunks
            WHERE file_id = %s
              AND chunk_id = %s
            ORDER BY created_at DESC
            LIMIT 1
        """, (file_id, chunk_id))

        primary = self.cursor.fetchone()

        if not primary:
            return {
                "success": False,
                "message": "Primary chunk not found",
                "file_id": file_id,
                "chunk_id": chunk_id
            }

        source_path = primary[0]
        checksum = primary[1]

        if not os.path.exists(source_path):
            return {
                "success": False,
                "message": "Primary chunk file missing on disk",
                "chunk_path": source_path
            }

        replica_id = "MREPLICA-" + str(uuid.uuid4())
        replica_path = os.path.join(CHUNK_DIR, replica_id + ".bin")

        shutil.copy2(source_path, replica_path)

        return {
            "success": True,
            "file_id": file_id,
            "chunk_id": chunk_id,
            "replica_id": replica_id,
            "source_path": source_path,
            "replica_path": replica_path,
            "checksum": checksum,
            "status": "materialized"
        }

    def materialize_replicas_v2(self, file_id):
        self.cursor.execute("""
            SELECT DISTINCT chunk_id
            FROM physical_chunks
            WHERE file_id = %s
            ORDER BY chunk_id
        """, (file_id,))

        rows = self.cursor.fetchall()

        if not rows:
            return {
                "success": False,
                "message": "No chunks found for file",
                "file_id": file_id
            }

        results = []

        for row in rows:
            chunk_id = row[0]
            result = self.materialize_chunk_replica(file_id, chunk_id)
            results.append(result)

        return {
            "success": True,
            "file_id": file_id,
            "chunks_processed": len(results),
            "results": results,
            "status": "replicas_materialized_v2"
        }

    def storage_report(self):
        self.cursor.execute("""
            SELECT COUNT(*), COALESCE(SUM(chunk_size_bytes), 0)
            FROM physical_chunks
        """)
        physical_count, physical_bytes = self.cursor.fetchone()

        self.cursor.execute("""
            SELECT COUNT(*)
            FROM distributed_chunk_storage
        """)
        distributed_count = self.cursor.fetchone()[0]

        self.cursor.execute("""
            SELECT COUNT(*)
            FROM distributed_chunk_replicas
        """)
        replica_count = self.cursor.fetchone()[0]

        return {
            "success": True,
            "physical_chunks": physical_count,
            "physical_bytes": physical_bytes,
            "distributed_chunks": distributed_count,
            "distributed_replicas": replica_count,
            "status": "storage_report_ready"
        }

    def file_report(self, file_id):
        self.cursor.execute("""
            SELECT file_id, filename, status, created_at
            FROM files
            WHERE file_id = %s
        """, (file_id,))
        file = self.cursor.fetchone()

        if not file:
            return {"success": False, "message": "File not found", "file_id": file_id}

        self.cursor.execute("""
            SELECT COUNT(*)
            FROM physical_chunks
            WHERE file_id = %s
        """, (file_id,))
        physical_chunks = self.cursor.fetchone()[0]

        self.cursor.execute("""
            SELECT COUNT(*)
            FROM distributed_chunk_storage
            WHERE file_id = %s
        """, (file_id,))
        distributed_chunks = self.cursor.fetchone()[0]

        self.cursor.execute("""
            SELECT COUNT(*)
            FROM distributed_chunk_replicas
            WHERE file_id = %s
        """, (file_id,))
        replicas = self.cursor.fetchone()[0]

        return {
            "success": True,
            "file_id": file[0],
            "filename": file[1],
            "status": file[2],
            "created_at": file[3],
            "physical_chunks": physical_chunks,
            "distributed_chunks": distributed_chunks,
            "replicas": replicas
        }

    def rebuild_corrupt_chunk(self, file_id, chunk_id):
        return self.restore_corrupted_chunk(file_id, chunk_id)

    def storage_summary(self):
        self.cursor.execute("""
            SELECT
                COUNT(*) AS total_chunks,
                COALESCE(SUM(chunk_size_bytes),0) AS total_bytes
            FROM physical_chunks
        """)
        physical = self.cursor.fetchone()

        self.cursor.execute("""
            SELECT COUNT(*)
            FROM distributed_chunk_storage
        """)
        distributed = self.cursor.fetchone()[0]

        self.cursor.execute("""
            SELECT COUNT(*)
            FROM distributed_chunk_replicas
        """)
        replicas = self.cursor.fetchone()[0]

        return {
            "success": True,
            "physical_chunks": physical[0],
            "physical_bytes": physical[1],
            "distributed_chunks": distributed,
            "replicas": replicas
        }

    def chunk_location(self, chunk_id):
        self.cursor.execute("""
            SELECT
                chunk_id,
                node_id,
                storage_type,
                status,
                chunk_path
            FROM distributed_chunk_storage
            WHERE chunk_id=%s
            ORDER BY created_at DESC
        """,(chunk_id,))

        rows=self.cursor.fetchall()

        locations=[]

        for row in rows:
            locations.append({
                "chunk_id":row[0],
                "node_id":row[1],
                "storage_type":row[2],
                "status":row[3],
                "chunk_path":row[4]
            })

        return {
            "success":True,
            "chunk_id":chunk_id,
            "locations":locations
        }

    def replica_location(self, chunk_id):

        self.cursor.execute("""
            SELECT
                replica_id,
                replica_node_id,
                replica_number,
                status,
                chunk_path
            FROM distributed_chunk_replicas
            WHERE chunk_id=%s
            ORDER BY replica_number
        """,(chunk_id,))

        rows=self.cursor.fetchall()

        replicas=[]

        for row in rows:
            replicas.append({
                "replica_id":row[0],
                "replica_node":row[1],
                "replica_number":row[2],
                "status":row[3],
                "chunk_path":row[4]
            })

        return {
            "success":True,
            "chunk_id":chunk_id,
            "replicas":replicas
        }

    def replica_report(self,file_id):

        self.cursor.execute("""
            SELECT
                replica_id,
                chunk_id,
                replica_node_id,
                replica_number,
                status
            FROM distributed_chunk_replicas
            WHERE file_id=%s
            ORDER BY replica_number
        """,(file_id,))

        rows=self.cursor.fetchall()

        replicas=[]

        for row in rows:
            replicas.append({
                "replica_id":row[0],
                "chunk_id":row[1],
                "replica_node":row[2],
                "replica_number":row[3],
                "status":row[4]
            })

        return{
            "success":True,
            "file_id":file_id,
            "replicas":replicas
        }

    def chunk_count(self):

        self.cursor.execute("""
            SELECT COUNT(*)
            FROM physical_chunks
        """)

        physical=self.cursor.fetchone()[0]

        self.cursor.execute("""
            SELECT COUNT(*)
            FROM distributed_chunk_storage
        """)

        distributed=self.cursor.fetchone()[0]

        self.cursor.execute("""
            SELECT COUNT(*)
            FROM distributed_chunk_replicas
        """)

        replicas=self.cursor.fetchone()[0]

        return{
            "success":True,
            "physical_chunks":physical,
            "distributed_chunks":distributed,
            "replicas":replicas
        }

    def file_list(self, file_id):
        self.cursor.execute("""
            SELECT file_id, filename, status, created_at
            FROM files
            WHERE file_id = %s
        """, (file_id,))
        file = self.cursor.fetchone()

        if not file:
            return {"success": False, "message": "File not found", "file_id": file_id}

        return {
            "success": True,
            "file_id": file[0],
            "filename": file[1],
            "status": file[2],
            "created_at": file[3]
        }

    def recovery_events(self):
        self.cursor.execute("""
            SELECT recovery_id, file_id, chunk_id, failed_node_id,
                   promoted_node_id, recovery_action, status, created_at
            FROM recovery_events
            ORDER BY created_at DESC
            LIMIT 20
        """)
        rows = self.cursor.fetchall()

        events = []
        for row in rows:
            events.append({
                "recovery_id": row[0],
                "file_id": row[1],
                "chunk_id": row[2],
                "failed_node_id": row[3],
                "promoted_node_id": row[4],
                "recovery_action": row[5],
                "status": row[6],
                "created_at": row[7]
            })

        return {
            "success": True,
            "total_events": len(events),
            "recovery_events": events
        }

    def integrity_events(self):

        self.cursor.execute("""
            SELECT
                integrity_id,
                file_id,
                chunk_id,
                verification_status,
                created_at
            FROM integrity_events
            ORDER BY created_at DESC
            LIMIT 20
        """)

        rows = self.cursor.fetchall()

        events = []

        for row in rows:
            events.append({
                "integrity_id": row[0],
                "file_id": row[1],
                "chunk_id": row[2],
                "verification_status": row[3],
                "created_at": row[4]
            })

        return {
            "success": True,
            "total_events": len(events),
            "events": events
        }

    def physical_chunks(self, file_id):

        self.cursor.execute("""
            SELECT
                physical_chunk_id,
                chunk_id,
                chunk_number,
                chunk_path,
                chunk_size_bytes,
                status
            FROM physical_chunks
            WHERE file_id=%s
            ORDER BY chunk_number
        """,(file_id,))

        rows=self.cursor.fetchall()

        chunks=[]

        for row in rows:
            chunks.append({
                "physical_chunk_id":row[0],
                "chunk_id":row[1],
                "chunk_number":row[2],
                "chunk_path":row[3],
                "chunk_size_bytes":row[4],
                "status":row[5]
            })

        return{
            "success":True,
            "file_id":file_id,
            "physical_chunks":chunks
        }

    def replica_health(self, file_id: str):
        self.cursor.execute("""
            SELECT
                replication_id,
                file_id,
                chunk_id,
                primary_node_id,
                replica_node_id,
                status,
                created_at
            FROM file_replication
            WHERE file_id = %s
            ORDER BY chunk_id, replica_node_id
        """, (file_id,))

        rows = self.cursor.fetchall()

        replicas = []
        healthy = 0

        for row in rows:
            if row[5] in ("replicated", "promoted_to_primary"):
                healthy += 1

            replicas.append({
                "replication_id": row[0],
                "file_id": row[1],
                "chunk_id": row[2],
                "primary_node_id": row[3],
                "replica_node_id": row[4],
                "status": row[5],
                "created_at": str(row[6])
            })

        return {
            "success": True,
            "file_id": file_id,
            "healthy_replicas": healthy,
            "total_replicas": len(replicas),
            "replicas": replicas
        }

    def allocation_report(self):
        self.cursor.execute("""
            SELECT
                node_id,
                COUNT(*) AS chunks_stored,
                COALESCE(SUM(chunk_size_bytes), 0) AS total_bytes
            FROM distributed_chunk_storage
            GROUP BY node_id
            ORDER BY chunks_stored DESC
        """)

        rows = self.cursor.fetchall()

        report = []
        for row in rows:
            report.append({
                "node_id": row[0],
                "chunks_stored": row[1],
                "total_bytes": row[2]
            })

        return {
            "success": True,
            "nodes_reported": len(report),
            "allocation_report": report
        }

    def get_replicas(self, file_id: str):
        self.cursor.execute("""
            SELECT replica_id, file_id, node_id, replica_number, created_at, status
            FROM file_replicas
            WHERE file_id = %s
            ORDER BY replica_number
        """, (file_id,))

        rows = self.cursor.fetchall()

        replicas = []
        for row in rows:
            replicas.append({
                "replica_id": row[0],
                "file_id": row[1],
                "node_id": row[2],
                "replica_number": row[3],
                "created_at": row[4],
                "status": row[5]
            })

        return {
            "success": True,
            "file_id": file_id,
            "total_replicas": len(replicas),
            "replicas": replicas
        }


    def create_chunks(self, file_id: str):
        self.cursor.execute("""
            SELECT node_id
            FROM file_replicas
            WHERE file_id = %s
            ORDER BY replica_number
        """, (file_id,))

        replicas = self.cursor.fetchall()

        if not replicas:
            return {
                "success": False,
                "message": "No replicas found"
            }

        created_chunks = []

        for replica in replicas:
            node_id = replica[0]

            for chunk_num in range(1, 5):
                chunk_id = "CHUNK-" + str(uuid.uuid4())
                created_at = datetime.now(timezone.utc).isoformat()

                self.cursor.execute("""
                    INSERT INTO chunks
                    (chunk_id, file_id, node_id, chunk_number, chunk_size_gb, status, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    chunk_id,
                    file_id,
                    node_id,
                    chunk_num,
                    12.5,
                    "planned",
                    created_at
                ))

                created_chunks.append({
                    "chunk_id": chunk_id,
                    "file_id": file_id,
                    "node_id": node_id,
                    "chunk_number": chunk_num,
                    "chunk_size_gb": 12.5,
                    "status": "planned",
                    "created_at": created_at
                })

        self.conn.commit()

        return {
            "success": True,
            "file_id": file_id,
            "total_chunks": len(created_chunks),
            "chunks": created_chunks
        }

    def get_chunks(self, file_id: str):
        self.cursor.execute(
            """
            SELECT chunk_id,
                   file_id,
                   node_id,
                   chunk_number,
                   chunk_size_gb,
                   status,
                   created_at
            FROM chunks
            WHERE file_id = %s
            ORDER BY chunk_number
            """,
            (file_id,)
        )

        rows = self.cursor.fetchall()

        chunk_list = []

        for row in rows:
            chunk_list.append({
                "chunk_id": row[0],
                "file_id": row[1],
                "node_id": row[2],
                "chunk_number": row[3],
                "chunk_size_gb": float(row[4]) if row[4] is not None else None,
                "status": row[5],
                "created_at": str(row[6])
            })

        return {
            "success": True,
            "file_id": file_id,
            "total_chunks": len(chunk_list),
            "chunks": chunk_list
        }

    def place_chunks(self, file_id: str):
        self.cursor.execute("""
            SELECT chunk_id, file_id
            FROM chunks
            WHERE file_id = %s
            ORDER BY chunk_number
        """, (file_id,))

        chunks = self.cursor.fetchall()

        if not chunks:
            return {"success": False, "message": "No chunks found for this file"}

        self.cursor.execute("""
            SELECT node_id
            FROM nodes
            WHERE status = 'online'
        """)

        online_nodes = self.cursor.fetchall()

        if not online_nodes:
            return {"success": False, "message": "No online nodes available"}

        created_at = datetime.now(timezone.utc).isoformat()
        placements = []
        node_index = 0

        for chunk in chunks:
            chunk_id = chunk[0]
            selected_node = online_nodes[node_index % len(online_nodes)][0]
            location_id = "LOC-" + str(uuid.uuid4())

            self.cursor.execute("""
                INSERT INTO chunk_locations
                (location_id, chunk_id, node_id, chunk_path, status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                location_id,
                chunk_id,
                selected_node,
                "",
                "placed",
                created_at
            ))

            placements.append({
                "chunk_id": chunk_id,
                "node_id": selected_node
            })

            node_index += 1

        self.conn.commit()

        return {
            "success": True,
            "file_id": file_id,
            "total_placements": len(placements),
            "placements": placements
        }


    def get_chunk_locations(self, file_id: str):
        self.cursor.execute("""
            SELECT cl.location_id, cl.chunk_id, c.file_id, cl.node_id, cl.chunk_path, cl.status, cl.created_at
            FROM chunk_locations cl
            JOIN chunks c
                ON cl.chunk_id = c.chunk_id
            WHERE c.file_id = %s
            ORDER BY c.chunk_number
        """, (file_id,))

        rows = self.cursor.fetchall()

        locations = []
        for row in rows:
            locations.append({
                "location_id": row[0],
                "chunk_id": row[1],
                "file_id": row[2],
                "node_id": row[3],
                "chunk_path": row[4],
                "status": row[5],
                "created_at": str(row[6])
            })

        return {
            "success": True,
            "file_id": file_id,
            "total_locations": len(locations),
            "locations": locations
        }

    def distribute_physical_chunks(self, file_id: str):
        created_at = datetime.now(timezone.utc).isoformat()

        self.cursor.execute("""
            SELECT chunk_id, chunk_path, chunk_size_bytes
            FROM physical_chunks
            WHERE file_id = %s
            ORDER BY chunk_number
        """, (file_id,))

        chunks = self.cursor.fetchall()

        if not chunks:
            return {
                "success": False,
                "message": "No physical chunks found for this file"
            }

        self.cursor.execute("""
            SELECT node_id
            FROM nodes
            WHERE status = 'online'
            ORDER BY node_id
        """)

        nodes = [row[0] for row in self.cursor.fetchall()]

        if not nodes:
            return {
                "success": False,
                "message": "No online nodes available"
            }

        distributed_records = []
        node_index = 0

        for chunk in chunks:
            chunk_id = chunk[0]
            chunk_path = chunk[1]
            chunk_size_bytes = chunk[2]

            selected_node = nodes[node_index % len(nodes)]
            node_index += 1

            storage_id = "DSTORAGE-" + str(uuid.uuid4())

            self.cursor.execute("""
                INSERT INTO distributed_chunk_storage
                (storage_id, file_id, chunk_id, node_id, chunk_path, chunk_size_bytes, storage_type, status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                storage_id,
                file_id,
                chunk_id,
                selected_node,
                chunk_path,
                chunk_size_bytes,
                "primary",
                "stored",
                created_at
            ))

            distributed_records.append({
                "storage_id": storage_id,
                "file_id": file_id,
                "chunk_id": chunk_id,
                "node_id": selected_node,
                "chunk_path": chunk_path,
                "chunk_size_bytes": chunk_size_bytes,
                "storage_type": "primary",
                "status": "stored"
            })

        self.conn.commit()

        return {
            "success": True,
            "file_id": file_id,
            "total_distributed_chunks": len(distributed_records),
            "distributed_chunks": distributed_records
        }


    def replicate_file(self, file_id: str):
        created_at = datetime.now(timezone.utc).isoformat()

        self.cursor.execute("""
            SELECT
                c.chunk_id,
                c.file_id,
                c.node_id,
                cl.node_id,
                cl.chunk_path,
                c.chunk_size_gb,
                c.chunk_number
            FROM chunks c
            JOIN chunk_locations cl
                ON c.chunk_id = cl.chunk_id
            WHERE c.file_id = %s
            ORDER BY c.chunk_number
        """, (file_id,))

        chunk_locations = self.cursor.fetchall()

        if not chunk_locations:
            return {
                "success": False,
                "message": "No placed chunks found for this file"
            }

        self.cursor.execute("""
            SELECT node_id
            FROM nodes
            WHERE status = 'online'
            ORDER BY node_id
        """)

        online_nodes = [row[0] for row in self.cursor.fetchall()]

        if len(online_nodes) < 2:
            return {
                "success": False,
                "message": "At least 2 online nodes required for replication"
            }

        replicas = []

        for chunk in chunk_locations:
            chunk_id = chunk[0]
            file_id = chunk[1]
            primary_node = chunk[2]
            replica_chunk_path = chunk[4]

            replica_number = 1

            for node_id in online_nodes:
                if node_id == primary_node:
                    continue

                replication_id = "REPLICATION-" + str(uuid.uuid4())

                self.cursor.execute("""
                    INSERT INTO file_replication
                    (replication_id, file_id, chunk_id, primary_node_id, replica_node_id, created_at, status, replica_chunk_path)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    replication_id,
                    file_id,
                    chunk_id,
                    primary_node,
                    node_id,
                    created_at,
                    "replicated",
                    replica_chunk_path
                ))

                replicas.append({
                    "replication_id": replication_id,
                    "file_id": file_id,
                    "chunk_id": chunk_id,
                    "primary_node_id": primary_node,
                    "replica_node_id": node_id,
                    "replica_number": replica_number,
                    "status": "replicated"
                })

                replica_number += 1

                if replica_number > 2:
                    break

        self.conn.commit()

        return {
            "success": True,
            "file_id": file_id,
            "total_replicas": len(replicas),
            "replicas": replicas
        }

    def get_file_replication(self, file_id: str):
        self.cursor.execute("""
            SELECT
                replication_id,
                file_id,
                chunk_id,
                primary_node_id,
                replica_node_id,
                replica_chunk_path,
                status,
                created_at
            FROM file_replication
            WHERE file_id = %s
            ORDER BY chunk_id, replica_node_id
        """, (file_id,))

        rows = self.cursor.fetchall()

        replicas = []
        for row in rows:
            replicas.append({
                "replication_id": row[0],
                "file_id": row[1],
                "chunk_id": row[2],
                "primary_node_id": row[3],
                "replica_node_id": row[4],
                "replica_chunk_path": row[5],
                "status": row[6],
                "created_at": str(row[7])
            })

        return {
            "success": True,
            "file_id": file_id,
            "total_replicas": len(replicas),
            "replicas": replicas
        }

    def register_file(self, file):
        self.cursor.execute("""
            SELECT allocation_id, node_id, file_size_gb, status
            FROM allocations
            WHERE status = 'active'
            ORDER BY allocated_at DESC
            LIMIT 1
        """)

        allocation = self.cursor.fetchone()

        if allocation is None:
            return {
                "success": False,
                "message": "No active allocation found. Allocate storage first."
            }

        file_id = "FILE-" + str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()

        self.cursor.execute("""
            INSERT INTO files
            (file_id, filename, file_size_gb, allocation_id, node_id, created_at, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            file_id,
            file.filename,
            file.file_size_gb,
            allocation[0],
            allocation[1],
            created_at,
            "registered"
        ))

        self.conn.commit()

        return {
            "success": True,
            "file_id": file_id,
            "filename": file.filename,
            "file_size_gb": file.file_size_gb,
            "allocation_id": allocation[0],
            "node_id": allocation[1],
            "created_at": created_at,
            "status": "registered"
        }

    def create_replicas(self, file_id):
        created_at = datetime.now(timezone.utc).isoformat()

        self.cursor.execute("""
            SELECT file_id, node_id
            FROM files
            WHERE file_id = %s
        """, (file_id,))

        file_record = self.cursor.fetchone()

        if file_record is None:
            return {"success": False, "message": "File not found"}

        self.cursor.execute("""
            SELECT node_id
            FROM nodes
            WHERE LOWER(status) = 'online'
            ORDER BY node_id
        """)

        online_nodes = self.cursor.fetchall()

        if not online_nodes:
            return {
                "success": False,
                "message": "No online nodes available for replication"
            }

        replicas_created = []
        replica_number = 1

        for node in online_nodes:
            replica_id = "REPLICA-" + str(uuid.uuid4())

            self.cursor.execute("""
                INSERT INTO file_replicas
                (replica_id, file_id, node_id, replica_number, created_at, status)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                replica_id,
                file_id,
                node[0],
                replica_number,
                created_at,
                "planned"
            ))

            replicas_created.append({
                "replica_id": replica_id,
                "file_id": file_id,
                "node_id": node[0],
                "replica_number": replica_number,
                "status": "planned"
            })

            replica_number += 1

        self.conn.commit()

        return {
            "success": True,
            "file_id": file_id,
            "total_replicas": len(replicas_created),
            "replicas": replicas_created
        }

    def file_health(self, file_id: str):
        self.cursor.execute("""
            SELECT COUNT(*)
            FROM chunks
            WHERE file_id = %s
        """, (file_id,))
        primary_chunks = self.cursor.fetchone()[0]

        self.cursor.execute("""
            SELECT COUNT(*)
            FROM chunk_locations cl
            JOIN chunks c ON cl.chunk_id = c.chunk_id
            WHERE c.file_id = %s
        """, (file_id,))
        placed_chunks = self.cursor.fetchone()[0]

        self.cursor.execute("""
            SELECT COUNT(*)
            FROM file_replication
            WHERE file_id = %s
        """, (file_id,))
        replica_chunks = self.cursor.fetchone()[0]

        self.cursor.execute("""
            SELECT COUNT(DISTINCT node_id)
            FROM chunks
            WHERE file_id = %s
        """, (file_id,))
        primary_nodes = self.cursor.fetchone()[0]

        self.cursor.execute("""
            SELECT COUNT(DISTINCT replica_node_id)
            FROM file_replication
            WHERE file_id = %s
        """, (file_id,))
        replica_nodes = self.cursor.fetchone()[0]

        healthy = primary_chunks > 0 and placed_chunks > 0 and replica_chunks > 0

        return {
            "file_id": file_id,
            "healthy": healthy,
            "primary_chunks": primary_chunks,
            "placed_chunks": placed_chunks,
            "replica_chunks": replica_chunks,
            "total_copies": placed_chunks + replica_chunks,
            "primary_nodes": primary_nodes,
            "replica_nodes": replica_nodes
        }

    def get_chunk(self, chunk_id: str):
        self.cursor.execute("""
            SELECT chunk_id, file_id, node_id, chunk_number, chunk_size_gb, status, created_at
            FROM chunks
            WHERE chunk_id = %s
        """, (chunk_id,))

        row = self.cursor.fetchone()

        if not row:
            return {
                "success": False,
                "message": "Chunk not found",
                "chunk_id": chunk_id
            }

        return {
            "success": True,
            "chunk": {
                "chunk_id": row[0],
                "file_id": row[1],
                "node_id": row[2],
                "chunk_number": row[3],
                "chunk_size_gb": float(row[4]) if row[4] is not None else None,
                "status": row[5],
                "created_at": str(row[6])
            }
        }

    def get_failover_events(self):
        self.cursor.execute("""
            SELECT failover_id, chunk_id, file_id, failed_node_id, promoted_node_id, created_at, status
            FROM failover_events
            ORDER BY created_at DESC
        """)
        rows = self.cursor.fetchall()

        events = []
        for row in rows:
            events.append({
                "failover_id": row[0],
                "chunk_id": row[1],
                "file_id": row[2],
                "failed_node_id": row[3],
                "promoted_node_id": row[4],
                "created_at": row[5],
                "status": row[6]
            })

        return {
            "success": True,
            "total_failover_events": len(events),
            "failover_events": events
        }
