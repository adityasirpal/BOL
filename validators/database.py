from contextlib import contextmanager
from collections.abc import Generator

import psycopg2
from psycopg2.extensions import connection, cursor

import database as bol_database


def create_read_only_connection() -> connection:
    """
    Create an independent PostgreSQL connection using BOL's existing
    database configuration.

    The transaction is read-only so validators cannot modify data.
    """
    connection_parameters = bol_database.conn.get_dsn_parameters()

    conn = psycopg2.connect(
        dbname=connection_parameters["dbname"],
        user=connection_parameters["user"],
        password=bol_database.conn.info.password,
        host=connection_parameters.get("host", "localhost"),
        port=connection_parameters.get("port", "5432"),
    )

    conn.set_session(readonly=True, autocommit=False)
    return conn


@contextmanager
def read_only_cursor() -> Generator[cursor, None, None]:
    conn = create_read_only_connection()
    db_cursor = conn.cursor()

    try:
        yield db_cursor
        conn.rollback()
    finally:
        db_cursor.close()
        conn.close()
