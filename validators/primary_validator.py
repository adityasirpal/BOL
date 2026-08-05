from psycopg2.extensions import cursor
from psycopg2.extras import RealDictCursor

from validators.result import ValidationResult


VALIDATOR_NAME = "Active primary consistency"


def validate(db_cursor: cursor) -> ValidationResult:
    """
    Verify that every distributed chunk represented in the storage system
    has exactly one active primary record.

    An active primary is:
        storage_type = 'primary'
        status = 'stored'
    """
    query = """
        WITH known_chunks AS (
            SELECT
                file_id,
                chunk_id
            FROM distributed_chunk_storage

            UNION

            SELECT
                file_id,
                chunk_id
            FROM distributed_chunk_replicas
        ),
        active_primaries AS (
            SELECT
                file_id,
                chunk_id,
                COUNT(*) AS active_primary_count
            FROM distributed_chunk_storage
            WHERE storage_type = 'primary'
              AND status = 'stored'
            GROUP BY file_id, chunk_id
        )
        SELECT
            kc.file_id,
            kc.chunk_id,
            COALESCE(ap.active_primary_count, 0) AS active_primary_count
        FROM known_chunks kc
        LEFT JOIN active_primaries ap
            ON ap.file_id = kc.file_id
           AND ap.chunk_id = kc.chunk_id
        WHERE COALESCE(ap.active_primary_count, 0) <> 1
        ORDER BY kc.file_id, kc.chunk_id
    """

    try:
        with db_cursor.connection.cursor(
            cursor_factory=RealDictCursor
        ) as result_cursor:
            result_cursor.execute(query)
            invalid_primaries = [
                dict(row)
                for row in result_cursor.fetchall()
            ]

        if not invalid_primaries:
            return ValidationResult.pass_result(
                name=VALIDATOR_NAME,
                message="Every distributed chunk has exactly one active primary.",
            )

        return ValidationResult.fail_result(
            name=VALIDATOR_NAME,
            message=(
                f"{len(invalid_primaries)} chunk(s) do not have exactly "
                "one active primary."
            ),
            details=invalid_primaries,
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
