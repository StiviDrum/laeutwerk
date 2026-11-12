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
    elif TOKENS.exists():
        saved = json.loads(TOKENS.read_text())
        data = {
            "grant_type": "refresh_token",
            "refresh_token": saved["refresh_token"],
            "client_id": CLIENT_ID,
        }
    else:
        # New output folder: log in as the dev user created during onboarding.
        async with session.post(
            f"{HA}/auth/login_flow",
            json={
                "client_id": CLIENT_ID,
                "handler": ["homeassistant", None],
                "redirect_uri": CLIENT_ID,
            },
        ) as resp:
            flow_id = (await resp.json())["flow_id"]
        async with session.post(
            f"{HA}/auth/login_flow/{flow_id}",
            json={
                "client_id": CLIENT_ID,
                "username": "dev",
                "password": "dev-dev-dev",
            },
        ) as resp:
            code = (await resp.json())["result"]
        data = {
            "grant_type": "authorization_code",
            "code": code,
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

    async def shot(self, name: str, *, full: bool = True) -> None:
        # full=False keeps the viewport, so popups that close on resize stay.
        res = await self.call(
            "Page.captureScreenshot", format="png", captureBeyondViewport=full
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
                # Keyword icons + headline (0.8.0): first row icon only (rule
                # colour), second row icon and colour, then a custom headline.
                updated = await cdp.js(
                    "(async () => { const c = window.__find(document, 'laeutwerk-card');"
                    " const r = JSON.parse(JSON.stringify(c._rules[0]));"
                    " const rows = (r.filter && r.filter.keywords && r.filter.keywords.rows) || [];"
                    " const icons = ['mdi:newspaper-variant-outline', 'mdi:leaf',"
                    "  'mdi:trash-can-outline', 'mdi:recycle'];"
                    " rows.forEach((row, i) => { row.icon = icons[i % 4];"
                    "  if (i === 0) delete row.color; else if (!row.color) row.color = '#43a047'; });"
                    " r.headline = '{wann} raus: {titel}';"
                    " delete r.status;"
                    " await c.hass.callWS({type: 'laeutwerk/rules/update', rule_id: r.id, rule: r});"
                    " await new Promise(res => setTimeout(res, 3000));"
                    " return rows.length })()"
                )
                print("keyword rows with icons:", updated)
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
                # Keyword table close-up, a help tip and the suggestion list.
                await cdp.js(
                    "(() => { const c = window.__find(document, 'laeutwerk-card');"
                    " const e = c.shadowRoot.querySelector('laeutwerk-rule-editor');"
                    " const sec = e.shadowRoot.querySelectorAll('section')[1];"
                    " sec.scrollIntoView(); return true })()"
                )
                await asyncio.sleep(1)
                await cdp.shot("keywords")
                tip = await cdp.js(
                    "(async () => { const c = window.__find(document, 'laeutwerk-card');"
                    " const e = c.shadowRoot.querySelector('laeutwerk-rule-editor');"
                    # The tip in the keyword table header (0.8.1: must not be covered).
                    " const t = e.shadowRoot.querySelector('.kwtable laeutwerk-help-tip')"
                    "  || e.shadowRoot.querySelector('laeutwerk-help-tip');"
                    " if (!t) return 'no help tip'; t.scrollIntoView({block: 'center'});"
                    " const b = t.shadowRoot.querySelector('button') || t;"
                    " b.click(); await new Promise(r => setTimeout(r, 400));"
                    # The bubble sits on <body>; it must be the topmost element.
                    " const tip = document.body.querySelector(':scope > [role=tooltip]');"
                    " if (!tip) return 'no bubble';"
                    " const r = tip.getBoundingClientRect();"
                    " tip.style.pointerEvents = 'auto';"
                    " const top = document.elementFromPoint(r.left + 20, r.top + r.height / 2);"
                    " tip.style.pointerEvents = 'none';"
                    " return (top === tip ? 'on top: ' : 'COVERED: ') + tip.textContent.slice(0, 60) })()"
                )
                print("help tip:", tip)
                await cdp.shot("helptip", full=False)
                await cdp.js(
                    "(() => { document.body.dispatchEvent(new PointerEvent('pointerdown',"
                    " {bubbles: true, composed: true})); document.body.click(); return true })()"
                )
                # Headline previews (0.8.1): one under each field.
                previews = await cdp.js(
                    "(() => { const c = window.__find(document, 'laeutwerk-card');"
                    " const e = c.shadowRoot.querySelector('laeutwerk-rule-editor');"
                    " const sec = e.shadowRoot.querySelectorAll('section')[5];"
                    " return [...sec.querySelectorAll('.preview, .muted')]"
                    "  .map(x => x.textContent.trim().replace(/\\s+/g, ' ')) })()"
                )
                print("headline previews:", previews)
                suggest = await cdp.js(
                    "(async () => { const c = window.__find(document, 'laeutwerk-card');"
                    " const e = c.shadowRoot.querySelector('laeutwerk-rule-editor');"
                    " const s = [...e.shadowRoot.querySelectorAll('laeutwerk-suggest')]"
                    "  .find(x => x.shadowRoot.querySelector('input,textarea'));"
                    " if (!s) return 'no suggest field'; s.scrollIntoView({block: 'center'});"
                    " const i = s.shadowRoot.querySelector('input,textarea'); i.focus();"
                    " i.value = '{w'; i.setSelectionRange(2, 2);"
                    " i.dispatchEvent(new InputEvent('input', {bubbles: true, composed: true}));"
                    " await new Promise(r => setTimeout(r, 500));"
                    " const root = s.shadowRoot; const items = [...root.querySelectorAll('li, .item, [role=option]')];"
                    " return items.map(x => x.textContent.trim()) })()"
                )
                print("suggestions for '{w':", suggest)
                await cdp.shot("suggest")
                await cdp.js(
                    "(() => { const c = window.__find(document, 'laeutwerk-card');"
                    " const e = c.shadowRoot.querySelector('laeutwerk-rule-editor');"
                    " const s = [...e.shadowRoot.querySelectorAll('laeutwerk-suggest')]"
                    "  .find(x => x.shadowRoot.querySelector('input,textarea'));"
                    " if (s) { const i = s.shadowRoot.querySelector('input,textarea');"
                    "  i.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true})); i.blur(); }"
                    " return true })()"
                )
                # Own colour picker (0.7.6): open it from the rule colour,
                # tap the wheel, check the value, then cancel.
                picked = await cdp.js(
                    "(async () => { const c = window.__find(document, 'laeutwerk-card');"
                    " const e = c.shadowRoot.querySelector('laeutwerk-rule-editor');"
                    " const f = [...e.shadowRoot.querySelectorAll('laeutwerk-field')]"
                    "  .find(x => x.selector && x.selector.color_rgb);"
                    " f.scrollIntoView();"
                    " f.shadowRoot.querySelector('.colorbtn, .pick').click();"
                    " await new Promise(r => setTimeout(r, 500));"
                    " const p = document.querySelector('laeutwerk-color-popup');"
                    " if (!p) return 'no popup';"
                    " const w = p.shadowRoot.querySelector('.wheel').getBoundingClientRect();"
                    " const opts = {bubbles: true, pointerId: 1, clientX: w.right - 4,"
                    "  clientY: w.top + w.height / 2};"
                    " p.shadowRoot.querySelector('.wheel').dispatchEvent(new PointerEvent('pointerdown', opts));"
                    " await p.updateComplete; return p._hex })()"
                )
                print("colour picker, right edge of the wheel:", picked)
                await cdp.shot("colorpicker")
                await cdp.js(
                    "(() => { const p = document.querySelector('laeutwerk-color-popup');"
                    " p.shadowRoot.querySelector('.pill.outline').click(); return true })()"
                )
                # Keyword table cell: the popup must not be clipped by the table.
                await cdp.js(
                    "(async () => { const c = window.__find(document, 'laeutwerk-card');"
                    " const e = c.shadowRoot.querySelector('laeutwerk-rule-editor');"
                    # 0.8.0: tap the keyword's round icon -> icon + colour popup.
                    " const b = e.shadowRoot.querySelector('.kwrow:not(.head) .lookbtn');"
                    " if (!b) return false; b.scrollIntoView({block: 'center'}); b.click();"
                    " await new Promise(r => setTimeout(r, 800)); return true })()"
                )
                await asyncio.sleep(1)
                await cdp.shot("keyword_look")
                await cdp.js(
                    "(async () => { const k = document.querySelector('laeutwerk-keyword-look');"
                    " if (!k) return false;"
                    " const f = k.shadowRoot.querySelectorAll('laeutwerk-field')[1];"
                    " f.shadowRoot.querySelector('.colorbtn, .pick').click(); return true })()"
                )
                await asyncio.sleep(1)
                await cdp.shot("colorpicker_keyword")
                await cdp.js(
                    "(() => { const p = document.querySelector('laeutwerk-color-popup');"
                    " if (p) p.shadowRoot.querySelector('.pill.outline').click();"
                    " const k = document.querySelector('laeutwerk-keyword-look');"
                    " if (k) k.shadowRoot.querySelector('.pill.outline').click(); return true })()"
                )
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
                    # Texts sit in suggestion fields (0.8.0); fall back to a plain textarea.
                    " const sf = [...se.shadowRoot.querySelectorAll('laeutwerk-suggest')]"
                    "  .find(x => x.multiline);"
                    " const ta = sf ? sf.shadowRoot.querySelector('textarea')"
                    "  : se.shadowRoot.querySelector('textarea');"
                    " ta.value = 'EDIT SURVIVES';"
                    " ta.dispatchEvent(new InputEvent('input', {bubbles: true, composed: true}));"
                    " return true })()"
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
