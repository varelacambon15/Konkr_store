#!/usr/bin/env python3
"""Revisa recomps y programas para la KONKR Pocket FIT (ARM64 + FEX).

SOLO LEE. No escribe nada salvo el informe, y únicamente si tú lo pides
(botón «Guardar informe» o --informe RUTA).

Uso:
  revisar_binarios.py                    -> ventana (elige carpeta o archivo)
  revisar_binarios.py RUTA [RUTA...]     -> informe en la terminal
  revisar_binarios.py --informe F RUTA   -> además lo guarda en F
  revisar_binarios.py offset APPIMAGE    -> imprime el offset del squashfs (uso interno)
  revisar_binarios.py arch ARCHIVO       -> imprime x86_64 / aarch64 / ... (uso interno)
"""
import json
import os
import struct
import sys
from pathlib import Path

HOME = Path.home()
MAX_ARCHIVOS = 4000          # para no recorrer carpetas enormes sin fin
MAX_PROFUNDIDAD = 6

MAQUINAS = {0x3E: "x86_64", 0xB7: "aarch64", 0x03: "x86 (32 bits)", 0x28: "arm (32 bits)"}


# ---------------------------------------------------------------- ELF
class Elf:
    """Lector mínimo de cabeceras ELF (64 bits, little endian). No ejecuta nada."""

    def __init__(self, ruta):
        self.ruta = Path(ruta)
        self.arch = None
        self.needed = []
        self.rpath = []
        self.es_appimage = False
        self.fin_secciones = None
        with open(self.ruta, "rb") as f:
            h = f.read(64)
            if len(h) < 64 or h[:4] != b"\x7fELF":
                raise ValueError("no es ELF")
            self.es_appimage = h[8:11] in (b"AI\x01", b"AI\x02")
            clase, endian = h[4], h[5]
            if endian != 1:
                raise ValueError("ELF big endian no soportado")
            maquina = struct.unpack_from("<H", h, 18)[0]
            self.arch = MAQUINAS.get(maquina, f"desconocida (0x{maquina:x})")
            if clase != 2:          # 32 bits: solo arquitectura
                return
            e_phoff, e_shoff = struct.unpack_from("<QQ", h, 32)
            e_phentsize, e_phnum, e_shentsize, e_shnum = struct.unpack_from("<HHHH", h, 54)
            self.fin_secciones = e_shoff + e_shentsize * e_shnum
            self._dinamico(f, e_phoff, e_phentsize, e_phnum)

    def _dinamico(self, f, phoff, phentsize, phnum):
        segs, dyn = [], None
        for i in range(min(phnum, 256)):
            f.seek(phoff + i * phentsize)
            p = f.read(56)
            if len(p) < 56:
                return
            p_type, _flags, p_offset, p_vaddr, _pa, p_filesz = struct.unpack_from("<IIQQQQ", p)
            if p_type == 1:
                segs.append((p_vaddr, p_offset, p_filesz))
            elif p_type == 2:
                dyn = (p_offset, p_filesz)
        if not dyn:
            return

        def a_offset(vaddr):
            for va, off, sz in segs:
                if va <= vaddr < va + sz:
                    return off + (vaddr - va)
            return None

        f.seek(dyn[0])
        datos = f.read(min(dyn[1], 1 << 20))
        strtab, needed_off, rpath_off = None, [], []
        for i in range(0, len(datos) - 15, 16):
            tag, val = struct.unpack_from("<qQ", datos, i)
            if tag == 0:
                break
            if tag == 1:
                needed_off.append(val)
            elif tag == 5:
                strtab = val
            elif tag in (15, 29):
                rpath_off.append(val)
        base = a_offset(strtab) if strtab is not None else None
        if base is None:
            return

        def cadena(o):
            f.seek(base + o)
            b = f.read(512)
            return b.split(b"\0", 1)[0].decode("utf-8", "replace")

        self.needed = [cadena(o) for o in needed_off]
        for o in rpath_off:
            self.rpath += [x for x in cadena(o).split(":") if x]


