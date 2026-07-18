import asyncio


class BrowserAgent:
    def __init__(self):
        self._playwright = None
        self._browser = None
        self._page = None

    async def start(self, headless=True):
        from playwright.async_api import async_playwright
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=headless)
        context = await self._browser.new_context(
            viewport={"width": 1280, "height": 720},
        )
        self._page = await context.new_page()

    async def stop(self):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def get_accessibility_tree(self):
        try:
            snapshot = await self._page.accessibility.snapshot()
            return self._format_tree(snapshot)
        except Exception as e:
            return f"Erro ao obter arvore: {e}"

    def _format_tree(self, node, depth=0):
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

    async def execute_action(self, action):
        act = action
        try:
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
            try:
                await self._page.wait_for_load_state("domcontentloaded")
            except Exception:
                pass

    async def get_page_content(self):
        return await self._page.content()

    async def get_current_url(self):
        return self._page.url


def navegar_web(url, timeout=30):
    agent = BrowserAgent()
    loop = asyncio.new_event_loop()

    async def _run():
        await agent.start(headless=True)
        await agent.execute_action({"action": "navigate", "url": url})
        tree = await agent.get_accessibility_tree()
        url_actual = await agent.get_current_url()
        await agent.stop()
        return f"URL: {url_actual}\n\nArvore de acessibilidade:\n{tree[:3000]}"

    try:
        resultado = loop.run_until_complete(asyncio.wait_for(_run(), timeout=timeout))
    except asyncio.TimeoutExpired:
        resultado = f"Timeout ao acessar {url}"
    except Exception as e:
        resultado = f"Erro ao navegar: {e}"
    finally:
        loop.close()

    return resultado
