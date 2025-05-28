"""
This file contains the chat router for the FastAPI application.
"""
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request, UploadFile, APIRouter
from pydantic import BaseModel
from typing import Optional, Dict, Any

from app.prompt import PromptHandler, PromptRequest
import logging

prompt_handler = PromptHandler()
logger = logging.getLogger(__name__)

router = APIRouter(prefix='/chat')
templates = Jinja2Templates(directory="templates")

@router.post("/thread/")
async def get_chat_response(data: PromptRequest):
    """
    Called from javascript when the user sends a message.
    """
    if data.content == "":
        return ""
    
    response = await prompt_handler.generate(
        prompt_name=data.prompt_name or "chatbot",
        content=data.content,
        previous_response_id=data.previous_response_id,
        files=data.file_ids or []
    )
    
    return JSONResponse(
        content={"text": {"value": response["response"]}},
        headers={"X-Response-Id": response.get("response_id", "")}
    )

@router.get("/", response_class=HTMLResponse)
async def chat_frontend(request: Request):
    """
    This function renders the chat frontend
    """
    return templates.TemplateResponse("index.html", {"request": request})

@router.post("/upload", response_class=JSONResponse)
async def upload_file(file: UploadFile):
    """
    This function uploads a file for use with prompts
    """
    file_upload = await prompt_handler.uploadfile(file_content=file.file, filename=file.filename)
    return JSONResponse({"status": "success", "message": "File uploaded successfully", "file": file_upload})

@router.get("/get_prompts", response_class=JSONResponse)
async def get_prompts():
    """
    This function gets the available prompts
    """
    prompts = await prompt_handler.get_prompts()
    return {"status": "success", "message": "Prompts retrieved successfully", "data": prompts}
