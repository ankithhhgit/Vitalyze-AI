from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pydantic import field_validator
import logging
import vertexai
from vertexai.generative_models import GenerativeModel
from google.oauth2 import service_account  # <--- IMPORT THIS
from app.core.config import settings
import os

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
    Helper to initialize the model with explicit credentials.
    """
    # 1. Check if file exists to give a clear error if missing
    if not os.path.exists(settings.GOOGLE_APPLICATION_CREDENTIALS):
        raise FileNotFoundError(f"Credential file not found at: {settings.GOOGLE_APPLICATION_CREDENTIALS}")

    # 2. Load the credentials from the JSON file
    my_credentials = service_account.Credentials.from_service_account_file(
        settings.GOOGLE_APPLICATION_CREDENTIALS
    )

    # 3. Initialize Vertex AI with these credentials
    vertexai.init(
        project=settings.GCP_PROJECT_ID, 
        location=settings.GCP_LOCATION, 
        credentials=my_credentials
    )
    
    return GenerativeModel("gemini-2.5-pro")

@router.post("/", response_model=dict)
async def chat_with_medical_assistant(request: ChatRequest):
    """
    Feature #4: AI Chatbot for medical queries.
    """
    try:
        # Initialize model inside the request to ensure creds are loaded
        model = get_chat_model()
        
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
        return {"response": response.text}
        
    except Exception as exc:
        # Exception messages and tracebacks can contain credentials or provider URLs.
        logger.error("Chat provider request failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=502,
            detail="The healthcare assistant is temporarily unavailable.",
        ) from None
