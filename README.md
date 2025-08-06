# FastAPI Responses API Demo

A FastAPI implementation showcasing the OpenAI Responses API with a smart wrapper class that enables prompt definition files for structured AI interactions.

## Overview

This project demonstrates how to build a clean, structured AI application using the OpenAI Responses API. It features a powerful prompt system that allows you to define AI behavior, tools, and conversation flow through simple markdown files.

## Key Features

- **📝 Prompt Definition Files**: Define AI behavior using markdown templates with instructions, tools, and models
- **🔄 Thread Persistence**: Automatic conversation continuity using response IDs
- **🛠️ Tool Integration**: Built-in support for web scraping, code interpreter, and custom functions
- **📁 File Handling**: Upload, process, and display files (images, documents, data)
- **🎯 Smart Response Wrapper**: Handles OpenAI API complexities behind a simple interface

- **💬 Interactive Chat TEST / DEMO Interface**: Web-based chat UI with sidebar showing prompt file details


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
- **`@@ Tools`**: Available tools (`code_interpreter`, `web_search`, `webscrape`, custom functions)
- **`@@ Prompt`**: The template with `{{content}}` placeholders for user input

### Built-in Tools

- **`code_interpreter`**: Execute Python code, create plots, analyze data
- **`web_search`**: Search the web for current information
- **`webscrape`**: Scrape content from websites
- **Custom Tools**: Add your own functions in `app/tools.py`

## API Endpoints

### Chat Interface
- `GET /chat/` - Interactive chat web interface
- `POST /chat/thread/` - Send message and get AI response
- `GET /chat/get_prompts` - List available prompts
- `GET /chat/prompt_details/{name}` - Get prompt configuration

### Demo Endpoints
- `GET /demo/list_prompts` - List all available prompts
- `POST /demo/prompt/{name}` - Execute a specific prompt
- `POST /demo/upload_file` - Upload files for processing

### File Management
- `POST /chat/upload` - Upload files for use in conversations
- `GET /chat/files/{container_id}/{file_id}` - Serve generated files

## Architecture

```
├── app/
│   ├── ai_processor.py    # Core Prompt class and OpenAI integration
│   ├── ai_tools.py        # Tool registration and schema handling
│   ├── chat.py           # Chat interface and handlers
│   ├── demo.py           # Demo endpoints
│   └── tools.py          # Custom tool implementations
├── prompts/              # Prompt definition files
├── templates/            # HTML templates for web interface
└── application.py        # FastAPI app configuration
```

## Key Components

### Prompt Class
The core `Prompt` class handles:
- Loading and parsing markdown prompt files
- Managing conversation threads with response IDs
- Tool execution and file handling
- Model switching and configuration

### PromptHandler
A singleton that manages:
- Prompt instances and caching
- File uploads and storage
- Response history for conversation continuity

### Chat Interface
Features include:
- Real-time prompt selection and configuration display
- File upload and inline image viewing
- Conversation history with thread persistence
- Clean, responsive UI with sidebar navigation

## Example Use Cases

1. **Code Assistant**: Help with programming questions using code interpreter
2. **Research Assistant**: Web search and scraping for information gathering
3. **Data Analyst**: Upload CSV files and create visualizations
4. **Content Creator**: Generate and refine content with specific guidelines

## Development

### Adding Custom Tools

1. Create your function in `app/tools.py`:
```python
async def my_custom_tool(params: dict):
    # Your tool implementation
    return result
```

2. Register it in the PromptHandler:
```python
register_tools("my_custom_tool", function=my_custom_tool)
```

3. Use it in prompts:
```markdown
@@ Tools
my_custom_tool
```

### Creating New Prompts

1. Create `prompts/my_prompt.md`
2. Define the sections as shown above
3. Restart the application
4. Select your prompt in the chat interface

## License

MIT License - feel free to use this as a foundation for your own AI applications!

## Contributing

This is a demo project showcasing the OpenAI Responses API capabilities. Feel free to fork and adapt for your needs!