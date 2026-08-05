import os
import uuid
import hashlib

from config import PRIMARY_CHUNK_DIR

CHUNK_SIZE = 16 * 1024 * 1024  # 16 MB


class ChunkService:

    def split_file(self, input_file, output_directory=None):
        if output_directory is None:
            output_directory = PRIMARY_CHUNK_DIR

        os.makedirs(output_directory, exist_ok=True)

        chunks = []

        with open(input_file, "rb") as source:

            chunk_number = 1

            while True:

                data = source.read(CHUNK_SIZE)

                if not data:
                    break

                chunk_id = "PCHUNK-" + str(uuid.uuid4())

                filename = f"{chunk_id}.bin"

                full_path = os.path.join(output_directory, filename)

                with open(full_path, "wb") as chunk:
                    chunk.write(data)

                sha256 = hashlib.sha256(data).hexdigest()

                chunks.append({
                    "chunk_id": chunk_id,
                    "chunk_number": chunk_number,
                    "chunk_path": full_path,
                    "size_bytes": len(data),
                    "sha256": sha256
                })

                chunk_number += 1

        return chunks

    def rebuild_file(self, chunks, output_path):
        """
        Rebuild a file from ordered chunk records.

        Expected chunk format:
        [
            {
                "chunk_path": "...",
                "checksum": "..."
            }
        ]
        """

        if not chunks:
            return {
                "success": False,
                "message": "No chunks provided for reconstruction"
            }

        output_directory = os.path.dirname(output_path)

        if output_directory:
            os.makedirs(output_directory, exist_ok=True)

        total_bytes = 0
        chunks_processed = 0

        try:
            with open(output_path, "wb") as output_file:
                for chunk in chunks:
                    chunk_path = chunk["chunk_path"]
                    expected_checksum = chunk["checksum"]

                    if not os.path.exists(chunk_path):
                        raise FileNotFoundError(
                            f"Missing chunk file: {chunk_path}"
                        )

                    with open(chunk_path, "rb") as chunk_file:
                        chunk_data = chunk_file.read()

                    actual_checksum = hashlib.sha256(
                        chunk_data
                    ).hexdigest()

                    if actual_checksum != expected_checksum:
                        raise ValueError(
                            f"Checksum mismatch for chunk: {chunk_path}"
                        )

                    output_file.write(chunk_data)

                    total_bytes += len(chunk_data)
                    chunks_processed += 1

            return {
                "success": True,
                "output_path": output_path,
                "chunks_processed": chunks_processed,
                "total_bytes": total_bytes
            }

        except Exception as exc:
            if os.path.exists(output_path):
                os.remove(output_path)

            return {
                "success": False,
                "message": "File reconstruction failed",
                "error": str(exc)
            }
