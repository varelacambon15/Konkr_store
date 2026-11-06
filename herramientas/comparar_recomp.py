#!/usr/bin/env python3
"""Prepara una recomp en sus dos versiones (ARM64 nativa y x86_64 con FEX) para compararlas.

  comparar_recomp.py lista
  comparar_recomp.py preparar ID [--release-json ARCHIVO]   descarga, extrae, verifica y crea los accesos
  comparar_recomp.py resumen ID                              tabla con las medidas de cada partida

Todo queda en ~/recomp/comparar/<ID>/ y los accesos en ~/recomp/accesos/. No toca Steam ni el sistema.
Los accesos se añaden a Steam desde la tienda (o con herramientas/anadir_a_steam.sh).
"""
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path

HOME = Path.home()
DIR = Path(__file__).resolve().parent.parent
RECETAS = DIR / "datos/comparar.json"
COMPARAR = HOME / "recomp/comparar"
ACCESOS = HOME / "recomp/accesos"
MEDIR = DIR / "herramientas/medir_y_lanzar.sh"
sys.path.insert(0, str(DIR / "herramientas"))
from revisar_binarios import arch_de  # noqa: E402

ARCH_ESPERADA = {"arm64": "aarch64", "x64": "x86_64"}


def recetas():
    return {r["id"]: r for r in json.loads(RECETAS.read_text(encoding="utf-8"))["recomps"]}


def palabras(nombre):
    n = nombre.lower().replace("x86_64", "x64").replace("x86-64", "x64").replace("aarch64", "arm64")
    return set(re.split(r"[^a-z0-9]+", n))


def elegir(assets, patron):
    ok = []
    for a in assets:
        n = a["name"].lower()
        if not (n.endswith(".zip") or ".tar." in n or n.endswith(".tgz")):
            continue
        w = palabras(a["name"])
        if all(p in w for p in patron["incluye"]) and not any(p in w or p in n for p in patron["excluye"]):
            ok.append(a)
    return ok[0] if ok else None


