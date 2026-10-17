import logging
import re
import os
import json  # Needed for parsing Gemini's JSON output
import cv2
import numpy as np
import pytesseract
import fitz  # PyMuPDF
import asyncio
import shutil
from pdf2image import convert_from_path
from typing import List, Dict, Any, Union, Optional

from motor.motor_asyncio import AsyncIOMotorClient
from .celery_app import celery
from app.core.config import settings
from app.services import gemini_service
from app.models.report import ReportCreate

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

custom_config = r'--psm 6'


class ReportExtractionError(ValueError):
    """A safe, user-actionable failure while extracting a PDF locally."""

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
    try:
        with fitz.open(file_path) as doc:
            if not doc.page_count:
                raise ReportExtractionError("The PDF contains no pages.")
            text = "\n".join(page.get_text() for page in doc).strip()
            if text:
                return text
            has_images = any(page.get_images(full=True) for page in doc)
    except ReportExtractionError:
        raise
    except Exception as exc:
        logger.warning("PDF could not be opened (%s).", type(exc).__name__)
        raise ReportExtractionError("This file is not a readable PDF. Please select a valid PDF.") from None

    if not has_images:
        raise ReportExtractionError("This PDF contains no extractable text or scanned page images.")
    if not shutil.which("tesseract") or not shutil.which("pdftoppm"):
        raise ReportExtractionError(
            "This appears to be a scanned PDF. Local OCR is unavailable; install Tesseract and Poppler, or use a text-based PDF."
        )

    try:
        cv2_images = pdf_to_cv2_objects(file_path, dpi=300)
        text = "\n".join(
            extract_text(preprocessor(image)) for image in cv2_images
        ).strip()
    except Exception as exc:
        logger.warning("Scanned PDF OCR failed (%s).", type(exc).__name__)
        raise ReportExtractionError("Local OCR could not read this scanned PDF.") from None
    if not text:
        raise ReportExtractionError("No text could be recognized in this scanned PDF.")
    return text


# --- NEW: Gemini Extraction Function ---

def extract_vitals_with_gemini(full_text: str) -> List[Dict[str, str]]:
    """
    Uses the Gemini Developer API to extract structured key-value pairs.
    """
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

    try:
        logger.info("Asking Gemini to extract structured vitals...")
        raw_response = gemini_service.generate_json(prompt)

        # Fallback fence-stripping in case the provider ignores JSON mode.
        clean_json = raw_response.replace("```json", "").replace("```", "").strip()
        extracted_data = json.loads(clean_json)
        if not isinstance(extracted_data, list):
            raise ValueError("Gemini vitals output was not a JSON array")
        return extracted_data

    except Exception as exc:
        logger.error("Gemini extraction failed (%s).", type(exc).__name__)
        raise RuntimeError("AI report interpretation failed") from None


def generate_summary_with_gemini(entities: List[Dict], full_text: str) -> str:
    """
    Summarization Step (Uses the same Gemini Developer API configuration)
    """
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

    try:
        return gemini_service.generate_text(prompt)
    except Exception as exc:
        logger.error("Gemini summary failed (%s).", type(exc).__name__)
        raise RuntimeError("AI report summary generation failed") from None


# --- Celery Tasks ---

@celery.task(bind=True)
def task_extract_data_from_pdf(self, file_path: str) -> Dict[str, Any]:
    logger.info("Starting local PDF text extraction.")
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
    logger.info("Starting report interpretation and persistence.")
    
    text_to_analyze = ""
    if isinstance(extraction_result, dict):
        text_to_analyze = extraction_result.get("full_text", "")
    else:
        text_to_analyze = str(extraction_result)

    if not text_to_analyze.strip():
        raise RuntimeError("Report extraction produced no text")

    # Prefer an explicit process environment value (runbook exports), otherwise
    # fall back to backend settings loaded from .env.
    analysis_mode = (
        os.getenv("REPORT_ANALYSIS_MODE") or settings.REPORT_ANALYSIS_MODE or "local"
    ).strip().lower()
    ai_configured = bool(
        analysis_mode == "ai"
        and gemini_service.is_configured()
    )
    if ai_configured:
        vital_indicators = extract_vitals_with_gemini(text_to_analyze)
        if not isinstance(vital_indicators, list) or not vital_indicators:
            raise RuntimeError("AI report interpretation returned no structured findings")
        simple_summary = generate_summary_with_gemini(vital_indicators, text_to_analyze)
        if not isinstance(simple_summary, str) or not simple_summary.strip() or simple_summary.startswith("Unable to"):
            raise RuntimeError("AI report summary was unavailable")
        analysis_mode = "ai_analysis"
    else:
        # Keep the credential-free route explicit. No values or diagnoses are inferred locally.
        vital_indicators = []
        simple_summary = (
            "LOCAL EXTRACTION PREVIEW — AI interpretation is unavailable until the backend "
            "is configured. This screen shows extracted PDF text only; it does not provide "
            "medical findings or advice."
        )
        analysis_mode = "local_extraction_preview"
    
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
            
            result = await db["reports"].insert_one(report_in.model_dump(by_alias=True, exclude=["id"]))
            return str(result.inserted_id)
        finally:
            client.close()

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        report_id = loop.run_until_complete(save_to_db())
    except Exception as exc:
        logger.error("Failed to persist processed report (%s).", type(exc).__name__)
        raise RuntimeError("Report processing failed") from None
    finally:
        loop.close()
        asyncio.set_event_loop(None)

    # Return structure matching what your frontend expects
    return {
        "status": "COMPLETED",
        "analysis_mode": analysis_mode,
        "report_id": report_id,
        "structured_entities": vital_indicators,
        "vital_indicators": vital_indicators,
        "simple_summary": simple_summary,
    }
