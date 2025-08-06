"""
This file is responsible for routing the incoming requests to the respective endpoints.
Available endpoints:
- /demo/list_prompts - List all available prompts
- /demo/joke - Simple test endpoint using the joker prompt
- /demo/prompt/{prompt_name} - Execute a prompt with JSON payload
- /demo/upload_file - Upload a single file and get file_id
- /demo/prompt_with_files/{prompt_name} - Execute a prompt with embedded files (recommended)
- /demo/graph_report?prompt=... - Generate PDF report with embedded charts using graph_demo prompt

"""
from fastapi.responses import JSONResponse, HTMLResponse, Response
from fastapi import UploadFile, APIRouter, Form, Query
from typing import List, Optional

from app.chat import PromptRequest, get_prompt_by_name, generate_response
from app.ai_processor import Prompt
from app.pdf_utils import PDFGenerator
import logging
from app.tools import markdown_to_html

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/demo')


@router.get("/list_prompts", response_class=HTMLResponse)
async def list_prompts():
    """
    This is a test endpoint that can be used to list all the prompts that are available.
    """
    from app.chat import get_prompts
    prompts = await get_prompts()
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
    from app.chat import generate_response
    return await generate_response(
        prompt_name=prompt_name,
        content=data.content,
        previous_response_id=data.previous_response_id
    )


@router.post("/upload_file", response_class=JSONResponse)
async def create_upload_file(file: UploadFile):
    """
    This is a test endpoint that expects a form data with the file to be uploaded.
    It uploads the file directly to OpenAI for use with prompts.

    Returns a file object if successful. Make sure to store the file_id as it will be used for further interactions.
    """
    import tempfile
    import os
    
    # Save file temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file.filename}") as temp_file:
        content_bytes = await file.read()
        temp_file.write(content_bytes)
        temp_file_path = temp_file.name
    
    try:
        # Create a temporary prompt instance to upload the file
        temp_prompt = Prompt(name="temp")
        file_id = await temp_prompt.upload_file(temp_file_path, file.filename)
        
        return {"file_id": file_id, "filename": file.filename}
    finally:
        # Clean up temporary file
        os.unlink(temp_file_path)


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
    prompt, error_msg = await get_prompt_by_name(prompt_name)
    if not prompt:
        return {"response": error_msg or f"Prompt '{prompt_name}' not found", "status_code": 404}
    
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


@router.get("/graph_report", response_class=Response)
async def generate_graph_report_pdf(prompt: str = Query(..., description="The prompt/question for generating graphs and charts")):
    """
    Generate a PDF report using the graph_demo prompt with embedded charts and graphs.
    
    This endpoint:
    1. Uses the 'graph_demo' prompt to generate charts/graphs based on the input
    2. Converts the markdown response to PDF format
    3. Embeds any generated files (charts, graphs, images) directly in the PDF
    4. Returns the complete PDF as a downloadable file
    
    **Example Usage:**
    GET /demo/graph_report?prompt=Create a revenue chart for Acme Corp for 2024 and put it on a billboard
    
    **Response:**
    Returns a PDF file with the generated content and embedded charts/graphs.
    
    **Production Considerations:**
    This demo endpoint waits for the AI response before returning, which can take 30-120+ seconds
    for complex chart generation. In production, you would typically:
    1. Accept the request and return immediately with a job_id
    2. Process the AI request asynchronously in the background
    3. Generate and save the PDF when complete
    4. Notify the client via webhook, polling endpoint, or WebSocket
    
    This synchronous approach is only suitable for demos/local development.
    """
    try:
        logger.info(f"Generating PDF report for prompt: {prompt}")
        
        # Generate response using the graph_demo prompt
        response = await generate_response(
            prompt_name="graph_demo",
            content=prompt,
            previous_response_id=None
        )
        
        if response["status_code"] != 200:
            return Response(
                content=f"Error generating report: {response['response']}",
                status_code=response["status_code"],
                media_type="text/plain"
            )
        
        # Extract content and files
        markdown_content = response["response"]
        output_files = response.get("files", [])
        
        logger.info(f"Generated response with {len(output_files)} files")
        
        # Generate PDF
        pdf_generator = PDFGenerator()
        pdf_content = await pdf_generator.generate_pdf(
            markdown_content=markdown_content,
            output_files=output_files,
            title="Graph Report - Generated by AI"
        )
        
        logger.info(f"Generated PDF with {len(pdf_content)} bytes")
        
        # Return PDF as response
        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": "attachment; filename=graph_report.pdf",
                "Content-Length": str(len(pdf_content))
            }
        )
        
    except Exception as e:
        logger.error(f"Error generating PDF report: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return Response(
            content=f"Error generating PDF report: {str(e)}",
            status_code=500,
            media_type="text/plain"
        )
