#!/usr/bin/env python3
"""Cómo ejecutar un programa Linux x86_64 en esta consola ARM64 (igual que herramientas/x86.sh).

  x86.py            imprime la ruta del traductor (FEXInterpreter, FEXLoader o box64), «directo» (binfmt) o nada (código 1)
Desde Python: traductor() → ruta | "directo" | None;  orden(prog, args) → la lista de argumentos para ejecutarlo.
"""
import os
import shutil
import sys
from pathlib import Path


def traductor():
    if os.environ.get("KONKR_X86"):
        return os.environ["KONKR_X86"]
    for c in ("FEXInterpreter", "FEXLoader", "box64"):
        p = shutil.which(c)
        if p:
            return p
    for f in sorted(Path("/proc/sys/fs/binfmt_misc").glob("*")):
        if f.name in ("register", "status"):
            continue
        try:
            t = f.read_text()
        except OSError:
            continue
        if t.startswith("enabled") and ("3e00" in t.lower() or any(k in f.name.lower() for k in ("box64", "fex", "x86"))):
            i = next((l.split(" ", 1)[1].strip() for l in t.splitlines() if l.startswith("interpreter ")), "")
            return i if i and os.access(i, os.X_OK) else "directo"
    for p in ("/usr/local/bin/box64", "/usr/lib/box64/box64", "/opt/box64/box64", str(Path.home() / ".local/bin/box64")):
        if os.access(p, os.X_OK):
            return p
    return None


def nombre():
    t = traductor()
    if not t:
        return "ninguno"
    return "binfmt" if t == "directo" else Path(t).name


def es_script(prog):
    try:
        with open(prog, "rb") as f:
            return f.read(2) == b"#!"
    except OSError:
        return False


def orden(prog, args=()):
    """Un script (AppRun, start.sh) se ejecuta tal cual: lo que lance en x86 lo traduce el kernel (binfmt) o FEX.
    Un ELF x86_64: con el traductor delante, o tal cual si el kernel lo traduce solo."""
    t = traductor()
    if es_script(prog) or t in (None, "directo"):
        return [str(prog), *args]
    return [t, str(prog), *args]


if __name__ == "__main__":
    t = traductor()
    if not t:
        sys.exit(1)
    print(t)
