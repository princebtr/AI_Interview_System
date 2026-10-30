"""Institution theme colours: validation and the palette the app uses.

An institution picks a primary and a secondary colour (hex). The client's CSS
names every colour through variables (client/src/index.css):

- `primary` / `secondary`: exactly the chosen colours, as solid fills (primary
  buttons, the active nav item; secondary badges and supporting highlights).
  They are never blended into a gradient or shifted to another hue.
- `on-primary` / `on-secondary`: white or near-black, whichever reads on that fill.
- `accent-50..900` / `accent2-50..900`: tints and shades of each, for soft
  backgrounds, rings and text. Step 600 is the colour itself when it is dark
  enough to read as text on white, otherwise the nearest shade that is.

This builds those values, so all three portals (admin, educator, student) and
the school's sign-in page share it.
"""
import re

from django.core.validators import RegexValidator

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
hex_color = RegexValidator(HEX, "Enter a colour as #RRGGBB, e.g. #2563EB")

# How far each step mixes the colour with white (lighter) or black (darker);
# the chosen colour is the 600 step, like Tailwind's palettes.
LIGHTER = {50: 0.94, 100: 0.88, 200: 0.75, 300: 0.58, 400: 0.36, 500: 0.16}
DARKER = {700: 0.16, 800: 0.32, 900: 0.46}
TEXT_CONTRAST = 4.5  # WCAG AA for normal text
INK = "#0f172a"  # the app's darkest text (slate-900), used on light fills


def _rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def _hex(rgb):
    return "#" + "".join(f"{round(max(0, min(255, c))):02x}" for c in rgb)


def _mix(rgb, other, amount):
    return tuple(c + (o - c) * amount for c, o in zip(rgb, other))


def luminance(value):
    def channel(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in _rgb(value))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    light, dark = sorted((luminance(a), luminance(b)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def contrast_with_white(value):
    return contrast(value, "#ffffff")


def on_color(value):
    """Text colour for a solid `value` fill: white when it meets AA, else whichever reads better."""
    if contrast_with_white(value) >= TEXT_CONTRAST:
        return "#ffffff"
    return "#ffffff" if contrast_with_white(value) > contrast(value, INK) else INK


def readable(value, target=TEXT_CONTRAST):
    """The colour, darkened just enough for white text on it (and as text on white)."""
    rgb = _rgb(value)
    for step in range(0, 101):
        candidate = _hex(_mix(rgb, (0, 0, 0), step / 100))
        if contrast_with_white(candidate) >= target:
            return candidate
    return "#000000"


def scale(value):
    """{50: hex, ..., 900: hex}. Steps 600 and darker are readable as text on white."""
    rgb = _rgb(value)
    base = readable(value)
    steps = {step: _hex(_mix(rgb, (255, 255, 255), amount)) for step, amount in LIGHTER.items()}
    steps[600] = base
    steps.update({step: _hex(_mix(_rgb(base), (0, 0, 0), amount)) for step, amount in DARKER.items()})
    return steps


def palette(primary, secondary):
    """CSS variables for an institution's colours, or None for the default theme.
    A missing secondary colour follows the primary."""
    if not primary:
        return None
    primary = primary.lower()
    secondary = (secondary or primary).lower()
    variables = {}
    for name, value in (("primary", primary), ("secondary", secondary)):
        variables[f"--color-{name}"] = value
        variables[f"--color-on-{name}"] = on_color(value)
    for name, value in (("accent", primary), ("accent2", secondary)):
        for step, color in scale(value).items():
            variables[f"--color-{name}-{step}"] = color
    return variables


def theme_dict(institution):
    primary = institution.primary_color or None
    secondary = institution.secondary_color or None
    return {"primary": primary, "secondary": secondary, "palette": palette(primary, secondary)}
