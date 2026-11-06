#!/usr/bin/env python3
"""Instala programas de Linux desde archivos locales, en tu carpeta de usuario (sin sudo, sin tocar el sistema).

  instalar_local.py tipo ARCHIVO                  qué es y cómo se instalaría (no cambia nada)
  instalar_local.py instalar ARCHIVO [--nombre N] [--programa RUTA_RELATIVA]
  instalar_local.py lista                         lo instalado así
  instalar_local.py candidatos                    archivos instalables en Descargas, Escritorio y memorias USB

Tipos:
  AppImage             se extrae (sin FUSE); ARM64 se ejecuta nativo, x86_64 con FEX
  .tar.* .tgz .zip     se extrae; se busca el programa principal (ELF o script) y su arquitectura
  .deb  .pkg.tar.*     se extrae su contenido (no se instala en el sistema); puede faltar alguna librería
  .flatpak .flatpakref flatpak install --user
  .sh                  instaladores (GOG...): no se instalan solos, se abren en Konsole
  .exe .msi .rpm       no: se explica qué hacer
Cada programa va a ~/Applications/Locales/<Nombre>/ con su lanzador jugar.sh y konkr-app.json; su acceso a
~/recomp/accesos/local-<Nombre>.desktop (la tienda lo añade a Steam).
"""
import json
import lzma
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import time
import zipfile
from pathlib import Path

HOME = Path.home()
DIR = Path(__file__).resolve().parent
LOCALES = HOME / "Applications/Locales"
ACCESOS = HOME / "recomp/accesos"
sys.path.insert(0, str(DIR))
from revisar_binarios import Elf, arch_de, offset_appimage  # noqa: E402

EXT_ARCHIVO = (".tar.gz", ".tgz", ".tar.xz", ".txz", ".tar.bz2", ".tbz2", ".tar.zst", ".tar", ".zip")
EXT_PAQUETE = (".deb", ".pkg.tar.zst", ".pkg.tar.xz")
TODAS = (".appimage",) + EXT_PAQUETE + EXT_ARCHIVO + (".flatpak", ".flatpakref", ".sh", ".run", ".exe", ".msi", ".rpm")


class NoSePuede(Exception):
    pass


def tipo(p):
    p = Path(p); n = p.name.lower()
    try:
        with open(p, "rb") as f:
            cab = f.read(16)
    except OSError as e:
        raise NoSePuede(f"no puedo leer {p}: {e}")
    if cab[:4] == b"\x7fELF" and cab[8:10] == b"AI" or n.endswith(".appimage"):
        return "appimage"
    for e in EXT_PAQUETE:
        if n.endswith(e):
            return "deb" if e == ".deb" else "arch"
    for e in EXT_ARCHIVO:
        if n.endswith(e):
            return "archivo"
    if n.endswith(".flatpakref") or n.endswith(".flatpak"):
        return "flatpak"
    if n.endswith((".sh", ".run")) or cab[:2] == b"#!":
        return "instalador"
    if n.endswith((".exe", ".msi")) or cab[:2] == b"MZ":
        return "windows"
    if n.endswith(".rpm"):
        return "rpm"
    return "?"


EXPLICA = {
    "appimage": "AppImage: se extrae en tu carpeta (sin FUSE) y se crea su lanzador",
    "archivo": "archivo comprimido: se extrae y se busca su programa principal",
    "deb": "paquete .deb: se extrae su contenido en tu carpeta, sin instalarlo en el sistema; si necesita librerías que SteamOS no tiene, no arrancará",
    "arch": "paquete de Arch: se extrae su contenido en tu carpeta, sin pacman; si necesita librerías que SteamOS no tiene, no arrancará",
    "flatpak": "Flatpak: flatpak install --user",
    "instalador": "instalador (.sh): se abre en Konsole para que sigas sus pasos; instálalo dentro de ~/Applications",
    "windows": "programa de Windows: no se instala aquí. Para probarlo, añádelo en Steam como juego que no es de Steam y fuerza Proton en sus propiedades",
    "rpm": "paquete .rpm (Fedora): no soportado. Busca el AppImage, el .tar.gz o el Flatpak del programa",
    "?": "no reconozco este archivo",
}


