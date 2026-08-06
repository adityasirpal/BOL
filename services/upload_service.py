import os
import uuid

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.file_service import FileService


class UploadService:
    def __init__(self, file_service: "FileService" = None):
        self.file_service = file_service

    async def save_incoming_upload(
        self,
        file,
        incoming_upload_dir: str,
    ) -> dict:
        """
        Save an incoming UploadFile to disk in 1 MB blocks.

        This method performs filesystem work only.
        It does not create metadata, chunks, storage records,
        replicas, or database commits.
        """
        original_filename = os.path.basename(
            file.filename or "uploaded_file.bin"
        )

        upload_id = "FILE-" + str(uuid.uuid4())

        os.makedirs(incoming_upload_dir, exist_ok=True)

        original_file_path = os.path.join(
            incoming_upload_dir,
            f"{upload_id}_{original_filename}",
        )

        file_size_bytes = 0

        try:
            with open(original_file_path, "wb") as output_file:
                while True:
                    data = await file.read(1024 * 1024)

                    if not data:
                        break

                    output_file.write(data)
                    file_size_bytes += len(data)

            return {
                "success": True,
                "upload_id": upload_id,
                "original_filename": original_filename,
                "original_file_path": original_file_path,
                "file_size_bytes": file_size_bytes,
            }

        except Exception:
            if os.path.exists(original_file_path):
                os.remove(original_file_path)

            raise

    def create_file_metadata(
        self,
        cursor,
        file_id: str,
        filename: str,
        file_size_gb: float,
        created_at: str,
        status: str = "uploaded_and_chunked",
    ) -> None:
        """
        Create the PostgreSQL file metadata record.

        UploadService owns upload-related file metadata creation.
        Transaction commit remains controlled by FileService.
        """
        cursor.execute(
            """
            INSERT INTO files
            (file_id, filename, file_size_gb, created_at, status)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                file_id,
                filename,
                file_size_gb,
                created_at,
                status,
            ),
        )

    def create_physical_chunk_metadata(
        self,
        cursor,
        file_id: str,
        chunks: list,
        created_at: str,
    ) -> None:
        """
        Create PostgreSQL physical chunk metadata records.

        UploadService owns upload-related physical chunk metadata creation.
        Transaction commit remains controlled by FileService.
        """
        for chunk in chunks:
            physical_chunk_id = "PHYSICAL-" + str(uuid.uuid4())

            cursor.execute(
                """
                INSERT INTO physical_chunks
                (
                    physical_chunk_id,
                    chunk_id,
                    file_id,
                    chunk_number,
                    chunk_path,
                    chunk_size_bytes,
                    checksum,
                    created_at,
                    status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    physical_chunk_id,
                    chunk["chunk_id"],
                    file_id,
                    chunk["chunk_number"],
                    chunk["chunk_path"],
                    chunk["size_bytes"],
                    chunk["sha256"],
                    created_at,
                    "stored",
                ),
            )


    def create_primary_storage_metadata(
        self,
        cursor,
        chunks,
        file_id,
        created_at,
        node_service,
    ):
        """
        Create primary storage records for uploaded chunks.

        Transaction commit remains controlled by FileService.
        """

        from services.primary_storage_service import create_primary_storage_record

        for chunk in chunks:
            best_node = node_service.select_best_node()

            if not best_node:
                raise RuntimeError("No online node available")

            create_primary_storage_record(
                cursor=cursor,
                file_id=file_id,
                chunk_id=chunk["chunk_id"],
                node_id=best_node["node_id"],
                chunk_path=chunk["chunk_path"],
                chunk_size_bytes=chunk["size_bytes"],
                created_at=created_at,
            )

    async def upload_and_chunk_file(self, file):
        """
        Temporary pass-through.

        The production workflow remains in FileService until each
        responsibility is migrated and independently validated.
        """
        return await self.file_service.upload_file(file)
