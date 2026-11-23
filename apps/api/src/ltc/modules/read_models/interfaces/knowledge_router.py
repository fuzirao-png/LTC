from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ltc.modules.iam.interfaces.router import AuthContext, get_auth_context
from ltc.platform.knowledge import KnowledgeNotConfiguredError, KnowledgeSearchRequest, KnowledgeService, WeKnoraProviderError


router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.post("/search")
def search_knowledge(
    body: KnowledgeSearchRequest,
    request: Request,
    _context: AuthContext = Depends(get_auth_context),
):
    try:
        result = request.app.state.knowledge_service.search(
            query=body.query,
            knowledge_base_ids=body.knowledge_base_ids,
            limit=body.limit,
        )
    except KnowledgeNotConfiguredError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"code": "KNOWLEDGE_NOT_CONFIGURED", "message": str(error)}) from error
    except WeKnoraProviderError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail={"code": "KNOWLEDGE_PROVIDER_UNAVAILABLE", "message": str(error)}) from error
    return {"request_id": request.headers.get("x-request-id", str(uuid4())), "data": result.model_dump()}
