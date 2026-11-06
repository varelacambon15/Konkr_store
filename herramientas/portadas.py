#!/usr/bin/env python3
"""Arte de las recomps (portada, banner, logo) y sus datos, como los muestra RecompLauncher.

Fuentes, por orden: el arte que elegiste en RecompLauncher (cover_file/hero_file/logo_file de library.json); las direcciones de su
catálogo (cache/pc-catalog.json: cover, hero, logo, relativas a https://recomplauncher.com). Una imagen se busca en la caché de
RecompLauncher (cache/img/<sha256(dirección)[:32]>), luego en la nuestra (~/recomp/cache/arte) y si no, se descarga una vez ahí.
Para la ventana: foto() la escala con Pillow (o, sin Pillow, PNG/GIF con Tk y JPEG/WebP con ffmpeg si lo hay).

  portadas.py datos ID        los datos y el arte de una recomp (sin descargar nada)
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

HOME = Path.home()
RL = Path(os.environ.get("XDG_DATA_HOME", HOME / ".local/share")) / "com.recomplauncher.app"
CACHE = HOME / "recomp/cache/arte"
WEB = os.environ.get("RL_API", "https://recomplauncher.com").rstrip("/")
_catalogo = None


def catalogo():
    global _catalogo
    if _catalogo is None:
        try:
            apps = json.loads((RL / "cache/pc-catalog.json").read_text(encoding="utf-8")).get("apps") or []
            _catalogo = {a.get("id"): a for a in apps if isinstance(a, dict)}
        except (OSError, ValueError):
            _catalogo = {}
    return _catalogo


def instalada(gid):
    try:
        lib = json.loads((RL / "library.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    for clave, g in (lib.get("installed") or {}).items():
        if isinstance(g, dict) and (g.get("id") or clave) == gid:
            return g
    return {}


def web(u):
    if not u:
        return ""
    if u.startswith(("http://", "https://", "file://", "data:")):
        return u
    return WEB + ("" if u.startswith("/") else "/") + u


def datos(gid):
    """Nombre, juego, género, autor, descripción y arte (rutas locales o direcciones) de una recomp."""
    c, g = catalogo().get(gid, {}), instalada(gid)
    def arte(tipo):
        f = g.get(f"{tipo}_file")
        if f and Path(f).is_file():
            return f
        return web(c.get(tipo) or "")
    return {"nombre": g.get("name") or c.get("name") or c.get("title") or gid, "juego": c.get("game") or g.get("game") or "",
            "genero": c.get("genre") or "", "autor": c.get("author") or c.get("dev") or "",
            "texto": c.get("blurb") or c.get("description") or "", "origen": c.get("origin") or "",
            "cover": arte("cover"), "hero": arte("hero"), "logo": arte("logo")}


def _sha(u):
    return hashlib.sha256(u.encode()).hexdigest()[:32]


def local(fuente):
    """La imagen en disco si ya está (sin descargar): ruta o None."""
    if not fuente:
        return None
    if not fuente.startswith(("http://", "https://", "file://")):
        return Path(fuente) if Path(fuente).is_file() else None
    for p in (RL / "cache/img" / _sha(fuente), CACHE / _sha(fuente)):
        if p.is_file() and p.stat().st_size > 0:
            return p
    return None


def descargar(fuente, timeout=15):
    """Descarga una vez a ~/recomp/cache/arte; devuelve la ruta o None (sin red, 404...)."""
    p = local(fuente)
    if p or not fuente or not fuente.startswith(("http://", "https://", "file://")):
        return p
    CACHE.mkdir(parents=True, exist_ok=True)
    dest = CACHE / _sha(fuente); tmp = dest.with_suffix(".parcial")
    try:
        req = urllib.request.Request(fuente, headers={"User-Agent": "Konkr_store"})
        with urllib.request.urlopen(req, timeout=timeout) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f, 1 << 16)
        if tmp.stat().st_size == 0:
            raise OSError("vacía")
        tmp.replace(dest)
        return dest
    except (OSError, ValueError):
        tmp.unlink(missing_ok=True)
        return None


def hay_pillow():
    try:
        import PIL.Image  # noqa: F401
        return True
    except ImportError:
        return False


def foto(tk, ruta, w, h, modo="cubrir"):
    """Un PhotoImage de w x h (cubrir: recorta para llenar; caber: cabe entero, con transparencia alrededor). None si no se puede."""
    if not ruta:
        return None
    try:
        from PIL import Image, ImageTk
        im = Image.open(ruta)
        im.load()
        im = im.convert("RGBA")
        if modo == "cubrir":
            esc = max(w / im.width, h / im.height)
            im = im.resize((max(1, round(im.width * esc)), max(1, round(im.height * esc))), Image.LANCZOS)
            x, y = (im.width - w) // 2, (im.height - h) // 2
            im = im.crop((x, y, x + w, y + h))
        else:
            im.thumbnail((w, h), Image.LANCZOS)
        return ImageTk.PhotoImage(im)
    except ImportError:
        pass
    except (OSError, ValueError):
        return None
    # Sin Pillow: PNG / GIF con Tk; JPEG / WebP pasando por ffmpeg a PNG (en caché)
    try:
        with open(ruta, "rb") as f:
            cab = f.read(8)
    except OSError:
        return None
    png = Path(ruta)
    if not (cab.startswith(b"\x89PNG") or cab.startswith(b"GIF")):
        ff = shutil.which("ffmpeg")
        if not ff:
            return None
        png = CACHE / f"{Path(ruta).name}_{w}x{h}_{modo}.png"
        if not png.is_file():
            CACHE.mkdir(parents=True, exist_ok=True)
            vf = (f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}" if modo == "cubrir"
                  else f"scale={w}:{h}:force_original_aspect_ratio=decrease")
            r = subprocess.run([ff, "-v", "error", "-y", "-i", str(ruta), "-vf", vf, "-frames:v", "1", str(png)], capture_output=True)
            if r.returncode or not png.is_file():
                return None
        try:
            return tk.PhotoImage(file=str(png))
        except Exception:
            return None
    try:
        im = tk.PhotoImage(file=str(png))
        f = max(1, min(im.width() // max(1, w), im.height() // max(1, h)))
        return im.subsample(f, f) if f > 1 else im
    except Exception:
        return None


if __name__ == "__main__":
    if sys.argv[1:2] == ["datos"] and len(sys.argv) == 3:
        d = datos(sys.argv[2])
        for k, v in d.items():
            print(f"{k:7} {v}" + (f"   (en disco: {local(v)})" if k in ("cover", "hero", "logo") and v else ""))
    else:
        print(__doc__)