def nombre_limpio(p):
    n = Path(p).name
    for e in sorted(TODAS, key=len, reverse=True):
        if n.lower().endswith(e):
            n = n[: -len(e)]
            break
    n = re.sub(r"[-_ .](x86[-_]?64|amd64|aarch64|arm64|linux(64)?|v?\d+(\.\d+)+.*)$", "", n, flags=re.I) or n
    n = re.sub(r"[^A-Za-z0-9._-]+", "_", n).strip("_.")[:50]
    return n or "Programa"


def _dentro(base, ruta):
    base, ruta = os.path.realpath(base), os.path.realpath(ruta)
    return ruta == base or ruta.startswith(base + os.sep)


def extraer(arch, dest):
    """Extracción segura (sin rutas fuera de dest) de tar.* y zip."""
    dest.mkdir(parents=True, exist_ok=True)
    n = arch.name.lower()
    if n.endswith(".zip"):
        with zipfile.ZipFile(arch) as z:
            for i in z.infolist():
                if not _dentro(dest, dest / i.filename):
                    raise NoSePuede(f"ruta peligrosa dentro del zip: {i.filename}")
                z.extract(i, dest)
                modo = (i.external_attr >> 16) & 0o777
                if modo and not i.is_dir():
                    os.chmod(dest / i.filename, modo)
        return
    if n.endswith(".zst"):
        zst = _zstd()
        if zst:                                      # el zstd de Python (3.14, o backports.zstd): luego, tarfile con sus comprobaciones
            plano = dest.parent / (".tmp-" + arch.name[:-4])
            with open(arch, "rb") as i, zst.open(i) as z, open(plano, "wb") as o:
                shutil.copyfileobj(z, o, 1 << 20)
            try:
                return extraer(plano, dest)
            finally:
                plano.unlink(missing_ok=True)
        r = subprocess.run(["tar", "--zstd", "-xf", str(arch), "-C", str(dest), "--no-same-owner"], capture_output=True, text=True)
        if r.returncode:
            raise NoSePuede(f"tar --zstd: {r.stderr.strip()[:200]}")
        for raiz, _c, fs in os.walk(dest):          # comprobación posterior: ningún enlace hacia fuera
            for f in fs:
                p = Path(raiz, f)
                if p.is_symlink() and not _dentro(dest, p):
                    p.unlink()
        return
    with tarfile.open(arch) as t:
        for m in t.getmembers():
            if not _dentro(dest, dest / m.name) or (m.issym() or m.islnk()) and not _dentro(dest, dest / Path(m.name).parent / m.linkname):
                raise NoSePuede(f"ruta peligrosa dentro del archivo: {m.name}")
        try:
            t.extractall(dest, filter="data")
        except TypeError:
            t.extractall(dest)


def extraer_deb(deb, dest):
    """Un .deb es un archivo «ar» con data.tar.{xz,zst,gz}: se extrae ese data.tar."""
    with open(deb, "rb") as f:
        if f.read(8) != b"!<arch>\n":
            raise NoSePuede("no es un .deb válido")
        while True:
            cab = f.read(60)
            if len(cab) < 60:
                raise NoSePuede("el .deb no tiene data.tar")
            nombre = cab[:16].decode().strip().rstrip("/"); tam = int(cab[48:58].decode().strip())
            if nombre.startswith("data.tar"):
                tmp = dest.parent / (".tmp-" + nombre)
                with open(tmp, "wb") as o:
                    o.write(f.read(tam))
                try:
                    extraer(tmp, dest)
                finally:
                    tmp.unlink(missing_ok=True)
                return
            f.seek(tam + (tam & 1), 1)


def _zstd():
    for m in ("compression.zstd", "backports.zstd"):
        try:
            return __import__(m, fromlist=["open"])
        except ImportError:
            continue
    return None


