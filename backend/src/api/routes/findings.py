from fastapi import APIRouter, Body
router = APIRouter()
@router.patch("/{finding_id}")
def patch_finding(finding_id: str, changes: dict = Body(...)):
    return {"finding_id": finding_id, "applied": changes}
