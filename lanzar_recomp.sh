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
set -u

# Steam mete en LD_PRELOAD/LD_LIBRARY_PATH librerías ARM64 (overlay, runtime) que un programa
# x86_64 no puede cargar: se quitan solo para RecompLauncher.
unset LD_PRELOAD LD_LIBRARY_PATH


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

FEX="$(command -v FEXInterpreter || command -v FEXLoader || true)"
if [ -z "$FEX" ]; then
    aviso "No encuentro FEXInterpreter. Comprueba la instalación de FEX (ejecuta diagnostico.sh)."
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
cd "$HOME" || exit 1

lanzar() {   # $1 = modo gráfico. Devuelve el código de salida; deja la duración en $dura.
    if [ "$1" = "seguro" ]; then export WEBKIT_DISABLE_COMPOSITING_MODE=1; else unset WEBKIT_DISABLE_COMPOSITING_MODE; fi
    {
        echo "$(date '+%F %T') Lanzando (gráficos: $1): $FEX $APPDIR/AppRun ${args[*]:-}"
        echo "  real: $(readlink -f "$APPDIR")  desde_steam=$desde_steam  DISPLAY=${DISPLAY:-}  WAYLAND=${WAYLAND_DISPLAY:-}"
    } >>"$LOG"
    local inicio=$SECONDS codigo
    "$FEX" "$APPDIR/AppRun" "${args[@]}" >>"$LOG" 2>&1
    codigo=$?
    dura=$((SECONDS - inicio))
    echo "$(date '+%F %T') Terminó: código $codigo tras ${dura}s" >>"$LOG"
    return $codigo
}

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
if [ "$codigo" != 0 ] && [ "$dura" -lt 20 ]; then
    aviso "RecompLauncher se cerró al arrancar (código $codigo). Mira el registro: $LOG"
fi
exit "$codigo"
