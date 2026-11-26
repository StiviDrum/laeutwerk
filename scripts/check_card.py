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
_DEFAULT_LIBS = Path.home() / ".cache/laeutwerk-chrome-libs/usr/lib/x86_64-linux-gnu"
# Viewport width: 390 (phone, default) or e.g. 1440 for desktop checks.
WIDTH = int(os.environ.get("LAEUTWERK_WIDTH", "390"))
LIBS = os.environ.get("LAEUTWERK_CHROME_LIBS") or (
    str(_DEFAULT_LIBS) if _DEFAULT_LIBS.is_dir() else ""
)


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
                                {"type": "custom:laeutwerk-card", "view": "overview"},
                                {"type": "custom:laeutwerk-card", "compact": True},
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
                f"--window-size={WIDTH},1600",
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
                    width=WIDTH,
                    height=1600,
                    deviceScaleFactor=1,
                    mobile=WIDTH < 600,
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
                # Early acknowledge (0.9.2): a reminder days ahead is not done,
                # the service answers with the "too early" text instead.
                early = await cdp.js(
                    "(async () => { const c = window.__find(document, 'laeutwerk-card');"
                    " const r = c._rules.find(x => (x.status?.reminders || [])"
                    "  .some(m => m.state === 'planned' && new Date(m.start) - Date.now() > 3 * 864e5));"
                    " if (!r) return 'no planned reminder > 3 days';"
                    " const m = r.status.reminders.find(m => m.state === 'planned'"
                    "  && new Date(m.start) - Date.now() > 3 * 864e5);"
                    " const res = await c.hass.callWS({type: 'call_service', domain: 'laeutwerk',"
                    "  service: 'acknowledge', service_data: {rule: r.id, reminder_id: m.id},"
                    "  return_response: true});"
                    " return JSON.stringify(res.response) })()"
                )
                print("acknowledge days ahead:", early)
                await cdp.shot("overview")
                # Reminder for the snooze/history checks: a trigger rule that we
                # start (service) – it shows up as an open reminder in the card.
                await cdp.js(
                    "(async () => { const c = window.__find(document, 'laeutwerk-card');"
                    " try { await c.hass.callWS({type: 'laeutwerk/rules/delete', rule_id: 'chk_hist'}); } catch (e) {}"
                    " await c.hass.callService('laeutwerk', 'create_rule', {config: {id: 'chk_hist',"
                    "  name: 'Check Verlauf', start_triggers: [{trigger: 'state', entity_id: 'input_boolean.lampe', to: 'on'}],"
                    "  signals: [{id: 'push', type: 'notify', audience: 'all', title: 'T', message: 'M', send_on: 'first'}],"
                    "  expire: '+32h'}});"
                    " await new Promise(r => setTimeout(r, 2500));"
                    " await c.hass.callService('laeutwerk', 'start', {rule: 'chk_hist'});"
                    " await new Promise(r => setTimeout(r, 3000)); return true })()"
                )
                # (a) The card has no rule editor and no template picker any more.
                no_editor = await cdp.js(
                    "(() => { const find = (root, sel, out = []) => {"
                    "  root.querySelectorAll(sel).forEach(x => out.push(x));"
                    "  root.querySelectorAll('*').forEach(x => x.shadowRoot && find(x.shadowRoot, sel, out));"
                    "  return out; };"
                    " return find(document, 'laeutwerk-rule-editor').length"
                    "  + find(document, 'laeutwerk-template-picker').length })()"
                )
                print("card has no editor/picker:", no_editor == 0)
                if no_editor:
                    raise SystemExit("the card still contains a rule editor or picker")
                # (c) "Später" opens the snooze menu with presets.
                later = await cdp.js(
                    "(async () => { const c = window.__find(document, 'laeutwerk-card');"
                    " const b = [...c.shadowRoot.querySelectorAll('.actions button.pill.outline')][0];"
                    " if (!b) return 'no open reminder / Später button';"
                    " b.click(); await c.updateComplete; await new Promise(r => setTimeout(r, 600));"
                    " const m = c.shadowRoot.querySelector('laeutwerk-snooze-menu');"
                    " if (!m) return 'no snooze menu';"
                    " await m.updateComplete;"
                    " const n = m.shadowRoot.querySelectorAll('button.pill').length;"
                    " m.scrollIntoView({block: 'center'});"
                    " return 'presets:' + n })()"
                )
                print("later -> snooze menu:", later)
                await cdp.shot("snooze_menu", full=False)
                if not later.startswith("presets:") or int(later.split(":")[1]) < 2:
                    raise SystemExit(f"snooze menu check failed: {later}")
                await cdp.js(
                    "(async () => { const c = window.__find(document, 'laeutwerk-card');"
                    " c._laterFor = undefined; await c.updateComplete; return true })()"
                )
                # Compact card: dialog lists every rule with a switch, no editor inside.
                compact = await cdp.js(
                    "(async () => { const find = (root, sel, out = []) => {"
                    "  root.querySelectorAll(sel).forEach(x => out.push(x));"
                    "  root.querySelectorAll('*').forEach(x => x.shadowRoot && find(x.shadowRoot, sel, out));"
                    "  return out; };"
                    " const card = find(document, 'laeutwerk-card').find(x => x._config && x._config.compact);"
                    " if (!card) return 'no compact card';"
                    " await card._openDialog(); await new Promise(r => setTimeout(r, 800));"
                    " const d = find(document, 'laeutwerk-task-dialog')[0];"
                    " if (!d) return 'no dialog';"
                    " await d.updateComplete;"
                    " const switches = d.shadowRoot.querySelectorAll('[role=switch]').length;"
                    " const editors = find(document, 'laeutwerk-rule-editor').length;"
                    " return JSON.stringify({switches, editors, rules: card._rules.length}) })()"
                )
                print("compact dialog:", compact)
                await cdp.shot("compact_dialog", full=False)
                await cdp.js(
                    "(() => { const find = (root, sel, out = []) => {"
                    "  root.querySelectorAll(sel).forEach(x => out.push(x));"
                    "  root.querySelectorAll('*').forEach(x => x.shadowRoot && find(x.shadowRoot, sel, out));"
                    "  return out; };"
                    " find(document, 'laeutwerk-task-dialog').forEach(d => d.close ? d.close() : d.remove());"
                    " return true })()"
                )
                info = json.loads(compact) if compact.startswith("{") else {}
                if not info:
                    raise SystemExit(f"compact dialog: {compact}")
                if info.get("switches", 0) < info.get("rules", 1):
                    raise SystemExit("compact dialog: rule switches missing")
                if info.get("editors"):
                    raise SystemExit("compact dialog: contains a rule editor")
                # (b) Admin "Bearbeiten" / "Neue Regel" navigate into the panel.
                nav = await cdp.js(
                    "(async () => { const c = window.__find(document, 'laeutwerk-card');"
                    " const out = {};"
                    " const edit = c.shadowRoot.querySelector('.rulebtn');"
                    " if (edit) { edit.click(); await new Promise(r => setTimeout(r, 400));"
                    "  out.edit = location.pathname; history.back();"
                    "  await new Promise(r => setTimeout(r, 800)); }"
                    " const add = [...c.shadowRoot.querySelectorAll('button.chip')]"
                    "  .find(b => b.querySelector('ha-icon[icon=\"mdi:plus\"]'));"
                    " if (add) { add.click(); await new Promise(r => setTimeout(r, 400));"
                    "  out.add = location.pathname; }"
                    " return JSON.stringify(out) })()"
                )
                print("admin navigation:", nav)
                nav_d = json.loads(nav)
                if not str(nav_d.get("edit", "")).startswith("/laeutwerk/rules/") or (
                    nav_d.get("add") != "/laeutwerk/rules/new"
                ):
                    raise SystemExit(
                        f"admin actions do not navigate into the panel: {nav}"
                    )
                # Admin panel (UI rework): rule list, open a rule, browser back.
                await cdp.call("Page.navigate", url=f"{HA}/laeutwerk/rules")
                await asyncio.sleep(8)
                await cdp.js(FIND)
                panel = await cdp.js(
                    "(() => { const p = window.__find(document, 'laeutwerk-panel');"
                    " if (!p) return 'no panel';"
                    " return JSON.stringify({hscroll: document.documentElement.scrollWidth"
                    "  > innerWidth + 1, rows: p.shadowRoot.querySelectorAll('[data-rule]').length}) })()"
                )
                print("panel:", panel)
                await cdp.shot("panel_list", full=False)
                opened = await cdp.js(
                    "(async () => { const p = window.__find(document, 'laeutwerk-panel');"
                    " const row = p && p.shadowRoot.querySelector('[data-rule]');"
                    " if (!row) return 'no row'; row.click();"
                    " await new Promise(r => setTimeout(r, 3000));"
                    " const ed = window.__find(p.shadowRoot, 'laeutwerk-rule-editor');"
                    " return JSON.stringify({path: location.pathname, editor: !!ed,"
                    "  hscroll: document.documentElement.scrollWidth > innerWidth + 1}) })()"
                )
                print("panel rule opened:", opened)
                await cdp.shot("panel_editor", full=False)
                back = await cdp.js(
                    "(async () => { history.back(); await new Promise(r => setTimeout(r, 1500));"
                    " return location.pathname })()"
                )
                print("panel after back:", back)
                # Rule editor in the panel (pipeline layout): same checks as before.
                OPEN = (
                    "const p = window.__find(document, 'laeutwerk-panel');"
                    " const go = async (path, ms = 3500) => {"
                    "  history.pushState(null, '', path);"
                    "  window.dispatchEvent(new CustomEvent('location-changed'));"
                    "  await new Promise(r => setTimeout(r, ms)); };"
                    " const getEd = async () => { let ed;"
                    "  for (let i = 0; i < 60 && !ed; i++) {"
                    "   ed = window.__find(p.shadowRoot, 'laeutwerk-rule-editor');"
                    "   if (!ed) await new Promise(r => setTimeout(r, 200)); }"
                    "  if (ed) await ed.updateComplete; return ed; };"
                )
                first_rule = await cdp.js(
                    "(() => { const p = window.__find(document, 'laeutwerk-panel');"
                    " const r = p._rules.find(x => (x.signals || []).length >= 1 && x.sources"
                    "  && x.filter && x.filter.keywords && x.filter.keywords.rows.length);"
                    " return (r || p._rules[0]).id })()"
                )
                opened = await cdp.js(
                    "(async () => { "
                    + OPEN
                    + f" await go('/laeutwerk/rules/{first_rule}', 4500);"
                    " const ed = await getEd(); if (!ed) return 'no editor';"
                    " ed._open = new Set([1, 2, 3, 4, 5, 6, 7]); await ed.updateComplete;"
                    " await new Promise(r => setTimeout(r, 2500));"
                    " return ed.layout })()"
                )
                print("panel editor layout:", opened)
                if opened != "pipeline":
                    raise SystemExit(f"panel editor not found: {opened}")
                await cdp.shot("editor", full=False)
                # Keyword table, icons, help tip.
                kw = await cdp.js(
                    "(async () => { " + OPEN + " const ed = await getEd();"
                    " const rows = ed.shadowRoot.querySelectorAll('.kwrow:not(.head)').length;"
                    " const looks = ed.shadowRoot.querySelectorAll('.kwrow:not(.head) .lookbtn').length;"
                    " const sec = ed.shadowRoot.querySelector('section[data-step=\"2\"]');"
                    " if (sec) sec.scrollIntoView(); return JSON.stringify({rows, looks, sec: !!sec}) })()"
                )
                print("keyword table:", kw)
                await asyncio.sleep(1)
                await cdp.shot("keywords", full=False)
                tip = await cdp.js(
                    "(async () => { " + OPEN + " const e = await getEd();"
                    " const t = e.shadowRoot.querySelector('.kwtable laeutwerk-help-tip')"
                    "  || e.shadowRoot.querySelector('laeutwerk-help-tip');"
                    " if (!t) return 'no help tip'; t.scrollIntoView({block: 'center'});"
                    " await new Promise(r => setTimeout(r, 400));"
                    " const b = t.shadowRoot.querySelector('button') || t;"
                    " b.click(); await new Promise(r => setTimeout(r, 400));"
                    " const tip = window.__find(document, '[role=tooltip]');"
                    " if (!tip) return 'no bubble';"
                    " const r = tip.getBoundingClientRect();"
                    " tip.style.pointerEvents = 'auto';"
                    " const root = tip.getRootNode();"
                    " const top = root.elementFromPoint(r.left + 20, r.top + r.height / 2);"
                    " tip.style.pointerEvents = 'none';"
                    " return (top === tip ? 'on top: ' : 'COVERED: ') + tip.textContent.slice(0, 60) })()"
                )
                print("help tip:", tip)
                await cdp.shot("helptip", full=False)
                await cdp.js(
                    "(() => { document.body.dispatchEvent(new PointerEvent('pointerdown',"
                    " {bubbles: true, composed: true})); document.body.click(); return true })()"
                )
                # Modal dialog (HA card editor): a help tip inside must be in the top layer.
                modal = await cdp.js(
                    "(async () => { const d = document.createElement('dialog');"
                    " d.style.cssText = 'width:300px;height:200px';"
                    " const tip = document.createElement('laeutwerk-help-tip');"
                    " tip.text = 'Hilfe im Dialog'; d.appendChild(tip);"
                    " document.body.appendChild(d); d.showModal();"
                    " await tip.updateComplete; await new Promise(r => setTimeout(r, 200));"
                    " (tip.shadowRoot.querySelector('button') || tip).click();"
                    " await new Promise(r => setTimeout(r, 300));"
                    " const b = [...(document.querySelector('home-assistant')?.shadowRoot || document).querySelectorAll('[role=tooltip]')]"
                    "  .find(x => x.textContent.includes('Hilfe im Dialog'));"
                    " const ok = b && b.matches(':popover-open'); d.close(); d.remove();"
                    " return b ? (ok ? 'in top layer (above modal)' : 'NOT in top layer') : 'no bubble' })()"
                )
                print("help tip in modal dialog:", modal)
                previews = await cdp.js(
                    "(async () => { " + OPEN + " const e = await getEd();"
                    " const sec = e.shadowRoot.querySelector('section[data-step=\"6\"]');"
                    " if (!sec) return 'no step 6';"
                    " return [...sec.querySelectorAll('.preview, .muted')]"
                    "  .map(x => x.textContent.trim().replace(/\\s+/g, ' ')) })()"
                )
                print("headline previews:", previews)
                suggest = await cdp.js(
                    "(async () => { " + OPEN + " const e = await getEd();"
                    " const s = [...e.shadowRoot.querySelectorAll('laeutwerk-suggest')]"
                    "  .find(x => x.shadowRoot.querySelector('input,textarea'));"
                    " if (!s) return 'no suggest field'; s.scrollIntoView({block: 'center'});"
                    " const i = s.shadowRoot.querySelector('input,textarea'); i.focus();"
                    " i.value = '{w'; i.setSelectionRange(2, 2);"
                    " i.dispatchEvent(new InputEvent('input', {bubbles: true, composed: true}));"
                    " await new Promise(r => setTimeout(r, 500));"
                    " const items = [...s.shadowRoot.querySelectorAll('li, .item, [role=option]')];"
                    " const out = items.map(x => x.textContent.trim());"
                    " i.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true})); i.blur();"
                    " return out })()"
                )
                print("suggestions for '{w':", suggest)
                picked = await cdp.js(
                    "(async () => { " + OPEN + " const e = await getEd();"
                    " const f = [...e.shadowRoot.querySelectorAll('laeutwerk-field')]"
                    "  .find(x => x.selector && x.selector.color_rgb);"
                    " if (!f) return 'no colour field'; f.scrollIntoView();"
                    " f.shadowRoot.querySelector('.colorbtn, .pick').click();"
                    " await new Promise(r => setTimeout(r, 500));"
                    " const pp = window.__find(document, 'laeutwerk-color-popup');"
                    " if (!pp) return 'no popup';"
                    " const w = pp.shadowRoot.querySelector('.wheel').getBoundingClientRect();"
                    " const opts = {bubbles: true, pointerId: 1, clientX: w.right - 4,"
                    "  clientY: w.top + w.height / 2};"
                    " pp.shadowRoot.querySelector('.wheel').dispatchEvent(new PointerEvent('pointerdown', opts));"
                    " await pp.updateComplete; const hex = pp._hex;"
                    " pp.shadowRoot.querySelector('.pill.outline').click(); return hex })()"
                )
                print("colour picker, right edge of the wheel:", picked)
                look = await cdp.js(
                    "(async () => { " + OPEN + " const e = await getEd();"
                    " const b = e.shadowRoot.querySelector('.kwrow:not(.head) .lookbtn');"
                    " if (!b) return 'no look button'; b.scrollIntoView({block: 'center'}); b.click();"
                    " await new Promise(r => setTimeout(r, 800));"
                    " const k = window.__find(document, 'laeutwerk-keyword-look');"
                    " if (!k) return 'no popup';"
                    " const f = k.shadowRoot.querySelectorAll('laeutwerk-field')[1];"
                    " const pk = f && f.shadowRoot.querySelector('.colorbtn, .pick'); if (pk) pk.click();"
                    " await new Promise(r => setTimeout(r, 800));"
                    " const popup = !!window.__find(document, 'laeutwerk-color-popup');"
                    " const cp = window.__find(document, 'laeutwerk-color-popup');"
                    " if (cp) cp.shadowRoot.querySelector('.pill.outline').click();"
                    " k.shadowRoot.querySelector('.pill.outline').click();"
                    " return 'popup ok, colour popup: ' + popup })()"
                )
                print("keyword look popup:", look)
                # Signal editor: opportunity trigger + condition, then the
                # "edit survives hass updates" regression.
                sig = await cdp.js(
                    "(async () => { " + OPEN + " const e = await getEd();"
                    " const r = e._rule;"
                    " e._signal = { index: 0, signal: JSON.parse(JSON.stringify("
                    "   Object.assign({}, r.signals[0], {when: {opportunity: [{trigger: 'state',"
                    "   entity_id: 'light.stehleuchte', to: 'on'}], manual_only: true},"
                    "   conditions: [{condition: 'state', entity_id: 'input_boolean.steven_home', state: 'on'}]})))};"
                    " await e.updateComplete;"
                    " let se; for (let i = 0; i < 50 && !se; i++) {"
                    "  se = window.__find(e.shadowRoot, 'laeutwerk-signal-editor');"
                    "  if (!se) await new Promise(r => setTimeout(r, 200)); }"
                    " if (!se) return 'no signal editor';"
                    " se._openSec = new Set(['when', 'only_if', 'what', 'texts']);"
                    " await se.updateComplete; await new Promise(r => setTimeout(r, 4500));"
                    " const fields = [...se.shadowRoot.querySelectorAll('laeutwerk-field')];"
                    " return fields.map(f => f.shadowRoot.querySelector('ha-selector') ? 'ha-selector' :"
                    " (f.shadowRoot.querySelector('textarea,input') ? 'fallback' : 'empty')) })()"
                )
                print("signal editor fields:", sig)
                await cdp.shot("signal", full=False)
                await cdp.js(
                    "(() => { const p = window.__find(document, 'laeutwerk-panel');"
                    " const se = window.__find(p.shadowRoot, 'laeutwerk-signal-editor');"
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
                    "(() => { const p = window.__find(document, 'laeutwerk-panel');"
                    " const se = window.__find(p.shadowRoot, 'laeutwerk-signal-editor');"
                    " return se ? se._sig.message : 'no signal editor' })()"
                )
                print("edit kept after state changes:", kept == "EDIT SURVIVES")
                if kept != "EDIT SURVIVES":
                    raise SystemExit(f"edits were reset by state changes: {kept}")
                # Advanced step (escalation / assignee) and trigger mode.
                advanced = await cdp.js(
                    "(async () => { " + OPEN + " const e = await getEd();"
                    " e._signal = undefined; e._open = new Set([7]); await e.updateComplete;"
                    " await new Promise(r => setTimeout(r, 2000));"
                    " const sec = e.shadowRoot.querySelector('section[data-step=\"7\"]');"
                    " if (!sec) return 'no step 7'; sec.scrollIntoView();"
                    " return [...sec.querySelectorAll('laeutwerk-field')].map(f =>"
                    "  f.shadowRoot.querySelector('ha-selector') ? 'ha-selector' : 'fallback') })()"
                )
                print("advanced step fields:", advanced)
                await cdp.shot("advanced", full=False)
                mode = await cdp.js(
                    "(async () => { " + OPEN + " const e = await getEd();"
                    " e._setMode('trigger'); e._open = new Set([1, 2, 3, 4, 5, 6, 7]);"
                    " await e.updateComplete; await new Promise(r => setTimeout(r, 2500));"
                    " const trg = [...e.shadowRoot.querySelectorAll('laeutwerk-field')]"
                    "  .find(f => f.selector && f.selector.trigger);"
                    " const trigger = !!(trg && window.__find(trg.shadowRoot, 'ha-automation-trigger'));"
                    " const texts = !!(trg && trg.hass.localize("
                    "  'ui.panel.config.automation.editor.triggers.add'));"
                    " const ent = [...e.shadowRoot.querySelectorAll('laeutwerk-field')]"
                    "  .find(f => f.selector && f.selector.entity);"
                    " return JSON.stringify({mode: e._mode, trigger, texts, picker: !!ent}) })()"
                )
                print("trigger mode:", mode)
                await cdp.shot("trigger", full=False)
                if '"trigger":true' not in mode or '"texts":true' not in mode:
                    raise SystemExit(f"trigger editor in the panel incomplete: {mode}")
                # Template picker on /laeutwerk/rules/new.
                templates = await cdp.js(
                    "(async () => { "
                    + OPEN
                    + " await go('/laeutwerk/rules/new', 3000);"
                    " const nr = window.__find(p.shadowRoot, 'laeutwerk-new-rule');"
                    " if (nr) { nr.shadowRoot.querySelectorAll('button.tile')[1].click();"
                    "  await new Promise(r => setTimeout(r, 500)); }"
                    " let pk; for (let i = 0; i < 40 && !pk; i++) {"
                    "  pk = window.__find(p.shadowRoot, 'laeutwerk-template-picker');"
                    "  if (!pk) await new Promise(r => setTimeout(r, 200)); }"
                    " if (!pk) return 'no picker';"
                    " await new Promise(r => setTimeout(r, 1000));"
                    " const names = [...pk.shadowRoot.querySelectorAll('.tpl .name')].map(n => n.textContent);"
                    " const muell = [...pk.shadowRoot.querySelectorAll('button.tpl')]"
                    "  .find(b => b.textContent.includes('Müll'));"
                    " if (muell) { muell.click(); await new Promise(r => setTimeout(r, 1500)); }"
                    " const asks = pk.shadowRoot.querySelectorAll('laeutwerk-field, ha-selector, ha-entity-picker').length;"
                    " return [...names, 'needs:' + asks] })()"
                )
                print("templates:", templates)
                await cdp.shot("templates", full=False)
                if not isinstance(templates, list) or templates[-1] == "needs:0":
                    raise SystemExit(f"template picker empty: {templates}")
                # (d) History tab lists events; acknowledge the check reminder first.
                hist = await cdp.js(
                    "(async () => { "
                    + OPEN
                    + " try { await p.hass.callService('laeutwerk',"
                    "  'acknowledge', {rule: 'chk_hist'}); } catch (e) {}"
                    " await new Promise(r => setTimeout(r, 1500));"
                    " await go('/laeutwerk/history', 4000);"
                    " const h = window.__find(p.shadowRoot, 'laeutwerk-history');"
                    " if (!h) return 'no history tab';"
                    " await new Promise(r => setTimeout(r, 1500));"
                    " const n = h.shadowRoot.querySelectorAll('.ev').length;"
                    " const txt = h.shadowRoot.textContent.replace(/\\s+/g, ' ');"
                    " return JSON.stringify({events: n, hscroll: document.documentElement.scrollWidth > innerWidth + 1,"
                    "  mine: txt.includes('Check Verlauf')}) })()"
                )
                print("history tab:", hist)
                await cdp.shot("panel_history", full=False)
                if not hist.startswith("{") or json.loads(hist)["events"] < 1:
                    raise SystemExit(f"history tab shows no events: {hist}")
                # (e) Overview tab shows tiles.
                tiles = await cdp.js(
                    "(async () => { " + OPEN + " await go('/laeutwerk', 4000);"
                    " const o = window.__find(p.shadowRoot, 'laeutwerk-overview');"
                    " if (!o) return 'no overview';"
                    " return o.shadowRoot.querySelectorAll('.tile').length })()"
                )
                print("overview tiles:", tiles)
                await cdp.shot("panel_overview", full=False)
                if not isinstance(tiles, int) or tiles < 3:
                    raise SystemExit(f"overview tiles missing: {tiles}")
                # Round trip (UI rework acceptance): open every rule in the panel,
                # save it unchanged, the export must stay byte-identical.
                await cdp.js(
                    "(async () => { const p = window.__find(document, 'laeutwerk-panel');"
                    " p._picking = false; p._tool = undefined;"
                    " history.pushState(null, '', '/laeutwerk/rules');"
                    " window.dispatchEvent(new CustomEvent('location-changed'));"
                    " await new Promise(r => setTimeout(r, 3000)); return true })()"
                )
                roundtrip = await cdp.js(
                    "(async () => { const p = window.__find(document, 'laeutwerk-panel');"
                    " const ws = (m) => p.hass.callWS(m);"
                    " try { await ws({type: 'laeutwerk/rules/delete', rule_id: 'rt_service'}); } catch (e) {}"
                    " await p.hass.callService('laeutwerk', 'create_rule', {config: {id: 'rt_service',"
                    "  name: 'Rundlauf Dienst', start_triggers: [{trigger: 'state', entity_id: 'input_boolean.lampe', to: 'on'}],"
                    "  signals: [{id: 'push', type: 'notify', audience: 'all', title: 'T', message: 'M', send_on: 'first'},"
                    "   {id: 'push2', type: 'notify', audience: 'all', title: 'W {seit}', message: 'M', send_on: 'repeat'}],"
                    "  repeat: {every: 60, max: 3}, escalation: [{after: '10:00', min_age: '8h'}], expire: '+32h'}});"
                    " await new Promise(r => setTimeout(r, 2500));"
                    " const before = (await ws({type: 'laeutwerk/rules/export'})).yaml;"
                    " const ids = [...p.shadowRoot.querySelectorAll('[data-rule]')].map(r => r.dataset.rule);"
                    " const bad = [];"
                    " for (const id of ids) {"
                    "  history.pushState(null, '', '/laeutwerk/rules/' + id);"
                    "  window.dispatchEvent(new CustomEvent('location-changed'));"
                    "  await new Promise(r => setTimeout(r, 2500));"
                    "  const ed = window.__find(p.shadowRoot, 'laeutwerk-rule-editor');"
                    "  if (!ed) { bad.push(id + ': no editor'); continue; }"
                    "  try { localStorage.clear(); } catch (e) {}"
                    "  await ed._save(); await new Promise(r => setTimeout(r, 1500));"
                    "  if (ed._error) bad.push(id + ': ' + ed._error); }"
                    " const after = (await ws({type: 'laeutwerk/rules/export'})).yaml;"
                    " const a = before.split('\\n'), b = after.split('\\n'); const diff = [];"
                    " for (let i = 0; i < Math.max(a.length, b.length) && diff.length < 12; i++)"
                    "  if (a[i] !== b[i]) diff.push(i + ': ' + JSON.stringify(a[i]) + ' -> ' + JSON.stringify(b[i]));"
                    " return JSON.stringify({rules: ids.length, identical: before === after, bad, diff}) })()"
                )
                print("panel round trip:", roundtrip)
                if '"identical":true' not in str(roundtrip):
                    raise SystemExit("round trip changed the stored rules")
                # Stage 2: health check finds a missing entity and an unused
                # keyword; the live preview shows the next passes.
                health = await cdp.js(
                    "(async () => { const p = window.__find(document, 'laeutwerk-panel');"
                    " const ws = (m) => p.hass.callWS(m);"
                    " try { await ws({type: 'laeutwerk/rules/delete', rule_id: 'hc_test'}); } catch (e) {}"
                    " await ws({type: 'laeutwerk/rules/create', rule: {id: 'hc_test', name: 'Health-Test',"
                    "  sources: ['calendar.abfallkalender'], filter: {all_day: true, keywords: {columns: [],"
                    "  rows: [{match: 'Papier'}, {match: 'Sperrmüll'}]}}, reminders: [{at: '-1d 17:00'}],"
                    "  repeat: {every: 60, max: 2}, escalation: [{after: '20:00'}],"
                    "  signals: [{id: 'lampe', type: 'light_signal', entities: ['light.gibts_nicht'],"
                    "   pattern: {effect: 'blink', count: 3}}]}});"
                    " await new Promise(r => setTimeout(r, 2000));"
                    " history.pushState(null, '', '/laeutwerk/health');"
                    " window.dispatchEvent(new CustomEvent('location-changed'));"
                    " await new Promise(r => setTimeout(r, 6000));"
                    " const txt = p.shadowRoot.textContent.replace(/\\s+/g, ' ');"
                    " history.pushState(null, '', '/laeutwerk/rules/hc_test');"
                    " window.dispatchEvent(new CustomEvent('location-changed'));"
                    " await new Promise(r => setTimeout(r, 4000));"
                    " const ed = window.__find(p.shadowRoot, 'laeutwerk-rule-editor');"
                    " const prev = ed ? ed.shadowRoot.textContent.replace(/\\s+/g, ' ') : '';"
                    " const i = prev.indexOf('Nächste Treffer');"
                    " return JSON.stringify({missing: txt.includes('light.gibts_nicht'),"
                    "  keyword: txt.includes('Sperrmüll'), preview: i >= 0 ? prev.slice(i, i + 260) : 'no preview'}) })()"
                )
                print("health + preview:", health)
                if "Nächste 5 Auslösungen" not in str(
                    health
                ) or '"missing":true' not in str(health):
                    raise SystemExit("health check or live preview of passes missing")
                await cdp.shot("panel_health_rule", full=False)
                # Stage 4: chooser + assistant, templates with needs, sentence
                # view, week tab.
                st4 = await cdp.js(
                    "(async () => { const p = window.__find(document, 'laeutwerk-panel');"
                    " const go = async (u, ms) => { history.pushState(null, '', u);"
                    "  window.dispatchEvent(new CustomEvent('location-changed'));"
                    "  await new Promise(r => setTimeout(r, ms)); };"
                    " const txt = (n) => n ? n.shadowRoot.textContent.replace(/\\s+/g, ' ') : '';"
                    " const out = {};"
                    " await go('/laeutwerk/rules/new', 4000);"
                    " const nr = window.__find(p.shadowRoot, 'laeutwerk-new-rule');"
                    " out.chooser = nr ? [...nr.shadowRoot.querySelectorAll('button.tile')].length : 0;"
                    " if (nr) { nr.shadowRoot.querySelector('button.tile').click();"
                    "  await new Promise(r => setTimeout(r, 1500));"
                    "  const t = txt(nr); const i = t.indexOf('So würde');"
                    "  out.wizard = i >= 0 ? t.slice(i, i + 160) : 'no sentence';"
                    "  out.pickers = nr.shadowRoot.querySelectorAll('laeutwerk-field').length; }"
                    " await go('/laeutwerk/week', 6000);"
                    " const wk = window.__find(p.shadowRoot, 'laeutwerk-week');"
                    " out.week = txt(wk).slice(0, 200);"
                    " out.weekItems = wk ? wk.shadowRoot.querySelectorAll('.day button, .day .item, .item').length : 0;"
                    " out.hscroll = document.documentElement.scrollWidth > innerWidth + 1;"
                    " await go('/laeutwerk/rules/muell', 4000);"
                    " const ed = window.__find(p.shadowRoot, 'laeutwerk-rule-editor');"
                    " out.path = location.pathname; out.editor = !!ed;"
                    " if (!ed) return JSON.stringify(out);"
                    " const btn = [...ed.shadowRoot.querySelectorAll('button')].find(b => /^(Satz|Sentence)$/.test(b.textContent.trim()));"
                    " if (btn) { btn.click(); await new Promise(r => setTimeout(r, 800));"
                    "  const s = ed.shadowRoot.querySelector('.sentence');"
                    "  out.sentence = s ? s.textContent.replace(/\\s+/g, ' ').slice(0, 300) : 'none';"
                    "  out.pieces = s ? s.querySelectorAll('button').length : 0; }"
                    " return JSON.stringify(out) })()"
                )
                print("stage 4:", st4)
                await cdp.shot("panel_sentence", full=False)
                st4j = json.loads(st4)
                if not (
                    st4j.get("weekItems") and st4j.get("pieces") and st4j.get("editor")
                ):
                    raise SystemExit(
                        f"stage 4: week empty or sentence without pieces: {st4}"
                    )
                for k in ('"chooser":4', "So würde", '"hscroll":false'):
                    if k not in str(st4):
                        raise SystemExit(f"stage 4 check failed: {k}")
                await cdp.js(
                    "(async () => { const p = window.__find(document, 'laeutwerk-panel');"
                    " for (const id of ['chk_hist', 'hc_test', 'rt_service'])"
                    "  try { await p.hass.callWS({type: 'laeutwerk/rules/delete', rule_id: id}); } catch (e) {}"
                    " return true })()"
                )
        finally:
            proc.terminate()


if __name__ == "__main__":
    asyncio.run(main())
