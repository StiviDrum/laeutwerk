"""The integration serves the card bundle and registers it with the frontend."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL, DATA_PANELS
from homeassistant.core import HomeAssistant
import pytest

from custom_components import laeutwerk
from custom_components.laeutwerk.const import CARD_URL_BASE, DOMAIN

from .ha_testing import MockConfigEntry


@pytest.fixture
def card_bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    bundle = tmp_path / "laeutwerk-card.js"
    bundle.write_text("console.log('laeutwerk');")
    monkeypatch.setattr(laeutwerk, "CARD_PATH", bundle)
    return bundle


async def _setup(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_card_registered_and_served(
    hass: HomeAssistant, hass_client, card_bundle: Path
) -> None:
    await _setup(hass)
    urls = [
        u for u in hass.data[DATA_EXTRA_MODULE_URL].urls if u.startswith(CARD_URL_BASE)
    ]
    assert len(urls) == 1
    assert urls[0].startswith(f"{CARD_URL_BASE}/laeutwerk-card.js?v=")

    client = await hass_client()
    resp = await client.get(urls[0])
    assert resp.status == 200
    assert "laeutwerk" in await resp.text()

    (card_bundle.parent / "chunk-editor-abc123.js").write_text("export default 1;")
    resp = await client.get(f"{CARD_URL_BASE}/chunk-editor-abc123.js")
    assert resp.status == 200


async def test_missing_bundle_only_warns(
    hass: HomeAssistant,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(laeutwerk, "CARD_PATH", tmp_path / "missing.js")
    await _setup(hass)
    assert "Card bundle" in caplog.text
    assert not any(
        u.startswith(CARD_URL_BASE) for u in hass.data[DATA_EXTRA_MODULE_URL].urls
    )


async def test_panel_registered_removed_and_reloaded(
    hass: HomeAssistant, card_bundle: Path
) -> None:
    (card_bundle.parent / "laeutwerk-panel.js").write_text("console.log('panel');")
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    panel = hass.data[DATA_PANELS]["laeutwerk"]
    assert panel.require_admin is True
    assert panel.sidebar_title == "Läutwerk"
    assert panel.sidebar_icon == "mdi:bell-ring-outline"
    custom = panel.config["_panel_custom"]
    assert custom["name"] == "laeutwerk-panel"
    assert custom["module_url"].startswith(f"{CARD_URL_BASE}/laeutwerk-panel.js?v=")

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert "laeutwerk" in hass.data[DATA_PANELS]

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert "laeutwerk" not in hass.data[DATA_PANELS]


async def test_missing_panel_bundle_skips_panel(
    hass: HomeAssistant, card_bundle: Path
) -> None:
    await _setup(hass)
    assert "laeutwerk" not in hass.data.get(DATA_PANELS, {})
