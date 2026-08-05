from psycopg2.extensions import cursor
from psycopg2.extras import RealDictCursor

from validators.result import ValidationResult


VALIDATOR_NAME = "Healthy copy count"


def validate(db_cursor: cursor) -> ValidationResult:
    """
    Verify every distributed chunk has exactly two healthy copies:
    one stored primary and one replicated backup.
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
            COUNT(*) AS healthy_copy_count
        FROM healthy_copies
        GROUP BY file_id, chunk_id
        HAVING COUNT(*) <> 2
        ORDER BY file_id, chunk_id
    """

    try:
        with db_cursor.connection.cursor(
            cursor_factory=RealDictCursor
        ) as result_cursor:
            result_cursor.execute(query)
            invalid_chunks = [
                dict(row)
                for row in result_cursor.fetchall()
            ]

        if not invalid_chunks:
            return ValidationResult.pass_result(
                name=VALIDATOR_NAME,
                message="Every distributed chunk has exactly two healthy copies.",
            )

        return ValidationResult.fail_result(
            name=VALIDATOR_NAME,
            message=(
                f"{len(invalid_chunks)} chunk(s) do not have exactly "
                "two healthy copies."
            ),
            details=invalid_chunks,
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
