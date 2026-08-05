import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()

_REQUIRED_VARIABLES = (
    "DB_NAME",
    "DB_USER",
    "DB_PASSWORD",
    "DB_HOST",
    "DB_PORT",
)

_missing_variables = [
    variable
    for variable in _REQUIRED_VARIABLES
    if not os.getenv(variable)
]

if _missing_variables:
    raise RuntimeError(
        "Missing required database environment variables: "
        + ", ".join(_missing_variables)
    )

conn = psycopg2.connect(
    dbname=os.environ["DB_NAME"],
    user=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"],
    host=os.environ["DB_HOST"],
    port=os.environ["DB_PORT"],
)

cursor = conn.cursor()
