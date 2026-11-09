#!/usr/bin/env bash
# Lanza RecompLauncher (x86_64) con FEX en la KONKR Pocket FIT (SteamOS ARM).
# - No usa sudo, no toca Steam; solo escribe en ~/recomp/logs y ~/recomp/ajustes.
# - Sin argumentos y abierto desde Steam/Modo Juego, arranca en Big Picture.
#
# Variables opcionales (ponlas delante en las opciones de lanzamiento de Steam):
#   RECOMP_GRAFICOS=seguro   desactiva también el compositing de WebKit (si ves pantalla negra)
#   RECOMP_GRAFICOS=normal   ignora el modo seguro recordado (~/recomp/ajustes/graficos)
#   RECOMP_ESCALA=2          escala la interfaz GTK x2
#   RECOMP_ESCRITORIO=1      no fuerza Big Picture
# Al cerrarse, añade a Steam las recomps nuevas (konkr_store.py auto-steam; ~/recomp/logs/auto_steam.log).
set -u

# Steam mete en LD_PRELOAD/LD_LIBRARY_PATH librerías ARM64 (overlay, runtime) que un programa
# x86_64 no puede cargar: se quitan solo para RecompLauncher.
unset LD_PRELOAD LD_LIBRARY_PATH


TIENDA="$(dirname "$(readlink -f "$0")")/konkr_store.py"   # antes de cualquier cd: $0 puede ser relativo
BASE="${RECOMP_BASE:-$HOME/Applications/RecompLauncher}"
APPDIR="$BASE/actual"
LOGDIR="$HOME/recomp/logs"
LOG="$LOGDIR/lanzar_recomp.log"
mkdir -p "$LOGDIR"
[ -f "$LOG" ] && mv -f "$LOG" "$LOG.anterior"

aviso() {
    echo "$1" >&2
    echo "$(date '+%F %T') ERROR: $1" >>"$LOG"
    if command -v zenity >/dev/null 2>&1; then
        zenity --error --title="RecompLauncher" --text="$1" --width=500 2>/dev/null
    fi
}

# Si en Steam se pegó «ruta/lanzar_recomp.sh %command%», Steam nos pasa nuestra propia ruta: se quita.
args=()
for a in "$@"; do
    case "$a" in
        "$0"|*/lanzar_recomp.sh) ;;
        *) args+=("$a") ;;
    esac
done

desde_steam=0
if [ -n "${SteamGameId:-}${SteamAppId:-}${SteamClientLaunch:-}" ] || [ "${XDG_CURRENT_DESKTOP:-}" = "gamescope" ] || [ -n "${GAMESCOPE_WAYLAND_DISPLAY:-}" ]; then
    desde_steam=1
fi
if [ "${#args[@]}" -eq 0 ] && [ "$desde_steam" = 1 ] && [ -z "${RECOMP_ESCRITORIO:-}" ]; then
    args=(--bigpicture)
fi

# Traductores x86_64 posibles, por orden: FEX (en el PATH o en cualquier sitio de /usr, /opt, ~/.local), luego lo que
# detecta x86.sh (Box64, binfmt). Se prueban uno tras otro hasta que RecompLauncher arranca. KONKR_X86=<ruta|directo> fuerza uno.
cands=()
agregar() { local c; for c in "${cands[@]:-}"; do [ "$c" = "$1" ] && return; done; cands+=("$1"); }
if [ -n "${KONKR_X86:-}" ]; then
    agregar "$KONKR_X86"
else
    for c in FEXInterpreter FEXLoader; do p="$(command -v "$c" 2>/dev/null)" && agregar "$p"; done
    while IFS= read -r p; do [ -n "$p" ] && agregar "$p"; done < <(find /usr /opt "$HOME/.local" "$HOME/.fex-emu" -maxdepth 6 -type f \( -name FEXInterpreter -o -name FEXLoader \) 2>/dev/null)
    p="$(sh "$(dirname "$TIENDA")/herramientas/x86.sh" || true)"
    [ -n "$p" ] && agregar "$p"
fi
if [ "${#cands[@]}" -eq 0 ]; then
    aviso "No encuentro cómo ejecutar programas x86_64 (ni FEX ni Box64). Ejecuta diagnostico.sh y pásame la salida."
    exit 1
fi
if [ -L "$BASE" ] && [ ! -e "$BASE" ]; then
    aviso "RecompLauncher está en la tarjeta SD ($(readlink "$BASE")) y no está montada. Inserta la SD y vuelve a intentarlo."
    exit 1
