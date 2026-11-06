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
    return shutil.which("FEXInterpreter") or shutil.which("FEXLoader") or ""


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


def anadidos():
    try:
        return set((ACCESOS / "anadidos.txt").read_text().split("\n")) - {""}
    except OSError:
        return set()


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
    return escribir_desktop(f"recomp-{gid}", g["nombre"], f'"{LANZADOR}" --play {gid}')


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
    FONDO, PANEL, TEXTO, ACENTO, FOCO = "#0e141b", "#1b2838", "#e8eef4", "#66c0f4", "#2a475e"

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
                en_ventana(lambda: escribir(salida, f"Error: {e}\n"))

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
                           ("Herramientas\n\nActualizar, versiones,\ndiagnóstico…", "herr")):
        t = boton(fila, texto, lambda d=destino: mostrar(d), ancho=18, alto=6)
        t.configure(font=("sans", 20, "bold"))
        t.pack(side="left", padx=18, pady=18)
        tiles.append(t)
    tk.Label(m, text="Flechas: moverse · Intro: elegir · Esc: volver/salir · Teclado en pantalla: Steam + X",
             font=("sans", 13), bg=FONDO, fg="#8f98a0").pack(side="bottom", pady=12)

    def entrar_inicio():
        v = version_actual() or "no instalado"
        estado_lbl.configure(text=f"RecompLauncher: {v}   ·   FEX: {'sí' if fex() else 'NO encontrado'}   ·   "
                                  f"Flatpak: {'sí' if flatpak() else 'no'}   ·   Recomps: {len(recomps())}")
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
            marca = "✔ " if a["id"] in inst else "   "
            lb_apps.insert("end", f"{marca}{a['nombre']}")
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

    def ver_instaladas():
        if sin_flatpak():
            return
        inst = apps_instaladas()
        pintar_apps([{"id": i, "nombre": v[0], "desc": f"Versión {v[1]}", "categoria": f"Instalación: {v[2]}"}
                     for i, v in sorted(inst.items(), key=lambda x: x[1][0].lower())], "Instaladas")

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
                              lambda cod: cod == 0 and (ver_detalle(), refrescar_marcas(),
                                                         pedir_steam(sal_apps, acceso_app(a["id"], a["nombre"]), a["nombre"])))
                en_ventana(seguir)
            threading.Thread(target=comprobar, daemon=True).start()
        asegurar_flathub(paso2)

    def refrescar_marcas():
        inst = apps_instaladas()
        for i, a in enumerate(apps_vista):
            lb_apps.delete(i)
            lb_apps.insert(i, ("✔ " if a["id"] in inst else "   ") + a["nombre"])

    def abrir_app():
        a = app_sel()
        if a and a["id"] in apps_instaladas():
            lanzar(["flatpak", "run", a["id"]], sal_apps, a["nombre"])
        elif a:
            info("Abrir", "Primero instálala.")

    def steam_app():
        a = app_sel()
        if a and a["id"] in apps_instaladas():
            pedir_steam(sal_apps, acceso_app(a["id"], a["nombre"]), a["nombre"])
        elif a:
            info("Añadir a Steam", "Primero instálala.")

    def desinstalar():
        a = app_sel()
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
                       ("Actualizar todas", actualizar_todas)):
        boton(barra, texto, cmd).pack(side="left", padx=(0, 10), pady=6)
    for texto, cmd in (("Instalar", instalar), ("Abrir", abrir_app), ("Añadir a Steam", steam_app),
                       ("Desinstalar", desinstalar), ("← Volver", lambda: mostrar("inicio"))):
        boton(acciones, texto, cmd).pack(side="left", padx=(0, 10), pady=6)
    pantallas["apps"] = {"marco": m, "foco": lambda: lb_apps,
                         "al_entrar": lambda: (not apps_vista) and ver_destacadas()}

    # ================= RECOMPILACIONES
    m = tk.Frame(raiz, bg=FONDO)
    cabecera(m, "Recompilaciones")
    barra = tk.Frame(m, bg=FONDO)
    barra.pack(fill="x", padx=24)
    lb_rec = lista(m)
    lb_rec.pack(fill="both", expand=True, padx=24, pady=6)
    acciones = tk.Frame(m, bg=FONDO)
    acciones.pack(fill="x", padx=24)
    sal_rec = caja_texto(m, 8)
    sal_rec.pack(fill="x", padx=24, pady=(6, 16))
    rec_vista = []
    ya_avisadas = set()

    def pintar_recomps(avisar=False, limpiar=True):
        rec_vista.clear()
        rec_vista.extend(recomps())
        ya = anadidos()
        lb_rec.delete(0, "end")
        for g in rec_vista:
            en_steam = str(ACCESOS / f"{nombre_archivo('recomp-' + g['id'])}.desktop") in ya
            lb_rec.insert("end", f"{'★ ' if en_steam else '   '}{g['nombre']}   {g['version']}")
        if rec_vista:
            lb_rec.selection_set(0)
            lb_rec.activate(0)
            escribir(sal_rec, f"{len(rec_vista)} recomps instaladas (★ = ya pedida a Steam)\n", limpiar=limpiar)
        else:
            escribir(sal_rec, "Aún no hay recomps. Pulsa «Descargar recomps» para abrir RecompLauncher.\n"
                              f"(Se leen de {LIBRERIA})\n", limpiar=True)
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
        s = lb_rec.curselection()
        return rec_vista[s[0]] if s and s[0] < len(rec_vista) else None

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
        if g and hay_launcher():
            lanzar([str(LANZADOR), "--play", g["id"]], sal_rec, g["nombre"])

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
    for texto, cmd in (("Jugar", jugar), ("Añadir a Steam", steam_rec), ("Revisar binarios", revisar),
                       ("← Volver", lambda: mostrar("inicio"))):
        boton(acciones, texto, cmd).pack(side="left", padx=(0, 10), pady=6)
    pantallas["recomps"] = {"marco": m, "foco": lambda: lb_rec,
                            "al_entrar": lambda: pintar_recomps(avisar=True)}

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

    def cambiar_graficos():
        nuevo = "normal" if modo_grafico() == "seguro" else "seguro"
        poner_modo_grafico(nuevo)
        escribir(sal_h, f"\nModo gráfico de RecompLauncher: {nuevo}\n"
                        "(seguro = sin compositing de WebKit; úsalo si ves la ventana en negro)\n")

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
                 ("Cambiar de versión", cambiar_version), ("Modo gráfico: cambiar", cambiar_graficos),
                 ("Añadir RecompLauncher a Steam", launcher_a_steam), ("Copia de seguridad de Steam", respaldo),
                 ("Diagnóstico", diagnostico), ("Ver registro", ver_registro),
                 ("Guardar esta salida", guardar_salida), ("← Volver", lambda: mostrar("inicio"))]
    bh = []
    for i, (texto, cmd) in enumerate(botones_h):
        b = boton(rejilla, texto, cmd, ancho=26)
        b.grid(row=i // 3, column=i % 3, padx=6, pady=6, sticky="we")
        bh.append(b)
    pantallas["herr"] = {"marco": m, "foco": lambda: bh[0],
                         "al_entrar": lambda: escribir(sal_h, f"RecompLauncher: {version_actual() or 'no instalado'}"
                                                              f"\nVersiones guardadas: {len(versiones())}"
                                                              f"\nModo gráfico: {modo_grafico()}\n", limpiar=True)}

    mostrar("inicio")
    raiz.mainloop()


# =================================================================== modo terminal
def cli(argv):
    cmd = argv[0]
    if cmd == "estado":
        print(f"RecompLauncher: {version_actual() or 'no instalado'}")
        print(f"Versiones: {', '.join(versiones()) or '-'}")
        print(f"FEX: {fex() or 'no encontrado'}")
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
            print(f"{g['id']}\t{g['nombre']}\t{g['version']}\t{g['ruta']}")
    elif cmd == "acceso-recomp" and len(argv) == 2:
        print(acceso_recomp(argv[1]))
    elif cmd == "acceso-app" and len(argv) == 2:
        print(acceso_app(argv[1]))
    elif cmd == "acceso-launcher":
        print(acceso_launcher())
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
