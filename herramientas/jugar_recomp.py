#!/usr/bin/env python3
"""Abre una recomp instalada con RecompLauncher, de la forma más directa posible (lo usan los accesos de Steam).

  jugar_recomp.py ID              abre la recomp
  jugar_recomp.py ID --info       solo dice qué haría (no abre nada)

Por defecto, a través de RecompLauncher (--play): prepara la recomp como siempre (tu copia del juego, sus ajustes y
argumentos, efectos, partidas en la nube). Las builds de Linux las ejecuta sin Proton; solo las de Windows usan su Proton.
Modo «directo» (opcional, por recomp, solo builds de Linux; Konkr Store > Recompilaciones > Directo / Launcher):
  · Linux aarch64  -> se ejecuta tal cual, nativa (sin FEX ni Proton; el overlay de Steam sigue funcionando)
  · Linux x86_64   -> con el traductor x86 (Box64, FEX o binfmt; herramientas/x86.py), sin RecompLauncher de por medio
  Se salta la preparación de RecompLauncher: úsalo después de jugar una vez con RecompLauncher.
La elección se toma al arrancar, así que el acceso de Steam no cambia nunca. En Steam: sin herramienta de compatibilidad.
Registro: ~/recomp/logs/jugar_<ID>.log
"""
import json
import os
import sys
from pathlib import Path

HOME = Path.home()
DIR = Path(__file__).resolve().parent
LIBRERIA = Path(os.environ.get("XDG_DATA_HOME", HOME / ".local/share")) / "com.recomplauncher.app/library.json"
LANZADOR = HOME / "Applications/lanzar_recomp.sh"
MODO = HOME / "recomp/ajustes/lanzamiento"          # MODO/<id> = "directo": sin RecompLauncher (solo builds de Linux)
sys.path.insert(0, str(DIR))
from revisar_binarios import arch_de  # noqa: E402


def leer(gid):
    try:
        lib = json.loads(LIBRERIA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    for clave, g in (lib.get("installed") or {}).items():
        if isinstance(g, dict) and (g.get("id") or clave) == gid:
            return g
    return None


def manifiesto(carpeta):
    for p in (carpeta / "recomplauncher.json", *carpeta.glob("*/recomplauncher.json")):
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return {}


def build_de(g):
    """(tipo, programa): tipo = linux-arm64 | linux-x64 | windows | ? (programa: la ruta del ejecutable, si se sabe)."""
    carpeta = Path(g.get("path") or "")
    exe = g.get("exe")
    prog = (Path(exe) if Path(exe).is_absolute() else carpeta / exe) if exe else None
    if g.get("proton") or (prog and prog.suffix.lower() in (".exe", ".bat", ".cmd", ".msi")):
        return "windows", prog
    arch = arch_de(prog) if prog and prog.is_file() else None
    return {"aarch64": "linux-arm64", "x86_64": "linux-x64"}.get(arch, "?"), prog


def directo_elegido(gid):
    try:
        return (MODO / gid).read_text().strip() == "directo"
    except OSError:
        return False


def plan(gid):
    """(modo, ejecutable, argumentos, carpeta, entorno extra, explicación); modo = launcher | nativo | x86."""
    g = leer(gid)
    via = ("launcher", None, [], HOME, {})
    if not g:
        return via + (f"no está en {LIBRERIA}: a través de RecompLauncher",)
    tipo, prog = build_de(g)
    if tipo == "windows":
        return via + ("build de Windows: RecompLauncher la abre con su propio Proton",)
    if tipo == "?":
        return via + ("RecompLauncher la prepara y la abre (no se sabe qué programa es)",)
    sin = "Linux aarch64: nativa, sin traductor ni Proton" if tipo == "linux-arm64" else "Linux x86_64: traducida (Box64/FEX), sin Proton"
    if not directo_elegido(gid):
        return via + (f"{sin}; RecompLauncher la prepara y la abre",)
    carpeta = Path(g.get("path") or "")
    arch = "aarch64" if tipo == "linux-arm64" else "x86_64"
    m = manifiesto(carpeta)
    inicio = m.get("start") or {}
    args = [str(a).replace("{install}", str(carpeta)) for a in (inicio.get("args") or [])]
    args += [a for a in (g.get("args") or "").split() if a]
    if g.get("manual") and g["manual"].get("how") == "arg" and g["manual"].get("copy"):
        args += [a.replace("{copy}", g["manual"]["copy"]) for a in g["manual"].get("arg", "{copy}").split()]
    entorno = {k: str(v).replace("{install}", str(carpeta)) for k, v in (inicio.get("env") or {}).items()
               if not k.startswith("RECOMPLAUNCHER_")}
    modo = "nativo" if arch == "aarch64" else "x86"
    return modo, prog, args, prog.parent, entorno, f"{sin}; directa, sin RecompLauncher"


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    gid = argv[0]
    modo, prog, args, carpeta, extra, expl = plan(gid)
    if "--info" in argv:
        print(f"{gid}: {modo} — {expl}")
        if prog:
            print(f"  programa: {prog}\n  argumentos: {' '.join(args) or '-'}\n  carpeta: {carpeta}")
        return 0
    logs = HOME / "recomp/logs"
    logs.mkdir(parents=True, exist_ok=True)
    log = open(logs / f"jugar_{gid}.log", "w")
    print(f"{gid}: {modo} — {expl}", file=log, flush=True)
    os.dup2(log.fileno(), 1)
    os.dup2(log.fileno(), 2)
    env = dict(os.environ, **extra)
    env.pop("LD_LIBRARY_PATH", None)                         # librerías del runtime de Steam: no son para el juego
    if modo == "launcher":
        if not LANZADOR.exists():
            print(f"No existe {LANZADOR}: instala RecompLauncher (instalar.sh)")
            return 1
        os.execve(str(LANZADOR), [str(LANZADOR), "--play", gid], env)
    os.chdir(carpeta)
    if modo == "x86":
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import x86
        if not x86.traductor():
            print("No encuentro cómo ejecutar x86_64 (ni Box64, ni FEX, ni binfmt)")
            return 1
        env.pop("LD_PRELOAD", None)                          # el overlay de Steam es ARM: un proceso x86 no puede cargarlo
        cmd = x86.orden(prog, args)
        print("orden:", " ".join(cmd), flush=True)
        os.execve(cmd[0], cmd, env)
    os.execve(str(prog), [str(prog), *args], env)            # nativo: se conserva LD_PRELOAD (overlay de Steam, ARM como el juego)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
