# FastAPI Responses API Demo

A FastAPI implementation showcasing the OpenAI Responses API with a smart wrapper class that enables prompt definition files for structured AI interactions.

## Overview

This project demonstrates how to build a clean, structured AI application using the OpenAI Responses API. It features a powerful "Prompt class that allows you to define AI behavior, tools, and conversation flow through simple markdown files per Prompt. (This was inspired by the OpenAI Assistants, and now the OpenaI Prompt objects)
After using both for a while I decided that i do want all my prompts in Github - but not in code.

## Key Features

- ** Prompt Definition Files**: Define AI behavior using markdown templates with instructions, tools, and models
- ** Thread Persistence**: Automatic conversation continuity using response IDs
- ** Tool Integration**: Built-in support for web scraping, code interpreter, and custom functions
- ** File Handling**: Upload, process, and display files (images, documents, data)
- ** Smart Response Wrapper**: Handles OpenAI API complexities behind a simple interface

- ** Interactive Chat TEST / DEMO Interface**: Web-based chat UI with sidebar showing prompt file details


## Quick Start

### 1. Installation

```bash
git clone https://github.com/jlvanhulst/fastapi-responses.git
cd fastapi-responses
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Environment Setup

Create a `.env` file:
```env
OPENAI_API_KEY=your_openai_api_key_here
DEBUG=True
```

### 3. Run the Application

**Option 1: Command Line**
```bash
uvicorn application:application --reload
```

**Option 2: VS Code/Cursor (Recommended)**
The project includes a preconfigured `launch.json` file. Simply:
1. Open the project in VS Code or Cursor
2. Press `F5` or go to Run → Start Debugging
3. The FastAPI server will start automatically with debugging enabled

Visit `http://localhost:8000/chat/` to start chatting!

## Prompt System

### Creating Prompts

Prompts are defined in markdown files in the `prompts/` directory. Each prompt file contains sections that define the AI's behavior:

```markdown
@@ Instructions
You are a helpful coding assistant that provides clear, well-documented code examples.

@@ Model
openai/gpt-4.1

@@ Tools
code_interpreter
webscrape

@@ Prompt
Help the user with their coding question: {{content}}
```

### Available Sections

- **`@@ Instructions`**: System prompt defining the AI's role and behavior
- **`@@ Model`**: Which model to use (e.g., `openai/gpt-4.1`)
- **`@@ Tools`**: Available tools (`code_interpreter`, `web_search`, `image_generation`, custom functions)
- **`@@ Prompt`**: The template with `{{content}}` placeholders for user input

### Built-in Tools

- **`code_interpreter`**: Execute Python code, create plots, analyze data
- **`web_search`**: Search the web for current information
- **`image_generation`**: Generate images using DALL-E
- **Custom Tools**: Add your own functions in `app/tools.py` (e.g., `webscrape`)

## API Endpoints

### Chat Interface
- `GET /chat/` - Interactive chat web interface
- `POST /chat/thread/` - Send message and get AI response
- `GET /chat/get_prompts` - List available prompts
- `GET /chat/prompt_details/{name}` - Get prompt configuration

### Demo Endpoints
- `GET /demo/list_prompts` - List all available prompts
- `POST /demo/prompt/{name}` - Execute a specific prompt with JSON payload
- `POST /demo/prompt_with_files/{name}` - Execute a prompt with embedded files (recommended)
- `POST /demo/upload_file` - Upload a single file and get file_id
- `GET /demo/graph_report?prompt=...` - Generate PDF report with embedded charts using graph_demo prompt

### File Management
- `POST /chat/upload` - Upload files for use in conversations
- `GET /chat/files/{container_id}/{file_id}` - Serve generated files

## Architecture

```
├── app/
│   ├── ai_processor.py    # Core Prompt class and OpenAI integration
│   ├── ai_tools.py        # Tool registration and schema handling
│   ├── chat.py           # Chat interface and handlers
│   ├── demo_routes.py    # Demo API endpoints
│   ├── pdf_utils.py      # PDF generation utilities
│   └── tools.py          # Custom tool implementations
├── prompts/              # Prompt definition files
├── templates/            # HTML templates for web interface
└── application.py        # FastAPI app configuration
```

