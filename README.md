# FastAPI Responses

A FastAPI-based application that uses the `Prompt` class for AI interactions instead of the OpenAI Assistants API.

## Overview

This project is a reimplementation of the fastapi-assistant repository, replacing the OpenAI Assistants API with a more flexible prompt-based system. It maintains the core functionality of the original project while introducing more flexibility through markdown-based prompt templates.

## Features

- **Prompt-based AI interactions**: Uses the `Prompt` class for flexible AI interactions
- **Multiple model support**: Works with both OpenAI and Gemini models
- **Tool integration**: Supports webscrape and other tools
- **File handling**: Upload and process files for analysis
- **Conversation continuity**: Maintains conversation context using previous response tracking
- **Prompt templates**: Define prompt behavior using markdown templates

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/fastapi-responses.git
cd fastapi-responses
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

or even better in a virtual environment:
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

And EASIEST: in Visual Studio Code: Open cmd-shift-p Create Virtual Environment select venv and then requirements.txt


3. Set up environment variables:
Create a `.env` file with the following variables:
```
OPENAI_API_KEY=your_openai_api_key
# Optional: GEMINI_API_KEY=your_gemini_api_key
```

## Usage

1. Start the server:
```bash
uvicorn application:application --reload
```
Or easier: in VS Code run debugger FastAPI.
(File is preconfigured)

2. Access the chat interface:
Open your browser and navigate to `http://localhost:8000/chat/` this is really just to the different prompts.
(Its like a simplified playground)

3. Use the API endpoints:
- `/demo/list_prompts`: List available prompts
- `/demo/joke`: Get a joke from the joker prompt
- `/demo/prompt/{prompt_name}`: Run a specific prompt with content
- `/demo/upload_file`: Upload a file for use with prompts

## Prompt Templates

Prompts are defined using markdown templates in the `prompts/` directory. Each template includes:

- **Instructions**: Behavior guidelines for the prompt
- **Model**: The AI model to use (OpenAI or Gemini)
- **Tools**: Available tools for the prompt
- **Prompt**: The template for the prompt with variable placeholders
- **Response**: Guidelines for response formatting

Example template:
```markdown
@@ Instructions
You are a helpful system that provides accurate and concise information.

@@ Model
openai/gpt-4

@@ Tools
webscrape

@@ Prompt
{{content}}

@@ Response
Respond in a helpful, accurate, and concise manner.
```

## Creating New Prompts

To create a new prompt:

1. Create a new markdown file in the `prompts/` directory (e.g., `prompts/my_prompt.md`)
2. Define the prompt behavior using the template format
3. The prompt will be automatically available via the API

## Architecture

- **app/prompt.py**: Core prompt handler class that manages prompts and responses
- **app/tools.py**: Tool implementations for webscraping and other functions
- **app/chat.py**: Chat interface and API endpoints
- **app/demo.py**: Demo endpoints and examples
- **prompts/**: Markdown templates for different prompts

## Differences from fastapi-assistant

- Uses the `Prompt` class instead of OpenAI Assistants API
- Simplified thread management using previous response tracking
- Markdown-based prompt templates instead of OpenAI assistant configurations
- Local file storage instead of OpenAI file attachments
- No Twilio integration
- Support for both OpenAI and Gemini models

## License

MIT
