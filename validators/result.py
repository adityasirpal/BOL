from dataclasses import dataclass, field
from typing import Any


@dataclass
class ValidationResult:
    name: str
    passed: bool
    count: int
    message: str
    details: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def pass_result(
        cls,
        name: str,
        message: str,
    ) -> "ValidationResult":
        return cls(
            name=name,
            passed=True,
            count=0,
            message=message,
            details=[],
        )

    @classmethod
    def fail_result(
        cls,
        name: str,
        message: str,
        details: list[dict[str, Any]],
    ) -> "ValidationResult":
        return cls(
            name=name,
            passed=False,
            count=len(details),
            message=message,
            details=details,
        )
