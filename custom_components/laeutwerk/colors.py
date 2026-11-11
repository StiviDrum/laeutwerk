"""Colour values for light signals: German and English names, hex, r,g,b."""

from __future__ import annotations

import re

from homeassistant.util import color as color_util

# German names (as used in keyword tables: "blau", "grün", ...) -> CSS names.
_GERMAN = {
    "rot": "red",
    "grün": "green",
    "gruen": "green",
    "blau": "blue",
    "gelb": "yellow",
    "orange": "orange",
    "lila": "purple",
    "violett": "violet",
    "pink": "deeppink",
    "rosa": "pink",
    "türkis": "turquoise",
    "tuerkis": "turquoise",
    "weiß": "white",
    "weiss": "white",
    "braun": "saddlebrown",
    # A lamp cannot shine grey or black: use a neutral white.
    "grau": "white",
    "schwarz": "white",
    "grey": "white",
    "gray": "white",
    "black": "white",
}
_HEX = re.compile(r"^#?([0-9a-f]{6})$")
_RGB = re.compile(r"^(\d{1,3})\s*[,; ]\s*(\d{1,3})\s*[,; ]\s*(\d{1,3})$")


# For drawing (colour dots in the card) grey stays grey.
_DRAWN = {
    "grau": "grey",
    "schwarz": "black",
    "grey": "grey",
    "gray": "grey",
    "black": "black",
    "braun": "brown",
}


def color_hex(value: str | None) -> str | None:
    """Return #rrggbb for drawing a colour text, None if not understood."""
    rgb = parse_color(value, for_light=False)
    return "#{:02x}{:02x}{:02x}".format(*rgb) if rgb else None


def parse_color(
    value: str | None, *, for_light: bool = True
) -> tuple[int, int, int] | None:
    """Return r, g, b for a colour text, None if it is not understood."""
    text = (value or "").strip().lower()
    if not text:
        return None
    if match := _HEX.match(text):
        number = int(match[1], 16)
        return (number >> 16) & 255, (number >> 8) & 255, number & 255
    if match := _RGB.match(text):
        red, green, blue = (int(part) for part in match.groups())
        return (red, green, blue) if max(red, green, blue) <= 255 else None
    name = _GERMAN.get(text, text)
    if not for_light:
        name = _DRAWN.get(text, name)
    name = name.replace(" ", "")
    try:
        rgb = color_util.color_name_to_rgb(name)
    except ValueError:
        return None
    return rgb[0], rgb[1], rgb[2]
