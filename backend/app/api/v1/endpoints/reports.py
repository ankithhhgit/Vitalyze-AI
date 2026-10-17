import logging
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, UploadFile, File, HTTPException, status, Depends
from typing import List, Optional
from pathlib import Path
from celery.result import AsyncResult
from celery import chain
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.tasks.celery_app import celery
from app.tasks.report_processing import task_extract_data_from_pdf, task_run_ai_analysis
from app.models.user import UserInDB
from app.models.report import ReportInDB
from app.api.v1.endpoints.auth import get_current_active_user, get_current_user
from app.db.mongodb import get_database
from app.tasks.report_processing import ReportExtractionError

router = APIRouter()
logger = logging.getLogger(__name__)

UPLOAD_DIR = Path("temp_uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
MAX_REPORT_SIZE_BYTES = 15 * 1024 * 1024


@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_report(
    file: UploadFile = File(...),
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Stores a bounded PDF locally and queues extraction/analysis. Cloud storage is
    intentionally not contacted by this local demo endpoint.
    """
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Invalid file type. Only PDFs allowed.")

    if not file.filename:
        raise HTTPException(status_code=400, detail="Choose a PDF file to upload.")

    original_filename = Path(file.filename).name
    safe_filename = f"{current_user.id}_{uuid.uuid4().hex}_{original_filename}"
    file_path = UPLOAD_DIR / safe_filename

    try:
        size = 0
        with file_path.open("wb") as buffer:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_REPORT_SIZE_BYTES:
                    raise HTTPException(status_code=413, detail="PDF is too large. Maximum size is 15 MB.")
                buffer.write(chunk)

        with file_path.open("rb") as stored_file:
            if not stored_file.read(5).startswith(b"%PDF-"):
                raise HTTPException(status_code=400, detail="The selected file is not a valid PDF.")
        
        workflow = chain(
            task_extract_data_from_pdf.s(str(file_path)),
            task_run_ai_analysis.s(
                user_id=str(current_user.id), 
                filename=original_filename,
                gcs_path=None
            )
        )
        
        task = workflow.apply_async()

        try:
            await db["report_jobs"].insert_one(
                {
                    "_id": task.id,
                    "user_id": str(current_user.id),
                    "filename": file.filename,
                    "created_at": datetime.now(timezone.utc),
                }
            )
        except Exception:
            logger.exception("Failed to persist report task ownership")
            task.revoke(terminate=False)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to record report processing status.",
            )
        
        return {
            "task_id": task.id, 
            "message": "Report uploaded successfully. Analysis started."
        }
        
    except HTTPException:
        file_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        file_path.unlink(missing_ok=True)
        logger.error("Report upload failed (%s).", type(exc).__name__)
        raise HTTPException(status_code=500, detail="Internal Server Error during upload.")
    finally:
        file.file.close()


@router.get("/status/{task_id}")
async def get_task_status(
    task_id: str,
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Check the status of the background analysis chain.
    """
    try:
        job = await db["report_jobs"].find_one(
            {"_id": task_id, "user_id": str(current_user.id)}
        )
    except Exception:
        logger.exception("Failed to load report task ownership")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Report status is temporarily unavailable.",
        )

    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report task not found")

    task_result = AsyncResult(task_id, app=celery)
    
    response = {"status": task_result.state}
    
    if task_result.state == 'SUCCESS':
        response["result"] = task_result.result
    elif task_result.state == 'FAILURE':
        if isinstance(task_result.info, ReportExtractionError):
            response["error"] = str(task_result.info)
        elif type(task_result.info).__name__ == "RuntimeError" and str(task_result.info).startswith("Report processing failed"):
            response["error"] = "Report could not be saved. Please try again."
        elif type(task_result.info).__name__ == "RuntimeError" and str(task_result.info).startswith("AI report"):
            response["error"] = "AI interpretation failed; the report was not saved."
        else:
            response["error"] = "Report processing failed. The report was not saved."
        
    return response


@router.get("/history", response_model=List[ReportInDB])
async def get_user_report_history(
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Fetches all past analyzed reports for the logged-in user.
    This data is used to generate the History Charts on the frontend.
    """
    reports = []
    
    cursor = db["reports"].find({"user_id": str(current_user.id)}).sort("upload_date", -1)
    
    async for doc in cursor:
        reports.append(ReportInDB(**doc))
        
    return reports
