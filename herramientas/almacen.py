#!/usr/bin/env python3
"""Dónde se guardan las descargas e instalaciones grandes de la Konkr Store: memoria interna o una tarjeta SD.

Las carpetas grandes (RecompLauncher, recomps, juegos de Switch, programas locales, comparaciones) van a <SD>/KonkrStore/<nombre>;
en tu carpeta personal quedan enlaces con los nombres de siempre, así los accesos de Steam y todo lo demás siguen igual.
Nunca se escribe fuera de tu carpeta personal y de <SD>/KonkrStore. La SD debe ser ext4/btrfs (como la formatea Steam): en
exFAT/FAT/NTFS los programas no se pueden ejecutar.

  almacen.py destinos               memoria interna y tarjetas montadas, con espacio libre y si sirven
  almacen.py estado                 dónde está ahora cada carpeta y cuánto ocupa
  almacen.py usar RUTA|interna      mueve las carpetas allí (pide confirmación; --si para no preguntar)
  almacen.py elegir                 menú en la terminal (lo usa instalar.sh)
  almacen.py comprobar              falla (código 1) si una carpeta apunta a una SD que no está montada
"""
import os
import shutil
import sys
from pathlib import Path

HOME = Path.home()
AJUSTE = HOME / "recomp/ajustes/almacen"
CARPETAS = {   # nombre en <SD>/KonkrStore  →  ruta de siempre
    "RecompLauncher": HOME / "Applications/RecompLauncher",
    "Locales": HOME / "Applications/Locales",
    "juegos-switch": HOME / "juegos-switch",
    "biblioteca": HOME / "recomp/biblioteca",
    "comparar": HOME / "recomp/comparar",
    "RecompLauncher-cache": Path(os.environ.get("XDG_DATA_HOME", HOME / ".local/share")) / "com.recomplauncher.app/cache",   # descomprime ahí tu copia del juego y los mods
    "claude-konkr": Path(os.environ.get("XDG_DATA_HOME", HOME / ".local/share")) / "claude-konkr",   # konkr-claude: ~340 MB por versión de Claude Code
}
BUENOS = {"ext4", "ext3", "btrfs", "xfs", "f2fs"}
SISTEMA = {"squashfs", "tmpfs", "overlay", "proc", "sysfs", "devtmpfs", "ramfs", "fuse.portal", "erofs", "iso9660"}   # no son tarjetas ni discos


def _gb(n):
    return f"{n / 2**30:.1f} GB"


def tamano(p):
    t = 0
    for r, _c, fs in os.walk(p):
        for f in fs:
            try:
                t += os.lstat(os.path.join(r, f)).st_size
            except OSError:
                pass
    return t


def destinos():
    """[(ruta, etiqueta, libre, sirve, motivo)]: la memoria interna y lo montado en /run/media, /media o /mnt."""
    out = []
    libre = shutil.disk_usage(HOME).free
    out.append(("interna", f"Memoria interna ({_gb(libre)} libres)", libre, True, ""))
    try:
        lineas = open("/proc/mounts").read().splitlines()
    except OSError:
        lineas = []
    vistos = set()
    for l in lineas:
        p = l.split()
        if len(p) < 4:
            continue
        punto = p[1].replace("\\040", " "); fs = p[2]; opts = p[3].split(",")
        if not punto.startswith(("/run/media/", "/media/", "/mnt/")) or punto in vistos or fs in SISTEMA:
            continue
        vistos.add(punto)
        try:
            libre = shutil.disk_usage(punto).free
        except OSError:
            continue
        motivo = ""
        if fs not in BUENOS:
            motivo = f"{fs}: no guarda permisos de ejecución ni enlaces (formatéala desde Steam: ext4)"
        elif "noexec" in opts:
            motivo = "montada sin permiso de ejecución (noexec)"
        elif not os.access(punto, os.W_OK):
            motivo = "sin permiso de escritura para tu usuario"
        out.append((punto, f"{Path(punto).name} — {fs}, {_gb(libre)} libres" + (f"  ✗ {motivo}" if motivo else ""), libre, not motivo, motivo))
    return out


def actual():
    try:
        return AJUSTE.read_text().strip() or "interna"
    except OSError:
        return "interna"


def estado():
    filas = []
    for nombre, p in CARPETAS.items():
        if p.is_symlink():
            dest = Path(os.readlink(p))
            filas.append((nombre, p, dest, dest.exists(), tamano(dest) if dest.exists() else 0))
        else:
            filas.append((nombre, p, None, p.exists(), tamano(p) if p.exists() else 0))
    return filas


def comprobar():
    """Las carpetas que apuntan a una SD que no está (enlaces rotos)."""
    return [(n, p, d) for n, p, d, existe, _t in estado() if d is not None and not existe]


def _mover(origen, destino, decir):
    """Mueve el contenido de origen a destino (destino puede existir: se juntan; un nombre repetido detiene todo)."""
    destino.mkdir(parents=True, exist_ok=True)
    for x in sorted(origen.iterdir()):
        if (destino / x.name).exists() or (destino / x.name).is_symlink():
            raise RuntimeError(f"ya existe {destino / x.name}: no lo piso. Resuélvelo a mano y repite")
    for x in sorted(origen.iterdir()):
        decir(f"  moviendo {x.name}…")
        shutil.move(str(x), str(destino / x.name))
    origen.rmdir()