def arch_de(ruta):
    try:
        return Elf(ruta).arch
    except (OSError, ValueError):
        return None


def offset_appimage(ruta):
    """Donde empieza el squashfs dentro de un AppImage tipo 2 (fin de la tabla de secciones)."""
    e = Elf(ruta)
    if not e.fin_secciones:
        raise ValueError("no se pudo calcular el offset")
    return e.fin_secciones


# ---------------------------------------------------------------- FEX
def config_fex():
    for d in (Path(os.environ.get("XDG_DATA_HOME", HOME / ".local/share")) / "fex-emu", HOME / ".fex-emu"):
        c = d / "Config.json"
        if c.is_file():
            try:
                return d, json.loads(c.read_text()).get("Config", {})
            except (OSError, ValueError):
                return d, {}
    return None, {}


def rootfs_fex():
    """Carpeta del rootfs x86_64 de FEX, si se puede leer. Devuelve (ruta o None, explicación)."""
    d, cfg = config_fex()
    nombre = cfg.get("RootFS", "")
    candidatos = []
    if nombre:
        p = Path(os.path.expanduser(nombre))
        candidatos += [p] if p.is_absolute() else [d / "RootFS" / nombre] if d else []
    for c in candidatos:
        if c.is_dir():
            return c, f"rootfs (carpeta): {c}"
    # Imagen .sqsh/.ero: FEX la monta mientras corre algo; se busca en /proc/mounts.
    try:
        for linea in open("/proc/mounts"):
            punto = linea.split()[1].replace("\\040", " ")
            if "FEX" in punto or (nombre and Path(nombre).stem in punto):
                if Path(punto, "usr").is_dir():
                    return Path(punto), f"rootfs montado: {punto}"
    except OSError:
        pass
    if candidatos:
        return None, f"rootfs configurado ({candidatos[0]}) es una imagen no montada: abre un juego con FEX y vuelve a revisar"
    return None, "no se encontró la configuración de FEX (~/.fex-emu/Config.json)"


LIBS_X86 = ["lib/x86_64-linux-gnu", "usr/lib/x86_64-linux-gnu", "lib64", "usr/lib64", "usr/lib", "lib"]
LIBS_ARM = ["/usr/lib", "/lib", "/usr/lib/aarch64-linux-gnu", "/lib/aarch64-linux-gnu", "/usr/lib64", "/lib64"]


def libs_que_faltan(elf, raiz_app, rootfs):
    if not elf.needed:
        return []
    dirs = []
    origen = elf.ruta.parent
    for r in elf.rpath:
        dirs.append(Path(r.replace("$ORIGIN", str(origen)).replace("${ORIGIN}", str(origen))))
    dirs += [origen, origen / "lib", origen / "libs"]
    if raiz_app:
        dirs += [raiz_app / "usr/lib", raiz_app / "usr/lib/x86_64-linux-gnu", raiz_app / "lib", raiz_app / "usr/lib64"]
    if elf.arch == "x86_64":
        if rootfs is None:
            return None          # no se puede saber
        dirs += [rootfs / x for x in LIBS_X86]
    elif elf.arch == "aarch64":
        dirs += [Path(x) for x in LIBS_ARM]
    else:
        return None
    return [n for n in elf.needed if not any((d / n).exists() for d in dirs)]


# ---------------------------------------------------------------- análisis
def tipo_de(ruta):
    try:
        with open(ruta, "rb") as f:
            h = f.read(4)
    except OSError:
        return None
    if h == b"\x7fELF":
        return "elf"
    if h[:2] == b"MZ" and ruta.suffix.lower() in (".exe", ".dll"):
        return "pe" if ruta.suffix.lower() == ".exe" else None
    if h[:2] == b"#!" and os.access(ruta, os.X_OK):
        return "script"
    return None


