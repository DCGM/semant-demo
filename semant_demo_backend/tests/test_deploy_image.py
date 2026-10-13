"""The backend image runs uvicorn without the development reloader (#298)."""
import json
from pathlib import Path

DOCKERFILE = Path(__file__).resolve().parents[2] / "deploy" / "Dockerfile"


def _entrypoint() -> str:
    [line] = [line for line in DOCKERFILE.read_text().splitlines() if line.startswith("ENTRYPOINT")]
    return " ".join(json.loads(line.removeprefix("ENTRYPOINT")))


def test_backend_image_serves_the_app_without_reload():
    entrypoint = _entrypoint()

    assert "uvicorn semant_demo.main:app" in entrypoint
    assert "--port \"${PORT:-8000}\"" in entrypoint
    assert "reload" not in entrypoint and "run.py" not in entrypoint