def usar(destino, decir=print):
    """Lleva las carpetas a destino (una ruta de destinos() o 'interna') y deja los enlaces. Devuelve 0 bien, 1 no se puede."""
    ds = {d[0]: d for d in destinos()}
    if destino != "interna":
        destino = str(Path(destino).resolve())
        d = ds.get(destino)
        if d and not d[3]:
            decir(f"No sirve: {d[4]}"); return 1
        if not d and not Path(destino).is_dir():
            decir(f"No existe {destino}"); return 1
    rotas = comprobar()
    if rotas:
        decir("Antes, monta la SD donde están: " + ", ".join(str(r[2]) for r in rotas)); return 1
    raiz = HOME if destino == "interna" else Path(destino) / "KonkrStore"
    # espacio: lo que hay que mover a ese disco
    mover = 0
    for nombre, p, dest, existe, t in estado():
        ahora = dest if dest is not None else p
        nuevo = p if destino == "interna" else raiz / nombre
        if existe and ahora.resolve() != nuevo.resolve() and os.stat(ahora).st_dev != os.stat(raiz if raiz.exists() else Path(destino if destino != "interna" else HOME)).st_dev:
            mover += t
    libre = shutil.disk_usage(HOME if destino == "interna" else destino).free
    margen = min(2**30, int(libre * 0.05))
    if mover > libre - margen:
        decir(f"No cabe: hay que mover {_gb(mover)} y quedan {_gb(libre)} libres (con un margen de {_gb(margen)})"); return 1
    for nombre, p, dest, existe, t in estado():
        if destino == "interna":
            if dest is None:
                continue                                  # ya está en la memoria interna
            decir(f"{nombre}: {dest} → {p} ({_gb(t)})")
            p.unlink()
            if dest.exists():
                _mover(dest, p, decir)
            else:
                p.mkdir(parents=True, exist_ok=True)
            continue
        nuevo = raiz / nombre
        if dest is not None and Path(dest).resolve() == nuevo.resolve():
            decir(f"{nombre}: ya está en {nuevo}"); continue
        decir(f"{nombre}: {dest or p} → {nuevo} ({_gb(t)})")
        if dest is not None:                              # estaba en otra SD
            p.unlink()
            if dest.exists():
                _mover(dest, nuevo, decir)
        elif p.exists():
            _mover(p, nuevo, decir)
        nuevo.mkdir(parents=True, exist_ok=True)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.symlink_to(nuevo, target_is_directory=True)
    AJUSTE.parent.mkdir(parents=True, exist_ok=True)
    AJUSTE.write_text(destino + "\n")
    decir(f"Listo: las descargas e instalaciones grandes van a {'la memoria interna' if destino == 'interna' else raiz}")
    if destino != "interna":
        decir("En RecompLauncher, elige como biblioteca ~/recomp/biblioteca (ya apunta a la SD).")
    return 0


def main(argv):
    if argv[:1] == ["destinos"]:
        for ruta, etq, _l, ok, _m in destinos():
            print(f"{'✔' if ok else '✗'} {ruta}\t{etq}")
    elif argv[:1] == ["estado"]:
        print(f"Elegido: {actual()}")
        for nombre, p, dest, existe, t in estado():
            print(f"  {nombre:15} {_gb(t):>9}  {p}" + (f" → {dest}" + ("" if existe else "  ✗ NO ESTÁ (¿SD sin montar?)") if dest else ""))
    elif argv[:1] == ["comprobar"]:
        rotas = comprobar()
        for n, p, d in rotas:
            print(f"✗ {p} apunta a {d}, que no está: ¿la SD no está montada?")
        return 1 if rotas else 0
    elif argv[:1] == ["usar"] and len(argv) >= 2:
        if "--si" not in argv:
            r = input(f"¿Mover las carpetas grandes a {argv[1]}? Cierra antes RecompLauncher y los juegos. [s/N] ")
            if not r.lower().startswith(("s", "y")):
                print("Cancelado."); return 0
        try:
            return usar(argv[1])
        except (OSError, RuntimeError) as e:
            print(f"Error: {e}"); return 1
    elif argv[:1] == ["elegir"]:
        ds = destinos()
        sd = [d for d in ds if d[0] != "interna"]
        validas = [d for d in sd if d[3]]
        for d in sd:
            if not d[3]:
                print(f"Tarjeta {Path(d[0]).name}: no sirve ({d[4]})")
        if len(validas) == 1 and actual() == "interna":   # una sola SD válida: se ofrece directamente (Intro = sí)
            ruta, etq = validas[0][0], validas[0][1]
            try:
                r = input(f"¿Guardar lo grande en la tarjeta SD {etq}? [S/n] ").strip().lower()
            except EOFError:
                r = ""
            if r.startswith("n"):
                print("Memoria interna (se cambia en la tienda > Herramientas > Dónde se guarda)."); return 0
            try:
                return usar(ruta)
            except (OSError, RuntimeError) as e:
                print(f"Error: {e}"); return 1
        if not sd:
            print("No hay ninguna tarjeta SD montada: se usa la memoria interna. (Si la insertas luego: tienda > Herramientas > Dónde se guarda.)")
            return 0
        print("¿Dónde se guardan RecompLauncher, las recomps, los juegos de Switch y los programas locales?")
        for i, (_r, etq, _l, ok, _m) in enumerate(ds, 1):
            print(f"  {i}) {etq}")
        print(f"  (ahora: {actual()}; Intro = no cambiar)")
        try:
            r = input("Número: ").strip()
        except EOFError:
            r = ""
        if not r:
            return 0
        if not r.isdigit() or not 1 <= int(r) <= len(ds):
            print("Número no válido: no cambio nada."); return 0
        ruta, _e, _l, ok, motivo = ds[int(r) - 1]
        if not ok:
            print(f"Esa no sirve: {motivo}"); return 0
        try:
            return usar(ruta)
        except (OSError, RuntimeError) as e:
            print(f"Error: {e}"); return 1
    else:
        print(__doc__); return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
