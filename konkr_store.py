#!/usr/bin/env python3
"""Konkr Store: tienda y panel para la KONKR Pocket FIT (SteamOS ARM).

Pantalla de inicio con secciones:
  · Aplicaciones     tipo Discover: aplicaciones Flatpak de Flathub, instaladas en tu usuario (--user)
  · Recompilaciones  las recomps de RecompLauncher: jugar, añadir a Steam, revisar
  · Herramientas     actualizar, versiones, modo gráfico, diagnóstico, registros, copia de Steam

Lo que instales se puede añadir a Steam («juego que no es de Steam») pidiéndoselo a Steam
(herramientas/anadir_a_steam.sh): la tienda NUNCA escribe en los archivos de Steam.

Mando / teclado: flechas para moverse, Intro para elegir, Esc para volver.

Uso en terminal (sin ventana):
  konkr_store.py estado | versiones | usar VERSION | graficos seguro|normal
  konkr_store.py recomps | acceso-recomp ID | acceso-app ID | acceso-launcher
  konkr_store.py auto-steam [--forzar] [--esperar]   añade a Steam lo nuevo: recomps y juegos de Switch de ~/juegos-switch
                                                    (copia de seguridad antes; --esperar: a que terminen las copias en curso)
  konkr_store.py switch                 lista los juegos de Switch de ~/juegos-switch
"""
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

HOME = Path.home()
DIR = Path(__file__).resolve().parent
BASE = HOME / "Applications/RecompLauncher"
LANZADOR = HOME / "Applications/lanzar_recomp.sh"
RECOMP = HOME / "recomp"
ACCESOS = RECOMP / "accesos"
PREF_GRAF = RECOMP / "ajustes/graficos"
LOG_LANZ = RECOMP / "logs/lanzar_recomp.log"
LIBRERIA = Path(os.environ.get("XDG_DATA_HOME", HOME / ".local/share")) / "com.recomplauncher.app/library.json"
RESPALDO = Path(os.environ.get("KONKR_RESPALDO", HOME / "iw6x-steamos/tools/respaldo_steam.sh"))
ANADIR = DIR / "herramientas/anadir_a_steam.sh"
JUGAR = DIR / "herramientas/jugar_recomp.py"
MODO_RECOMP = RECOMP / "ajustes/lanzamiento"
FLATHUB_REPO = "https://dl.flathub.org/repo/flathub.flatpakrepo"
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
ID_VALIDO = re.compile(r"^[A-Za-z0-9_.\-]+$")


