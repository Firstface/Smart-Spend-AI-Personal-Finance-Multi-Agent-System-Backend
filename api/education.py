from fastapi import APIRouter
from schemas.education import AskRequest, AskResponse, CitationItem
from agents.education.service import answer_question

router = APIRouter(
    prefix="/education",
    tags=["education"],
)


@router.post("/ask", response_model=AskResponse)
def ask_education(req: AskRequest):
    result = answer_question(
        question=req.question,
        user_id=req.user_id
    )

    citations = [
        CitationItem(
            doc_id=item["doc_id"],
            title=item["title"],
        )
        for item in result["citations"]
    ]

    return AskResponse(
        answer=result["answer"],
        citations=citations,
        status=result["status"],
        refusal_type=result.get("refusal_type"),
    )