def release(repo, archivo=None):
    archivo = archivo or os.environ.get("KONKR_RELEASE_JSON")    # solo para pruebas sin red
    if archivo:
        return json.loads(Path(archivo).read_text(encoding="utf-8"))
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/releases/latest",
                                 headers={"Accept": "application/vnd.github+json", "User-Agent": "Konkr_store"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def descargar(asset, destino):
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists():
        print(f"  ya descargado: {destino.name}")
    else:
        url = asset["browser_download_url"]
        print(f"  descargando {asset['name']} ({asset.get('size', 0) / 1e6:.0f} MB)…", flush=True)
        if url.startswith("file://"):                       # solo para pruebas
            shutil.copy(url[7:], destino)
        else:
            tmp = destino.with_suffix(destino.suffix + ".parcial")
            req = urllib.request.Request(url, headers={"User-Agent": "Konkr_store"})
            with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
                shutil.copyfileobj(r, f, 1 << 20)
            tmp.rename(destino)
    dig = (asset.get("digest") or "").replace("sha256:", "")
    if dig:
        h = hashlib.sha256()
        with open(destino, "rb") as f:
            for b in iter(lambda: f.read(1 << 20), b""):
                h.update(b)
        if h.hexdigest() != dig:
            raise SystemExit(f"¡SHA-256 de {destino.name} NO coincide! Borra el archivo y repite.")
        print("  SHA-256 correcto")
    else:
        print("  (GitHub no publica SHA-256 para este archivo)")


def _dentro(base, ruta):
    base, ruta = os.path.realpath(base), os.path.realpath(ruta)
    return ruta == base or ruta.startswith(base + os.sep)


def extraer(archivo, destino, anidado=True):
    destino.mkdir(parents=True, exist_ok=True)
    n = archivo.name.lower()
    if n.endswith(".zip"):
        with zipfile.ZipFile(archivo) as z:
            for info in z.infolist():
                final = destino / info.filename
                if not _dentro(destino, final):
                    raise SystemExit(f"Ruta peligrosa dentro del zip: {info.filename}")
                z.extract(info, destino)
                modo = (info.external_attr >> 16) & 0o777
                if modo and not info.is_dir():
                    os.chmod(final, modo)
    else:
        with tarfile.open(archivo) as t:
            for m in t.getmembers():
                if not _dentro(destino, destino / m.name) or m.issym() and not _dentro(destino, destino / Path(m.name).parent / m.linkname):
                    raise SystemExit(f"Ruta peligrosa dentro del tar: {m.name}")
            try:
                t.extractall(destino, filter="data")
            except TypeError:                                 # Python < 3.12
                t.extractall(destino)
    # Un tar.gz dentro del zip (así empaqueta su CI algunas releases): se extrae también, un solo nivel.
    if anidado:
        for interior in list(destino.glob("*.tar.gz")) + list(destino.glob("*.tgz")):
            extraer(interior, destino, anidado=False)
            interior.unlink()


def buscar_programa(raiz, nombre):
    for p in sorted(raiz.rglob(nombre), key=lambda x: len(x.parts)):
        if p.is_file() and len(p.relative_to(raiz).parts) <= 4:
            return p
    return None


def escribir_desktop(fichero, nombre, exec_):
    ACCESOS.mkdir(parents=True, exist_ok=True)
    ruta = ACCESOS / f"{fichero}.desktop"
    ruta.write_text("[Desktop Entry]\nType=Application\n"
                    f"Name={nombre}\nExec={exec_}\nPath={HOME}\nIcon=applications-games\n"
                    "Categories=Game;\nTerminal=false\n", encoding="utf-8")
    return ruta


def preparar(rid, release_json=None):
    r = recetas().get(rid)
    if not r:
        raise SystemExit(f"No conozco «{rid}». Opciones: {', '.join(recetas())}")
    base = COMPARAR / rid
    print(f"== {r['nombre']}  ({r['repo']})")
    print(f"Archivo del juego que pide: {r['juego']}")
    rel = release(r["repo"], release_json)
    tag = re.sub(r"[^A-Za-z0-9._-]", "_", rel.get("tag_name", "sin-tag"))
    print(f"Release: {tag}")
    accesos = []
    for modo in ("arm64", "x64"):
        print(f"\n-- {modo}")
        a = elegir(rel.get("assets", []), r[modo])
        if not a:
            nombres = ", ".join(x["name"] for x in rel.get("assets", []))
            raise SystemExit(f"No encuentro la build {modo} en la release. Archivos: {nombres}")
        archivo = base / "descargas" / a["name"]
        descargar(a, archivo)
        carpeta = base / f"{modo}-{tag}"
        ya_extraida = carpeta.exists() and buscar_programa(carpeta, r["programa"])
        if not ya_extraida:
            if carpeta.exists():
                carpeta.rename(base / f"{modo}-{tag}.incompleto.{int(time.time())}")
            tmp = base / f".{modo}-{tag}.extrayendo"
            if tmp.exists():
                tmp.rename(base / f".{modo}-{tag}.fallido.{int(time.time())}")
            print("  extrayendo…", flush=True)
            extraer(archivo, tmp)
            tmp.rename(carpeta)              # solo si la extracción terminó bien
        prog = buscar_programa(carpeta, r["programa"])
        if not prog:
            raise SystemExit(f"No encuentro el programa {r['programa']} dentro de {carpeta}")
        arch = arch_de(prog)
        if arch != ARCH_ESPERADA[modo]:
            raise SystemExit(f"{prog} es {arch}, no {ARCH_ESPERADA[modo]}: no sigo")
        prog.chmod(prog.stat().st_mode | stat.S_IXUSR)
        enlace = base / modo
        if enlace.is_symlink():
            enlace.unlink()
        enlace.symlink_to(carpeta.name)
        print(f"  programa: {prog.relative_to(base)}  →  {arch} ✔")
        etiqueta = f"{r['nombre']} ({'ARM64 nativo' if modo == 'arm64' else 'x86_64 + FEX'})"
        rel_prog = prog.relative_to(carpeta)
        exec_ = f'"{MEDIR}" {modo} "{(base / modo / rel_prog).parent}" "{rel_prog.name}" "{etiqueta}"'
        accesos.append(escribir_desktop(f"comparar-{rid}-{modo}", etiqueta, exec_))
    print("\nAccesos creados (añádelos a Steam desde la tienda):")
    for a in accesos:
        print(f"  {a}")
    print(f"\nPara jugar necesitas: {r['juego']}")
    print("Las dos versiones comparten partidas (~/.config/Zelda64Recompiled/saves en el caso de Zelda 64).")
    return accesos


def resumen(rid):
    f = COMPARAR / rid / "medidas/resumen.csv"
    if not f.exists():
        print("Aún no hay medidas: juega un rato con cada versión (desde sus accesos) y vuelve aquí.")
        return
    filas = [l.split(";") for l in f.read_text(encoding="utf-8").splitlines() if l.count(";") >= 8]
    print(f"{'Fecha':19}  {'Versión':13}  {'Duración':>8}  {'W media':>7}  {'°C máx':>6}  {'CPU %':>5}  {'Bat. %':>6}")
    tot = {}
    for fecha, _etq, modo, dura, w, t, cpu, bat, *_ in filas:
        nombre = "ARM64 nativo" if modo == "arm64" else "x86_64 + FEX"
        print(f"{fecha:19}  {nombre:13}  {int(dura) // 60:>5}:{int(dura) % 60:02d}  {w:>7}  {t:>6}  {cpu:>5}  {bat:>6}")
        if w not in ("", "-"):
            tot.setdefault(nombre, []).append((float(w), int(dura)))
    if tot:
        print("\nConsumo medio ponderado por tiempo de juego:")
        for nombre, v in tot.items():
            seg = sum(d for _, d in v) or 1
            print(f"  {nombre:13}  {sum(w * d for w, d in v) / seg:.2f} W  ({seg // 60} min medidos)")
        print("Los FPS míralos con el indicador de rendimiento de Steam (botón ··· > batería).")


def main(argv):
    if argv[:1] == ["lista"]:
        for rid, r in recetas().items():
            print(f"{rid}\t{r['nombre']}\t{r['repo']}")
    elif argv[:1] == ["preparar"] and len(argv) >= 2:
        rj = argv[argv.index("--release-json") + 1] if "--release-json" in argv else None
        try:
            preparar(argv[1], rj)
        except OSError as e:
            print(f"Error de red o de disco: {e}")
            return 2
    elif argv[:1] == ["resumen"] and len(argv) == 2:
        resumen(argv[1])
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
