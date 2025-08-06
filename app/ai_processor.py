import importlib
import json
import mimetypes
import os
from datetime import datetime

import aiofiles
from fastapi import HTTPException
from openai import AsyncOpenAI

from app.ai_tools import FunctionRequest, JsonResponse, frommarkdown, handle_openai_function

PROMPTS_DIR = os.getenv("PROMPTS_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prompts"))
AI_MODEL = os.getenv("AI_MODEL", "openai/gpt-4.1")


class SafeDict(dict):
    def __missing__(self, key):
        return "n/a"


class OpenAIAttachment():
    openai_file_id: str
    name: str = None
    mime_type: str = None
    container_id: str = None

    async def read(self) -> bytes:
        client = AsyncOpenAI()
        if self.container_id:
            file = await client.containers.files.retrieve(self.openai_file_id, self.container_id)
        else:
            file = await client.files.retrieve(self.openai_file_id)
        if file:
            self.name = file.filename
            # guess the mime type
            self.mime_type = mimetypes.guess_type(file.filename)[0]
        resp = await client.files.content(self.openai_file_id)
        return resp


class Prompt:
    '''
    Creates a Prompt object that can run on the Responses API using Tools, Code Interpreter
    The definition of the prompt is in a markdown file in the prompts directory.

    The prompt file must contain @@ Instruction and @@ Prompt sections.
    The prompt file can also contain @@ Model, @@ Tools, @@ Response, @@ Handoffs sections.

    The @@ Model section can be used to specify the model to use.
    syntax: @@ Model: openai/gpt-4.1
    The @@ Tools section can be used to specify the tools to use.
    tools can be specifed with there file name and tool name. Buitl in tools supported in OpenAI
    - code_interpreter, web_search

    The @@ Response section can be used to specify the response class to use.
    - include the file name of the response class definition.

    @@ Handoffs section is only relevant if using PromptAgent

    Gemini support in not as complete as OpenAI.
    '''
    _cache = {}

    @classmethod
    async def load(cls, name: str) -> dict:
        if name in cls._cache:
            return cls._cache[name]

        file_path = os.path.join(PROMPTS_DIR, f"{name}.md")
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail=f"Prompt file {file_path} not found")

        async with aiofiles.open(file_path, mode="r") as f:
            content = await f.read()

        # Parse sections based on markers (case-insensitive, allowing any spacing after @@)
        import re

        section_pattern = re.compile(r"^@@\s*(\S+)", re.IGNORECASE)
        sections = {}
        current_section = None
        for line in content.splitlines():
            match = section_pattern.match(line)
            if match:
                section_name = match.group(1).strip().lower()
                current_section = section_name
                sections[current_section] = ""
            elif current_section is not None:
                sections[current_section] += line + "\n"

        # Ensure mandatory sections exist: either 'instruction' or 'instructions', and 'prompt'
        if ("instruction" not in sections and "instructions" not in sections) or (
            "prompt" not in sections
        ):
            raise HTTPException(
                status_code=400,
                detail="Prompt file must contain @@ Instruction and @@ Prompt sections",
            )

        instructions = (sections.get("instruction") or sections.get("instructions")).strip()
        prompt = sections["prompt"].strip()

        model = sections.get("model", None)
        if isinstance(model, str):
            model = model.strip()
        handoffs = []
        if "handoffs" in sections:
            handoffs = re.split(r"[\s,;]+", sections["handoffs"].strip())
            handoffs = [handoff for handoff in handoffs if handoff]
        tools = []
        tool_schemas = []
        if "tools" in sections:
            tools_list = re.split(r"[\s,;]+", sections["tools"].strip())
            tools = [tool for tool in tools_list if tool]
            # Check for mcp.tools directive - remove this check since MCP is deprecated
            if "mcp.tools" in tools:
                # Remove mcp.tools from the list as it's not an actual tool
                tools = [tool for tool in tools if tool != "mcp.tools"]
            # Get schemas for all tools
            tool_schemas = []
            for tool in tools:
                if tool == "code_interpreter":
                    tool_schemas.append({"type": "code_interpreter"})
                elif tool in ("web_search_preview", "web_search"):
                    tool_schemas.append({"type": "web_search_preview"})
                elif tool == "image_generation":
                    tool_schemas.append({"type": "image_generation"})
                else:
                    tool_schemas.append(
                        await handle_openai_function(
                            FunctionRequest(function=tool, params={}), schema=True
                        )
                    )

        response_class = sections.get("response", "").strip()

        result = {
            "instructions": instructions,
            "prompt": prompt,
            "model": model,
            "tools": tools,
            "tool_schemas": tool_schemas,
            "response": response_class,
            "handoffs": handoffs,
        }
        cls._cache[name] = result
        return result

    def __init__(
        self,
        name: str,
        variables: dict = None,
        response_class: JsonResponse = None,
        model: str = None,
        provider: str = None,
    ):
        self.name = name
        self.variables = variables
        self.response_class = response_class
        self.model = model
        self.provider = provider
        self.files = {}
        self.raw_response = None
        self.annotations = []
        self.container_id = None

    async def setup(self):
        result = await self.load(self.name)
        self.id = None
        self.instructions = result["instructions"]
        # store original prompt template for variable substitution on each run
        self.prompt_template = result["prompt"]
        self.prompt = result["prompt"]
        self.handoffs = result["handoffs"]
        if self.model is None:
            if result.get("model") is None:
                self.model = AI_MODEL
            else:
                self.model = result["model"]
        if "/" in self.model:
            self.provider = self.model.split("/")[0]
            self.model = self.model.split("/")[1]

        if self.variables:
            self._apply_variables()
        if self.response_class is None and result.get("response"):
            try:
                response_class_path = result["response"]
                if "." in response_class_path:
                    module_name, class_name = response_class_path.rsplit(".", 1)
                    module = importlib.import_module(module_name)
                    self.response_class = getattr(module, class_name)
                else:
                    self.response_class = eval(response_class_path, globals())
            except Exception as e:
                raise ValueError(f"Failed to import response class: {result['response']}") from e
        self.response = None
        self.tool_schemas = result["tool_schemas"]
        if self.model is None:
            self.model = result.get("model", AI_MODEL)

    def _apply_variables(self):
        import re

        # Reset to the original template, then substitute any {{key}} placeholders
        self.prompt = self.prompt_template
        d = SafeDict(self.variables)
        pattern = r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}"
        self.prompt = re.sub(pattern, lambda m: str(d[m.group(1)]), self.prompt)

    @classmethod
    async def create(
        cls,
        name: str,
        variables: dict = None,
        response_class: JsonResponse = None,
        model: str = None,
        provider: str = None,
    ):
        instance = cls(
            name=name,
            variables=variables,
            response_class=response_class,
            model=model,
            provider=provider,
        )
        await instance.setup()
        return instance

    async def run(self, previous_response_id: str = None, variables: dict = None):
        # Rebuild prompt if new variables provided
        self.output_files = []
        if variables is not None:
            self.variables = variables
            self._apply_variables()
        if self.provider == "openai":
            self.response = await self.openai(previous_response_id=previous_response_id)
        else:
            raise ValueError(f"Invalid provider/provider not set: {self.provider}. Only OpenAI is supported.")
        return self.response

    @classmethod
    async def get_with_params(cls, name: str, params: dict) -> str:
        import re

        prompt = await cls.get(name, PROMPTS_DIR)
        # Replace new {{key}} placeholders
        for key, value in params.items():
            pattern = rf"\{{\{{\s*{re.escape(key)}\s*\}}\}}"
            prompt = re.sub(pattern, value, prompt)
        return prompt

    @property
    def frommarkdown(self, response: str = None):
        if response is None:
            response = self.response
        return frommarkdown(response)

    @property
    def asjson(self):
        return self.response.model_dump()

    @property
    def pydantic_response(self):
        if isinstance(self.response, dict) or isinstance(self.response, list):
            return self.response_class.model_validate(self.response, strict=False)
        elif isinstance(self.response, str):
            # if the response is a string, we need to parse it as a json object
            return self.response_class.model_validate(
                json.loads(self.response, strict=False), strict=False
            )
        else:
            return self.response

    async def upload_file(self, file_path: str, title: str):
        client = AsyncOpenAI()
        with open(file_path, "rb") as file:
            response = await client.files.create(
                file=file,
                purpose="user_data",
            )
            self.files[response.id] = {"title": title, "file_path": file_path}
            return response.id

    async def get_annotation_file(self, annotation: dict):
        """Retrieve file content for a given annotation."""
        client = AsyncOpenAI()
        container_id = annotation.get("container_id") or self.container_id
        file_id = annotation.get("file_id")
        if not container_id or not file_id:
            raise ValueError("annotation must contain 'file_id' and 'container_id'")
        content = await client.containers.files.content.retrieve(
            file_id=file_id,
            container_id=container_id,
        )
        return content

    async def openai(self, previous_response_id: str = None) -> str:
        client = AsyncOpenAI()
        content = [{"type": "input_text", "text": self.prompt}]
        if self.files:
            for file_id in self.files:
                content.append({"type": "input_file", "file_id": file_id})
        input_messages = [
            {
                "role": "developer",
                "content": "Today's date is " + datetime.now().strftime("%Y-%m-%d"),
            },
            {"role": "user", "content": content},
        ]
        # set strict to True in self.tool_schemas
        schema = None
        if self.response_class:
            schema = self.response_class.model_json_schema()
        tool_schemas = [dict(t) for t in self.tool_schemas]
        for tool in tool_schemas:
            if tool.get("type") == "code_interpreter":
                tool["container"] = {"type": "auto", **({"file_ids": list(self.files.keys())} if self.files else {})}
        response = await client.responses.create(
            instructions=self.instructions,
            model=self.model,
            input=input_messages,
            text={
                "format": {
                    "type": "json_schema" if schema is not None else "text",
                    **({"name": "response"} if schema is not None else {}),
                    **({"schema": schema} if schema is not None else {}),
                },
            },
            tools=tool_schemas,
            previous_response_id=previous_response_id,
            max_output_tokens=16000 if self.model != "gpt-4.1" else 32000,
        )
        self.id = response.id
        self.raw_response = response
        self.container_id = (
            getattr(response, "container_id", None)
            or getattr(getattr(response, "container", None), "id", None)
        )
        self.annotations = []
        while any(o.type == "function_call" for o in response.output):
            for tool_call in response.output:
                if tool_call.type == "function_call":
                    output = await handle_openai_function(
                        FunctionRequest(function=tool_call.name, params=json.loads(tool_call.arguments))
                    )
                    input_messages.append(tool_call)
                    input_messages.append(
                        {
                            "type": "function_call_output",
                            "call_id": tool_call.call_id,
                            "output": str(output),
                        }
                    )
                else:
                    # o3 seems to reallu want this reasoning message to be included
                    input_messages.append(tool_call)
            response = await client.responses.create(
                instructions=self.instructions,
                model=self.model,
                input=input_messages,
                text={
                    "format": {
                        "type": "json_schema" if schema is not None else "text",
                        **({"name": "response"} if schema is not None else {}),
                        **({"schema": schema} if schema is not None else {}),
                    },
                },
                tools=tool_schemas,
                max_output_tokens=16000 if self.model != "gpt-4.1" else 32000,
            )
        self.raw_response = response
        self.id = response.id  # Update to the final response ID after function calls
        self.text_response_object = None
        self.output_files = []
        # collect the files from the code interpreter calls and the text response object if it exists
        for output in self.raw_response.output:
            if output.type == "message":
                content = output.content
                for item in content:
                    if item.type == "output_text":
                        self.text_response_object = item
                        if len(item.annotations) > 0:
                            for annotation in item.annotations:
                                if annotation.type == "container_file_citation":
                                    self.output_files.append({
                                        "file_id": annotation.file_id,
                                        "container_id": annotation.container_id,
                                        "filename": annotation.filename,
                                    })

        return response.output_text
