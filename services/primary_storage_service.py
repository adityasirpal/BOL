import uuid
from typing import Any


def create_primary_storage_record(
    cursor: Any,
    *,
    file_id: str,
    chunk_id: str,
    node_id: str,
    chunk_path: str,
    chunk_size_bytes: int,
    created_at: str,
) -> str:
    """
    Canonical method for creating an active primary record.

    The caller controls the transaction and must commit or roll back.
    """

    # A chunk must not already have an active primary.
    cursor.execute(
        """
        SELECT storage_id, node_id
        FROM distributed_chunk_storage
        WHERE file_id = %s
          AND chunk_id = %s
          AND storage_type = 'primary'
          AND status = 'stored'
        """,
        (file_id, chunk_id),
    )

    existing_primary = cursor.fetchone()

    if existing_primary:
        raise ValueError(
            f"Active primary already exists for file_id={file_id}, "
            f"chunk_id={chunk_id}, storage_id={existing_primary[0]}, "
            f"node_id={existing_primary[1]}"
        )

    storage_id = "DSTORAGE-" + str(uuid.uuid4())

    cursor.execute(
        """
        INSERT INTO distributed_chunk_storage
        (
            storage_id,
            file_id,
            chunk_id,
            node_id,
            chunk_path,
            chunk_size_bytes,
            storage_type,
            status,
            created_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            storage_id,
            file_id,
            chunk_id,
            node_id,
            chunk_path,
            chunk_size_bytes,
            "primary",
            "stored",
            created_at,
        ),
    )

    # Verify the insert produced exactly one active primary.
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM distributed_chunk_storage
        WHERE file_id = %s
          AND chunk_id = %s
          AND storage_type = 'primary'
          AND status = 'stored'
        """,
        (file_id, chunk_id),
    )

    active_primary_count = cursor.fetchone()[0]

    if active_primary_count != 1:
        raise RuntimeError(
            f"Primary integrity violation for file_id={file_id}, "
            f"chunk_id={chunk_id}: active_primary_count="
            f"{active_primary_count}"
        )

    return storage_id
