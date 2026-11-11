"""Drive the real HA frontend of the local dev instance and screenshot the card.

Usage (dev instance running via scripts/develop):
    python scripts/check_card.py <output dir>

Needs Playwright's headless Chromium (``npx playwright install chromium``);
if system libraries are missing (libnss3, libnspr4), extract them without
root (``apt-get download libnss3 libnspr4`` + ``dpkg -x``) and point
``LAEUTWERK_CHROME_LIBS`` at the directory with the .so files.

1. Onboard the dev instance via its API (first run only) and get tokens.
2. Put a laeutwerk-card on the default dashboard (lovelace/config/save).
3. Start headless Chromium with remote debugging, log in by writing the
   tokens to localStorage, open the dashboard and take screenshots of the
   overview, the rule editor and the signal editor.

Only talks to http://localhost:8123 (the dev instance in ./config).
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import aiohttp

HA = "http://localhost:8123"
CLIENT_ID = f"{HA}/"
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
TOKENS = OUT / "ha_tokens.json"
SHELL = (
    Path.home()
    / ".cache/ms-playwright/chromium_headless_shell-1194/chrome-linux/headless_shell"
)
LIBS = os.environ.get("LAEUTWERK_CHROME_LIBS", "")


async def tokens(session: aiohttp.ClientSession) -> dict:
    async with session.get(f"{HA}/api/onboarding") as resp:
        # After onboarding Home Assistant removes this endpoint (404).
        steps = await resp.json() if resp.status == 200 else []
    user_done = next((s["done"] for s in steps if s["step"] == "user"), True)
    if not user_done:
        async with session.post(
            f"{HA}/api/onboarding/users",
            json={
                "client_id": CLIENT_ID,
                "name": "Dev",
                "username": "dev",
                "password": "dev-dev-dev",
                "language": "de",
            },
        ) as resp:
            code = (await resp.json())["auth_code"]
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": CLIENT_ID,
        }
    else:
        saved = json.loads(TOKENS.read_text())
        data = {
            "grant_type": "refresh_token",
            "refresh_token": saved["refresh_token"],
            "client_id": CLIENT_ID,
        }
    async with session.post(f"{HA}/auth/token", data=data) as resp:
        tok = await resp.json()
    if "refresh_token" not in tok:
        tok["refresh_token"] = json.loads(TOKENS.read_text())["refresh_token"]
    TOKENS.write_text(json.dumps(tok))
    headers = {"Authorization": f"Bearer {tok['access_token']}"}
    for step, body in (
        ("core_config", {}),
        ("analytics", {}),
        (
            "integration",
            {"client_id": CLIENT_ID, "redirect_uri": f"{HA}/?auth_callback=1"},
        ),
    ):
        if not next((s["done"] for s in steps if s["step"] == step), True):
            await session.post(
                f"{HA}/api/onboarding/{step}", json=body, headers=headers
            )
    return tok


async def save_dashboard(session: aiohttp.ClientSession, token: str) -> None:
    async with session.ws_connect(f"{HA}/api/websocket") as ws:
        await ws.receive_json()
        await ws.send_json({"type": "auth", "access_token": token})
        assert (await ws.receive_json())["type"] == "auth_ok"
        await ws.send_json({"id": 9, "type": "lovelace/dashboards/list"})
        dashboards = (await ws.receive_json())["result"]
        if not any(d["url_path"] == "laeutwerk-dev" for d in dashboards):
            await ws.send_json(
                {
                    "id": 10,
                    "type": "lovelace/dashboards/create",
                    "url_path": "laeutwerk-dev",
                    "title": "Läutwerk",
                    "mode": "storage",
                }
            )
            print("dashboard created:", (await ws.receive_json())["success"])
        await ws.send_json({"id": 11, "type": "repairs/list_issues"})
        issues = (await ws.receive_json())["result"]["issues"]
        print(
            "issues:",
            [
                (i["domain"], i["issue_id"], i.get("translation_placeholders"))
                for i in issues
            ],
        )
        await ws.send_json(
            {
                "id": 12,
                "url_path": "laeutwerk-dev",
                "type": "lovelace/config/save",
                "config": {
                    "views": [
                        {
                            "title": "Läutwerk",
                            "path": "lw",
                            "cards": [
                                {"type": "custom:laeutwerk-card", "view": "overview"}
                            ],
                        }
                    ]
                },
            }
        )
        print("dashboard saved:", (await ws.receive_json())["success"])


class Cdp:
    """Minimal Chrome DevTools Protocol client."""

    def __init__(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        self.ws = ws
        self.n = 0

    async def call(self, method: str, **params):
        self.n += 1
        await self.ws.send_json({"id": self.n, "method": method, "params": params})
        while True:
            msg = await self.ws.receive_json()
            if msg.get("id") == self.n:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result", {})

    async def js(self, expression: str):
        res = await self.call(
            "Runtime.evaluate",
            expression=expression,
            awaitPromise=True,
            returnByValue=True,
        )
        if "exceptionDetails" in res:
            raise RuntimeError(res["exceptionDetails"])
        return res["result"].get("value")

    async def shot(self, name: str) -> None:
        res = await self.call(
            "Page.captureScreenshot", format="png", captureBeyondViewport=True
        )
        (OUT / f"real_{name}.png").write_bytes(base64.b64decode(res["data"]))
        print("screenshot", name)


# Find the card through all shadow roots.
FIND = """
(() => {
  const find = (root, sel) => {
    const hit = root.querySelector(sel);
    if (hit) return hit;
    for (const el of root.querySelectorAll('*')) {
      if (el.shadowRoot) { const r = find(el.shadowRoot, sel); if (r) return r; }
    }
    return null;
  };
  window.__find = find;
  return true;
})()
"""


async def main() -> None:
    async with aiohttp.ClientSession() as session:
        tok = await tokens(session)
        await save_dashboard(session, tok["access_token"])
        hass_tokens = {
            "access_token": tok["access_token"],
            "refresh_token": tok["refresh_token"],
            "expires_in": tok["expires_in"],
            "token_type": "Bearer",
            "hassUrl": HA,
            "clientId": CLIENT_ID,
            "expires": int(time.time() * 1000) + tok["expires_in"] * 1000,
        }
        env = {**os.environ, "LD_LIBRARY_PATH": LIBS} if LIBS else dict(os.environ)
        proc = subprocess.Popen(
            [
                str(SHELL),
                "--no-sandbox",
                "--remote-debugging-port=9333",
                "--window-size=390,1600",
                "--hide-scrollbars",
                "about:blank",
            ],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            for _ in range(50):
                try:
                    async with session.get("http://127.0.0.1:9333/json") as resp:
                        pages = await resp.json()
                    if pages:
                        break
                except aiohttp.ClientError:
                    pass
                await asyncio.sleep(0.2)
            page = next(p for p in pages if p["type"] == "page")
            async with session.ws_connect(
                page["webSocketDebuggerUrl"], max_msg_size=0
            ) as ws:
                cdp = Cdp(ws)
                await cdp.call("Page.enable")
                await cdp.call("Runtime.enable")
                await cdp.call(
                    "Emulation.setDeviceMetricsOverride",
                    width=390,
                    height=1600,
                    deviceScaleFactor=1,
                    mobile=True,
                )
                await cdp.call("Page.navigate", url=f"{HA}/onboarding.html")
                await asyncio.sleep(2)
                await cdp.js(
                    f"localStorage.setItem('hassTokens', {json.dumps(json.dumps(hass_tokens))});"
                    "localStorage.setItem('selectedLanguage', '\"de\"'); true"
                )
                await cdp.call("Page.navigate", url=f"{HA}/laeutwerk-dev/lw")
                await asyncio.sleep(10)
                await cdp.js(FIND)
                errors = await cdp.js(
                    "(() => { const c = window.__find(document, 'laeutwerk-card');"
                    " return c ? c.shadowRoot.innerHTML.length : -1 })()"
                )
                print("card rendered, shadow html length:", errors)
                await cdp.shot("overview")
                # Open the editor for the first rule.
                await cdp.js(
                    "(async () => { const c = window.__find(document, 'laeutwerk-card');"
                    " c._editing = c._rules[0]; await c.updateComplete;"
                    " const e = c.shadowRoot.querySelector('laeutwerk-rule-editor');"
                    " await e.updateComplete;"
                    " e._open = new Set([1, 2, 3, 4, 5, 6, 7]); return true })()"
                )
                await asyncio.sleep(4)
                await cdp.shot("editor")
                # Open the second signal (opportunity trigger) in the signal editor.
                await cdp.js(
                    "(async () => { const c = window.__find(document, 'laeutwerk-card');"
                    " const e = c.shadowRoot.querySelector('laeutwerk-rule-editor');"
                    " const r = c._rules[0];"
                    " e._signal = { index: 0, signal: JSON.parse(JSON.stringify("
                    "   Object.assign({}, r.signals[0], {when: {opportunity: [{trigger: 'state',"
                    "   entity_id: 'light.stehleuchte', to: 'on'}], manual_only: true},"
                    "   conditions: [{condition: 'state', entity_id: 'input_boolean.steven_home', state: 'on'}]})))};"
                    " await e.updateComplete;"
                    # Sections are collapsible (0.7.5): open the ones with HA editors.
                    " const se = window.__find(document, 'laeutwerk-signal-editor');"
                    " se._openSec = new Set(['when', 'only_if', 'what', 'texts']);"
                    " await se.updateComplete; return true })()"
                )
                await asyncio.sleep(5)
                info = await cdp.js(
                    "(() => { const c = window.__find(document, 'laeutwerk-signal-editor');"
                    " const fields = [...c.shadowRoot.querySelectorAll('laeutwerk-field')];"
                    " return fields.map(f => f.shadowRoot.querySelector('ha-selector') ? 'ha-selector' :"
                    " (f.shadowRoot.querySelector('textarea,input') ? 'fallback' : 'empty')) })()"
                )
                print("signal editor fields:", info)
                await cdp.shot("signal")
                # Regression (0.6.1): edits must survive Home Assistant state
                # changes (the card re-renders the editor on every hass update).
                await cdp.js(
                    "(() => { const se = window.__find(document, 'laeutwerk-signal-editor');"
                    " const ta = se.shadowRoot.querySelector('textarea');"
                    " ta.value = 'EDIT SURVIVES'; ta.dispatchEvent(new Event('input')); return true })()"
                )
                for value in range(3):
                    async with session.post(
                        f"{HA}/api/states/sensor.laeutwerk_check",
                        json={"state": str(value)},
                        headers={"Authorization": f"Bearer {tok['access_token']}"},
                    ):
                        pass
                    await asyncio.sleep(1)
                kept = await cdp.js(
                    "(() => { const se = window.__find(document, 'laeutwerk-signal-editor');"
                    " return se._sig.message })()"
                )
                print("edit kept after state changes:", kept == "EDIT SURVIVES")
                if kept != "EDIT SURVIVES":
                    raise SystemExit("edits were reset by state changes")
                # Template picker (new rule) and the "advanced" step.
                templates = await cdp.js(
                    "(async () => { const c = window.__find(document, 'laeutwerk-card');"
                    " c._editing = undefined; c._picking = true; await c.updateComplete;"
                    " await new Promise(r => setTimeout(r, 1500));"
                    " const p = c.shadowRoot.querySelector('laeutwerk-template-picker');"
                    " return [...p.shadowRoot.querySelectorAll('.tpl .name')].map(n => n.textContent) })()"
                )
                print("templates:", templates)
                await cdp.shot("templates")
                advanced = await cdp.js(
                    "(async () => { const c = window.__find(document, 'laeutwerk-card');"
                    " c._picking = false; c._editing = Object.assign({}, c._rules[0], {"
                    "  escalation: [{after: '2h'}], assignee: {persons: [], rotation: 'fixed'}});"
                    " await c.updateComplete; await new Promise(r => setTimeout(r, 2500));"
                    " const e = c.shadowRoot.querySelector('laeutwerk-rule-editor');"
                    " e._open = new Set([7]); await e.updateComplete;"
                    " await new Promise(r => setTimeout(r, 1500));"
                    " const sec = e.shadowRoot.querySelectorAll('section')[6];"
                    " sec.scrollIntoView();"
                    " return [...sec.querySelectorAll('laeutwerk-field')].map(f =>"
                    "  f.shadowRoot.querySelector('ha-selector') ? 'ha-selector' : 'fallback') })()"
                )
                print("advanced step fields:", advanced)
                await cdp.shot("advanced")
        finally:
            proc.terminate()


asyncio.run(main())
