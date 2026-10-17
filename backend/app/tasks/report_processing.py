import logging
import re
import os
import json  # Needed for parsing Gemini's JSON output
import cv2
import numpy as np
import pytesseract
import fitz  # PyMuPDF
import asyncio
from pdf2image import convert_from_path
from typing import List, Dict, Any, Union, Optional

from google.oauth2 import service_account
import vertexai
from vertexai.generative_models import GenerativeModel

from motor.motor_asyncio import AsyncIOMotorClient
from .celery_app import celery
from app.core.config import settings
from app.models.report import ReportCreate

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

custom_config = r'--psm 6'

# --- PDF & Image Processing Utilities (Unchanged) ---

def pdf_to_cv2_objects(pdf_path: str, dpi: int = 300) -> List[np.ndarray]:
    cv2_images = []
    logger.info(f"Rendering PDF pages to images at {dpi} dpi...")
    try:
        pages = convert_from_path(pdf_path, dpi=dpi)
        for page_image in pages:
            page_array = np.array(page_image)
            cv2_image = cv2.cvtColor(page_array, cv2.COLOR_RGB2BGR)
            cv2_images.append(cv2_image)
    except Exception as e:
        logger.error(f"Error converting PDF to images: {e}")
        raise e
    return cv2_images

def preprocessor(cv2_image: np.ndarray) -> np.ndarray:
    # 1. Convert to Gray
    gray = cv2.cvtColor(cv2_image, cv2.COLOR_BGR2GRAY)
    
    # 2. Rescale (Zoom) - Tesseract loves 300+ DPI. 
    # If the input is small, double the size.
    # height, width = gray.shape[:2]
    # gray = cv2.resize(gray, (width*2, height*2), interpolation=cv2.INTER_CUBIC)

    # 3. Apply Adaptive Thresholding (Better for shadows/uneven lighting)
    # This keeps local details that Otsu misses
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )
    
    # 4. Denoise slightly
    processed = cv2.medianBlur(thresh, 3)
    
    return processed

def extract_text(processed_image: np.ndarray) -> str:
    return pytesseract.image_to_string(processed_image, lang="eng", config=custom_config)

def extract_text_from_pdf(file_path: str) -> str:
    text = ""
    try:
        logger.info(f"Attempting direct text extraction for {file_path}...")
        with fitz.open(file_path) as doc:
            for page in doc:
                text += page.get_text()
        
        if len(text.strip()) < 50:
            logger.info("Text too short. Likely scanned. Switching to OCR.")
            raise ValueError("Likely Scanned PDF")
    except Exception:
        logger.info(f"Running Tesseract OCR pipeline on {file_path}")
        full_ocr_text = []
        try:
            cv2_images = pdf_to_cv2_objects(file_path, dpi=300)
            for i, image in enumerate(cv2_images):
                processed_image = preprocessor(image)
                page_text = extract_text(processed_image)
                full_ocr_text.append(page_text)
            text = "\n".join(full_ocr_text)
        except Exception as e:
            logger.error(f"OCR extraction failed: {e}")
            raise e
    return text


# --- NEW: Gemini Extraction Function ---

def extract_vitals_with_gemini(full_text: str) -> List[Dict[str, str]]:
    """
    Uses Vertex AI (Gemini) to extract structured key-value pairs.
    """
    try:
        creds = service_account.Credentials.from_service_account_file(
            settings.GOOGLE_APPLICATION_CREDENTIALS
        )
        
        vertexai.init(
            project=settings.GCP_PROJECT_ID, 
            location=settings.GCP_LOCATION, 
            credentials=creds
        )
        
        model = GenerativeModel("gemini-2.5-pro")
        
        # We ask Gemini to output strict JSON
        prompt = f"""
        You are an expert medical data extractor. 
        Analyze the following medical report text and extract the medical test results.

        REPORT TEXT:
        "{full_text}"

        INSTRUCTIONS:
        1. Identify specific medical tests and their measured values.
        2. Combine the numeric value and the unit into the "Value" field (e.g., "14.2 g/dL").
        3. IGNORE reference ranges, dates, patient IDs, page numbers, QR codes, and scanner metadata.
        4. IGNORE normal/abnormal flags (like "High", "Low").
        5. Return ONLY a valid JSON array of objects.
        6. Each object must have exactly two keys: "Indicator" (the test name) and "Value" (the result).

        Example Output Format:
        [
            {{"Indicator": "Hemoglobin", "Value": "12.5 g/dL"}},
            {{"Indicator": "RBC Count", "Value": "4.5 mill/mm3"}}
        ]
        """

        logger.info("Asking Gemini to extract structured vitals...")
        response = model.generate_content(prompt)
        
        # Clean the response to ensure it's valid JSON (Gemini sometimes adds ```json markers)
        raw_response = response.text.strip()
        clean_json = raw_response.replace("```json", "").replace("```", "").strip()
        
        extracted_data = json.loads(clean_json)
        return extracted_data

    except Exception as e:
        logger.error(f"Gemini Extraction failed: {e}")
        # Return empty list so the app doesn't crash
        return []