fi
if [ ! -e "$APPDIR/AppRun" ]; then
    aviso "No encuentro $APPDIR/AppRun. Ejecuta primero instalar.sh."
    exit 1
fi

# Modo gráfico: RECOMP_GRAFICOS (seguro|normal) manda; si no, lo que se recordó en ~/recomp/ajustes/graficos.
PREF="$HOME/recomp/ajustes/graficos"
modo="${RECOMP_GRAFICOS:-}"
[ -z "$modo" ] && [ -f "$PREF" ] && modo="$(head -c 20 "$PREF" | tr -dc 'a-z')"
[ -z "$modo" ] && modo="normal"

# WebKitGTK: el renderizador DMA-BUF suele dejar la ventana en negro bajo FEX/gamescope.
export WEBKIT_DISABLE_DMABUF_RENDERER=1
# En el Modo Juego (gamescope) GTK funciona mejor por X11 (Xwayland de gamescope).
if [ "$desde_steam" = 1 ] && [ -n "${DISPLAY:-}" ]; then
    export GDK_BACKEND=x11
fi
export GDK_SCALE="${RECOMP_ESCALA:-1}"
# Box64: el AppImage trae sus GLib, libselinux, etc. y Box64 por defecto usaría las del sistema (más antiguas o ausentes en SteamOS ARM).
# Se prueban varias combinaciones hasta que una arranque (variante 1, 2, 3); FEX ignora estas variables.
STUB="$(dirname "$TIENDA")/herramientas/stubs/sdjournal_stub_x86_64.so"
RT="$(ls -d /run/media/*/*/SteamLibrary/steamapps/common/SteamLinuxRuntime_4/steamrt4_platform_*/files/lib/x86_64-linux-gnu "$HOME"/.local/share/Steam/steamapps/common/SteamLinuxRuntime_4/steamrt4_platform_*/files/lib/x86_64-linux-gnu 2>/dev/null | head -1)"
entorno_box64() {   # $1 = variante
    unset BOX64_LD_LIBRARY_PATH BOX64_EMULATED_LIBS BOX64_LD_PRELOAD
    [ -d "$APPDIR/usr/lib" ] || return 0
    local libs="" l
    case "$1" in
        3) return 0 ;;   # Box64 sin ajustes
        2) export BOX64_LD_LIBRARY_PATH="$APPDIR/usr/lib${RT:+:$RT}"
           libs="libglib-2.0.so.0:libgobject-2.0.so.0:libgio-2.0.so.0:libgmodule-2.0.so.0"
           for l in libselinux.so.1 libmount.so.1 libblkid.so.1 libdbus-1.so.3 libsystemd.so.0 libcap.so.2 libgcrypt.so.20 libgpg-error.so.0 liblzma.so.5 liblz4.so.1 libzstd.so.1; do
               if [ -e "$APPDIR/usr/lib/$l" ] || { [ -n "$RT" ] && [ -e "$RT/$l" ]; }; then libs="$libs:$l"; fi
           done ;;
        *) export BOX64_LD_LIBRARY_PATH="$APPDIR/usr/lib"
           libs="libglib-2.0.so.0:libgobject-2.0.so.0:libgio-2.0.so.0:libgmodule-2.0.so.0"
           for l in libselinux.so.1 libmount.so.1 libblkid.so.1; do [ -e "$APPDIR/usr/lib/$l" ] && libs="$libs:$l"; done ;;
    esac
    export BOX64_EMULATED_LIBS="${libs}"
    [ -f "$STUB" ] && export BOX64_LD_PRELOAD="$STUB"
    return 0
}
cd "$HOME" || exit 1

lanzar() {   # $1 = modo gráfico. Devuelve el código de salida; deja la duración en $dura.
    if [ "$1" = "seguro" ]; then export WEBKIT_DISABLE_COMPOSITING_MODE=1; else unset WEBKIT_DISABLE_COMPOSITING_MODE; fi
    {
        echo "$(date '+%F %T') Lanzando (gráficos: $1, x86: $X86): $APPDIR/AppRun ${args[*]:-}"
        echo "  real: $(readlink -f "$APPDIR")  desde_steam=$desde_steam  DISPLAY=${DISPLAY:-}  WAYLAND=${WAYLAND_DISPLAY:-}"
    } >>"$LOG"
    local inicio=$SECONDS codigo
    # AppRun suele ser un script: se ejecuta tal cual y el programa x86_64 que lanza lo traduce el kernel (binfmt) o FEX.
    # Si es un ELF x86_64, va con el traductor delante (salvo binfmt, que lo hace solo)
    if [ "$X86" = directo ] || [ "$(head -c 2 "$APPDIR/AppRun")" = '#!' ]; then
        "$APPDIR/AppRun" "${args[@]}" >>"$LOG" 2>&1
    else
        "$X86" "$APPDIR/AppRun" "${args[@]}" >>"$LOG" 2>&1
    fi
    codigo=$?
    dura=$((SECONDS - inicio))
    echo "$(date '+%F %T') Terminó: código $codigo tras ${dura}s" >>"$LOG"
    return $codigo
}

