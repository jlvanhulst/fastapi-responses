"""
(C) 2025 Jean-Luc Vanhulst - Valor Ventures
MIT License

The Chat interfact is PURELY for quick testing and demo purposes its like a the playground but can run with your own
functions and prompt files.
This NOT meant to be a chat app there are way better examples for that.

"""
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request, UploadFile, APIRouter, HTTPException
import mimetypes
import io
import os
from typing import Optional, List, Dict, Any
import logging
from pydantic import BaseModel

from app.ai_processor import Prompt
from app.ai_tools import register_tools


logger = logging.getLogger(__name__)
router = APIRouter(prefix='/chat')
templates = Jinja2Templates(directory="templates")


class Singleton(type):
    """
    Metaclass for creating singleton classes
    """
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class PromptRequest(BaseModel):
    """
    This is the request model for the prompt.

    content: str is mandatory and is the content for the prompt.
    file_ids: Optional[list[str]] = None is optional and is a list of file ids to be used by the prompt.
    """
    content: str
    file_ids: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None
    prompt_name: Optional[str] = None
    previous_response_id: Optional[str] = None


class PromptHandler(metaclass=Singleton):
    """
    This is the PromptHandler class which is used to handle interactions with the Prompt API.
    It is a singleton class which means that only one instance of the class is created and reused.
    """
    def __init__(self) -> None:
        self.prompts = {}  # Cache for prompt instances
        self.files = {}  # Cache for uploaded files
        self.responses = {}  # Cache for responses (used for conversation continuity)

        from app.tools import webscrape
        register_tools("webscrape", function=webscrape)

    async def get_prompt_by_name(self, prompt_name: Optional[str]) -> Optional[Prompt]:
        """
        Get or create a Prompt instance for the given prompt name.

        Args:
            prompt_name: The name of the prompt to use.

        Returns:
            A Prompt instance or None if not found.
        """
        if not prompt_name:
            logger.error("No prompt name provided")
            return None

        if prompt_name in self.prompts:
            return self.prompts[prompt_name]

        try:
            logger.info(f"Attempting to create prompt '{prompt_name}'")
            logger.info(f"PROMPTS_DIR: {os.getenv('PROMPTS_DIR')}")
            prompt = await Prompt.create(name=prompt_name)
            self.prompts[prompt_name] = prompt
            return prompt
        except Exception as e:
            logger.error(f"Error creating prompt '{prompt_name}': {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    async def get_prompts(self) -> List[Dict[str, str]]:
        """
        Get a list of available prompts based on prompt templates.

        Returns:
            A list of dictionaries with prompt_id and prompt_name.
        """
        import os
        from app.ai_processor import PROMPTS_DIR
        prompts = []

        logger.info(f"Looking for prompts in: {PROMPTS_DIR}")
        if os.path.exists(PROMPTS_DIR):
            for filename in os.listdir(PROMPTS_DIR):
                if filename.endswith(".md"):
                    prompt_name = filename[:-3]  # Remove .md extension
                    prompts.append({
                        "prompt_id": prompt_name,
                        "prompt_name": prompt_name
                    })
            logger.info(f"Found prompts: {[p['prompt_id'] for p in prompts]}")
        else:
            logger.error(f"Prompts directory not found: {PROMPTS_DIR}")

        return prompts

    async def generate(self, prompt_name: Optional[str] = None, content: Optional[str] = None,
                       metadata: Dict[str, Any] = {},
                       files: List[str] = [], previous_response_id: Optional[str] = None):
        """
        Generate a response using the specified prompt.

        Args:
            prompt_name: The name of the prompt to use.
            content: The content to send to the prompt.
            tools: The tools module to use for function calls.
            metadata: Additional metadata to include.
            files: List of file paths to include.
            previous_response_id: ID of the previous response for conversation continuity.

        Returns:
            A dictionary with the response and status code.
        """
        logger.info(f"Generating response for prompt '{prompt_name}'")

        prompt = await self.get_prompt_by_name(prompt_name)
        if not prompt:
            return {"response": f"Prompt '{prompt_name}' not found", "status_code": 404}

        variables = {"content": content}

        if previous_response_id and previous_response_id in self.responses:
            variables["previous_response"] = self.responses[previous_response_id]

        if files:
            file_contents = []
            for file_id in files:
                if file_id in self.files:
                    file_info = self.files[file_id]
                    with open(file_info.file_path, 'r') as f:
                        file_contents.append(f"File: {file_info.filename}\n{f.read()}")

            if file_contents:
                variables["file_contents"] = "\n\n".join(file_contents)

        try:
            result = await prompt.run(variables=variables, previous_response_id=previous_response_id)

            # Use the actual OpenAI response ID instead of generating our own UUID
            response_id = prompt.id
            self.responses[response_id] = result

            logger.info(f"Generated response: {result}")
            return {
                "response": result,
                "status_code": 200,
                "response_id": response_id,
                "files": prompt.output_files
            }
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return {"response": f"Error generating response: {str(e)}", "status_code": 500}

    async def uploadfile(self, file_content: Any, filename: str) -> Dict[str, str]:
        """
        Upload a file for use with prompts.

        Args:
            file_content: The content of the file.
            filename: The name of the file.

        Returns:
            A dictionary with file_id and filename.
        """
        import os
        import uuid

        uploads_dir = os.path.join(os.getcwd(), "uploads")
        os.makedirs(uploads_dir, exist_ok=True)

        file_id = str(uuid.uuid4())

        file_path = os.path.join(uploads_dir, f"{file_id}_{filename}")
        with open(file_path, 'wb') as f:
            f.write(file_content.read())

        file_upload = FileUpload(file_path=file_path, filename=filename)
        self.files[file_id] = file_upload

        return {"file_id": file_id, "filename": filename}


prompt_handler = PromptHandler()


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


"""
(C) 2024 Jean-Luc Vanhulst - Valor Ventures
MIT License

An async prompt handler class that can be used to interact with the Prompt API.

The most basic call is

result = await prompt_handler.generate(prompt_name=prompt_name, content=data.content)
where prompt_name is the name of the prompt to use and content is the content to use.
this will return json with the response and status_code

optional parameters are:
    files: list of file paths to be used by the prompt

"""

logger = logging.getLogger(__name__)


class FileUpload(BaseModel):
    """
    A BaseModel class for handling file uploads.

    Attributes:
        file_path: str - The path to the uploaded file.
        filename: str - The name of the file being uploaded.
    """
    file_path: str
    filename: str

    @property
    def extension(self) -> str:
        return self.filename.split('.')[-1].lower()

    @property
    def vision(self) -> bool:
        image_extensions = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff']
        return self.extension in image_extensions

    @property
    def retrieval(self) -> bool:
        retrieval_extensions = [
            'c', 'cs', 'cpp', 'doc', 'docx', 'html', 'java', 'json', 'md', 'pdf', 'php',
            'pptx', 'py', 'rb', 'tex', 'txt', 'css', 'js', 'sh', 'ts'
        ]
        return self.extension in retrieval_extensions
