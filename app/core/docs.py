"""Documentation pages, with two rendering defects patched.

Both defects come from the stock page rather than from this application, and both
are visible to anyone opening the interactive documentation:

1. **No colour scheme.** Swagger UI ships no dark theme. Under
   ``prefers-color-scheme: dark`` the browser paints its own dark canvas behind
   components that keep their light colours, and the page becomes unreadable.
   The stock page declares neither a colour scheme nor a background.

2. **Unstyled buttons in the Schemas section.** The JSON Schema 2020-12 renderer,
   used because this API publishes OpenAPI 3.1, builds its accordions from
   ``<button>`` elements that the bundled stylesheet never resets. The browser's
   default button background then paints a grey rectangle hugging every schema
   name, which reads as if the text were highlighted.
"""

from fastapi import FastAPI
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import HTMLResponse

_PAGE_FIXES = """
    <meta name="color-scheme" content="light">
    <style>
      :root { color-scheme: light; }
      html, body { background-color: #fafafa; }

      /* Sem este reset, o fundo padrão de <button> do navegador desenha um
         retângulo cinza atrás de cada nome de schema e de cada "Expand all". */
      .swagger-ui .json-schema-2020-12-accordion,
      .swagger-ui .json-schema-2020-12-expand-deep-button {
        background: transparent;
      }
    </style>"""


def _with_page_fixes(response: HTMLResponse) -> HTMLResponse:
    html = response.body.decode()
    return HTMLResponse(html.replace("<head>", "<head>" + _PAGE_FIXES, 1))


def register_documentation_routes(app: FastAPI) -> None:
    """Replace the stock /docs and /redoc with the patched versions.

    The application must be created with ``docs_url=None`` and ``redoc_url=None``
    so these routes are the ones serving those paths.
    """

    @app.get("/docs", include_in_schema=False)
    async def swagger_ui() -> HTMLResponse:
        return _with_page_fixes(
            get_swagger_ui_html(
                openapi_url=app.openapi_url,
                title=f"{app.title} - Swagger UI",
                oauth2_redirect_url=None,
            )
        )

    @app.get("/redoc", include_in_schema=False)
    async def redoc() -> HTMLResponse:
        return _with_page_fixes(
            get_redoc_html(openapi_url=app.openapi_url, title=f"{app.title} - ReDoc")
        )
