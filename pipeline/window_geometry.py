"""
Window geometry persistence and validation for Smart Studio desktop app.

Validates stored width, height, x, y coordinates against the available display screens,
clamping or falling back to safe defaults so an offscreen, disconnected-monitor, or
below-minimum window geometry never leaves the app unreachable or broken.
"""

DEFAULT_WIDTH = 1000
DEFAULT_HEIGHT = 900
MIN_WIDTH = 900
MIN_HEIGHT = 750


def validate_window_geometry(geom: dict, screens=None,
                             min_size=(MIN_WIDTH, MIN_HEIGHT),
                             default_size=(DEFAULT_WIDTH, DEFAULT_HEIGHT)) -> dict:
    """
    Validate stored window geometry dictionary.

    Returns a dict with validated 'width', 'height', 'x', 'y', 'maximized'.
    Falls back to safe defaults if geometry is invalid, below min_size, or offscreen.
    """
    if not isinstance(geom, dict):
        return {
            "width": default_size[0],
            "height": default_size[1],
            "x": None,
            "y": None,
            "maximized": False,
        }

    try:
        w = int(geom.get("width", default_size[0]))
        h = int(geom.get("height", default_size[1]))
    except (TypeError, ValueError):
        w, h = default_size

    # Enforce minimum size: fall back to default if below minimum
    if w < min_size[0] or h < min_size[1]:
        w, h = default_size

    maximized = bool(geom.get("maximized", False))

    raw_x = geom.get("x")
    raw_y = geom.get("y")
    if raw_x is None or raw_y is None:
        return {"width": w, "height": h, "x": None, "y": None, "maximized": maximized}

    try:
        x = int(raw_x)
        y = int(raw_y)
    except (TypeError, ValueError):
        return {"width": w, "height": h, "x": None, "y": None, "maximized": maximized}

    # Validate against screens if provided
    if screens:
        fits_any = False
        for s in screens:
            sx = getattr(s, "x", s.get("x", 0) if isinstance(s, dict) else 0)
            sy = getattr(s, "y", s.get("y", 0) if isinstance(s, dict) else 0)
            sw = getattr(s, "width", s.get("width", 0) if isinstance(s, dict) else 0)
            sh = getattr(s, "height", s.get("height", 0) if isinstance(s, dict) else 0)

            overlap_x = max(0, min(x + w, sx + sw) - max(x, sx))
            overlap_y = max(0, min(y + h, sy + sh) - max(y, sy))
            title_visible = (sy <= y <= sy + sh - 40)
            if overlap_x >= 100 and overlap_y >= 100 and title_visible:
                fits_any = True
                break

        if not fits_any:
            return {"width": default_size[0], "height": default_size[1], "x": None, "y": None, "maximized": False}

    return {"width": w, "height": h, "x": x, "y": y, "maximized": maximized}