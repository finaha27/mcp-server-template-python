"""
MCP Server Template
"""

import base64
import json
import os
from typing import Any, Protocol
from urllib import error, parse, request

from mcp.server.fastmcp import FastMCP
from pydantic import AnyHttpUrl, Field

from pdf_api_server import start_pdf_api_server_in_thread

import mcp.types as types

try:
    from mcp.server.auth.middleware.auth_context import get_access_token
    from mcp.server.auth.provider import AccessToken, TokenVerifier
    from mcp.server.auth.settings import AuthSettings

    MCP_AUTH_SUPPORTED = True
except Exception:
    MCP_AUTH_SUPPORTED = False

    class TokenVerifier(Protocol):
        async def verify_token(self, token: str) -> Any:
            ...

    AccessToken = Any  # type: ignore[assignment]

    def get_access_token() -> Any | None:
        return None

MCP_STREAMABLE_HTTP_PATH = os.getenv("MCP_STREAMABLE_HTTP_PATH", "/")

PDF_API_BIND_HOST = os.getenv("PDF_API_BIND_HOST", "127.0.0.1")
PDF_API_CONNECT_HOST = os.getenv("PDF_API_CONNECT_HOST", "127.0.0.1")
PDF_API_PORT = int(os.getenv("PDF_API_PORT", "8001"))
PDF_API_BASE_URL = f"http://{PDF_API_CONNECT_HOST}:{PDF_API_PORT}"

ENABLE_OAUTH = os.getenv("ENABLE_OAUTH", "false").lower() in {"1", "true", "yes", "on"}
KEYCLOAK_ISSUER_URL = os.getenv("KEYCLOAK_ISSUER_URL", "")
KEYCLOAK_INTROSPECTION_URL = os.getenv("KEYCLOAK_INTROSPECTION_URL", "")
KEYCLOAK_CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID", "")
KEYCLOAK_CLIENT_SECRET = os.getenv("KEYCLOAK_CLIENT_SECRET", "")
MCP_RESOURCE_SERVER_URL = os.getenv("MCP_RESOURCE_SERVER_URL", "")
MCP_EXPECTED_AUDIENCE = os.getenv("MCP_EXPECTED_AUDIENCE", "")


class KeycloakIntrospectionTokenVerifier(TokenVerifier):
    """Validate bearer tokens by calling Keycloak introspection endpoint."""

    def __init__(
        self,
        introspection_url: str,
        client_id: str,
        client_secret: str,
        expected_audience: str | None = None,
    ):
        self.introspection_url = introspection_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.expected_audience = expected_audience

    async def verify_token(self, token: str) -> AccessToken | None:
        payload = parse.urlencode(
            {
                "token": token,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            }
        ).encode("utf-8")

        basic = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode("utf-8")).decode("utf-8")
        req = request.Request(
            self.introspection_url,
            data=payload,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {basic}",
            },
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception:
            return None

        if not data.get("active", False):
            return None

        if self.expected_audience:
            aud = data.get("aud")
            azp = data.get("azp")
            audience_ok = False
            if isinstance(aud, list):
                audience_ok = self.expected_audience in aud
            elif isinstance(aud, str):
                audience_ok = aud == self.expected_audience
            if not audience_ok and isinstance(azp, str):
                audience_ok = azp == self.expected_audience
            if not audience_ok:
                return None

        scopes = data.get("scope", "").split() if data.get("scope") else []
        return AccessToken(
            token=token,
            client_id=data.get("client_id") or data.get("sub") or "unknown",
            scopes=scopes,
            expires_at=data.get("exp"),
            resource=str(data.get("aud")) if data.get("aud") is not None else None,
        )


def _build_mcp_server() -> FastMCP:
    base_kwargs = {
        "name": "Echo Server",
        "stateless_http": True,
        "json_response": True,
        "streamable_http_path": MCP_STREAMABLE_HTTP_PATH,
    }

    if not ENABLE_OAUTH:
        return FastMCP(**base_kwargs)

    if not MCP_AUTH_SUPPORTED:
        raise RuntimeError(
            "OAuth is enabled but current mcp package does not expose server auth modules. "
            "Please use an mcp version that supports mcp.server.auth.*"
        )

    required = {
        "KEYCLOAK_ISSUER_URL": KEYCLOAK_ISSUER_URL,
        "KEYCLOAK_INTROSPECTION_URL": KEYCLOAK_INTROSPECTION_URL,
        "KEYCLOAK_CLIENT_ID": KEYCLOAK_CLIENT_ID,
        "KEYCLOAK_CLIENT_SECRET": KEYCLOAK_CLIENT_SECRET,
        "MCP_RESOURCE_SERVER_URL": MCP_RESOURCE_SERVER_URL,
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        missing_str = ", ".join(missing)
        raise RuntimeError(f"OAuth is enabled but missing environment variables: {missing_str}")

    verifier = KeycloakIntrospectionTokenVerifier(
        introspection_url=KEYCLOAK_INTROSPECTION_URL,
        client_id=KEYCLOAK_CLIENT_ID,
        client_secret=KEYCLOAK_CLIENT_SECRET,
        expected_audience=MCP_EXPECTED_AUDIENCE or None,
    )

    return FastMCP(
        **base_kwargs,
        token_verifier=verifier,
        auth=AuthSettings(
            issuer_url=AnyHttpUrl(KEYCLOAK_ISSUER_URL),
            resource_server_url=AnyHttpUrl(MCP_RESOURCE_SERVER_URL),
        ),
    )


mcp = _build_mcp_server()


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


def _authorize_lecture_access(lecture_number: int) -> None:
    if not ENABLE_OAUTH:
        return

    token = get_access_token()
    if token is None:
        raise PermissionError("Authentication required")

    scopes = set(token.scopes)
    if "senior" in scopes:
        return
    if "freshman" in scopes and lecture_number <= 3:
        return
    if "freshman" in scopes:
        raise PermissionError("Freshman access is limited to lectures 1, 2, and 3")
    raise PermissionError("Missing required scope: freshman or senior")


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
    _authorize_lecture_access(lecture_number)
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
