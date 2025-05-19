from fastapi import APIRouter, Request
from matcher import match_issue_to_operation

router = APIRouter()

@router.post("/chat/submit")
async def submit_issue(request: Request):
    body = await request.json()
    user_description = body.get("issue_description", "")

    matched_operation = match_issue_to_operation(user_description)

    return {
        "matched_operation": matched_operation,
        "status": "success"
    }
