from psycopg2.extensions import cursor
from psycopg2.extras import RealDictCursor

from validators.result import ValidationResult


VALIDATOR_NAME = "Orphan metadata"


def validate(db_cursor: cursor) -> ValidationResult:
    """
    Detect distributed storage and replica records whose file_id
    does not exist in the files table.
    """
    query = """
        WITH orphan_records AS (
            SELECT
                'distributed_chunk_storage' AS source_table,
                dcs.file_id,
                COUNT(*) AS orphan_record_count
            FROM distributed_chunk_storage dcs
            LEFT JOIN files f
                ON f.file_id = dcs.file_id
            WHERE f.file_id IS NULL
            GROUP BY dcs.file_id

            UNION ALL

            SELECT
                'distributed_chunk_replicas' AS source_table,
                dcr.file_id,
                COUNT(*) AS orphan_record_count
            FROM distributed_chunk_replicas dcr
            LEFT JOIN files f
                ON f.file_id = dcr.file_id
            WHERE f.file_id IS NULL
            GROUP BY dcr.file_id
        )
        SELECT
            source_table,
            file_id,
            orphan_record_count
        FROM orphan_records
        ORDER BY file_id, source_table
    """

    try:
        with db_cursor.connection.cursor(
            cursor_factory=RealDictCursor
        ) as result_cursor:
            result_cursor.execute(query)
            orphan_records = [
                dict(row)
                for row in result_cursor.fetchall()
            ]

        if not orphan_records:
            return ValidationResult.pass_result(
                name=VALIDATOR_NAME,
                message="No orphan storage or replica metadata was detected.",
            )

        return ValidationResult.fail_result(
            name=VALIDATOR_NAME,
            message=(
                f"{len(orphan_records)} orphan metadata group(s) detected."
            ),
            details=orphan_records,
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