def generate_summary_with_gemini(entities: List[Dict], full_text: str) -> str:
    """
    Summarization Step (Uses the same model configuration)
    """
    try:
        creds = service_account.Credentials.from_service_account_file(
            settings.GOOGLE_APPLICATION_CREDENTIALS
        )
        
        vertexai.init(
            project=settings.GCP_PROJECT_ID, 
            location=settings.GCP_LOCATION, 
            credentials=creds
        )
        
        model = GenerativeModel("gemini-2.5-pro")
        
        prompt = f"""
        You are a helpful medical assistant using Vitalyze.ai. 
        
        Based on these extracted test results:
        {json.dumps(entities)}

        And this raw report text context:
        "{full_text[:2000]}..."

        Write a simple, comforting summary for the patient.
        1. Mention the key findings in plain English.
        2. Briefly explain what the tests are for (e.g., "Hemoglobin carries oxygen").
        3. Do not use complex jargon.
        4. End with a disclaimer that you are an AI.
        """

        response = model.generate_content(prompt)
        return response.text

    except Exception as e:
        logger.error(f"Gemini Summary failed: {e}")
        return "Unable to generate AI summary at this time."


# --- Celery Tasks ---

@celery.task(bind=True)
def task_extract_data_from_pdf(self, file_path: str) -> Dict[str, Any]:
    logger.info(f"Starting data extraction for: {file_path}")
    try:
        extracted_text = extract_text_from_pdf(file_path)
        if os.path.exists(file_path):
            os.remove(file_path)
        return {"full_text": extracted_text}
    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise e


@celery.task(bind=True)
def task_run_ai_analysis(self, extraction_result: Union[Dict, str], user_id: str, filename: str, gcs_path: Optional[str] = None):
    logger.info(f"Starting AI analysis for User: {user_id}")
    
    text_to_analyze = ""
    if isinstance(extraction_result, dict):
        text_to_analyze = extraction_result.get("full_text", "")
    else:
        text_to_analyze = str(extraction_result)

    if not text_to_analyze:
        raise RuntimeError("Report extraction produced no text")

    # --- STEP 1: Extract Clean Data using Gemini ---
    # We replaced the Regex/Google NLP with this single intelligent call.
    vital_indicators = extract_vitals_with_gemini(text_to_analyze)
    
    # --- STEP 2: Generate Summary based on that data ---
    simple_summary = generate_summary_with_gemini(vital_indicators, text_to_analyze)
    
    # 3. Save to DB
    async def save_to_db():
        client = AsyncIOMotorClient(settings.MONGO_URI)
        try:
            db = client[settings.MONGO_DB_NAME]
            
            report_in = ReportCreate(
                user_id=user_id,
                filename=filename,
                raw_text=text_to_analyze,
                simple_summary=simple_summary,
                # Store the clean indicators as the 'structured_entities' so the frontend works automatically
                structured_entities=vital_indicators,
                file_storage_path=gcs_path
            )
            
            await db["reports"].insert_one(report_in.model_dump(by_alias=True, exclude=["id"]))
            return True
        finally:
            client.close()

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(save_to_db())
    except Exception:
        logger.exception("Failed to persist processed report")
        raise RuntimeError("Report processing failed") from None
    finally:
        loop.close()
        asyncio.set_event_loop(None)

    # Return structure matching what your frontend expects
    return {
        "status": "COMPLETED",
        # We populate both keys with the clean data to ensure frontend compatibility
        "structured_entities": vital_indicators,
        "vital_indicators": vital_indicators,
        "simple_summary": simple_summary
    }
