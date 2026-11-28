"""Variable providers of other integrations."""

from __future__ import annotations

from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant, ServiceCall
import pytest

from custom_components.laeutwerk.providers import PROVIDERS_KEY

from .common import PHONE, setup_integration
from .ha_testing import WebSocketGenerator, async_mock_service
from .test_start_confirm import bell_rule, pushes, ring, sent, start  # noqa: F401


class Words:
    title = "Randowerk"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.mode = "ok"

    def variables(self) -> list[dict[str, str]]:
        return [{"name": "wort", "description": "random word", "example": "Mond"}]

    async def async_values(self, names: set[str], context: dict) -> dict[str, str]:
        self.calls.append({"names": names, **context})
        if self.mode == "raise":
            raise RuntimeError("boom")
        if self.mode == "hang":
            raise TimeoutError  # the frozen clock cannot expire a real timeout
        return {"wort": f"Wort{len(self.calls)}"}


def register(hass: HomeAssistant, provider: Any) -> None:
    hass.data.setdefault(PROVIDERS_KEY, {})["randowerk"] = provider


SIGNALS = [
    {
        "id": "push",
        "type": "notify",
        "targets": [PHONE],
        "message": "{wort} {titel}",
    },
    {
        "id": "act",
        "type": "action",
        "actions": [{"action": "test.say", "data": {"text": "{{ wort }}"}}],
    },
]


async def test_one_draw_per_pass_shared_by_signals(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    pushes: list[ServiceCall],  # noqa: F811
) -> None:
    said = async_mock_service(hass, "test", "say")
    provider = Words()
    await start(hass, freezer, signals=SIGNALS)
    register(hass, provider)  # registered after setup
    await ring(hass)
    assert len(provider.calls) == 1
    assert provider.calls[0]["pass_kind"] == "first"
    assert provider.calls[0]["names"] == {"wort"}
    assert provider.calls[0]["rule_id"] == "klingel"
    assert sent(pushes) == ["Wort1 Klingel"]
    assert said[0].data["text"] == "Wort1"


async def test_test_signal_draws_anew(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    pushes: list[ServiceCall],  # noqa: F811
) -> None:
    provider = Words()
    register(hass, provider)
    _, manager = await start(hass, freezer, signals=SIGNALS[:1])
    for _ in range(2):
        await manager.async_test_signal("klingel", "push")
    assert [c["pass_kind"] for c in provider.calls] == ["test", "test"]
    assert sent(pushes) == ["Wort1 Klingel", "Wort2 Klingel"]


@pytest.mark.parametrize("mode", ["raise", "hang", "missing"])
async def test_broken_or_missing_provider_keeps_placeholder(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    pushes: list[ServiceCall],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    monkeypatch.setattr("custom_components.laeutwerk.providers.PROVIDER_TIMEOUT", 0.01)
    if mode != "missing":
        provider = Words()
        provider.mode = mode
        register(hass, provider)
    await start(hass, freezer, signals=SIGNALS[:1])
    await ring(hass)
    assert sent(pushes) == ["{wort} Klingel"]


async def test_catalog_websocket_and_unregister(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator
) -> None:
    await setup_integration(hass)
    ws = await hass_ws_client(hass)

    async def catalog() -> list[Any]:
        await ws.send_json(
            {"id": 1 + len(calls), "type": "laeutwerk/variables/providers"}
        )
        calls.append(1)
        return (await ws.receive_json())["result"]["providers"]

    calls: list[int] = []
    assert await catalog() == []
    register(hass, Words())
    hass.data[PROVIDERS_KEY]["bad"] = object()
    assert await catalog() == [
        {
            "key": "randowerk",
            "title": "Randowerk",
            "variables": [
                {"name": "wort", "description": "random word", "example": "Mond"}
            ],
        }
    ]
    del hass.data[PROVIDERS_KEY]["randowerk"]
    del hass.data[PROVIDERS_KEY]["bad"]
    assert await catalog() == []
