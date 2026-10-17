import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pydantic import field_validator

from app.services import gemini_service
from app.api.v1.endpoints.auth import get_current_user
from app.models.user import UserInDB
from fastapi import Depends

router = APIRouter()
logger = logging.getLogger(__name__)

class ChatRequest(BaseModel):
    message: str

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be blank")
        return value

def get_chat_model():
    """
    Return the configured Gemini Developer API model handle.

    Uses GEMINI_API_KEY (Google AI Studio) instead of Vertex AI service-account
    credentials. Raises GeminiConfigurationError when the backend key is absent.
    """
    return gemini_service.get_text_model()

@router.post("/", response_model=dict)
async def chat_with_medical_assistant(
    request: ChatRequest,
    current_user: UserInDB = Depends(get_current_user),
):
    """
    Feature #4: AI Chatbot for medical queries.
    """
    try:
        # Model/credential initialization failures indicate unavailable local config.
        model = get_chat_model()
    except Exception as exc:
        logger.error("Chat provider initialization failed (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="The healthcare assistant is not configured on the backend.",
        ) from None

    try:
        
        system_instruction = (
            "You are Vitalyze AI, a helpful and empathetic medical assistant. "
            "Answer the user's health questions in simple, easy-to-understand language. "
            "If the question is serious, advise them to see a doctor. "
            "Do not advise on taking any medication. If asked direct them to reach out to their doctor"
            "If the question is regarding information about any medicine. Follow the below format of output.Provide a structured summary for the medicine        Format the response in these 3 clear sections:        1. **What it is used for:** (Simple explanation)        2. **Common Side Effects:** (List format)       3. **Warning/Precautions:** (When to be careful)        Keep it concise and easy to read."
            "Do not answer non-medical questions."
        )
        
        full_prompt = f"{system_instruction}\n\nUser: {request.message}\nAssistant:"
        
        response = model.generate_content(full_prompt)
        if not isinstance(response.text, str) or not response.text.strip():
            raise ValueError("Provider returned an empty response")
        return {"response": response.text}
        
    except Exception as exc:
        # Exception messages and tracebacks can contain credentials or provider URLs.
        logger.error("Chat provider request failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=502,
            detail="The healthcare assistant is temporarily unavailable.",
        ) from None
