"""
This file is responsible for routing the incoming requests to the respective endpoints.
"""
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi import UploadFile, APIRouter
from pydantic import BaseModel
from typing import Optional, Dict, Any

from app.assistant import Assistant_call, AssistantRequest
import logging
from app.tools import markdown_to_html

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/demo')
assistant = Assistant_call()

@router.get("/list_assistants", response_class=HTMLResponse)
async def list_assistants():
    """
    This is a test endpoint that can be used to list all the assistants that are available.
    """
    assistants = await assistant.get_assistants()
    html = "<html><body><h1>Available Assistants</h1>"
    for a in assistants:
        html += f"<p>{a['assistant_id']} - {a['assistant_name']}</p>"
    html += "</body></html>"
    return HTMLResponse(content=html, status_code=200)

@router.get("/joke", response_class=JSONResponse)
async def assistant_test():
    """
    This is a test endpoint that can be used to test the assistant.
    
    This is the simplest way to 'run' an Assistant. Get the assistant object, provide the name of the Assistant 
    ('joker' in this case) and the prompt. 
    """
    response = await assistant.generate(assistant_name="joker", content="tell me a joke about sales people")  
    return response

@router.post("/assistant/{assistant_name}", response_class=JSONResponse)
async def run_assistant(assistant_name: str, data: AssistantRequest):
    """
    A simple example endpoint that can be used to call any Assistant with a prompt. Give it the name of the Assistant 
    in the request and the {"content": "your prompt here"} as the body of the request.
    
    What it returns depends on the settings for that particular Assistant. This can be text or some json if the assistant 
    is set to return json.
    """
    return await assistant.generate(
        assistant_name=assistant_name, 
        content=data.content, 
        files=data.file_ids,
        metadata=data.metadata,
        previous_response_id=data.previous_response_id
    )

@router.post("/upload_file", response_class=JSONResponse)
async def create_upload_file(file: UploadFile):    
    """
    This is a test endpoint that expects a form data with the file to be uploaded.
    It can then be used by any Assistant that has access to the file storage.
    YOU HAVE TO STORE THE FILE_ID if you want to use it in your Assistant call.
    
    Returns a file object if successful. Make sure to store the file_id as it will be used for further interactions.
    """
    file_upload = await assistant.uploadfile(file_content=file.file, filename=file.filename)
    return file_upload

@router.get("/assistant_demo", response_class=HTMLResponse)
async def file_demo():
    """
    A demo that shows how to use files with the assistant.
    """
    files = []
    
    result = await assistant.generate(
        assistant_name="research", 
        content="Create a summary of the attached files", 
        files=files
    )
    
    return markdown_to_html(result['response'])
