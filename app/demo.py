"""
This file is responsible for routing the incoming requests to the respective endpoints.
Available endpoints:
- /demo/list_prompts
- /demo/joke
- /demo/prompt/{prompt_name}
- /demo/upload_file
- /demo/prompt_demo

"""
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi import UploadFile, APIRouter

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


@router.get("/prompt_demo", response_class=HTMLResponse)
async def file_demo():
    """
    A demo that shows how to use files with the prompt system.
    """
    files = []

    prompt = await Prompt.create(name="research")
    response = await prompt.run(variables={
        "content": "Create a summary of the attached files",
        "file_contents": "" if not files else "\n\n".join(files)
    })

    return markdown_to_html(response)
