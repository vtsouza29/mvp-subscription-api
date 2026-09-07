"""Documentation pages pinned to a light colour scheme.

Swagger UI ships no dark theme. Under ``prefers-color-scheme: dark`` the browser
paints its own dark canvas behind components that keep their light colours, and
the schema blocks end up looking highlighted. FastAPI's stock documentation page
declares neither a colour scheme nor a background, so it inherits that. Pinning
both keeps the page legible regardless of the reader's system setting.
"""

from fastapi import FastAPI
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import HTMLResponse

_LIGHT_THEME = """
    <meta name="color-scheme" content="light">
    <style>
      :root { color-scheme: light; }
      html, body { background-color: #fafafa; }
    </style>"""


def _with_light_theme(response: HTMLResponse) -> HTMLResponse:
    html = response.body.decode()
    return HTMLResponse(html.replace("<head>", "<head>" + _LIGHT_THEME, 1))


def register_documentation_routes(app: FastAPI) -> None:
    """Replace the stock /docs and /redoc with light-pinned versions.

    The application must be created with ``docs_url=None`` and ``redoc_url=None``
    so these routes are the ones serving those paths.
    """

    @app.get("/docs", include_in_schema=False)
    async def swagger_ui() -> HTMLResponse:
        return _with_light_theme(
            get_swagger_ui_html(
                openapi_url=app.openapi_url,
                title=f"{app.title} - Swagger UI",
                oauth2_redirect_url=None,
            )
        )

    @app.get("/redoc", include_in_schema=False)
    async def redoc() -> HTMLResponse:
        return _with_light_theme(
            get_redoc_html(openapi_url=app.openapi_url, title=f"{app.title} - ReDoc")
        )