def ejecutables(raiz):
    """Programas candidatos: ELF ejecutables (no librerías) y scripts con #!, con su arquitectura."""
    out = []
    for r, carpetas, fs in os.walk(raiz):
        carpetas[:] = [c for c in carpetas if c not in ("lib", "lib64", "share", "include", "doc", "locale", "__pycache__")]
        prof = len(Path(r).relative_to(raiz).parts)
        if prof > 4:
            carpetas[:] = []
        for f in fs:
            p = Path(r, f)
            if p.is_symlink() or ".so" in f or f.endswith((".py", ".txt", ".json", ".png", ".desktop")):
                continue
            try:
                with open(p, "rb") as h:
                    c = h.read(4)
            except OSError:
                continue
            if c == b"\x7fELF":
                try:
                    e = Elf(p)
                except (OSError, ValueError):
                    continue
                if e.arch in ("aarch64", "x86_64"):
                    out.append((p, e.arch, prof, p.stat().st_size))
            elif c[:2] == b"#!" and (f in ("AppRun",) or f.endswith(".sh") or os.access(p, os.X_OK)):
                out.append((p, "script", prof, p.stat().st_size))
    return out


def elegir_programa(raiz, pista):
    """El programa principal: AppRun o un script de arranque arriba; si no, el ELF que más se parece al nombre, poco profundo y grande."""
    cands = ejecutables(raiz)
    if not cands:
        raise NoSePuede("no encuentro ningún programa de Linux dentro")
    pista = re.sub(r"[^a-z0-9]", "", pista.lower())
    def nota(c):
        p, arch, prof, tam = c
        n = re.sub(r"[^a-z0-9]", "", p.stem.lower())
        s = -prof * 10 + min(tam / 2**20, 50)
        if p.name == "AppRun": s += 100
        if pista and (pista in n or n in pista): s += 60
        if arch == "script": s += 15 if prof <= 1 else -20
        if any(w in n for w in ("uninstall", "crash", "helper", "update", "setup")): s -= 80
        return s
    return sorted(cands, key=nota, reverse=True)


def arch_real(prog):
    """La arquitectura que manda: la del ELF; para un script (AppRun, start.sh), la del ELF más grande junto a él."""
    a = arch_de(prog)
    if a in ("aarch64", "x86_64"):
        return a
    elfs = sorted(((c[3], c[1]) for c in ejecutables(prog.parent) if c[1] in ("aarch64", "x86_64")), reverse=True)
    return elfs[0][1] if elfs else "?"


LANZADOR = """#!/bin/sh
# {nombre}: instalado por la Konkr Store desde {origen}
# {arch}: {como}
DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
cd "$DIR/{carpeta_rel}" || exit 1
unset LD_LIBRARY_PATH
{extra}exec {fex}"$DIR/{prog_rel}" "$@"
"""


