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
                      tools: Optional[types.ModuleType] = None, metadata: Dict[str, Any] = {},
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
