"""
This file contains the chat router for the FastAPI application.
"""
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request, UploadFile, APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
import mimetypes
import io

from app.prompt import PromptHandler, PromptRequest
from app.ai_processor import Prompt
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
        content={
            "text": {"value": response["response"]},
            "files": response.get("files", [])
        },
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

@router.get("/prompt_details/{prompt_name}", response_class=JSONResponse)
async def get_prompt_details(prompt_name: str):
    """
    Get detailed information about a specific prompt including instructions, tools, and model
    """
    try:
        from app.ai_processor import Prompt
        prompt_data = await Prompt.load(prompt_name)
        return {
            "status": "success",
            "data": {
                "name": prompt_name,
                "instructions": prompt_data["instructions"],
                "model": prompt_data["model"],
                "tools": prompt_data["tools"],
                "tool_schemas": prompt_data.get("tool_schemas", [])
            }
        }
    except Exception as e:
        logger.error(f"Error getting prompt details for {prompt_name}: {e}")
        return {"status": "error", "message": f"Prompt not found: {str(e)}"}

@router.get("/files/{container_id}/{file_id}")
async def get_file(container_id: str, file_id: str, filename: str = None):
    """
    Serve files from OpenAI responses API
    """
    try:
        from openai import AsyncOpenAI
        
        # Get file content directly from OpenAI API
        client = AsyncOpenAI()
        response_content = await client.containers.files.content.retrieve(
            file_id=file_id,
            container_id=container_id,
        )
        
        # Read the actual bytes from the response
        file_content = response_content.read()
        
        # Get file info from OpenAI API to determine proper content type and filename
        file_info = await client.containers.files.retrieve(
            file_id=file_id,
            container_id=container_id
        )
        
        # Use actual filename if available, otherwise use file_id with guessed extension
        actual_filename = getattr(file_info, 'filename', None) or getattr(file_info, 'name', None)
        if not actual_filename:
            # Try to detect file type from content and add appropriate extension
            if file_content.startswith(b'\x89PNG'):
                actual_filename = f"{file_id}.png"
            elif file_content.startswith(b'\xff\xd8\xff'):
                actual_filename = f"{file_id}.jpg"
            elif file_content.startswith(b'GIF8'):
                actual_filename = f"{file_id}.gif"
            elif b'matplotlib.figure' in file_content[:1000] or b'plot' in file_content[:1000].lower():
                actual_filename = f"{file_id}.png"  # Assume matplotlib plots are PNG
            else:
                actual_filename = f"{file_id}.txt"  # Default fallback
        
        # Determine content type from filename
        content_type = mimetypes.guess_type(actual_filename)[0] or "application/octet-stream"
        
        # Return file as streaming response
        return StreamingResponse(
            io.BytesIO(file_content),
            media_type=content_type,
            headers={"Content-Disposition": f"inline; filename=\"{actual_filename}\""}
        )
    except Exception as e:
        logger.error(f"Error serving file {container_id}/{file_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=404, detail=f"File not found: {str(e)}")
