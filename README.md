# mcp-server-template-python

A very simple Python template for building MCP servers using Streamable HTTP transport.

## Overview
This template provides a foundation for creating MCP servers that can communicate with AI assistants and other MCP clients. It includes a simple HTTP server implementation with example tools, resources & prompts to help you get started building your own MCP integrations.

## Deploy

Use the following button to clone the repository and directly deploy the server to Alpic

[![Deploy on Alpic](https://assets.alpic.ai/button.svg)](https://app.alpic.ai/new/clone?repositoryUrl=https%3A%2F%2Fgithub.com%2Falpic-ai%2Fmcp-server-template-python)

## Prerequisites
- Install uv (https://docs.astral.sh/uv/getting-started/installation/)

## Installation

1. Clone the repository:

```bash
git clone git@github.com:alpic-ai/mcp-server-template-python.git
cd mcp-server-template-python
```

2. Install python version & dependencies:

```bash
uv python install
uv sync --locked
```

## Usage

Start the server on port 3000:

```bash
uv run main.py
```

Running `main.py` now starts two local servers:
- MCP server (Streamable HTTP): `http://127.0.0.1:3000/mcp`
- PDF API server (separate app): `http://127.0.0.1:8001`

The MCP tool does not parse PDFs directly. It sends an HTTP request to the PDF API as if it were a remote service.

You can configure the PDF API host/port using environment variables:
- `PDF_API_BIND_HOST` (default: `127.0.0.1`)
- `PDF_API_CONNECT_HOST` (default: `127.0.0.1`)
- `PDF_API_PORT` (default: `8001`)

You can configure Streamable HTTP path for MCP clients:
- `MCP_STREAMABLE_HTTP_PATH` (default: `/`)

## OAuth2 (Keycloak) Integration

The server supports OAuth2 as an MCP Resource Server when enabled.

Set these environment variables:
- `ENABLE_OAUTH=true`
- `KEYCLOAK_ISSUER_URL` (example: `https://auth.example.com/realms/myrealm`)
- `KEYCLOAK_INTROSPECTION_URL` (example: `https://auth.example.com/realms/myrealm/protocol/openid-connect/token/introspect`)
- `KEYCLOAK_CLIENT_ID` (confidential client used for introspection)
- `KEYCLOAK_CLIENT_SECRET`
- `MCP_RESOURCE_SERVER_URL` (public URL of this MCP server)
- `MCP_EXPECTED_AUDIENCE` (optional but recommended)

Authorization model:
- `freshman`: can analyze lectures `1..3`
- `senior`: can analyze all lectures

Any authenticated token without one of these scopes is rejected for lecture analysis.

## Lecture PDF API

The separate API app is implemented in `pdf_api_server.py`.

Endpoint:
- `GET /lecture-summary?lecture_number=1`

Response fields:
- `lecture_number`
- `file_name`
- `word_count`
- `first_sentence`
- `last_sentence`

The API reads files from `docs/` using this pattern:
- `MachineLearning-LectureXX.pdf`

## Running the Inspector

### Requirements
- Node.js: ^22.7.5

### Quick Start (UI mode)
To get up and running right away with the UI, just execute the following:
```bash
npx @modelcontextprotocol/inspector
```

The inspector server will start up and the UI will be accessible at http://localhost:6274.

You can test your server locally by selecting:
- Transport Type: Streamable HTTP
- URL: http://127.0.0.1:3000/mcp

## Development

### Adding New Tools

To add a new tool, modify `main.py`:

```python
@mcp.tool(
    title="Your Tool Name",
    description="Tool Description for the LLM",
)
async def new_tool(
    tool_param1: str = Field(description="The description of the param1 for the LLM"), 
    tool_param2: float = Field(description="The description of the param2 for the LLM") 
)-> str:
    """The new tool underlying method"""
    result = await some_api_call(tool_param1, tool_param2)
    return result
```

### Adding New Resources

To add a new resource, modify `main.py`:

```python
@mcp.resource(
    uri="your-scheme://{param1}/{param2}",
    description="Description of what this resource provides",
    name="Your Resource Name",
)
def your_resource(param1: str, param2: str) -> str:
    """The resource template implementation"""
    # Your resource logic here
    return f"Resource content for {param1} and {param2}"
```

The URI template uses `{param_name}` syntax to define parameters that will be extracted from the resource URI and passed to your function.

### Adding New Prompts

To add a new prompt , modify `main.py`:

```python
@mcp.prompt("")
async def your_prompt(
    prompt_param: str = Field(description="The description of the param for the user")
) -> str:
    """Generate a helpful prompt"""

    return f"You are a friendly assistant, help the user and don't forget to {prompt_param}."

```
