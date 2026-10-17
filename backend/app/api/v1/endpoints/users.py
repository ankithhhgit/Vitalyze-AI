from fastapi import APIRouter, Depends, HTTPException

from app.models.user import UserInDB, UserPublic
from app.api.v1.endpoints.auth import get_current_user

router = APIRouter()

@router.get("/{user_id}", response_model=UserPublic)
async def read_user_by_id(
    user_id: str,
    current_user: UserInDB = Depends(get_current_user),
):
    """
    Retrieve the authenticated user's own profile.
    """
    if str(current_user.id) != user_id:
        raise HTTPException(status_code=404, detail="User not found")
    return current_user
