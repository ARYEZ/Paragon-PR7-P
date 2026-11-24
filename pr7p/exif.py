"""A photo's camera details (EXIF), read with Pillow, as IrfanView's Information dialog lists them (no Qt)."""

from __future__ import annotations

from fractions import Fraction

EXIF_IFD, GPS_IFD = 0x8769, 0x8825
TAGS = {"make": 0x010F, "model": 0x0110, "orientation": 0x0112, "software": 0x0131, "datetime": 0x0132,
        "exposure": 0x829A, "fnumber": 0x829D, "iso": 0x8827, "taken": 0x9003, "flash": 0x9209,
        "focal": 0x920A, "focal35": 0xA405, "lens": 0xA434, "lensmake": 0xA433}


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def exposure_text(seconds) -> str:
    s = _num(seconds)
    if not s:
        return ""
    if s >= 1:
        return f"{s:g} s"
    return f"1/{round(1 / s)} s"


def _gps(gps: dict) -> str:
    def deg(v, ref):
        try:
            d, m, s = (float(x) for x in v)
        except (TypeError, ValueError):
            return None
        return d + m / 60 + s / 3600, ref
    lat = deg(gps.get(2), gps.get(1, "N"))
    lon = deg(gps.get(4), gps.get(3, "E"))
    if not lat or not lon:
        return ""
    return f"{lat[0]:.4f} {lat[1]}, {lon[0]:.4f} {lon[1]}"


def read(path: str) -> dict[str, str]:
    """{label: text} in the dialog's order; empty when the picture has no camera details."""
    try:
        from PIL import Image
        with Image.open(path) as pil:
            ex = pil.getexif()
            sub = ex.get_ifd(EXIF_IFD) if ex else {}
            gps = ex.get_ifd(GPS_IFD) if ex else {}
    except Exception:  # noqa: BLE001 - not a picture Pillow knows, or no EXIF
        return {}
    if not ex and not sub:
        return {}

    def get(name):
        tag = TAGS[name]
        return sub.get(tag, ex.get(tag))

    out: dict[str, str] = {}
    make, model = str(get("make") or "").strip(), str(get("model") or "").strip()
    camera = model if model.lower().startswith(make.lower().split(" ")[0] if make else "\0") else f"{make} {model}"
    if camera.strip():
        out["Camera"] = camera.strip()
    if get("lens"):
        out["Lens"] = str(get("lens")).strip()
    taken = get("taken") or get("datetime")
    if taken:
        out["Taken"] = _date(str(taken))
    parts = [exposure_text(get("exposure"))]
    f = _num(get("fnumber"))
    if f:
        parts.append(f"f/{f:g}")
    iso = get("iso")
    if iso:
        parts.append(f"ISO {iso[0] if isinstance(iso, tuple) else iso}")
    if any(parts):
        out["Exposure"] = "   ".join(p for p in parts if p)
    focal = _num(get("focal"))
    if focal:
        f35 = get("focal35")
        out["Focal length"] = f"{focal:g} mm" + (f" ({f35} mm in 35 mm film)" if f35 else "")
    flash = get("flash")
    if flash is not None:
        out["Flash"] = "On" if int(flash) & 1 else "Off"
    if get("software"):
        out["Software"] = str(get("software")).strip()
    if gps:
        where = _gps(gps)
        if where:
            out["GPS"] = where
    return out


def _date(s: str) -> str:
    """EXIF's "2026:10:03 18:41:07" as "3 October 2026, 18:41:07"."""
    import datetime
    try:
        d = datetime.datetime.strptime(s.strip("\x00 ")[:19], "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return s
    return f"{d.day} {d:%B %Y, %H:%M:%S}"


def fraction(v) -> Fraction:
    return Fraction(v).limit_denominator(100000)
