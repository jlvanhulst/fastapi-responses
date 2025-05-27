"""
(C) 2024 Jean-Luc Vanhulst - Valor Ventures 
MIT License

An async assistant class that can be used to interact with the vic-20 Prompt API.

The most basic call is 

result = await assistant.generate(assistant_name=assistant_name, content=data.content)
where assistant_name is the name of the assistant to use and content is the prompt to use.
this will return json with the response and status_code

optional parameters are:
    files: list of file paths to be used by the assistant
    
"""
import asyncio
import json
import os
import types
from typing import Optional, List, Dict, Any
import logging
from functools import partial
from pydantic import BaseModel, Field

from app.ai_processor import Prompt
from app.ai_tools import register_tools, handle_openai_function

logger = logging.getLogger(__name__)

class Singleton(type):
    """
    Metaclass for creating singleton classes
    """
    _instances = {}
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]

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

class AssistantRequest(BaseModel):
    """
    This is the request model for the assistant.
    
    content: str is mandatory and is the prompt for the assistant.
    file_ids: Optional[list[str]] = None is optional and is a list of file ids to be used by the assistant.
    """
    content: str
    file_ids: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None
    assistant_name: Optional[str] = None
    previous_response_id: Optional[str] = None

class Assistant_call(metaclass=Singleton):
    """
    This is the Assistant class which is used to handle prompts for the vic-20 Prompt API.
    It is a singleton class which means that only one instance of the class is created and reused.
    """
    def __init__(self) -> None:
        self.assistants = {}  # Cache for assistant prompts
        self.files = {}  # Cache for uploaded files
        self.responses = {}  # Cache for responses (used for conversation continuity)
        
        from app.tools import webscrape
        register_tools("webscrape", function=webscrape)
    
    async def get_assistant_by_name(self, assistant_name: str) -> Prompt:
        """
        Get or create a Prompt instance for the given assistant name.
        
        Args:
            assistant_name: The name of the assistant/prompt to use.
            
        Returns:
            A Prompt instance.
        """
        if assistant_name in self.assistants:
            return self.assistants[assistant_name]
        
        try:
            logger.info(f"Attempting to create prompt for assistant '{assistant_name}'")
            logger.info(f"PROMPTS_DIR: {os.getenv('PROMPTS_DIR')}")
            prompt = await Prompt.create(name=assistant_name)
            self.assistants[assistant_name] = prompt
            return prompt
        except Exception as e:
            logger.error(f"Error creating prompt for assistant '{assistant_name}': {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    async def get_assistants(self) -> List[Dict[str, str]]:
        """
        Get a list of available assistants based on prompt templates.
        
        Returns:
            A list of dictionaries with assistant_id and assistant_name.
        """
        import os
        from app.ai_processor import PROMPTS_DIR
        assistants = []
        
        logger.info(f"Looking for prompts in: {PROMPTS_DIR}")
        if os.path.exists(PROMPTS_DIR):
            for filename in os.listdir(PROMPTS_DIR):
                if filename.endswith(".md"):
                    assistant_name = filename[:-3]  # Remove .md extension
                    assistants.append({
                        "assistant_id": assistant_name,
                        "assistant_name": assistant_name
                    })
            logger.info(f"Found assistants: {[a['assistant_id'] for a in assistants]}")
        else:
            logger.error(f"Prompts directory not found: {PROMPTS_DIR}")
        
        return assistants
    
    async def generate(self, assistant_name: str = None, content: str = None, 
                      tools: types.ModuleType = None, metadata: Dict[str, Any] = {},
                      files: List[str] = [], previous_response_id: str = None):
        """
        Generate a response using the specified assistant/prompt.
        
        Args:
            assistant_name: The name of the assistant/prompt to use.
            content: The content/prompt to send to the assistant.
            tools: The tools module to use for function calls.
            metadata: Additional metadata to include.
            files: List of file paths to include.
            previous_response_id: ID of the previous response for conversation continuity.
            
        Returns:
            A dictionary with the response and status code.
        """
        logger.info(f"Generating response for assistant '{assistant_name}'")
        
        prompt = await self.get_assistant_by_name(assistant_name)
        if not prompt:
            return {"response": f"Assistant '{assistant_name}' not found", "status_code": 404}
        
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
            result = await prompt.run(variables=variables)
            
            import uuid
            response_id = str(uuid.uuid4())
            self.responses[response_id] = result
            
            logger.info(f"Generated response: {result}")
            return {"response": result, "status_code": 200, "response_id": response_id}
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return {"response": f"Error generating response: {str(e)}", "status_code": 500}
    
    async def uploadfile(self, file_content=None, filename=None) -> Dict[str, str]:
        """
        Upload a file for use with assistants.
        
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