## Key Components

### Prompt Class (ai_processor.py and ai_tools.py)
The core `Prompt` class handles:
- Loading and parsing markdown prompt files
- Managing conversation threads with response IDs
- Tool execution and file handling
- Model switching and configuration

### Test / Demo Chat Interface (chat.py)
Features include:
- Prompt file selection and configuration display
- File upload and inline image viewing
- Conversation history with thread persistence
- Ability to talk to your prompt like in the OpenAI Playground but with your own functions and prompt files.



## Development

### Adding Custom Functions for Tool Calls

This project supports custom function calling that can be used with OpenAI's function calling capabilities. Here's how to add your own functions:

#### 1. Create a Function with Pydantic Schema

Create your function in `app/tools.py` with proper type hints and Pydantic models:

```python
from pydantic import BaseModel, Field

class MyToolRequest(BaseModel):
    """Request model for my custom tool."""
    param1: str = Field(..., description="Description of parameter 1")
    param2: int = Field(..., description="Numeric parameter with constraints", ge=0, le=100)
    optional_param: str = Field(None, description="Optional parameter")

async def my_custom_tool(request: MyToolRequest) -> str:
    """
    Description of what this tool does.

    This docstring becomes the function description for OpenAI.
    Be clear and specific about the function's purpose.
    """
    # Your implementation here
    result = f"Processed {request.param1} with value {request.param2}"

    if request.optional_param:
        result += f" and {request.optional_param}"

    return result
```

#### 2. Register the Function

Add the registration in `application.py` at startup:

```python
# Register tools at application startup
from app.ai_tools import register_tools
from app.tools import my_custom_tool
register_tools("my_custom_tool", function=my_custom_tool)
```

#### 3. Use in Prompt Templates

Add your function to the `@@ Tools` section in your prompt files:

```markdown
@@ Model
openai/gpt-4o

@@ Instructions
You can help users with custom processing tasks.

@@ Tools
my_custom_tool
generate_client_revenue_data

@@ Prompt
{{content}}
```

#### 4. Example: Revenue Data Generator

See the existing `generate_client_revenue_data` function as a complete example:

```python
class RevenueDataRequest(BaseModel):
    client_name: str = Field(..., description="The name of the client")
    year: int = Field(..., description="The year for revenue data", ge=2020, le=2030)

async def generate_client_revenue_data(request: RevenueDataRequest) -> RevenueDataResponse:
    """Generate mock client revenue data for demonstration purposes."""
    # Implementation generates 12 months of data with realistic variations
    return RevenueDataResponse(...)
```

#### Key Points:

- **Pydantic Models**: Always use Pydantic models for request parameters - this generates OpenAI function schemas automatically
- **Type Safety**: Proper typing ensures reliable function calling
- **Documentation**: Docstrings become function descriptions for AI
- **Async Support**: Functions can be async for database/API calls
- **Error Handling**: Include proper error handling in your functions
- **Field Validation**: Use Pydantic Field constraints for parameter validation

#### Testing Your Functions:

1. **Direct Testing**: Test functions directly in your code
2. **API Testing**: Use `/demo/prompt/{prompt_name}` endpoints with prompts that use your tools
3. **Chat Interface**: Test through the web chat interface at `/chat/`

### Creating New Prompts

1. Create `prompts/my_prompt.md`
2. Define the sections as shown above
3. Restart the application
4. Select your prompt in the chat interface to test it.



## Production Considerations

**Important**: The demo endpoints in this project wait for AI responses before returning (synchronous). This is only suitable for local development and demos.

### For Production Applications:

**Don't do this (demo approach):**
```python
# Blocks for 10-60+ seconds waiting for AI response
response = await prompt.run(...)
return {"result": response}  # Client waits the entire time
```



## License

MIT License - feel free to use this as a foundation for your own AI applications!

## Contributing

This is a demo project showcasing the OpenAI Responses API capabilities. Feel free to fork and adapt for your needs!