def archivos(raiz):
    raiz = Path(raiz)
    if raiz.is_file():
        yield raiz
        return
    n = 0
    for actual, carpetas, ficheros in os.walk(raiz):
        if len(Path(actual).relative_to(raiz).parts) >= MAX_PROFUNDIDAD:
            carpetas[:] = []
        carpetas[:] = [c for c in carpetas if not c.startswith(".")]
        for nombre in ficheros:
            n += 1
            if n > MAX_ARCHIVOS:
                return
            yield Path(actual, nombre)


def manifiestos(raiz):
    raiz = Path(raiz)
    base = raiz if raiz.is_dir() else raiz.parent
    for p in list(base.glob("recomplauncher.json")) + list(base.glob("*/recomplauncher.json")):
        yield p


def resumen_manifiesto(p):
    try:
        m = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return [f"  (no se pudo leer: {e})"]
    out = []
    g = m.get("game") or {}
    if g.get("label"):
        out.append(f"  Pide: {g['label']}")
    if g.get("kind"):
        out.append(f"  Formato aceptado (kind): {g['kind']}")
    chk = g.get("check") or {}
    for k, v in chk.items():
        out.append(f"  Comprobación «{k}»: {v}")
    for d in g.get("dumps") or []:
        out.append(f"  Volcado verificado: {d.get('name','?')}  tamaño={d.get('size','?')}  crc32={d.get('crc32','?')}")
    upd = g.get("update")
    if isinstance(upd, dict) and upd.get("label"):
        opc = " (opcional)" if upd.get("optional") else ""
        out.append(f"  Además pide: {upd['label']}{opc}")
    st = (m.get("start") or {}).get("program")
    if st:
        out.append(f"  Programa de inicio: {st}")
    return out or ["  (el manifiesto no indica qué archivo pide)"]


def revisar(rutas):
    rootfs, nota_rootfs = rootfs_fex()
    lineas = [f"Máquina: {os.uname().machine}", f"FEX: {nota_rootfs}", ""]
    for ruta in rutas:
        ruta = Path(ruta).expanduser()
        lineas.append(f"=== {ruta}")
        if not ruta.exists():
            lineas.append("  no existe")
            continue
        raiz_app = None
        if ruta.is_dir():
            for c in (ruta, *ruta.glob("*")):
                if (c / "AppRun").exists():
                    raiz_app = c
                    break
        cuenta = {"aarch64": 0, "x86_64": 0, "pe": 0}
        for f in archivos(ruta):
            if f.is_symlink() or f.suffix in (".so",) or ".so." in f.name:
                continue
            t = tipo_de(f)
            if not t:
                continue
            rel = f.relative_to(ruta) if ruta.is_dir() else f.name
            if t == "pe":
                cuenta["pe"] += 1
                lineas.append(f"  [WINDOWS] {rel}  -> necesita Proton; en ARM no lo doy por bueno")
            elif t == "script":
                with open(f, "rb") as fh:
                    sb = fh.readline().decode("utf-8", "replace").strip()
                lineas.append(f"  [script]  {rel}  ({sb})")
            else:
                try:
                    e = Elf(f)
                except (OSError, ValueError) as ex:
                    lineas.append(f"  [ELF?]    {rel}: {ex}")
                    continue
                if e.arch in cuenta:
                    cuenta[e.arch] += 1
                tipo = "AppImage " if e.es_appimage else ""
                como = {"aarch64": "NATIVO (sin FEX)", "x86_64": "con FEX"}.get(e.arch, "no ejecutable aquí")
                lineas.append(f"  [{e.arch}] {tipo}{rel}  -> {como}")
                falta = libs_que_faltan(e, raiz_app, rootfs)
                if falta is None and e.needed:
                    lineas.append("            librerías: no comprobadas (rootfs de FEX no accesible)")
                elif falta:
                    lineas.append("            FALTAN: " + ", ".join(falta))
        for m in manifiestos(ruta):
            lineas.append(f"  recomplauncher.json ({m}):")
            lineas += resumen_manifiesto(m)
        if cuenta["aarch64"]:
            veredicto = "Trae binario ARM64: se puede ejecutar nativo."
        elif cuenta["x86_64"]:
            veredicto = "Solo x86_64: se ejecuta con FEX."
        elif cuenta["pe"]:
            veredicto = "Solo Windows: necesitaría Proton (no probado en esta consola)."
        else:
            veredicto = "No se encontraron programas."
        lineas += [f"  VEREDICTO: {veredicto}", ""]
    return "\n".join(lineas)


