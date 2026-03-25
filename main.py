"""
MCP Server Template
"""

import json
import os
from urllib import error, parse, request

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from pdf_api_server import start_pdf_api_server_in_thread

import mcp.types as types

mcp = FastMCP("Echo Server", stateless_http=True)

PDF_API_BIND_HOST = os.getenv("PDF_API_BIND_HOST", "127.0.0.1")
PDF_API_CONNECT_HOST = os.getenv("PDF_API_CONNECT_HOST", "127.0.0.1")
PDF_API_PORT = int(os.getenv("PDF_API_PORT", "8001"))
PDF_API_BASE_URL = f"http://{PDF_API_CONNECT_HOST}:{PDF_API_PORT}"


def _fetch_lecture_pdf_summary(lecture_number: int) -> dict[str, str | int]:
    query = parse.urlencode({"lecture_number": lecture_number})
    url = f"{PDF_API_BASE_URL}/lecture-summary?{query}"

    try:
        with request.urlopen(url, timeout=10) as response:
            payload = response.read().decode("utf-8")
            return json.loads(payload)
    except error.HTTPError as exc:
        error_payload = exc.read().decode("utf-8")
        raise ValueError(f"PDF API returned HTTP {exc.code}: {error_payload}") from exc
    except error.URLError as exc:
        raise RuntimeError("Could not connect to the PDF API service") from exc


@mcp.tool(
    title="Echo Tool",
    description="Echo the input text",
)
def echo(text: str = Field(description="The text to echo")) -> str:
    return text


@mcp.tool(
    title="Analyze Lecture PDF",
    description=(
        "Request a remote-style API to analyze a lecture PDF by number and return "
        "word_count, first_sentence, and last_sentence."
    ),
)
def analyze_lecture_pdf(
    lecture_number: int = Field(
        ge=1,
        description="Lecture number to analyze (example: 1 for MachineLearning-Lecture01.pdf)",
    ),
) -> dict[str, str | int]:
    return _fetch_lecture_pdf_summary(lecture_number)


@mcp.resource(
    uri="greeting://{name}",
    description="Get a personalized greeting",
    name="Greeting Resource",
)
def get_greeting(
    name: str,
) -> str:
    return f"Hello, {name}!"


@mcp.prompt("")
def greet_user(
    name: str = Field(description="The name of the person to greet"),
    style: str = Field(description="The style of the greeting", default="friendly"),
) -> str:
    """Generate a greeting prompt"""
    styles = {
        "friendly": "Please write a warm, friendly greeting",
        "formal": "Please write a formal, professional greeting",
        "casual": "Please write a casual, relaxed greeting",
    }

    return f"{styles.get(style, styles['friendly'])} for someone named {name}."


if __name__ == "__main__":
    pdf_api_server = start_pdf_api_server_in_thread(
        host=PDF_API_BIND_HOST,
        port=PDF_API_PORT,
    )
    try:
        mcp.run(transport="streamable-http")
    finally:
        pdf_api_server.shutdown()
        pdf_api_server.server_close()
