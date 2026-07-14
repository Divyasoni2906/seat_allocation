from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..ai_assistant import handle_query

router = APIRouter(prefix="/ai", tags=["AI Assistant"])


@router.post("/query", response_model=schemas.AIQueryResponse)
def query(payload: schemas.AIQueryRequest, db: Session = Depends(get_db)):
    result = handle_query(db, payload.query)
    return schemas.AIQueryResponse(answer=result["answer"], intent=result.get("intent"))