# ---------------------------------------------------------------- interfaz
def ventana():
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext

    inicio = next((str(p) for p in (HOME / "recomp/biblioteca", HOME / "Applications", HOME) if p.is_dir()), str(HOME))
    raiz = tk.Tk()
    raiz.title("Revisar recomps (KONKR)")
    raiz.geometry("1100x650")
    fuente = ("monospace", 13)
    barra = tk.Frame(raiz)
    barra.pack(fill="x", padx=8, pady=8)
    texto = scrolledtext.ScrolledText(raiz, font=fuente, wrap="none")
    texto.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def mostrar(rutas):
        if not rutas:
            return
        texto.delete("1.0", "end")
        texto.insert("end", "Revisando…\n")
        raiz.update_idletasks()
        texto.delete("1.0", "end")
        texto.insert("end", revisar(rutas))

    def carpeta():
        mostrar([filedialog.askdirectory(title="Elige la carpeta de la recomp", initialdir=inicio)] or [])

    def archivo():
        r = filedialog.askopenfilename(title="Elige un programa o AppImage", initialdir=inicio)
        mostrar([r] if r else [])

    def guardar():
        destino_dir = HOME / "recomp/informes"
        destino_dir.mkdir(parents=True, exist_ok=True)
        r = filedialog.asksaveasfilename(title="Guardar informe", initialdir=str(destino_dir),
                                         initialfile="informe.txt", defaultextension=".txt")
        if r:
            Path(r).write_text(texto.get("1.0", "end"), encoding="utf-8")
            messagebox.showinfo("Guardado", f"Informe guardado en:\n{r}")

    for t, cmd in (("Elegir carpeta…", carpeta), ("Elegir archivo…", archivo), ("Guardar informe…", guardar), ("Salir", raiz.destroy)):
        tk.Button(barra, text=t, command=cmd, font=("sans", 14), padx=14, pady=8).pack(side="left", padx=4)
    texto.insert("end", "Pulsa «Elegir carpeta…» y selecciona la carpeta de una recomp instalada.\n"
                        "Este programa solo lee archivos.\n")
    raiz.mainloop()


def ventana_zenity():
    import shutil
    import subprocess
    z = shutil.which("zenity")
    if not z:
        return False
    r = subprocess.run([z, "--file-selection", "--directory", "--title=Elige la carpeta de la recomp"],
                       capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        return True
    informe = revisar([r.stdout.strip()])
    subprocess.run([z, "--text-info", "--title=Informe", "--width=1000", "--height=600", "--font=monospace 12"],
                   input=informe, text=True)
    return True


def main(argv):
    if len(argv) >= 2 and argv[0] == "offset":
        print(offset_appimage(argv[1]))
        return 0
    if len(argv) >= 2 and argv[0] == "arch":
        print(arch_de(argv[1]) or "no-elf")
        return 0
    informe = None
    if len(argv) >= 2 and argv[0] == "--informe":
        informe, argv = argv[1], argv[2:]
    if argv:
        txt = revisar(argv)
        print(txt)
        if informe:
            Path(informe).expanduser().parent.mkdir(parents=True, exist_ok=True)
            Path(informe).expanduser().write_text(txt, encoding="utf-8")
        return 0
    try:
        ventana()
    except Exception as e:  # sin tkinter o sin pantalla
        if not ventana_zenity():
            print(f"No hay interfaz gráfica disponible ({e}). Uso: {sys.argv[0]} CARPETA")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
