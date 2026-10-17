import logging
import os
from fastapi import APIRouter, HTTPException
import vertexai
from vertexai.generative_models import GenerativeModel
from google.oauth2 import service_account
from app.core.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


def get_medicine_model():
    credentials_path = settings.GOOGLE_APPLICATION_CREDENTIALS
    if (
        not settings.GCP_PROJECT_ID
        or settings.GCP_PROJECT_ID.startswith("replace-with-")
        or not credentials_path
        or not os.path.isfile(credentials_path)
    ):
        raise HTTPException(
            status_code=503,
            detail="Medicine information requires backend AI provider configuration.",
        )
    credentials = service_account.Credentials.from_service_account_file(credentials_path)
    vertexai.init(
        project=settings.GCP_PROJECT_ID,
        location=settings.GCP_LOCATION,
        credentials=credentials,
    )
    return GenerativeModel("gemini-1.5-flash")

@router.get("/{name}")
async def get_medicine_details(name: str):
    """
    Feature #5: Get details (side effects, usage) for a specific medicine.
    """
    try:
        model = get_medicine_model()
        prompt = f"""
        Provide a structured summary for the medicine: {name}.
        Format the response in these 3 clear sections:
        1. **What it is used for:** (Simple explanation)
        2. **Common Side Effects:** (List format)
        3. **Warning/Precautions:** (When to be careful)
        
        Keep it concise and easy to read.
        """
        
        response = model.generate_content(prompt)
        return {"name": name, "details": response.text}
        
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Medicine provider request failed (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=502,
            detail="Medicine information is temporarily unavailable.",
        ) from None
