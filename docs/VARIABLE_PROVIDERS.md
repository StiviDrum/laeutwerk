# Variable providers

Other integrations can supply `{variables}` for all Läutwerk texts (push title/message, announcement text, custom-action variables, confirmation push). Läutwerk never imports a provider and works without any.

## Contract

- Register: `hass.data.setdefault("laeutwerk_variable_providers", {})[key] = provider` (`key` = your domain).
- Fire the bus event `laeutwerk_variable_providers_changed` after registering, unregistering or changing the variable list. Läutwerk reads the registry live, so order of setup does not matter.
- Provider object (duck-typed):
  - `title: str`
  - `variables() -> list[dict]` with `{"name": str, "description": str, "example": str}`
  - `async async_values(names: set[str], context: dict) -> dict[str, str]`
- `context`: `rule_id`, `rule_name`, `signal_id` (or `None` when several signals share the pass), `signal_type` (or `None`), `pass_kind` (`first` | `repeat` | `stage` | `test` | `preview` | `confirm`), `language`, `variables` (copy of the built-in variables).

## Behaviour

- Only names used in a text and not built in are requested, only from providers offering them.
- Values are drawn once per pass for all signals sent in it (push and announcement get the same value); each repeat/stage pass and each test draws anew.
- Each call has a 2 s timeout. Errors and timeouts are logged (rate limited) and ignored; the placeholder stays as `{name}`.
- Not applied to the headline/sensor attributes. Action signals receive provider values as script variables (`{{ name }}`).
- Catalog: websocket `laeutwerk/variables/providers` -> `{providers: [{key, title, variables}]}`; also in the diagnostics (names only).

## Example

```python
class WordProvider:
    title = "Random words"

    def variables(self) -> list[dict[str, str]]:
        return [{"name": "wort", "description": "A random word", "example": "Mond"}]

    async def async_values(self, names: set[str], context: dict) -> dict[str, str]:
        return {"wort": random.choice(WORDS)} if "wort" in names else {}


def register(hass):
    hass.data.setdefault("laeutwerk_variable_providers", {})["words"] = WordProvider()
    hass.bus.async_fire("laeutwerk_variable_providers_changed")
```
