import asyncio
import contextlib
import logging
from typing import Any

from core.circuit_breaker import CircuitBreakerOpenError, get_circuit_breaker
from core.network_security import UnsafeNetworkTargetError, validate_public_http_url

logger = logging.getLogger(__name__)

# Circuit breakers for browser operations
_browser_navigate_cb = get_circuit_breaker(
    "browser:navigate", failure_threshold=3, recovery_timeout=120
)
_browser_content_cb = get_circuit_breaker(
    "browser:content", failure_threshold=5, recovery_timeout=60
)


class BrowserAgent:
    def __init__(self) -> None:
        self._playwright: Any = None
        self._browser: Any = None
        self._page: Any = None

    async def start(self, headless: bool = True) -> None:
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=headless)
        context = await self._browser.new_context(
            viewport={"width": 1280, "height": 720},
        )
        await context.route("**/*", self._guard_outbound_request)
        self._page = await context.new_page()

    @staticmethod
    async def _guard_outbound_request(route: Any) -> None:
        url = route.request.url
        if url.startswith(("data:", "blob:", "about:")):
            await route.continue_()
            return
        try:
            validate_public_http_url(url)
        except UnsafeNetworkTargetError:
            await route.abort("blockedbyclient")
            return
        await route.continue_()

    async def stop(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def get_accessibility_tree(self) -> str:
        if self._page is None:
            return "Erro: navegador nao iniciado."
        try:
            snapshot = await self._page.accessibility.snapshot()
            return self._format_tree(snapshot)
        except Exception as e:
            return f"Erro ao obter arvore: {e}"

    def _format_tree(self, node: Any, depth: int = 0) -> str:
        if not node:
            return ""
        lines = []
        role = node.get("role", "")
        name = node.get("name", "")
        value = node.get("value", "")
        indent = "  " * depth
        label = f"{role}: {name}" if name else role
        if value:
            label += f" = {value}"
        lines.append(f"{indent}{label}")
        for child in node.get("children", []):
            lines.append(self._format_tree(child, depth + 1))
        return "\n".join(lines)

    async def execute_action(self, action: dict) -> Any:
        act = action
        try:
            if self._page is None:
                return "Erro: navegador nao iniciado."
            if act["action"] == "navigate":
                await self._page.goto(act["url"], wait_until="domcontentloaded")
            elif act["action"] == "click":
                await self._page.get_by_role(act["role"], name=act.get("name")).click(timeout=5000)
            elif act["action"] == "type":
                locator = self._page.get_by_role(act["role"], name=act.get("name"))
                await locator.fill(act["text"])
            elif act["action"] == "press":
                await self._page.keyboard.press(act["key"])
            elif act["action"] == "screenshot":
                return await self._page.screenshot(full_page=False)
            elif act["action"] == "evaluate":
                return await self._page.evaluate(act["expression"])
            return None
        except Exception as e:
            return f"Erro: {e}"
        finally:
            with contextlib.suppress(Exception):
                await self._page.wait_for_load_state("domcontentloaded")

    async def get_page_content(self) -> str:
        if self._page is None:
            return ""
        return str(await self._page.content())

    async def get_current_url(self) -> str:
        if self._page is None:
            return ""
        return str(self._page.url)


def navegar_web(url: str, timeout: int = 30) -> str:
    # Check circuit breaker before attempting
    if not _browser_navigate_cb.allow_request():
        raise CircuitBreakerOpenError(
            "Navegacao web indisponivel (circuit breaker aberto). Tente novamente em 120s."
        )

    agent = BrowserAgent()
    loop = asyncio.new_event_loop()

    async def _run() -> str:
        validated_url = validate_public_http_url(url)
        await agent.start(headless=True)
        await agent.execute_action({"action": "navigate", "url": validated_url})
        tree = await agent.get_accessibility_tree()
        url_actual = await agent.get_current_url()
        await agent.stop()
        return f"URL: {url_actual}\n\nArvore de acessibilidade:\n{tree[:3000]}"

    try:
        resultado: str = loop.run_until_complete(asyncio.wait_for(_run(), timeout=timeout))
        _browser_navigate_cb.record_success()
    except TimeoutError:
        _browser_navigate_cb.record_failure()
        resultado = f"Timeout ao acessar {url}"
    except (CircuitBreakerOpenError, UnsafeNetworkTargetError):
        raise
    except Exception as e:
        _browser_navigate_cb.record_failure()
        resultado = f"Erro ao navegar: {e}"
    finally:
        loop.close()

    return resultado
