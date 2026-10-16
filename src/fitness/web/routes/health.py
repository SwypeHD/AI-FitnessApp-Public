from fastapi import APIRouter, Depends

from fitness.config.composition import Container
from fitness.web.dependencies import get_container

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/ai-status")
def ai_status(container: Container = Depends(get_container)):
    from fitness.adapters.llm.null_client import NullLlmClient
    from fitness.adapters.llm.ollama_client import OllamaLlmClient

    llm = container.llm
    if isinstance(llm, NullLlmClient):
        return {"connected": False, "provider": "none"}

    if isinstance(llm, OllamaLlmClient):
        import httpx
        try:
            r = httpx.get(f"{llm._host}/api/tags", timeout=3.0)
            return {"connected": r.status_code == 200, "provider": "ollama"}
        except Exception:
            return {"connected": False, "provider": "ollama"}

    return {"connected": True, "provider": "anthropic"}
