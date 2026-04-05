from pydantic import BaseModel
from typing import List, Optional, Literal


class CitationItem(BaseModel):
    doc_id: str
    title: str


class AskRequest(BaseModel):
    question: str
    user_id: Optional[str] = None


class AskResponse(BaseModel):
    answer: str
    citations: List[CitationItem]
    status: Literal["answer", "refuse"]
    refusal_type: Optional[str] = None