dura=0; codigo=1
pares=()
for c in "${cands[@]}"; do
    case "$(basename "$c")" in
        box64|directo) pares+=("$c|1" "$c|2" "$c|3") ;;
        *) pares+=("$c|1") ;;
    esac
done
for par in "${pares[@]}"; do
    X86="${par%|*}"; variante="${par##*|}"
    entorno_box64 "$variante"
    echo "$(date '+%F %T') Variante $variante: BOX64_EMULATED_LIBS=${BOX64_EMULATED_LIBS:-}" >>"$LOG"
    dura=0
    lanzar "$modo"
    codigo=$?
    # Si se cierra con error en menos de 20 s y no estaba ya en modo seguro, reintenta una vez en modo seguro.
    if [ "$codigo" != 0 ] && [ "$dura" -lt 20 ] && [ "$modo" != "seguro" ] && [ -z "${RECOMP_GRAFICOS:-}" ]; then
        echo "$(date '+%F %T') Cierre rápido con error: reintento en modo gráfico seguro" >>"$LOG"
        lanzar seguro
        codigo=$?
        if [ "$codigo" = 0 ] || [ "$dura" -ge 20 ]; then
            mkdir -p "$(dirname "$PREF")"
            echo seguro >"$PREF"
            echo "$(date '+%F %T') El modo seguro funcionó: se recuerda en $PREF" >>"$LOG"
        fi
    fi
    { [ "$codigo" = 0 ] || [ "$dura" -ge 20 ]; } && break
    echo "$(date '+%F %T') $X86 (variante $variante) no arranca RecompLauncher: pruebo la siguiente" >>"$LOG"
done
if [ "$codigo" != 0 ] && [ "$dura" -lt 20 ]; then
    # Todo falló: una pasada más con trazas de Box64 (variante 2) para saber qué librería no carga. Resumen en depuracion_box64.log
    DEP="$LOGDIR/depuracion_box64.log"
    entorno_box64 2
    {
        echo "== Box64 con trazas (variante 2), $(date '+%F %T')"
        echo "BOX64_LD_LIBRARY_PATH=${BOX64_LD_LIBRARY_PATH:-}"; echo "BOX64_EMULATED_LIBS=${BOX64_EMULATED_LIBS:-}"; echo "RT=${RT:-}"
        BOX64_LOG=1 BOX64_DLSYM_ERROR=1 "${cands[0]}" "$APPDIR/usr/bin/recomplauncher" >"$LOGDIR/box64_completo.log" 2>&1
        echo "-- líneas sobre dbus, systemd y sus dependencias, y todos los errores:"
        grep -v JUMP_SLOT "$LOGDIR/box64_completo.log" | grep -n -i -E "dbus|systemd|libcap|gcrypt|gpg-error|lzma|lz4|zstd|Error|cannot|not found|undefined|failed" | cut -c1-240 | head -40
    } >"$DEP" 2>&1
    aviso_extra="Detalle técnico guardado en $DEP"
    echo "$aviso_extra" >>"$LOG"
fi
if [ "$codigo" != 0 ] && [ "$dura" -lt 20 ]; then
    aviso "RecompLauncher se cerró al arrancar (código $codigo). Mira el registro: $LOG y $LOGDIR/depuracion_box64.log"
fi
# Recomps instaladas en esta sesión: a Steam automáticamente (Konkr Store > Herramientas lo activa o desactiva), con copia de
# seguridad antes y pidiéndoselo a Steam. En segundo plano y separado de Steam, para no retrasar ni depender de esta ventana
if [ -f "$TIENDA" ] && [ "$(cat "$HOME/recomp/ajustes/auto_steam" 2>/dev/null)" != "no" ]; then
    setsid python3 "$TIENDA" auto-steam >>"$LOGDIR/auto_steam.log" 2>&1 </dev/null &
fi
exit "$codigo"
