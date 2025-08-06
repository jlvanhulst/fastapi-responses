"""
This file is responsible for routing the incoming requests to the respective endpoints.
Available endpoints:
- /demo/list_prompts - List all available prompts
- /demo/joke - Simple test endpoint using the joker prompt
- /demo/prompt/{prompt_name} - Execute a prompt with JSON payload
- /demo/upload_file - Upload a single file and get file_id
- /demo/prompt_with_files/{prompt_name} - Execute a prompt with embedded files (recommended)

"""
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi import UploadFile, APIRouter, Form
from typing import List, Optional

from app.chat import PromptHandler, PromptRequest
from app.ai_processor import Prompt
import logging
from app.tools import markdown_to_html

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/demo')
prompt_handler = PromptHandler()


@router.get("/list_prompts", response_class=HTMLResponse)
async def list_prompts():
    """
    This is a test endpoint that can be used to list all the prompts that are available.
    """
    prompts = await prompt_handler.get_prompts()
    html = "<html><body><h1>Available Prompts</h1>"
    for p in prompts:
        html += f"<p>{p['prompt_id']} - {p['prompt_name']}</p>"
    html += "</body></html>"
    return HTMLResponse(content=html, status_code=200)


@router.get("/joke", response_class=JSONResponse)
async def prompt_test():
    """
    This is a test endpoint that can be used to test the prompt system.

    This is the simplest way to run a prompt. Create a Prompt instance directly and run it.
    """
    prompt = await Prompt.create(name="joker")
    response = await prompt.run(variables={"content": "tell me a joke about sales people"})
    return {"response": response, "status_code": 200}


@router.post("/prompt/{prompt_name}", response_class=JSONResponse)
async def run_prompt(prompt_name: str, data: PromptRequest):
    """
    A simple example endpoint that can be used to call any prompt. Give it the name of the prompt
    in the request and the {"content": "your message here"} as the body of the request.

    What it returns depends on the settings for that particular prompt. This can be text or some json if the prompt
    is set to return json.
    """
    return await prompt_handler.generate(
        prompt_name=prompt_name,
        content=data.content,
        files=data.file_ids,
        metadata=data.metadata,
        previous_response_id=data.previous_response_id
    )


@router.post("/upload_file", response_class=JSONResponse)
async def create_upload_file(file: UploadFile):
    """
    This is a test endpoint that expects a form data with the file to be uploaded.
    It can then be used by any prompt that has access to the file storage.
    YOU HAVE TO STORE THE FILE_ID if you want to use it in your prompt call.

    Returns a file object if successful. Make sure to store the file_id as it will be used for further interactions.
    """
    file_upload = await prompt_handler.uploadfile(file_content=file.file, filename=file.filename)
    return file_upload


@router.post("/prompt_with_files/{prompt_name}", response_class=JSONResponse)
async def run_prompt_with_files(
    prompt_name: str,
    content: str = Form(..., description="The message content to send to the prompt"),
    files: Optional[List[UploadFile]] = None,
    previous_response_id: Optional[str] = Form(None, description="Previous response ID for conversation continuity")
):
    """
    Run a prompt with embedded files that are automatically uploaded and processed.
    
    This endpoint accepts:
    - prompt_name: The name of the prompt to use (in the URL path)
    - content: The message content (form field)
    - files: One or more files to upload and attach (optional)
    - previous_response_id: For conversation continuity (optional)
    
    The files are automatically uploaded and their file_ids are added to the prompt execution.
    
    **IMPORTANT - Production Considerations:**
    This demo endpoint waits for the AI response before returning, which can take 10-60+ seconds.
    In production, you would typically:
    1. Accept the request and return immediately with a job_id
    2. Process the AI request asynchronously in the background
    3. Save results to database/storage when complete
    4. Notify the client via webhook, polling endpoint, or WebSocket
    
    This synchronous approach is only suitable for demos/local development.
    
    Example usage with curl:
    curl -X POST "http://localhost:8000/demo/prompt_with_files/research" \
         -F "content=Analyze these files and create a summary" \
         -F "files=@document1.pdf" \
         -F "files=@chart.png"
    """
    # Get the prompt instance first
    prompt = await prompt_handler.get_prompt_by_name(prompt_name)
    if not prompt:
        return {"response": f"Prompt '{prompt_name}' not found", "status_code": 404}
    
    openai_file_ids = []
    
    # Upload any provided files to OpenAI
    if files:
        for file in files:
            if file.filename:  # Skip empty file uploads
                logger.info(f"Uploading file to OpenAI: {file.filename}")
                
                # Save file temporarily
                import tempfile
                import os
                with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file.filename}") as temp_file:
                    content_bytes = await file.read()
                    temp_file.write(content_bytes)
                    temp_file_path = temp_file.name
                
                try:
                    # Upload to OpenAI
                    openai_file_id = await prompt.upload_file(temp_file_path, file.filename)
                    openai_file_ids.append(openai_file_id)
                    logger.info(f"File uploaded to OpenAI with ID: {openai_file_id}")
                finally:
                    # Clean up temporary file
                    os.unlink(temp_file_path)
    
    # Execute the prompt with variables and previous_response_id
    variables = {"content": content}
    response_text = await prompt.run(
        variables=variables, 
        previous_response_id=previous_response_id
    )
    
    # Build response
    response = {
        "response": response_text,
        "status_code": 200,
        "response_id": prompt.id,
        "uploaded_files": len(openai_file_ids),
        "openai_file_ids": openai_file_ids,
        "files": prompt.output_files if hasattr(prompt, 'output_files') else []
    }
    
    return response
