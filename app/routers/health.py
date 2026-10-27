"""Health endpoints (Playbook ARC-07).

/health        "Is the process alive?"  Never touches other systems.
/health/ready  "Can it do its job?"     Checks what the app depends on.
Containers use /health/ready in their HEALTHCHECK (CTR-06).
"""

from fastapi import APIRouter, Response

from app.services import readiness

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
def ready(response: Response) -> dict[str, str]:
    problems = readiness.check_dependencies()
    if problems:
        # 503 tells the orchestrator "do not send traffic here yet".
        response.status_code = 503
        return {"status": "not ready", "problems": ", ".join(problems)}
    return {"status": "ready"}
