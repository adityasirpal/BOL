from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from validators.database import read_only_cursor
from validators.duplicate_validator import validate as duplicate
from validators.healthy_copy_validator import validate as healthy_copy
from validators.orphan_validator import validate as orphan
from validators.primary_validator import validate as primary

VALIDATORS = [
    healthy_copy,
    duplicate,
    orphan,
    primary,
]


def main() -> int:
    print("=" * 60)
    print("BOL DATABASE INTEGRITY VALIDATOR")
    print("=" * 60)

    passed = 0
    failed = 0

    with read_only_cursor() as db_cursor:
        for validator in VALIDATORS:
            result = validator(db_cursor)
            status = "PASS" if result.passed else "FAIL"

            print(f"[{status}] {result.name}")
            print(f"       {result.message}")

            if result.details:
                for detail in result.details:
                    print(f"       {detail}")

            print()

            if result.passed:
                passed += 1
            else:
                failed += 1

    print("=" * 60)
    print(f"Passed : {passed}")
    print(f"Failed : {failed}")
    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
