"""Preview: made-up bundle for the plural headline."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .common import setup_integration
from .ha_testing import WebSocketGenerator
from .test_headline_badges import rule_data


async def _preview(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, rule: dict
) -> Any:
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "laeutwerk/preview", "rule": rule})
    msg = await ws.receive_json()
    assert msg["success"], msg
    return msg["result"]


async def test_plural_sample(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator
) -> None:
    await setup_integration(hass)
    result = await _preview(
        hass,
        hass_ws_client,
        rule_data(headline="{wann}: {tonne}", headline_plural="{wann}: {tonnen}"),
    )
    sample = result["plural_sample"]
    assert sample["id"] == "sample_bundle"
    assert sample["titles"] == ["Papier", "Bio"]
    assert sample["variables"]["tonnen"] == "Papiertonne und Biotonne"
    assert sample["headline"] == "Morgen: Papiertonne und Biotonne"
    assert len(sample["badges"]) == 2


async def test_plural_sample_none(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator
) -> None:
    await setup_integration(hass)

    def rows(*items: dict[str, str]) -> dict[str, Any]:
        return {"keywords": {"columns": ["tonne"], "rows": list(items)}}

    one = {**rule_data(), "filter": rows({"match": "Papier", "tonne": "P"})}
    regex = {
        **rule_data(),
        "filter": rows(
            {"match": "Pap.*", "mode": "regex", "tonne": "P"},
            {"match": "Bi.*", "mode": "regex", "tonne": "B"},
        ),
    }
    no_bundle = rule_data(bundle=False)
    for rule in (one, regex, no_bundle):
        assert (await _preview(hass, hass_ws_client, rule))["plural_sample"] is None
