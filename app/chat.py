"""
(C) 2025 Jean-Luc Vanhulst - Valor Ventures
MIT License

The Chat interfact is PURELY for quick testing and demo purposes its like a the playground but can run with your own
functions and prompt files.
This NOT meant to be a chat app there are way better examples for that.

"""
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request, UploadFile, APIRouter, HTTPException, WebSocket, WebSocketDisconnect
import mimetypes
import io
import os
import json
import asyncio
from typing import Optional, List, Dict, Any
import logging
from pydantic import BaseModel

from app.ai_processor import Prompt


logger = logging.getLogger(__name__)
router = APIRouter(prefix='/chat')
templates = Jinja2Templates(directory="templates")

# Simple cache for prompt instances and responses
_prompt_cache = {}
_response_cache = {}


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


class WebSocketMessage(BaseModel):
    """WebSocket message model for real-time chat."""
    type: str  # 'chat_message', 'set_prompt', 'new_chat'
    content: Optional[str] = None
    prompt_name: Optional[str] = None
    previous_response_id: Optional[str] = None


class ConnectionManager:
    """Manages WebSocket connections for real-time chat."""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.user_contexts: Dict[WebSocket, Dict] = {}
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        self.user_contexts[websocket] = {
            "prompt_name": None,
            "previous_response_id": None
        }
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        if websocket in self.user_contexts:
            del self.user_contexts[websocket]
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")
    
    async def send_message(self, websocket: WebSocket, message: dict):
        try:
            await websocket.send_text(json.dumps(message))
        except Exception as e:
            logger.error(f"Error sending WebSocket message: {e}")
            self.disconnect(websocket)


manager = ConnectionManager()


async def get_prompt_by_name(prompt_name: Optional[str]) -> tuple[Optional[Prompt], Optional[str]]:
    """
    Get or create a Prompt instance for the given prompt name.

    Args:
        prompt_name: The name of the prompt to use.

    Returns:
        A tuple of (Prompt instance or None, error message or None).
    """
    if not prompt_name:
        logger.error("No prompt name provided")
        return None, "No prompt name provided"

    if prompt_name in _prompt_cache:
        return _prompt_cache[prompt_name], None

    try:
        logger.info(f"Attempting to create prompt '{prompt_name}'")
        logger.info(f"PROMPTS_DIR: {os.getenv('PROMPTS_DIR')}")
        prompt = await Prompt.create(name=prompt_name)
        _prompt_cache[prompt_name] = prompt
        return prompt, None
    except Exception as e:
        error_msg = f"Error loading prompt '{prompt_name}': {str(e)}"
        logger.error(error_msg)
        import traceback
        logger.error(traceback.format_exc())
        return None, error_msg


async def get_prompts() -> List[Dict[str, str]]:
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


async def generate_response(prompt_name: Optional[str] = None, content: Optional[str] = None,
                           previous_response_id: Optional[str] = None):
    """
    Generate a response using the specified prompt.

    Args:
        prompt_name: The name of the prompt to use.
        content: The content to send to the prompt.
        previous_response_id: ID of the previous response for conversation continuity.

    Returns:
        A dictionary with the response and status code.
    """
    logger.info(f"Generating response for prompt '{prompt_name}'")

    prompt, error_msg = await get_prompt_by_name(prompt_name)
    if not prompt:
        return {"response": error_msg or f"Prompt '{prompt_name}' not found", "status_code": 404}

    variables = {"content": content}

    # Add previous response for conversation continuity
    if previous_response_id and previous_response_id in _response_cache:
        variables["previous_response"] = _response_cache[previous_response_id]

    try:
        result = await prompt.run(variables=variables, previous_response_id=previous_response_id)

        # Cache the response for conversation continuity
        response_id = prompt.id
        _response_cache[response_id] = result

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


async def process_chat_message_async(websocket: WebSocket, message_data: WebSocketMessage):
    """Process chat message asynchronously and send updates via WebSocket."""
    try:
        # Send acknowledgment
        await manager.send_message(websocket, {
            "type": "processing",
            "status": "started",
            "message": "Processing your message..."
        })
        
        # Get user context
        context = manager.user_contexts.get(websocket, {})
        prompt_name = message_data.prompt_name or context.get("prompt_name") or "chatbot"
        previous_response_id = message_data.previous_response_id or context.get("previous_response_id")
        
        # Generate response
        response = await generate_response(
            prompt_name=prompt_name,
            content=message_data.content,
            previous_response_id=previous_response_id
        )
        
        # Update user context with new response_id
        if websocket in manager.user_contexts and response.get("response_id"):
            manager.user_contexts[websocket]["previous_response_id"] = response["response_id"]
            manager.user_contexts[websocket]["prompt_name"] = prompt_name
        
        # Send response
        if response["status_code"] == 200:
            await manager.send_message(websocket, {
                "type": "response",
                "content": response["response"],
                "response_id": response.get("response_id"),
                "files": response.get("files", []),
                "prompt_name": prompt_name
            })
        else:
            await manager.send_message(websocket, {
                "type": "error",
                "message": response["response"]
            })
            
    except Exception as e:
        logger.error(f"Error processing chat message: {e}")
        await manager.send_message(websocket, {
            "type": "error",
            "message": f"Error processing message: {str(e)}"
        })


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time chat."""
    await manager.connect(websocket)
    
    try:
        # Send welcome message
        await manager.send_message(websocket, {
            "type": "system",
            "message": "Connected to FastAPI Chat! Select a prompt to get started."
        })
        
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            message_data = WebSocketMessage.model_validate_json(data)
            
            if message_data.type == "chat_message":
                # Process chat message asynchronously
                asyncio.create_task(process_chat_message_async(websocket, message_data))
                
            elif message_data.type == "set_prompt":
                # Update user's prompt selection
                if websocket in manager.user_contexts:
                    manager.user_contexts[websocket]["prompt_name"] = message_data.prompt_name
                await manager.send_message(websocket, {
                    "type": "prompt_set",
                    "prompt_name": message_data.prompt_name,
                    "message": f"Switched to {message_data.prompt_name} prompt"
                })
                
            elif message_data.type == "new_chat":
                # Clear conversation history
                if websocket in manager.user_contexts:
                    manager.user_contexts[websocket]["previous_response_id"] = None
                await manager.send_message(websocket, {
                    "type": "chat_cleared",
                    "message": "Started new conversation"
                })
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


@router.post("/thread/")
async def get_chat_response(data: PromptRequest):
    """
    Called from javascript when the user sends a message.
    """
    if data.content == "":
        return ""

    response = await generate_response(
        prompt_name=data.prompt_name or "chatbot",
        content=data.content,
        previous_response_id=data.previous_response_id
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
    This function uploads a file directly to OpenAI for use with prompts
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
        
        return JSONResponse({
            "status": "success", 
            "message": "File uploaded successfully", 
            "file": {"file_id": file_id, "filename": file.filename}
        })
    finally:
        # Clean up temporary file
        os.unlink(temp_file_path)


@router.get("/get_prompts", response_class=JSONResponse)
async def list_prompts():
    """
    This function gets the available prompts
    """
    prompts = await get_prompts()
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
