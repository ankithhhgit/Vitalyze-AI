from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from pydantic import BaseModel

from app.services.maps_service import (
    maps_service,
    MapsProviderError,
    MapsProviderTimeoutError,
)
from app.api.v1.endpoints.auth import get_current_user
from app.models.user import UserInDB

router = APIRouter()

class Geometry(BaseModel):
    lat: float
    lng: float

class Pharmacy(BaseModel):
    name: str
    vicinity: Optional[str] = None
    rating: Optional[float] = None
    user_ratings_total: Optional[int] = None
    geometry: Geometry
    place_id: str

@router.get("/pharmacies", response_model=List[Pharmacy])
def get_nearby_pharmacies(
    lat: float = Query(..., ge=-90, le=90, description="Latitude of the user"),
    lng: float = Query(..., ge=-180, le=180, description="Longitude of the user"),
    radius: int = Query(5000, ge=100, le=50000, description="Search radius in meters (default 5km)"),
    current_user: UserInDB = Depends(get_current_user),
):
    """
    Get list of pharmacies near the provided coordinates.
    """
    if not maps_service.is_configured:
        raise HTTPException(
            status_code=503,
            detail="Pharmacy search is not configured. Configure GEOAPIFY_API_KEY on the backend.",
        )

    try:
        return maps_service.get_nearby_pharmacies(lat, lng, radius)
    except MapsProviderTimeoutError:
        raise HTTPException(
            status_code=504,
            detail="The pharmacy provider timed out. Please try again.",
        ) from None
    except MapsProviderError:
        raise HTTPException(
            status_code=502,
            detail="The pharmacy provider is temporarily unavailable.",
        ) from None
