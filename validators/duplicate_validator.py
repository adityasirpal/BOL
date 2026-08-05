from psycopg2.extras import RealDictCursor
from psycopg2.extensions import cursor

from validators.result import ValidationResult


VALIDATOR_NAME = "Duplicate healthy placement"


def validate(db_cursor: cursor) -> ValidationResult:
    """
    Verify that a chunk is not counted more than once on the same node.

    Healthy copies are:
    - active primaries in distributed_chunk_storage
    - active replicas with status='replicated'

    promoted_to_primary rows are historical records and are not counted.
    """
    query = """
        WITH healthy_copies AS (
            SELECT
                file_id,
                chunk_id,
                node_id
            FROM distributed_chunk_storage
            WHERE storage_type = 'primary'
              AND status = 'stored'

            UNION ALL

            SELECT
                file_id,
                chunk_id,
                replica_node_id AS node_id
            FROM distributed_chunk_replicas
            WHERE status = 'replicated'
        )
        SELECT
            file_id,
            chunk_id,
            node_id,
            COUNT(*) AS duplicate_count
        FROM healthy_copies
        GROUP BY file_id, chunk_id, node_id
        HAVING COUNT(*) > 1
        ORDER BY file_id, chunk_id, node_id
    """

    try:
        with db_cursor.connection.cursor(
            cursor_factory=RealDictCursor
        ) as result_cursor:
            result_cursor.execute(query)
            duplicates = [dict(row) for row in result_cursor.fetchall()]

        if not duplicates:
            return ValidationResult.pass_result(
                name=VALIDATOR_NAME,
                message="No chunk has duplicate healthy placement on the same node.",
            )

        return ValidationResult.fail_result(
            name=VALIDATOR_NAME,
            message=(
                f"{len(duplicates)} duplicate healthy placement "
                "record(s) detected."
            ),
            details=duplicates,
        )

    except Exception as exc:
        return ValidationResult.fail_result(
            name=VALIDATOR_NAME,
            message=f"Validator execution failed: {exc}",
            details=[
                {
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            ],
        )