# =================================================================== lógica (sin ventana)
def sh(cmd, timeout=60):
    """Ejecuta y devuelve (código, salida). Nunca lanza excepción."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 127, str(e)


def version_actual():
    act = BASE / "actual"
    return os.readlink(act) if act.is_symlink() else ""


def versiones():
    if not BASE.is_dir():
        return []
    return sorted(p.name for p in BASE.iterdir()
                  if p.is_dir() and not p.is_symlink() and (p / "AppRun").exists())


def usar_version(nombre):
    if nombre not in versiones():
        raise ValueError(f"No existe la versión {nombre}")
    tmp = BASE / ".actual.nuevo"
    if tmp.is_symlink() or tmp.exists():
        tmp.unlink()
    tmp.symlink_to(nombre)
    os.replace(tmp, BASE / "actual")      # cambio atómico del enlace


def modo_grafico():
    try:
        return PREF_GRAF.read_text().strip() or "normal"
    except OSError:
        return "normal"


def poner_modo_grafico(modo):
    if modo not in ("seguro", "normal"):
        raise ValueError("modo: seguro o normal")
    PREF_GRAF.parent.mkdir(parents=True, exist_ok=True)
    PREF_GRAF.write_text(modo + "\n")


def fex():
    """Traductor de x86_64 (Box64, FEX o «directo» por binfmt), o "" si no hay; ver herramientas/x86.py."""
    try:
        sys.path.insert(0, str(DIR / "herramientas"))
        import x86
        return x86.traductor() or ""
    except Exception:
        return ""


def recomps():
    """Recomps instaladas por RecompLauncher: lista de dict(id, nombre, ruta, version)."""
    try:
        lib = json.loads(LIBRERIA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for clave, g in (lib.get("installed") or {}).items():
        if not isinstance(g, dict):
            continue
        gid = g.get("id") or clave
        out.append({"id": gid, "nombre": g.get("name") or gid, "ruta": g.get("path", ""),
                    "version": g.get("tag") or g.get("version") or ""})
    return sorted(out, key=lambda x: x["nombre"].lower())


TIPOS = {"linux-arm64": "Linux ARM64", "linux-x64": "Linux x86 (Box64/FEX)", "windows": "Windows·Proton", "?": "¿?"}


def _jugar():
    sys.path.insert(0, str(DIR / "herramientas"))
    import jugar_recomp
    return jugar_recomp


def tipo_recomp(gid):
    """(modo, etiqueta corta, explicación): qué build es y cómo la abrirá su acceso (herramientas/jugar_recomp.py)."""
    j = _jugar()
    modo, _p, _a, _c, _e, expl = j.plan(gid)
    g = j.leer(gid)
    tipo = j.build_de(g)[0] if g else "?"
    etq = TIPOS[tipo] + (" · directo" if modo != "launcher" else "")
    return modo, etq, expl


def cambiar_modo_recomp(gid):
    """Alterna entre «vía RecompLauncher» (por defecto) y «directo» (solo builds de Linux). Devuelve tipo_recomp, o None si no se puede."""
    j = _jugar()
    g = j.leer(gid)
    if not g or j.build_de(g)[0] not in ("linux-arm64", "linux-x64"):
        return None
    f = MODO_RECOMP / gid
    if f.exists():
        f.unlink()
    else:
        MODO_RECOMP.mkdir(parents=True, exist_ok=True)
        f.write_text("directo\n")
    return tipo_recomp(gid)


def anadidos():
    try:
        return set((ACCESOS / "anadidos.txt").read_text().split("\n")) - {""}
    except OSError:
        return set()


AUTO_STEAM = RECOMP / "ajustes/auto_steam"


def auto_activo():
    try:
        return AUTO_STEAM.read_text().strip() != "no"
    except OSError:
        return True                      # activado salvo que se desactive en Herramientas


def poner_auto(on):
    AUTO_STEAM.parent.mkdir(parents=True, exist_ok=True)
    AUTO_STEAM.write_text("si\n" if on else "no\n")


def recomps_pendientes():
    ya = anadidos()
    return [g for g in recomps() if str(ACCESOS / f"{nombre_archivo('recomp-' + g['id'])}.desktop") not in ya]


# ---- Juegos de Switch portados con nx2konkr: una carpeta por juego en ~/juegos-switch (dmhost, jugar.sh, mods/, env.txt...) ----
SWITCH = Path(os.environ.get("KONKR_SWITCH", HOME / "juegos-switch"))
SWITCH_NECESARIOS = ("dmhost", "jugar.sh", "env.txt", "mods", "nx2a-data.json")


def juegos_switch():
    """Carpetas de juegos portados en SWITCH: dict(carpeta, nombre, id, version, completo)."""
    out = []
    if not SWITCH.is_dir():
        return out
    for d in sorted(SWITCH.iterdir()):
        if not d.is_dir() or not (d / "dmhost").exists() and not (d / "jugar.sh").exists():
            continue
        try:
            man = json.loads((d / "nx2a-data.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            man = {}
        out.append({"carpeta": d, "nombre": man.get("name") or d.name, "id": man.get("title_id", ""), "version": man.get("display", ""),
                    "completo": all((d / n).exists() for n in SWITCH_NECESARIOS)})
    return out


def acceso_switch(j):
    d = j["carpeta"]
    for n in ("dmhost", "jugar.sh"):          # una copia por USB (exFAT/NTFS) pierde el permiso de ejecución
        try:
            (d / n).chmod((d / n).stat().st_mode | 0o755)
        except OSError:
            pass
    icono = d / "icon.png"
    return escribir_desktop(f"nx-{d.name}", j["nombre"], f'"{d / "jugar.sh"}"', str(icono) if icono.exists() else "applications-games")


def switch_pendientes():
    ya = anadidos()
    return [j for j in juegos_switch() if j["completo"] and str(ACCESOS / f"{nombre_archivo('nx-' + j['carpeta'].name)}.desktop") not in ya]


def tamano(d):
    t = 0
    for raiz, _c, fs in os.walk(d):
        for f in fs:
            try:
                t += os.lstat(os.path.join(raiz, f)).st_size
            except OSError:
                pass
    return t


def esperar_copias(decir=print, quieto=None, maximo=7200):
    """Espera a que ~/juegos-switch deje de cambiar de tamaño (una copia en curso) durante `quieto` segundos."""
    quieto = quieto if quieto is not None else int(os.environ.get("KONKR_QUIETO", "30"))
    antes, estable, t0 = -1, 0, time.time()
    while time.time() - t0 < maximo:
        ahora = tamano(SWITCH) if SWITCH.is_dir() else 0
        estable = estable + 5 if ahora == antes else 0
        if estable >= quieto:
            return True
        if antes >= 0 and ahora != antes and estable == 0:
            decir(f"Copiando en {SWITCH}… ({ahora / 2**30:.1f} GB)")
        antes = ahora
        time.sleep(5)
    return False


def steam_abierto():
    return any(sh(["pgrep", "-x", n])[0] == 0 for n in ("steam", "steamwebhelper"))


def auto_steam(decir=print):
    """Añade a Steam lo instalado que aún no tiene acceso: recomps de RecompLauncher y juegos de Switch de ~/juegos-switch
    (nx2konkr). Una copia de seguridad por tanda y luego una petición a Steam por juego (herramientas/anadir_a_steam.sh).
    Devuelve 0 hecho/nada que hacer, 3 Steam cerrado (quedan pendientes), 4 falló la copia, 5 no hay copia de seguridad,
    6 ya hay otra tanda en marcha."""
    import fcntl
    pend = [(g["nombre"], lambda g=g: acceso_recomp(g["id"])) for g in recomps_pendientes()]
    pend += [(j["nombre"] + " (Switch)", lambda j=j: acceso_switch(j)) for j in switch_pendientes()]
    if not pend:
        decir("No hay nada nuevo sin acceso en Steam.")
        return 0
    decir(f"Nuevo sin acceso en Steam: {', '.join(n for n, _ in pend)}")
    if not steam_abierto():
        decir("Steam no está abierto: se añadirán la próxima vez.")
        return 3
    if not RESPALDO.is_file():
        decir(f"No encuentro {RESPALDO}: sin copia de seguridad no se añade nada automáticamente.")
        return 5
    ACCESOS.mkdir(parents=True, exist_ok=True)
    cerrojo = open(ACCESOS / ".auto.lock", "w")
    try:
        fcntl.flock(cerrojo, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        decir("Ya hay otra tanda añadiendo a Steam.")
        return 6
    decir(f"Copia de seguridad de Steam: {RESPALDO}")
    c, out = sh(["bash", str(RESPALDO)], timeout=600)
    if out:
        decir(out)
    if c != 0:
        decir("La copia de seguridad falló: no se añade nada.")
        return 4
    entorno = dict(os.environ, KONKR_RESPALDO_HECHO="1")
    for nombre, crear in pend:
        try:
            acc = crear()
        except (ValueError, OSError) as e:
            decir(f"{nombre}: {e}")
            continue
        r = subprocess.run(["bash", str(ANADIR), str(acc)], capture_output=True, text=True, env=entorno)
        decir(f"{nombre}: {'pedido a Steam' if r.returncode == 0 else 'no se pudo (' + (r.stdout + r.stderr).strip().splitlines()[-1] + ')'}")
        time.sleep(1.5)                  # una petición tras otra, sin amontonarlas en Steam
    return 0


def nombre_archivo(texto):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", texto).strip("_")[:60] or "acceso"


def escribir_desktop(nombre_fichero, nombre, exec_, icono="applications-games"):
    ACCESOS.mkdir(parents=True, exist_ok=True)
    ruta = ACCESOS / f"{nombre_archivo(nombre_fichero)}.desktop"
    nombre = nombre.replace("\n", " ")
    ruta.write_text(
        "[Desktop Entry]\nType=Application\n"
        f"Name={nombre}\nExec={exec_}\nPath={HOME}\nIcon={icono}\n"
        "Categories=Game;\nTerminal=false\n", encoding="utf-8")
    return ruta


def acceso_recomp(gid):
    if not ID_VALIDO.match(gid):
        raise ValueError("id no válido")
    g = next((r for r in recomps() if r["id"] == gid), None)
    if not g:
        raise ValueError(f"No encuentro la recomp {gid} en {LIBRERIA}")
    # Siempre el mismo lanzador: decide al arrancar (nativa, FEX o RecompLauncher), así el acceso de Steam no cambia
    return escribir_desktop(f"recomp-{gid}", g["nombre"], f'"{JUGAR}" {gid}')


def acceso_launcher():
    icono = BASE / "arte-steam/poster.jpg"
    return escribir_desktop("RecompLauncher", "RecompLauncher", f'"{LANZADOR}" --bigpicture',
                            str(icono) if icono.exists() else "applications-games")


def acceso_app(app_id, nombre=None):
    if not ID_VALIDO.match(app_id):
        raise ValueError("id no válido")
    # El .desktop que exporta el propio Flatpak (lo mismo que usa Discover), si existe.
    for base in (HOME / ".local/share/flatpak/exports/share/applications",
                 Path("/var/lib/flatpak/exports/share/applications")):
        d = base / f"{app_id}.desktop"
        if d.is_file() and str(d).startswith(str(HOME)):
            return d
    return escribir_desktop(f"app-{app_id}", nombre or app_id, f"flatpak run {app_id}", app_id)


# ------------------------------------------------------------------- Flatpak (siempre --user)
def flatpak():
    return shutil.which("flatpak") or ""


def destacadas():
    try:
        return json.loads((DIR / "datos/aplicaciones.json").read_text(encoding="utf-8"))["destacadas"]
    except (OSError, ValueError, KeyError):
        return []


def apps_instaladas():
    """{id: (nombre, versión, instalación)} de usuario y de sistema."""
    if not flatpak():
        return {}
    c, out = sh(["flatpak", "list", "--app", "--columns=application,name,version,installation"])
    res = {}
    if c == 0:
        for linea in out.splitlines():
            p = linea.split("\t")
            if len(p) >= 4 and ID_VALIDO.match(p[0]):
                res[p[0]] = (p[1], p[2], p[3])
    return res


def tiene_flathub_usuario():
    c, out = sh(["flatpak", "remotes", "--user", "--columns=name"])
    return c == 0 and "flathub" in out.split()


def buscar_apps(texto):
    c, out = sh(["flatpak", "search", "--columns=application,name,description,version,remotes", texto], timeout=120)
    res = []
    if c == 0:
        for linea in out.splitlines():
            p = linea.split("\t")
            if len(p) >= 2 and ID_VALIDO.match(p[0]) and "flathub" in (p[4] if len(p) > 4 else "flathub"):
                res.append({"id": p[0], "nombre": p[1], "desc": p[2] if len(p) > 2 else "",
                            "categoria": p[3] if len(p) > 3 else ""})
    return res


# =================================================================== interfaz gráfica
def interfaz():
    import tkinter as tk
    import tkinter.font as tkfont

    juego = os.environ.get("XDG_CURRENT_DESKTOP", "").lower() == "gamescope" or bool(os.environ.get("SteamGameId"))
    F_TIT, F_BOT, F_TXT, F_LIS = ("sans", 28, "bold"), ("sans", 18), ("monospace", 12), ("sans", 18)
    # La paleta de RecompLauncher (ui/app.css): fondo, tarjetas, texto, acento cian
    FONDO, PANEL, TEXTO, ACENTO, FOCO = "#0B1220", "#0f1829", "#F4F8FC", "#34F2E8", "#1b2842"
    TARJETA2, TENUE = "#141f33", "#A9B4C4"

    raiz = tk.Tk()
    raiz.title("Konkr Store")
    raiz.configure(bg=FONDO)
    if juego:
        raiz.attributes("-fullscreen", True)
    else:
        raiz.geometry("1280x800")
        try:
            raiz.attributes("-zoomed", True)     # maximizada en el escritorio
        except tk.TclError:
            pass
    # Letra grande también en los cuadros de diálogo (pantalla de 6" a 1080p).
    for nombre in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkCaptionFont"):
        try:
            tkfont.nametofont(nombre).configure(size=16)
        except tk.TclError:
            pass

    # Tras cada cuadro de diálogo el foco vuelve a la tienda (si no, el mando deja de responder).
    ultimo = {"w": None}
    modal = {"var": None, "cancelar": None}

    def recordar_foco(e):
        try:
            if modal["var"] is None and e.widget.winfo_toplevel() is raiz:
                ultimo["w"] = e.widget
        except (tk.TclError, AttributeError):
            pass
    raiz.bind_all("<FocusIn>", recordar_foco, add="+")

    def reenfocar():
        def hacer():
            if modal["var"] is not None:
                return
            w = ultimo["w"]
            try:
                if w is None or not w.winfo_exists() or not w.winfo_viewable():
                    w = None
            except tk.TclError:
                w = None
            try:
                w = w or pantallas[actual["nombre"]]["foco"]()
                raiz.focus_force()
                w.focus_force()
            except (tk.TclError, KeyError, TypeError):
                pass
        raiz.after(60, hacer)

    # Cuadros de diálogo DENTRO de la ventana (capa a pantalla completa con botones grandes).
    # Los diálogos emergentes de Tk pierden el foco sin gestor de ventanas o en gamescope.

    def capa_modal(titulo, texto, botones, entrada=False, opciones=None, marcada=0, cancelar=None):
        """botones: [(texto, valor)]. Devuelve el valor del botón, o con `entrada` el texto escrito,
        o con `opciones` el índice elegido. Esc devuelve `cancelar`."""
        capa = tk.Frame(raiz, bg=FONDO)
        capa.place(relx=0, rely=0, relwidth=1, relheight=1)
        caja = tk.Frame(capa, bg=PANEL, padx=34, pady=26, highlightthickness=3, highlightbackground=ACENTO)
        caja.place(relx=0.5, rely=0.5, anchor="center")
        tk.Label(caja, text=titulo, font=("sans", 24, "bold"), bg=PANEL, fg=TEXTO).pack(anchor="w")
        if texto:
            tk.Label(caja, text=texto, font=("sans", 17), bg=PANEL, fg=TEXTO, justify="left",
                     wraplength=1100).pack(anchor="w", pady=(12, 16))
        var = tk.StringVar(value="")
        enfocables = []
        caja_ent = lb = None
        if entrada:
            caja_ent = tk.Entry(caja, font=("sans", 22), width=40, bg="#0a0f14", fg=TEXTO, insertbackground=TEXTO,
                                relief="flat", highlightthickness=4, highlightcolor=ACENTO)
            caja_ent.pack(fill="x", pady=(0, 16))
            caja_ent.bind("<Return>", lambda e: var.set("__ok__"))
            enfocables.append(caja_ent)
        if opciones:
            lb = lista(caja)
            lb.configure(height=min(10, len(opciones)), width=60)
            for o in opciones:
                lb.insert("end", o)
            lb.selection_set(marcada)
            lb.activate(marcada)
            lb.see(marcada)
            lb.pack(fill="x", pady=(0, 16))
            lb.bind("<Return>", lambda e: var.set("__ok__"))
            enfocables.append(lb)
        fila = tk.Frame(caja, bg=PANEL)
        fila.pack(anchor="e")
        for t, v in botones:
            b = boton(fila, t, lambda v=v: var.set(f"__b__{v}"))
            b.configure(width=12)
            b.pack(side="left", padx=8)
            enfocables.append(b)

        def mover(paso):
            def f(e):
                i = enfocables.index(e.widget) if e.widget in enfocables else 0
                enfocables[(i + paso) % len(enfocables)].focus_set()
                return "break"
            return f
        for w in enfocables:
            w.bind("<Left>", mover(-1))
            w.bind("<Right>", mover(1))
            if w is not lb:
                w.bind("<Up>", mover(-1))
                w.bind("<Down>", mover(1))
        anterior = dict(modal)
        modal.update(var=var, cancelar=cancelar)
        capa.grab_set()
        raiz.focus_force()
        enfocables[0].focus_force()
        raiz.wait_variable(var)
        v = var.get()
        valor = cancelar
        if v.startswith("__b__"):
            valor = dict((f"__b__{bv}", bv) for _, bv in botones).get(v, cancelar)
            if valor == "__ok__":
                v = "__ok__"
        if v == "__ok__":
            if entrada:
                valor = caja_ent.get().strip() or cancelar
            elif opciones:
                s_ = lb.curselection()
                valor = s_[0] if s_ else cancelar
        capa.grab_release()
        capa.destroy()
        modal.update(anterior)
        reenfocar()
        return valor

    def si_no(titulo, texto):
        return capa_modal(titulo, texto, [("Sí", True), ("No", False)], cancelar=False) is True

    def info(titulo, texto):
        capa_modal(titulo, texto, [("Aceptar", True)], cancelar=True)
    error = alerta = info

    def pedir_texto(titulo, texto):
        return capa_modal(titulo, texto, [("Buscar", "__ok__"), ("Cancelar", None)], entrada=True)

    def elegir_de(titulo, texto, opciones, marcada=0):
        return capa_modal(titulo, texto, [("Elegir", "__ok__"), ("Cancelar", None)], opciones=opciones,
                          marcada=marcada)

    cola = queue.Queue()      # (función) para ejecutar en el hilo de la ventana
    ocupado = {"v": False}

    def en_ventana(f):
        cola.put(f)

    def bombear():
        try:
            while True:
                cola.get_nowait()()
        except queue.Empty:
            pass
        raiz.after(100, bombear)

    raiz.after(100, bombear)

    # ---------- utilidades de widgets
    def boton(padre, texto, cmd, ancho=None, alto=1):
        b = tk.Button(padre, text=texto, command=cmd, font=F_BOT, bg=PANEL, fg=TEXTO, activebackground=FOCO,
                      activeforeground=TEXTO, relief="flat", padx=18, pady=10, height=alto,
                      highlightthickness=4, highlightbackground=FONDO, highlightcolor=ACENTO, takefocus=1)
        if ancho:
            b.configure(width=ancho)
        b.bind("<Return>", lambda e: b.invoke())
        b.bind("<KP_Enter>", lambda e: b.invoke())
        for k in ("<Left>", "<Up>"):
            b.bind(k, lambda e: (e.widget.tk_focusPrev().focus_set(), "break")[1])
        for k in ("<Right>", "<Down>"):
            b.bind(k, lambda e: (e.widget.tk_focusNext().focus_set(), "break")[1])
        return b

    def caja_texto(padre, alto=10):
        t = tk.Text(padre, height=alto, font=F_TXT, bg="#0a0f14", fg=TEXTO, insertbackground=TEXTO,
                    relief="flat", wrap="word", takefocus=0)
        t.configure(state="disabled")
        return t

    def escribir(t, texto, limpiar=False):
        t.configure(state="normal")
        if limpiar:
            t.delete("1.0", "end")
        t.insert("end", ANSI.sub("", texto))
        t.see("end")
        t.configure(state="disabled")

    def lista(padre):
        lb = tk.Listbox(padre, font=F_LIS, bg=PANEL, fg=TEXTO, selectbackground=ACENTO, selectforeground="#000",
                        relief="flat", highlightthickness=4, highlightbackground=FONDO, highlightcolor=ACENTO,
                        activestyle="none", exportselection=False, takefocus=1)
        lb.bind("<Left>", lambda e: (e.widget.tk_focusPrev().focus_set(), "break")[1])
        lb.bind("<Right>", lambda e: (e.widget.tk_focusNext().focus_set(), "break")[1])
        lb.bind("<FocusIn>", lambda e: (lb.size() and not lb.curselection()) and (lb.selection_set(0), lb.activate(0)))
        return lb

    def tarea(salida, titulo, cmd, al_terminar=None):
        """Ejecuta cmd en segundo plano y vuelca su salida en la caja `salida`."""
        if ocupado["v"]:
            info("Konkr Store", "Espera a que termine la tarea en curso.")
            return
        ocupado["v"] = True
        escribir(salida, f"\n=== {titulo} ===\n")

        def trabajo():
            codigo = 127
            try:
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                     stdin=subprocess.DEVNULL, bufsize=1)
                for linea in p.stdout:
                    en_ventana(lambda l=linea: escribir(salida, l))
                codigo = p.wait()
            except OSError as e:
                en_ventana(lambda err=str(e): escribir(salida, f"Error: {err}\n"))   # e deja de existir al salir del except

            def fin():
                ocupado["v"] = False
                escribir(salida, f"--- terminado (código {codigo}) ---\n")
                if al_terminar:
                    al_terminar(codigo)
            en_ventana(fin)

        threading.Thread(target=trabajo, daemon=True).start()

    def lanzar(cmd, salida=None, titulo=""):
        """Abre un programa aparte (no espera)."""
        try:
            subprocess.Popen(cmd, start_new_session=True, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if salida is not None:
                escribir(salida, f"\nAbriendo {titulo}…\n")
        except OSError as e:
            error("Konkr Store", f"No pude abrir {titulo}: {e}")

    def pedir_steam(salida, archivo, nombre, al_terminar=None):
        """Confirma y pide a Steam que añada `archivo` como juego que no es de Steam."""
        txt = (f"¿Añadir «{nombre}» a Steam como juego que no es de Steam?\n\n"
               f"Archivo: {archivo}\n\n"
               "Antes se hará tu copia de seguridad de Steam. Steam añadirá el acceso él mismo; "
               "la tienda no toca sus archivos.")
        if not si_no("Añadir a Steam", txt):
            return
        extra = [] if RESPALDO.is_file() else ["--sin-respaldo"]
        if extra and not si_no("Sin copia de seguridad",
                                             f"No encuentro {RESPALDO}.\n¿Añadirlo igualmente sin copia?"):
            return
        tarea(salida, f"Añadir a Steam: {nombre}", ["bash", str(ANADIR), str(archivo), *extra], al_terminar)

    # ---------- pantallas
    pantallas = {}
    actual = {"nombre": None}

    def mostrar(nombre):
        for p in pantallas.values():
            p["marco"].pack_forget()
        p = pantallas[nombre]
        p["marco"].pack(fill="both", expand=True)
        actual["nombre"] = nombre
        if p.get("al_entrar"):
            p["al_entrar"]()
        raiz.after(50, lambda: p["foco"]().focus_set())

    def atras(_e=None):
        if modal["var"] is not None:          # Esc dentro de un cuadro de diálogo = cancelar
            modal["var"].set("__esc__")
            return "break"
        if actual["nombre"] == "inicio":
            if si_no("Konkr Store", "¿Salir de Konkr Store?"):
                raiz.destroy()
        else:
            mostrar("inicio")

    raiz.bind("<Escape>", atras)

    def cabecera(marco, titulo, volver=True):
        c = tk.Frame(marco, bg=FONDO)
        c.pack(fill="x", padx=24, pady=(18, 6))
        tk.Label(c, text=titulo, font=F_TIT, bg=FONDO, fg=TEXTO).pack(side="left")
        if volver:
            tk.Label(c, text="Esc: volver", font=("sans", 14), bg=FONDO, fg="#8f98a0").pack(side="right")
        return c

    # ================= INICIO
    m = tk.Frame(raiz, bg=FONDO)
    cabecera(m, "Konkr Store", volver=False)
    estado_lbl = tk.Label(m, text="", font=("sans", 14), bg=FONDO, fg="#8f98a0", justify="left")
    estado_lbl.pack(anchor="w", padx=28)
    fila = tk.Frame(m, bg=FONDO)
    fila.pack(expand=True)
    tiles = []
    for texto, destino in (("Aplicaciones\n\nTipo Discover:\napps de Flathub", "apps"),
                           ("Recompilaciones\n\nJuegos recompilados\ncon RecompLauncher", "recomps"),
                           ("Juegos de Switch\n\nTus juegos portados\ncon nx2konkr", "switch"),
                           ("Herramientas\n\nActualizar, versiones,\ndiagnóstico…", "herr"),
                           ("Opciones\n\nDónde se guarda,\nSteam, gráficos", "opciones")):
        t = boton(fila, texto, lambda d=destino: mostrar(d), ancho=18, alto=4)
        t.configure(font=("sans", 18, "bold"))
        t.grid(row=len(tiles) // 3, column=len(tiles) % 3, padx=12, pady=12)   # 3 columnas: caben en cualquier pantalla
        tiles.append(t)
    tk.Label(m, text="Flechas: moverse · Intro: elegir · Esc: volver/salir · Teclado en pantalla: Steam + X",
             font=("sans", 13), bg=FONDO, fg="#8f98a0").pack(side="bottom", pady=12)

    def entrar_inicio():
        v = version_actual() or "no instalado"
        try:
            alm = (RECOMP / "ajustes/almacen").read_text().strip() or "interna"
        except OSError:
            alm = "interna"
        alm = "memoria interna" if alm == "interna" else Path(alm).name
        rotas = [p for p in (BASE, SWITCH) if p.is_symlink() and not p.exists()]
        estado_lbl.configure(text=f"RecompLauncher: {v}   ·   x86: {(Path(fex()).name if fex() != 'directo' else 'binfmt') if fex() else 'NO encontrado'}   ·   "
                                  f"Recomps: {len(recomps())}   ·   Guardado en: {alm}" + ("   ·   ⚠ ¡LA SD NO ESTÁ MONTADA!" if rotas else ""))
    pantallas["inicio"] = {"marco": m, "foco": lambda: tiles[0], "al_entrar": entrar_inicio}

    # ================= APLICACIONES
    m = tk.Frame(raiz, bg=FONDO)
    cabecera(m, "Aplicaciones")
    barra = tk.Frame(m, bg=FONDO)
    barra.pack(fill="x", padx=24)
    cuerpo = tk.Frame(m, bg=FONDO)
    cuerpo.pack(fill="both", expand=True, padx=24, pady=6)
    lb_apps = lista(cuerpo)
    lb_apps.pack(side="left", fill="both", expand=True)
    detalle = tk.Label(cuerpo, text="", font=("sans", 16), bg=PANEL, fg=TEXTO, justify="left", anchor="nw",
                       wraplength=420, width=32, padx=14, pady=14)
    detalle.pack(side="left", fill="y", padx=(12, 0))
    acciones = tk.Frame(m, bg=FONDO)
    acciones.pack(fill="x", padx=24)
    sal_apps = caja_texto(m, 8)
    sal_apps.pack(fill="x", padx=24, pady=(6, 16))
    apps_vista = []          # lista de dicts mostrada

    def pintar_apps(items, titulo):
        inst = apps_instaladas()
        apps_vista.clear()
        apps_vista.extend(items)
        lb_apps.delete(0, "end")
        for a in items:
            marca = "✔ " if a.get("local") or a["id"] in inst else "   "
            lb_apps.insert("end", f"{marca}{a['nombre']}" + (f"   [{a['desc']}]" if a.get("local") else ""))
        escribir(sal_apps, f"{titulo}: {len(items)} aplicaciones\n")
        if items:
            lb_apps.selection_set(0)
            lb_apps.activate(0)
        ver_detalle()

    def app_sel():
        s = lb_apps.curselection()
        return apps_vista[s[0]] if s and s[0] < len(apps_vista) else None

    def ver_detalle(_e=None):
        a = app_sel()
        if not a:
            detalle.configure(text="")
            return
        if a.get("local"):
            i = a["local"]
            detalle.configure(text=f"{a['nombre']}\n\nInstalado desde archivo\n({i.get('tipo')}, "
                                   f"{'ARM64 nativo' if i.get('arch') == 'aarch64' else 'x86_64 traducido'})\n\n{Path(i.get('origen', '')).name}\n\n"
                                   f"{i.get('instalado', '')}\n\n{i['carpeta']}")
            return
        inst = apps_instaladas().get(a["id"])
        estado = f"Instalada ({inst[2]}) {inst[1]}" if inst else "No instalada"
        detalle.configure(text=f"{a['nombre']}\n\n{a.get('desc', '')}\n\n{a.get('categoria', '')}\n\n{a['id']}\n\n{estado}")
    lb_apps.bind("<<ListboxSelect>>", ver_detalle)

    def sin_flatpak():
        if flatpak():
            return False
        error("Aplicaciones", "Flatpak no está instalado en esta consola.\n"
                             "(Ejecuta diagnostico.sh y pásame la salida.)")
        return True

    def asegurar_flathub(siguiente):
        if tiene_flathub_usuario():
            siguiente()
            return
        if si_no("Flathub", "Para instalar en tu usuario hace falta añadir Flathub a tu Flatpak "
                               "de usuario (no toca el sistema):\n\nflatpak remote-add --user flathub\n\n¿Añadirlo?"):
            tarea(sal_apps, "Añadir Flathub (usuario)",
                  ["flatpak", "remote-add", "--user", "--if-not-exists", "flathub", FLATHUB_REPO],
                  lambda c: c == 0 and siguiente())

    def ver_destacadas():
        pintar_apps(destacadas(), "Destacadas")

    def locales():
        sys.path.insert(0, str(DIR / "herramientas"))
        import instalar_local
        return instalar_local

    def ver_instaladas():
        loc = [{"id": "local:" + Path(i["carpeta"]).name, "nombre": i["nombre"], "categoria": "Local",
                "desc": f"{i['tipo']} · {'ARM64' if i['arch'] == 'aarch64' else 'x86_64'}", "local": i} for i in locales().lista()]
        inst = apps_instaladas() if flatpak() else {}
        pintar_apps(loc + [{"id": i, "nombre": v[0], "desc": f"Versión {v[1]}", "categoria": f"Instalación: {v[2]}"}
                           for i, v in sorted(inst.items(), key=lambda x: x[1][0].lower())], "Instaladas")

    def instalar_archivo():
        L = locales()
        cands = L.candidatos()
        opciones = [f"{p.name}   ({p.parent})" for p in cands[:40]] + ["Escribir otra ruta…"]
        i = elegir_de("Instalar archivo", "Instalables encontrados en Descargas, Escritorio y memorias USB (recientes primero). "
                      "AppImage, .tar.gz, .zip, .deb, paquetes de Arch, Flatpak o instaladores .sh.", opciones)
        if i is None:
            return
        if i == len(opciones) - 1:
            r = pedir_texto("Instalar archivo", "Ruta completa del archivo (teclado en pantalla: Steam + X):")
            if not r:
                return
            ruta = Path(r).expanduser()
        else:
            ruta = cands[i]
        try:
            t = L.tipo(ruta)
        except L.NoSePuede as e:
            error("Instalar archivo", str(e)); return
        if t in ("windows", "rpm", "?"):
            info("Instalar archivo", L.EXPLICA[t]); return
        if t == "instalador":
            if si_no("Instalador", f"{ruta.name}: {L.EXPLICA[t]}\n\n¿Abrirlo en Konsole?"):
                lanzar(["konsole", "--workdir", str(HOME / "Applications"), "-e", "bash", str(ruta)], sal_apps, ruta.name)
            return
        nombre = L.nombre_limpio(ruta)
        if not si_no("Instalar archivo", f"{ruta.name}\n\n{L.EXPLICA[t]}.\n\nSe instalará como «{nombre}» en ~/Applications/Locales/{nombre}"
                     "\n(nada fuera de tu carpeta de usuario). ¿Instalar?"):
            return

        def fin(codigo):
            hecho = next((x for x in L.lista() if x.get("origen") == str(ruta.resolve())), None)
            ver_instaladas()
            if codigo == 0 and hecho:
                acc = Path(hecho["acceso"])
                if auto_activo():
                    tarea(sal_apps, f"Añadir {hecho['nombre']} a Steam (automático)", ["bash", str(ANADIR), str(acc)])
                else:
                    pedir_steam(sal_apps, acc, hecho["nombre"])
        tarea(sal_apps, f"Instalar {ruta.name}", [sys.executable, str(DIR / "herramientas/instalar_local.py"), "instalar", str(ruta)], fin)

    def buscar():
        if sin_flatpak():
            return
        texto = pedir_texto("Buscar", "¿Qué buscas? (teclado en pantalla: Steam + X)")
        if not texto:
            return
        escribir(sal_apps, f"Buscando «{texto}»…\n")

        def trabajo():
            r = buscar_apps(texto)
            en_ventana(lambda: pintar_apps(r, f"Resultados de «{texto}»"))
            if not r:
                en_ventana(lambda: escribir(sal_apps, "Sin resultados. Si es la primera búsqueda, prueba "
                                                      "«Actualizar todas» para descargar el catálogo.\n"))
        threading.Thread(target=trabajo, daemon=True).start()

    def instalar():
        a = app_sel()
        if not a or sin_flatpak():
            return
        if a["id"] in apps_instaladas():
            info("Instalar", f"{a['nombre']} ya está instalada.")
            return

        def paso2():
            escribir(sal_apps, f"Comprobando si {a['id']} existe para esta consola (ARM64)…\n")

            def comprobar():
                c, out = sh(["flatpak", "remote-info", "--user", "flathub", a["id"]], timeout=120)

                def seguir():
                    if c != 0:
                        escribir(sal_apps, out + "\n")
                        alerta("Instalar", f"{a['nombre']} no está disponible en Flathub para "
                                                           "esta consola (ARM64), o no hay conexión.")
                        return
                    if si_no("Instalar", f"¿Instalar {a['nombre']} ({a['id']}) en tu usuario?"):
                        tarea(sal_apps, f"Instalar {a['nombre']}",
                              ["flatpak", "install", "--user", "-y", "--noninteractive", "flathub", a["id"]],
                              lambda cod: cod == 0 and (ver_detalle(), refrescar_marcas(), app_a_steam(a)))
                en_ventana(seguir)
            threading.Thread(target=comprobar, daemon=True).start()
        asegurar_flathub(paso2)

    def app_a_steam(a):
        """Tras instalar: a Steam sin preguntar si «A Steam: automático» está activado (la copia de seguridad la hace
        anadir_a_steam.sh y, si falta o falla, no añade nada); si no, con la confirmación de siempre."""
        acc = acceso_app(a["id"], a["nombre"])
        if auto_activo():
            tarea(sal_apps, f"Añadir {a['nombre']} a Steam (automático)", ["bash", str(ANADIR), str(acc)])
        else:
            pedir_steam(sal_apps, acc, a["nombre"])

    def refrescar_marcas():
        inst = apps_instaladas()
        for i, a in enumerate(apps_vista):
            lb_apps.delete(i)
            lb_apps.insert(i, ("✔ " if a["id"] in inst else "   ") + a["nombre"])

    def abrir_app():
        a = app_sel()
        if a and a.get("local"):
            lanzar([str(Path(a["local"]["carpeta"]) / "jugar.sh")], sal_apps, a["nombre"])
        elif a and a["id"] in apps_instaladas():
            lanzar(["flatpak", "run", a["id"]], sal_apps, a["nombre"])
        elif a:
            info("Abrir", "Primero instálala.")

    def steam_app():
        a = app_sel()
        if a and a.get("local"):
            pedir_steam(sal_apps, Path(a["local"]["acceso"]), a["nombre"])
        elif a and a["id"] in apps_instaladas():
            pedir_steam(sal_apps, acceso_app(a["id"], a["nombre"]), a["nombre"])
        elif a:
            info("Añadir a Steam", "Primero instálala.")

    def desinstalar():
        a = app_sel()
        if a and a.get("local"):
            c = Path(a["local"]["carpeta"])
            if si_no("Desinstalar", f"¿Mover a la papelera {a['nombre']}?\n({c})\n\nSi lo añadiste a Steam, quita el acceso desde Steam."):
                for p in (c, Path(a["local"]["acceso"])):
                    if p.exists() and sh(["gio", "trash", str(p)])[0] != 0:
                        dest = HOME / "Papelera_konkr_store" / time.strftime("%Y%m%d_%H%M%S"); dest.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(p), str(dest / p.name))
                escribir(sal_apps, f"\n{a['nombre']}: a la papelera.\n"); ver_instaladas()
            return
        inst = apps_instaladas().get(a["id"]) if a else None
        if not inst:
            return
        if inst[2] != "user":
            info("Desinstalar", "Esta app está instalada en el sistema, no en tu usuario: "
                                               "no la toco.")
            return
        if si_no("Desinstalar", f"¿Desinstalar {a['nombre']}?\n(Si la añadiste a Steam, "
                                              "quita el acceso desde Steam.)"):
            tarea(sal_apps, f"Desinstalar {a['nombre']}",
                  ["flatpak", "uninstall", "--user", "-y", "--noninteractive", a["id"]],
                  lambda c: (ver_detalle(), refrescar_marcas()))

    def actualizar_todas():
        if sin_flatpak():
            return
        if si_no("Actualizar", "¿Actualizar todas las aplicaciones Flatpak de tu usuario?"):
            asegurar_flathub(lambda: tarea(sal_apps, "Actualizar aplicaciones",
                                           ["flatpak", "update", "--user", "-y", "--noninteractive"]))

    for texto, cmd in (("Destacadas", ver_destacadas), ("Buscar…", buscar), ("Instaladas", ver_instaladas),
                       ("Instalar archivo…", instalar_archivo), ("Actualizar todas", actualizar_todas)):
        boton(barra, texto, cmd).pack(side="left", padx=(0, 10), pady=6)
    for texto, cmd in (("Instalar", instalar), ("Abrir", abrir_app), ("Añadir a Steam", steam_app),
                       ("Desinstalar", desinstalar), ("← Volver", lambda: mostrar("inicio"))):
        boton(acciones, texto, cmd).pack(side="left", padx=(0, 10), pady=6)
    pantallas["apps"] = {"marco": m, "foco": lambda: lb_apps,
                         "al_entrar": lambda: (not apps_vista) and ver_destacadas()}

    # ================= RECOMPILACIONES (al estilo de RecompLauncher: cuadrícula de portadas y panel de detalle)
    sys.path.insert(0, str(DIR / "herramientas"))
    import portadas
    m = tk.Frame(raiz, bg=FONDO)
    cabecera(m, "Recompilaciones")
    barra = tk.Frame(m, bg=FONDO)
    barra.pack(fill="x", padx=24)
    cuerpo_r = tk.Frame(m, bg=FONDO)
    cuerpo_r.pack(fill="both", expand=True, padx=24, pady=6)
    rej = tk.Canvas(cuerpo_r, bg=FONDO, highlightthickness=0, takefocus=1)
    rej.pack(side="left", fill="both", expand=True)
    det = tk.Frame(cuerpo_r, bg=PANEL, width=560)
    det.pack(side="left", fill="y", padx=(14, 0)); det.pack_propagate(False)
    det_hero = tk.Label(det, bg=TARJETA2, bd=0); det_hero.pack(fill="x")
    det_logo = tk.Label(det, bg=PANEL, fg=TEXTO, font=("sans", 24, "bold"), wraplength=520, justify="left", anchor="w")
    det_logo.pack(fill="x", padx=18, pady=(14, 4))
    det_meta = tk.Label(det, bg=PANEL, fg=ACENTO, font=("sans", 14, "bold"), wraplength=520, justify="left", anchor="w")
    det_meta.pack(fill="x", padx=18)
    det_txt = tk.Label(det, bg=PANEL, fg=TENUE, font=("sans", 14), wraplength=520, justify="left", anchor="nw")
    det_txt.pack(fill="both", expand=True, padx=18, pady=(10, 14))
    acciones = tk.Frame(m, bg=FONDO)
    acciones.pack(fill="x", padx=24)
    sal_rec = caja_texto(m, 4)
    sal_rec.pack(fill="x", padx=24, pady=(6, 16))
    rec_vista = []
    ya_avisadas = set()
    R = {"sel": 0, "fotos": {}, "en_steam": set(), "datos": {}}
    CW, CH, TXT, GAP = 176, 264, 54, 18          # portada 2:3, como las de RecompLauncher

    def r_cols():
        return max(1, (rej.winfo_width() - GAP) // (CW + GAP))

    def r_pintar(_e=None):
        rej.delete("all")
        cols = r_cols(); foco = raiz.focus_get() is rej
        for i, g in enumerate(rec_vista):
            x = GAP // 2 + (i % cols) * (CW + GAP); y = GAP // 2 + (i // cols) * (CH + TXT + GAP)
            sel = i == R["sel"]
            if sel:
                rej.create_rectangle(x - 5, y - 5, x + CW + 5, y + CH + TXT + 3, outline=ACENTO if foco else FOCO, width=4)
            rej.create_rectangle(x, y, x + CW, y + CH + TXT - 2, fill=PANEL, outline="")
            f = R["fotos"].get(g["id"])
            if f:
                rej.create_image(x, y, image=f, anchor="nw")
            else:                                  # sin imagen: tarjeta con las iniciales
                rej.create_rectangle(x, y, x + CW, y + CH, fill=TARJETA2, outline="")
                ini = "".join(w if w.isdigit() else w[0] for w in re.findall(r"[A-Za-z0-9]+", g["nombre"])[:3]).upper()[:4]
                rej.create_text(x + CW / 2, y + CH / 2, text=ini, fill=TENUE, font=("sans", 34, "bold"))
            nombre = g["nombre"] if len(g["nombre"]) <= 17 else g["nombre"][:16].rstrip() + "…"
            rej.create_text(x + 8, y + CH + 8, text=("★ " if g["id"] in R["en_steam"] else "") + nombre, fill=TEXTO,
                            font=("sans", 13, "bold"), anchor="nw")
            rej.create_text(x + 8, y + CH + 30, text=tipo_recomp(g["id"])[1], fill=ACENTO if "ARM64" in tipo_recomp(g["id"])[1] else TENUE,
                            font=("sans", 11), anchor="nw")
        filas = (len(rec_vista) + cols - 1) // cols
        rej.configure(scrollregion=(0, 0, rej.winfo_width(), filas * (CH + TXT + GAP) + GAP))

    def r_ver_sel():
        if not rec_vista:
            return
        cols = r_cols(); y = (R["sel"] // cols) * (CH + TXT + GAP)
        alto = max(1, (len(rec_vista) + cols - 1) // cols * (CH + TXT + GAP) + GAP)
        top, bot = rej.yview()
        if y / alto < top or (y + CH + TXT + GAP) / alto > bot:
            rej.yview_moveto(max(0, y / alto - 0.02))
        r_detalle()

    def r_mover(dx, dy):
        n = len(rec_vista)
        if not n:
            return "break"
        cols = r_cols(); i = R["sel"]
        if dy < 0 and i < cols:                   # arriba del todo: a la barra de botones
            rej.tk_focusPrev().focus_set(); return "break"
        if dy > 0 and i + cols >= n and (i // cols) == (n - 1) // cols:   # última fila: a los botones de abajo
            acciones.winfo_children()[0].focus_set(); return "break"
        R["sel"] = max(0, min(n - 1, i + dx + dy * cols))
        r_pintar(); r_ver_sel(); return "break"
    rej.bind("<Left>", lambda e: r_mover(-1, 0)); rej.bind("<Right>", lambda e: r_mover(1, 0))
    rej.bind("<Up>", lambda e: r_mover(0, -1)); rej.bind("<Down>", lambda e: r_mover(0, 1))
    rej.bind("<Return>", lambda e: (jugar(), "break")[1]); rej.bind("<KP_Enter>", lambda e: (jugar(), "break")[1])
    rej.bind("<FocusIn>", r_pintar); rej.bind("<FocusOut>", r_pintar); rej.bind("<Configure>", r_pintar)
    rej.bind("<Button-4>", lambda e: rej.yview_scroll(-2, "units")); rej.bind("<Button-5>", lambda e: rej.yview_scroll(2, "units"))

    def r_click(e):
        cols = r_cols(); x, y = rej.canvasx(e.x), rej.canvasy(e.y)
        i = int(y // (CH + TXT + GAP)) * cols + int(x // (CW + GAP))
        if 0 <= i < len(rec_vista) and x % (CW + GAP) < CW + GAP // 2:
            R["sel"] = i; rej.focus_set(); r_pintar(); r_detalle()
    rej.bind("<Button-1>", r_click)

    def r_detalle():
        g = rec_sel()
        if not g:
            det_hero.configure(image="", height=1); det_logo.configure(image="", text=""); det_meta.configure(text=""); det_txt.configure(text=""); return
        d = R["datos"].get(g["id"]) or portadas.datos(g["id"])
        h = R["fotos"].get(g["id"] + ":hero"); lg = R["fotos"].get(g["id"] + ":logo")
        det_hero.configure(image=h or "", height=175 if h else 1)
        det_logo.configure(image=lg or "", text="" if lg else g["nombre"])
        modo, etq, expl = tipo_recomp(g["id"])
        meta = " · ".join(x for x in (d["juego"], d["genero"], g["version"], etq) if x)
        det_meta.configure(text=meta)
        t = d["texto"].strip()
        det_txt.configure(text=(t[:300].rstrip() + "…" if len(t) > 300 else t) + ("\n\n" if t else "") + expl
                               + (f"\n\nPor {d['autor']}" if d["autor"] else "") + ("\n\n★ Ya en Steam" if g["id"] in R["en_steam"] else ""))

    def r_cargar_arte():
        """En segundo plano: busca/descarga portada, banner y logo de cada recomp; las fotos se crean en el hilo de la ventana."""
        lista_ids = [g["id"] for g in rec_vista]
        def trabajo():
            for gid in lista_ids:
                d = portadas.datos(gid); R["datos"][gid] = d
                for clave, fuente, w, hh, modo in ((gid, d["cover"], CW, CH, "cubrir"), (gid + ":hero", d["hero"], 560, 175, "cubrir"),
                                                   (gid + ":logo", d["logo"], 400, 110, "caber")):
                    if clave in R["fotos"] or not fuente:
                        continue
                    ruta = portadas.local(fuente) or portadas.descargar(fuente)
                    if ruta:
                        def poner(c=clave, r=ruta, w=w, hh=hh, modo=modo):
                            f = portadas.foto(tk, r, w, hh, modo)
                            if f:
                                R["fotos"][c] = f; r_pintar(); r_detalle()
                        en_ventana(poner)
        threading.Thread(target=trabajo, daemon=True).start()

    def pintar_recomps(avisar=False, limpiar=True):
        rec_vista.clear()
        rec_vista.extend(recomps())
        ya = anadidos()
        R["en_steam"] = {g["id"] for g in rec_vista if str(ACCESOS / f"{nombre_archivo('recomp-' + g['id'])}.desktop") in ya}
        R["sel"] = min(R["sel"], max(0, len(rec_vista) - 1))
        r_pintar(); r_detalle(); r_cargar_arte()
        if rec_vista:
            escribir(sal_rec, f"{len(rec_vista)} recomps instaladas (★ = ya pedida a Steam). Las de Linux se abren sin Proton; "
                              "las [Windows·Proton] usan el Proton de RecompLauncher. En Steam ninguna necesita Proton.\n", limpiar=limpiar)
        else:
            escribir(sal_rec, "Aún no hay recomps. Pulsa «Descargar recomps» para abrir RecompLauncher.\n"
                              f"(Se leen de {LIBRERIA})\n", limpiar=True)
        if avisar and auto_activo():
            if recomps_pendientes() and not ocupado["v"]:
                tarea(sal_rec, "Añadir recomps nuevas a Steam (automático)",
                      [sys.executable, str(DIR / "konkr_store.py"), "auto-steam"], lambda c: pintar_recomps(limpiar=False))
            return
        if avisar:
            nuevas = [g for g in rec_vista
                      if str(ACCESOS / f"{nombre_archivo('recomp-' + g['id'])}.desktop") not in ya
                      and g["id"] not in ya_avisadas]
            ya_avisadas.update(g["id"] for g in nuevas)
            if nuevas and si_no(
                    "Recomps nuevas", f"Hay {len(nuevas)} recomp(s) sin acceso en Steam:\n\n"
                    + "\n".join("· " + g["nombre"] for g in nuevas[:8])
                    + "\n\n¿Añadir la primera ahora? (las demás, una a una con «Añadir a Steam»)"):
                g = nuevas[0]
                pedir_steam(sal_rec, acceso_recomp(g["id"]), g["nombre"], lambda c: pintar_recomps(limpiar=False))

    def rec_sel():
        return rec_vista[R["sel"]] if 0 <= R["sel"] < len(rec_vista) else None

    def hay_launcher():
        if LANZADOR.exists() and version_actual():
            return True
        error("RecompLauncher", "RecompLauncher no está instalado. Ejecuta instalar.sh.")
        return False

    def descargar_recomps():
        if hay_launcher():
            lanzar([str(LANZADOR), "--bigpicture"] if juego else [str(LANZADOR)], sal_rec, "RecompLauncher")
            escribir(sal_rec, "Cuando termines de instalar, vuelve aquí y pulsa «Recargar».\n"
                              "No uses su botón «Add to Steam»: añádelas desde aquí.\n")

    def jugar():
        g = rec_sel()
        if g:
            modo, etq, expl = tipo_recomp(g["id"])
            if modo == "launcher" and not hay_launcher():
                return
            escribir(sal_rec, f"\n{g['nombre']}: {expl}\n")
            lanzar([sys.executable, str(JUGAR), g["id"]], sal_rec, g["nombre"])

    def modo_recomp():
        g = rec_sel()
        if not g:
            return
        if tipo_recomp(g["id"])[0] == "launcher" and not si_no(
                "Modo directo", f"{g['nombre']} se abrirá sin RecompLauncher: más ligero y, si es ARM64, con el overlay de Steam.\n\n"
                "Pero se salta su preparación (tu copia del juego, ajustes, efectos, partidas en la nube). Úsalo después de "
                "haberla jugado una vez con RecompLauncher. Se puede volver atrás con el mismo botón.\n\n¿Activar el modo directo?"):
            return
        r = cambiar_modo_recomp(g["id"])
        if r is None:
            info("Modo directo", "Solo para builds de Linux: esta es de Windows o no se sabe qué programa es.")
            return
        escribir(sal_rec, f"\n{g['nombre']}: {r[2]}\n(El acceso de Steam no cambia: decide al arrancar.)\n")
        pintar_recomps(limpiar=False)

    def steam_rec():
        g = rec_sel()
        if g:
            pedir_steam(sal_rec, acceso_recomp(g["id"]), g["nombre"], lambda c: pintar_recomps(limpiar=False))

    def revisar():
        g = rec_sel()
        if g and g["ruta"]:
            tarea(sal_rec, f"Revisar {g['nombre']}",
                  [sys.executable, str(DIR / "herramientas/revisar_binarios.py"), g["ruta"]])

    COMPARAR_PY = DIR / "herramientas/comparar_recomp.py"

    def receta_elegida():
        try:
            rs = json.loads((DIR / "datos/comparar.json").read_text(encoding="utf-8"))["recomps"]
        except (OSError, ValueError, KeyError):
            rs = []
        if not rs:
            info("Comparar", "No hay recomps configuradas en datos/comparar.json.")
            return None
        if len(rs) == 1:
            return rs[0]
        i = elegir_de("Comparar", "¿Qué recomp quieres comparar?", [r["nombre"] for r in rs])
        return rs[i] if i is not None else None

    def comparar():
        r = receta_elegida()
        if not r:
            return
        if not si_no("Comparar ARM64 nativo vs x86_64 + FEX",
                     f"Se descargarán las dos builds de Linux de {r['nombre']} (de su GitHub) a "
                     f"~/recomp/comparar/{r['id']}/ y se crearán dos accesos que miden batería, temperatura y "
                     f"CPU mientras juegas.\n\nPara jugar necesitas: {r['juego']}\n\n¿Continuar?"):
            return
        accesos = [ACCESOS / f"comparar-{r['id']}-arm64.desktop", ACCESOS / f"comparar-{r['id']}-x64.desktop"]

        def anadir(i):
            if i < len(accesos):
                nombre = f"{r['nombre']} ({'ARM64 nativo' if i == 0 else 'x86_64 + FEX'})"
                pedir_steam(sal_rec, accesos[i], nombre, lambda c: anadir(i + 1))
                if ocupado["v"] is False:          # dijo que no a esta: se pregunta por la siguiente
                    anadir(i + 1)

        def fin(codigo):
            if codigo == 0 and all(a.exists() for a in accesos):
                escribir(sal_rec, "\nJuega un rato con cada versión (mismo sitio del juego) y luego pulsa "
                                  "«Resultados comparación». Los FPS, con el indicador de rendimiento de Steam.\n")
                anadir(0)
        tarea(sal_rec, f"Preparar comparación de {r['nombre']}",
              [sys.executable, str(COMPARAR_PY), "preparar", r["id"]], fin)

    def resultados():
        r = receta_elegida()
        if r:
            escribir(sal_rec, "", limpiar=True)
            tarea(sal_rec, f"Resultados: {r['nombre']}", [sys.executable, str(COMPARAR_PY), "resumen", r["id"]])

    for texto, cmd in (("Descargar recomps", descargar_recomps),
                       ("Recargar", lambda: pintar_recomps(avisar=True)),
                       ("Comparar ARM vs FEX", comparar), ("Resultados", resultados)):
        boton(barra, texto, cmd).pack(side="left", padx=(0, 10), pady=6)
    for texto, cmd in (("Jugar", jugar), ("Añadir a Steam", steam_rec), ("Directo / Launcher", modo_recomp), ("Revisar binarios", revisar),
                       ("← Volver", lambda: mostrar("inicio"))):
        boton(acciones, texto, cmd).pack(side="left", padx=(0, 10), pady=6)
    pantallas["recomps"] = {"marco": m, "foco": lambda: rej,
                            "al_entrar": lambda: pintar_recomps(avisar=True)}

    # ================= JUEGOS DE SWITCH (nx2konkr)
    m = tk.Frame(raiz, bg=FONDO)
    cabecera(m, "Juegos de Switch")
    lb_sw = lista(m)
    lb_sw.pack(fill="both", expand=True, padx=24, pady=6)
    acciones = tk.Frame(m, bg=FONDO)
    acciones.pack(fill="x", padx=24)
    sal_sw = caja_texto(m, 8)
    sal_sw.pack(fill="x", padx=24, pady=(6, 16))
    sw_vista = []

    def pintar_switch(auto=False, limpiar=True):
        sw_vista.clear()
        sw_vista.extend(juegos_switch())
        ya = anadidos()
        lb_sw.delete(0, "end")
        for j in sw_vista:
            en = str(ACCESOS / f"{nombre_archivo('nx-' + j['carpeta'].name)}.desktop") in ya
            lb_sw.insert("end", f"{'★ ' if en else '   '}{j['nombre']}   {j['version']}" + ("" if j["completo"] else "   [incompleto: ¿se está copiando?]"))
        if sw_vista:
            lb_sw.selection_set(0)
            lb_sw.activate(0)
            escribir(sal_sw, f"{len(sw_vista)} juego(s) en {SWITCH} (★ = ya en Steam). Copia aquí la carpeta <Juego>-konkr que genera "
                             "nx2konkr en tu PC y se añade sola a Steam.\n", limpiar=limpiar)
        else:
            escribir(sal_sw, f"Aún no hay juegos. Copia a {SWITCH} la carpeta <Juego>-konkr que genera nx2konkr en tu PC: "
                             "se añadirá sola a Steam.\n", limpiar=True)
        if auto and auto_activo() and switch_pendientes() and not ocupado["v"]:
            tarea(sal_sw, "Añadir juegos nuevos a Steam (automático)", [sys.executable, str(DIR / "konkr_store.py"), "auto-steam"],
                  lambda c: pintar_switch(limpiar=False))

    def sw_sel():
        s = lb_sw.curselection()
        return sw_vista[s[0]] if s and s[0] < len(sw_vista) else None

    def jugar_switch():
        j = sw_sel()
        if j and j["completo"]:
            acceso_switch(j)                 # deja los permisos de ejecución bien
            lanzar([str(j["carpeta"] / "jugar.sh")], sal_sw, j["nombre"])
        elif j:
            info("Juegos de Switch", "Esta carpeta está incompleta: espera a que termine de copiarse.")

    def steam_switch():
        j = sw_sel()
        if j and j["completo"]:
            pedir_steam(sal_sw, acceso_switch(j), j["nombre"], lambda c: pintar_switch(limpiar=False))

    def registro_switch():
        j = sw_sel()
        if not j:
            return
        try:
            lineas = (j["carpeta"] / "log.txt").read_text(errors="replace").splitlines()[-120:]
            escribir(sal_sw, f"=== {j['carpeta'] / 'log.txt'} (últimas líneas) ===\n" + "\n".join(lineas) + "\n", limpiar=True)
        except OSError:
            escribir(sal_sw, "Aún no hay registro: el juego no se ha abierto.\n", limpiar=True)

    def partidas_switch():
        j = sw_sel()
        if j:
            d = HOME / ".local/share/nx2konkr" / j["carpeta"].name / "save"
            d.mkdir(parents=True, exist_ok=True)
            lanzar(["xdg-open", str(d)], sal_sw, f"partidas de {j['nombre']}")

    for texto, cmd in (("Jugar", jugar_switch), ("Añadir a Steam", steam_switch), ("Ver registro", registro_switch),
                       ("Partidas", partidas_switch), ("← Volver", lambda: mostrar("inicio"))):
        boton(acciones, texto, cmd).pack(side="left", padx=(0, 10), pady=6)
    pantallas["switch"] = {"marco": m, "foco": lambda: lb_sw, "al_entrar": lambda: pintar_switch(auto=True)}

    # ================= HERRAMIENTAS
    m = tk.Frame(raiz, bg=FONDO)
    cabecera(m, "Herramientas")
    rejilla = tk.Frame(m, bg=FONDO)
    rejilla.pack(fill="x", padx=24, pady=6)
    sal_h = caja_texto(m, 14)
    sal_h.pack(fill="both", expand=True, padx=24, pady=(6, 16))

    def buscar_actualizaciones():
        escribir(sal_h, "", limpiar=True)

        def fin(codigo):
            if codigo == 10 and si_no("Actualizar", "Hay una versión nueva de RecompLauncher. "
                                                    "¿Instalarla? (la actual se guarda)"):
                tarea(sal_h, "Instalar versión nueva", ["bash", str(DIR / "actualizar.sh"), "--si"])
        tarea(sal_h, "Buscar actualizaciones", ["bash", str(DIR / "instalar.sh"), "--comprobar"], fin)

    def actualizar_todo():
        if si_no("Actualizar", "¿Actualizar los scripts de Konkr Store (git pull) y "
                               "RecompLauncher si hay versión nueva?\nDespués cierra y abre la tienda."):
            tarea(sal_h, "Actualizar todo", ["bash", str(DIR / "actualizar.sh"), "--si"])

    def cambiar_version():
        vs = versiones()
        if not vs:
            info("Versiones", "No hay versiones instaladas.")
            return
        act = version_actual()
        i = elegir_de("Cambiar de versión", "● = la que se usa ahora. Las demás siguen guardadas.",
                      [("● " if v == act else "   ") + v for v in vs], vs.index(act) if act in vs else 0)
        if i is not None:
            usar_version(vs[i])
            escribir(sal_h, f"\nAhora se usa: {vs[i]}\n")

    def diagnostico():
        escribir(sal_h, "", limpiar=True)
        tarea(sal_h, "Diagnóstico (solo lectura)", ["bash", str(DIR / "diagnostico.sh")])

    def guardar_salida():
        d = RECOMP / "informes"
        d.mkdir(parents=True, exist_ok=True)
        f = d / time.strftime("konkr_store_%Y%m%d_%H%M%S.txt")
        f.write_text(sal_h.get("1.0", "end"), encoding="utf-8")
        escribir(sal_h, f"\nGuardado en {f}\n")

    def ver_registro():
        try:
            lineas = LOG_LANZ.read_text(errors="replace").splitlines()[-150:]
            escribir(sal_h, f"=== {LOG_LANZ} (últimas líneas) ===\n" + "\n".join(lineas) + "\n", limpiar=True)
        except OSError:
            escribir(sal_h, "Aún no hay registro (abre RecompLauncher una vez).\n", limpiar=True)

    def respaldo():
        if not RESPALDO.is_file():
            error("Copia de seguridad", f"No encuentro {RESPALDO}")
        elif si_no("Copia de seguridad", f"¿Ejecutar {RESPALDO}?"):
            tarea(sal_h, "Copia de seguridad de Steam", ["bash", str(RESPALDO)])

    def launcher_a_steam():
        if hay_launcher():
            pedir_steam(sal_h, acceso_launcher(), "RecompLauncher")

    botones_h = [("Buscar actualizaciones", buscar_actualizaciones), ("Actualizar todo", actualizar_todo),
                 ("Cambiar de versión", cambiar_version), ("Añadir RecompLauncher a Steam", launcher_a_steam), ("Copia de seguridad de Steam", respaldo),
                 ("Diagnóstico", diagnostico), ("Ver registro", ver_registro),
                 ("Guardar esta salida", guardar_salida), ("← Volver", lambda: mostrar("inicio"))]
    bh = []
    for i, (texto, cmd) in enumerate(botones_h):
        b = boton(rejilla, texto, cmd, ancho=26)
        b.grid(row=i // 2, column=i % 2, padx=6, pady=5, sticky="we")   # 2 columnas: caben también en una ventana de 1280 px
        bh.append(b)
    pantallas["herr"] = {"marco": m, "foco": lambda: bh[0],
                         "al_entrar": lambda: escribir(sal_h, f"RecompLauncher: {version_actual() or 'no instalado'}"
                                                              f"\nVersiones guardadas: {len(versiones())}"
                                                              f"\nModo gráfico: {modo_grafico()}"
                                                              f"\nA Steam automáticamente (apps, recomps y juegos de Switch): {'sí' if auto_activo() else 'no'}\n", limpiar=True)}

    # ================= OPCIONES: dónde se guarda, Steam automático, modo gráfico
    import almacen
    m = tk.Frame(raiz, bg=FONDO)
    cabecera(m, "Opciones")
    cuadro_o = tk.Frame(m, bg=FONDO)
    cuadro_o.pack(fill="x", padx=24, pady=6)
    sal_o = caja_texto(m, 12)
    sal_o.pack(fill="both", expand=True, padx=24, pady=(6, 16))

    def corto(p):
        p = str(p); h = str(HOME)
        return "~" + p[len(h):] if p == h or p.startswith(h + "/") else p

    def elegir_carpeta(titulo, texto, inicio):
        """Explorador de carpetas manejable con el mando: devuelve la carpeta elegida o None."""
        cur = almacen._ancestro(Path(inicio))
        while True:
            try:
                subs = sorted((d for d in cur.iterdir() if d.is_dir() and not d.name.startswith(".")), key=lambda d: d.name.lower())[:80]
            except OSError:
                subs = []
            discos = [("⌂  Memoria interna (tu carpeta personal)", HOME)] + [("▣  " + d[1], Path(d[0])) for d in almacen.destinos() if d[0] != "interna"]
            ops = [f"✔  Elegir esta carpeta:  {corto(cur)}", "↑  Subir", "+  Nueva carpeta aquí…"] + [d[0] for d in discos] + ["▸  " + d.name for d in subs]
            i = elegir_de(titulo, texto + f"\n\nAhora en: {cur}", ops)
            if i is None:
                return None
            if i == 0:
                return cur
            if i == 1:
                cur = cur.parent if cur != cur.parent else cur
            elif i == 2:
                n = capa_modal("Nueva carpeta", f"Nombre de la nueva carpeta dentro de {cur} (teclado en pantalla: Steam + X):",
                               [("Crear", "__ok__"), ("Cancelar", None)], entrada=True)
                if n and "/" not in n:
                    try:
                        (cur / n).mkdir(exist_ok=True); cur = cur / n
                    except OSError as e:
                        info("Nueva carpeta", f"No se pudo crear: {e}")
            elif i < 3 + len(discos):
                cur = discos[i - 3][1]
            else:
                cur = subs[i - 3 - len(discos)]

    def cambiar_instalaciones():
        act = almacen.raiz_de(almacen.actual())
        p = elegir_carpeta("Carpeta de instalaciones", "Dónde van RecompLauncher, las recomps, los juegos de Switch, los programas "
                           "instalados desde archivo y Claude Code. Si eliges la raíz de una tarjeta, se usa <tarjeta>/KonkrStore. "
                           "Tiene que ser un disco ext4 (como formatea Steam las SD).", act if act != HOME else HOME)
        if p is None:
            return
        raiz_n = almacen.raiz_de("interna" if Path(p) == HOME else str(p))
        if raiz_n == act:
            info("Carpeta de instalaciones", "Ya es esa."); return
        ok, motivo = almacen.sirve_para_instalar(raiz_n)
        if not ok:
            info("Carpeta de instalaciones", f"Esa no sirve para instalar: {motivo}"); return
        total = sum(t for _n, _p, _d, e, t in almacen.estado() if e)
        if not si_no("Carpeta de instalaciones", f"Las instalaciones irán a:\n{raiz_n}\n\nLo que ya hay ({total / 2**30:.1f} GB) se moverá allí. "
                     "En tu carpeta quedan enlaces con los nombres de siempre (los accesos de Steam siguen igual).\n\n"
                     "Cierra antes RecompLauncher y los juegos. ¿Continuar?"):
            return
        escribir(sal_o, "", limpiar=True)
        tarea(sal_o, f"Mover las instalaciones a {raiz_n}",
              [sys.executable, str(DIR / "herramientas/almacen.py"), "usar", "interna" if Path(p) == HOME else str(p), "--si"], lambda c: pintar_opciones(False))

    def cambiar_descargas():
        p = elegir_carpeta("Carpeta de descargas", "Dónde se guardan los archivos que se descargan (RecompLauncher, comparaciones…) y el primer "
                           "sitio donde «Instalar archivo…» busca. Vale cualquier disco, también una tarjeta o memoria USB en exFAT.",
                           almacen.descargas())
        if p is None:
            return
        out = []
        almacen.poner_descargas(p, out.append)
        escribir(sal_o, "\n" + "\n".join(out) + "\n(Las descargas anteriores se quedan donde estaban.)\n")
        pintar_opciones(False)

    def cambiar_auto_o():
        poner_auto(not auto_activo()); pintar_opciones(False)

    def cambiar_graficos_o():
        poner_modo_grafico("normal" if modo_grafico() == "seguro" else "seguro"); pintar_opciones(False)

    bo = {}
    for clave, cmd in (("inst", cambiar_instalaciones), ("desc", cambiar_descargas), ("auto", cambiar_auto_o), ("graf", cambiar_graficos_o),
                       ("volver", lambda: mostrar("inicio"))):
        b = boton(cuadro_o, "", cmd)
        b.configure(anchor="w", justify="left")
        b.pack(fill="x", pady=4)
        bo[clave] = b

    def pintar_opciones(limpiar=True):
        rotas = almacen.comprobar()
        inst = almacen.raiz_de(almacen.actual())
        bo["inst"].configure(text=f"Carpeta de instalaciones:   {corto(inst)}" + ("   (⚠ no está montada)" if rotas else ""))
        bo["desc"].configure(text=f"Carpeta de descargas:   {corto(almacen.descargas())}")
        bo["auto"].configure(text=f"Añadir a Steam automáticamente (apps, recomps, juegos de Switch):   {'sí' if auto_activo() else 'no'}")
        bo["graf"].configure(text=f"Modo gráfico de RecompLauncher:   {modo_grafico()}   (seguro: si su ventana sale en negro)")
        bo["volver"].configure(text="← Volver")
        if limpiar:
            escribir(sal_o, "Elige una opción con las flechas e Intro.\n\nInstalaciones: van a la carpeta elegida; en tu carpeta personal quedan "
                            "enlaces con los nombres de siempre (~/juegos-switch, ~/Applications/...), así los accesos de Steam no cambian.\n"
                            "Descargas: solo archivos, así que vale cualquier disco.\n", limpiar=True)
        if rotas:
            escribir(sal_o, "\n⚠ La carpeta de instalaciones está en un disco que no está montado: inserta la tarjeta.\n")
    pantallas["opciones"] = {"marco": m, "foco": lambda: bo["inst"], "al_entrar": pintar_opciones}

    mostrar("inicio")
    raiz.mainloop()


# =================================================================== modo terminal
def cli(argv):
    cmd = argv[0]
    if cmd == "estado":
        print(f"RecompLauncher: {version_actual() or 'no instalado'}")
        print(f"Versiones: {', '.join(versiones()) or '-'}")
        print(f"Traductor x86_64: {fex() or 'no encontrado'}")
        print(f"Flatpak: {flatpak() or 'no'}")
        print(f"Modo gráfico: {modo_grafico()}")
        print(f"Recomps: {len(recomps())}")
    elif cmd == "versiones":
        act = version_actual()
        for v in versiones():
            print(("* " if v == act else "  ") + v)
    elif cmd == "usar" and len(argv) == 2:
        usar_version(argv[1])
        print(f"Ahora se usa: {argv[1]}")
    elif cmd == "graficos" and len(argv) == 2:
        poner_modo_grafico(argv[1])
        print(f"Modo gráfico: {argv[1]}")
    elif cmd == "recomps":
        for g in recomps():
            modo, etq, expl = tipo_recomp(g["id"])
            print(f"{g['id']}\t{g['nombre']}\t{g['version']}\t[{etq}]\t{expl}")
    elif cmd == "acceso-recomp" and len(argv) == 2:
        print(acceso_recomp(argv[1]))
    elif cmd == "acceso-app" and len(argv) == 2:
        print(acceso_app(argv[1]))
    elif cmd == "acceso-launcher":
        print(acceso_launcher())
    elif cmd == "switch":
        ya = anadidos()
        for j in juegos_switch():
            en = str(ACCESOS / f"{nombre_archivo('nx-' + j['carpeta'].name)}.desktop") in ya
            print(f"{'★' if en else ' '} {j['nombre']}\t{j['id']}\t{j['version']}\t{'completo' if j['completo'] else 'INCOMPLETO'}\t{j['carpeta']}")
    elif cmd == "auto-steam":
        if not auto_activo() and "--forzar" not in argv:
            print("Añadir recomps a Steam automáticamente está desactivado (Herramientas).")
            return 0
        print(time.strftime("== %Y-%m-%d %H:%M:%S auto-steam"), flush=True)
        if "--esperar" in argv and not esperar_copias(lambda m: print(m, flush=True)):
            print("La copia no terminó en 2 horas: se intentará la próxima vez.")
            return 0
        return auto_steam(lambda m: print(m, flush=True))
    else:
        print(__doc__)
        return 1
    return 0


def main(argv):
    if argv:
        try:
            return cli(argv)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
    try:
        interfaz()
    except ImportError:
        print("Falta Tkinter: no puedo abrir la ventana. Usa: konkr_store.py estado", file=sys.stderr)
        return 1
    except Exception as e:   # sin pantalla, etc.
        if "display" in str(e).lower():
            print(f"No hay pantalla disponible ({e}).", file=sys.stderr)
            return 1
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