def escribir_lanzador(dest, nombre, origen, prog, arch, libdirs=()):
    fex = ""
    if arch == "x86_64":
        como = "con FEX (x86_64 traducido a ARM64)"
        fex = '"$(command -v FEXInterpreter || command -v FEXLoader)" '
    elif arch == "aarch64":
        como = "nativo, sin FEX ni Proton"
    else:
        como = "script; lo que ejecute decide"
    extra = "unset LD_PRELOAD   # el overlay de Steam es ARM: un programa x86 no puede cargarlo\n" if arch == "x86_64" else ""
    if libdirs:
        extra += 'export LD_LIBRARY_PATH="' + ":".join(f"$DIR/{d}" for d in libdirs) + '"\n'
    rel = prog.relative_to(dest)
    (dest / "jugar.sh").write_text(LANZADOR.format(nombre=nombre, origen=origen, arch=arch, como=como, carpeta_rel=rel.parent.as_posix() or ".",
                                                  extra=extra, fex=fex, prog_rel=rel.as_posix()), encoding="utf-8")
    (dest / "jugar.sh").chmod(0o755)
    prog.chmod(prog.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def icono_de(dest):
    for pat in ("*.png", "usr/share/icons/hicolor/256x256/apps/*.png", "usr/share/icons/hicolor/128x128/apps/*.png", "usr/share/pixmaps/*.png", "**/*.png"):
        for p in sorted(dest.glob(pat), key=lambda x: -x.stat().st_size):
            if p.stat().st_size > 2000:
                return p
    return None


def escribir_acceso(dest, nombre, icono):
    ACCESOS.mkdir(parents=True, exist_ok=True)
    acc = ACCESOS / f"local-{dest.name}.desktop"
    acc.write_text("[Desktop Entry]\nType=Application\n"
                   f"Name={nombre}\nExec=\"{dest / 'jugar.sh'}\"\nPath={dest}\nIcon={icono or 'applications-games'}\n"
                   "Categories=Game;Utility;\nTerminal=false\n", encoding="utf-8")
    return acc


def destino_libre(nombre):
    d = LOCALES / nombre
    if d.exists():
        raise NoSePuede(f"ya existe {d}: desinstálalo antes o elige otro nombre (--nombre)")
    return d


def instalar(archivo, nombre=None, programa=None, decir=print):
    archivo = Path(archivo).expanduser().resolve()
    t = tipo(archivo)
    decir(f"{archivo.name}: {EXPLICA[t]}")
    if t in ("windows", "rpm", "?"):
        raise NoSePuede(EXPLICA[t])
    if t == "instalador":
        return {"tipo": t, "abrir": ["konsole", "--workdir", str(HOME / "Applications"), "-e", "bash", str(archivo)]}
    if t == "flatpak":
        opt = "--from" if archivo.name.lower().endswith(".flatpakref") else "--bundle"
        r = subprocess.run(["flatpak", "install", "--user", "-y", "--noninteractive", opt, str(archivo)], capture_output=True, text=True)
        decir((r.stdout + r.stderr).strip()[-1500:])
        if r.returncode:
            raise NoSePuede("flatpak no pudo instalarlo (¿falta añadir Flathub para el runtime? Abre Aplicaciones > Actualizar todas una vez)")
        return {"tipo": t}
    nombre = nombre or nombre_limpio(archivo)
    dest = destino_libre(re.sub(r"[^A-Za-z0-9._-]+", "_", nombre))
    tmp = LOCALES / f".instalando-{dest.name}"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    libdirs = []
    try:
        if t == "appimage":
            arch = arch_de(archivo)
            decir("AppImage: extrayendo…")
            raiz = tmp / "app"
            if shutil.which("unsquashfs"):
                r = subprocess.run(["unsquashfs", "-q", "-o", str(offset_appimage(archivo)), "-d", str(raiz), str(archivo)], capture_output=True, text=True)
            else:
                copia = tmp / "app.AppImage"; shutil.copyfile(archivo, copia); copia.chmod(0o755)
                cmd = [str(copia), "--appimage-extract"]
                if arch == "x86_64":
                    fex = shutil.which("FEXInterpreter") or shutil.which("FEXLoader")
                    if not fex:
                        raise NoSePuede("es x86_64 y no encuentro FEXInterpreter")
                    cmd = [fex] + cmd
                r = subprocess.run(cmd, cwd=tmp, capture_output=True, text=True)
                copia.unlink(missing_ok=True)
                if (tmp / "squashfs-root").is_dir():
                    (tmp / "squashfs-root").rename(raiz)
            if not (raiz / "AppRun").exists():
                raise NoSePuede(f"no se pudo extraer el AppImage: {(r.stdout + r.stderr).strip()[-300:]}")
            prog = raiz / "AppRun"
            dentro = arch_real(prog)                  # manda lo que lleva dentro (el runtime del AppImage puede ser de otra arquitectura)
            arch = dentro if dentro in ("aarch64", "x86_64") else arch
        else:
            raiz = tmp / "app"
            if t == "deb":
                extraer_deb(archivo, raiz)
            else:
                extraer(archivo, raiz)
            for d in ("usr/lib", "usr/lib/aarch64-linux-gnu", "usr/lib/x86_64-linux-gnu", "usr/lib64", "lib"):
                if (raiz / d).is_dir() and t in ("deb", "arch"):
                    libdirs.append(f"app/{d}")
            if programa:
                prog = raiz / programa
                if not prog.is_file():
                    raise NoSePuede(f"no existe {programa} dentro")
            else:
                cands = elegir_programa(raiz, nombre)
                prog = cands[0][0]
                otros = [str(c[0].relative_to(raiz)) for c in cands[1:4]]
                decir(f"programa principal: {prog.relative_to(raiz)}" + (f" (otros: {', '.join(otros)}; elige con --programa)" if otros else ""))
            arch = arch_real(prog)
        if arch not in ("aarch64", "x86_64"):
            raise NoSePuede("no sé de qué arquitectura es el programa")
        if arch == "x86_64" and not (shutil.which("FEXInterpreter") or shutil.which("FEXLoader")):
            decir("[aviso] es x86_64 y no encuentro FEX: no podrá ejecutarse")
        escribir_lanzador(tmp, nombre, archivo.name, prog, arch, [d for d in libdirs])
        info = {"nombre": nombre, "tipo": t, "arch": arch, "programa": str(prog.relative_to(tmp)), "origen": str(archivo),
                "instalado": time.strftime("%Y-%m-%d %H:%M:%S")}
        (tmp / "konkr-app.json").write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.rename(dest)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    icono = icono_de(dest)
    acc = escribir_acceso(dest, nombre, icono)
    decir(f"instalado en {dest} ({'ARM64 nativo' if arch == 'aarch64' else 'x86_64 con FEX'}); acceso {acc}")
    return {"tipo": t, "carpeta": str(dest), "acceso": str(acc), "arch": arch, "nombre": nombre}


def lista():
    out = []
    if LOCALES.is_dir():
        for d in sorted(LOCALES.iterdir()):
            try:
                i = json.loads((d / "konkr-app.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            i["carpeta"] = str(d); i["acceso"] = str(ACCESOS / f"local-{d.name}.desktop")
            out.append(i)
    return out


def candidatos():
    """Archivos instalables en Descargas, Escritorio, la carpeta personal y memorias USB / microSD, recientes primero."""
    sitios = [HOME / n for n in ("Downloads", "Descargas", "Desktop", "Escritorio")] + [HOME]
    media = Path("/run/media") / os.environ.get("USER", "")
    if media.is_dir():
        sitios += [p for p in media.iterdir() if p.is_dir()]
    vistos, out = set(), []
    for s in sitios:
        prof_max = 0 if s == HOME else 2
        for r, carpetas, fs in os.walk(s):
            if len(Path(r).relative_to(s).parts) >= prof_max:
                carpetas[:] = []
            carpetas[:] = [c for c in carpetas if not c.startswith(".")]
            for f in fs:
                if f.lower().endswith(TODAS) and not f.lower().endswith((".exe", ".msi", ".rpm")):
                    p = Path(r, f)
                    if p not in vistos and p.is_file():
                        vistos.add(p); out.append(p)
    return sorted(out, key=lambda p: -p.stat().st_mtime)


def main(argv):
    try:
        if argv[:1] == ["tipo"] and len(argv) == 2:
            t = tipo(argv[1]); print(f"{t}: {EXPLICA[t]}")
            if t == "appimage": print(f"arquitectura: {arch_de(argv[1])}")
        elif argv[:1] == ["instalar"] and len(argv) >= 2:
            nombre = argv[argv.index("--nombre") + 1] if "--nombre" in argv else None
            programa = argv[argv.index("--programa") + 1] if "--programa" in argv else None
            r = instalar(argv[1], nombre, programa)
            if r.get("abrir"):
                print("Ábrelo en Konsole: " + " ".join(r["abrir"]))
            print("RESULTADO " + json.dumps(r, ensure_ascii=False))
        elif argv[:1] == ["lista"]:
            for i in lista():
                print(f"{i['nombre']}\t{i['tipo']}\t{i['arch']}\t{i['carpeta']}")
        elif argv[:1] == ["candidatos"]:
            for p in candidatos():
                print(p)
        else:
            print(__doc__); return 1
    except NoSePuede as e:
        print(f"No se puede: {e}"); return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
