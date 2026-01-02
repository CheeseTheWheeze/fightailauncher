import json
from pathlib import Path
from typing import Any


class ResultStatus:
    OK = "ok"
    ERROR = "error"


def safe_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    temp_path.replace(path)


def write_result_ok(result: dict[str, Any]) -> dict[str, Any]:
    result["status"] = ResultStatus.OK
    result.pop("error", None)
    return result


def write_result_error(result: dict[str, Any], code: str, message: str, hint: str | None = None) -> dict[str, Any]:
    result["status"] = ResultStatus.ERROR
    result["error"] = {
        "code": code,
        "message": message,
        "hint": hint or "",
    }
    return result
