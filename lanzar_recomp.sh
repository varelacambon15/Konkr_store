#!/usr/bin/env bash
# Lanza RecompLauncher (x86_64) con FEX en la KONKR Pocket FIT (SteamOS ARM).
# - No usa sudo, no toca Steam, solo escribe su registro en ~/recomp/logs.
# - Sin argumentos y abierto desde Steam/Modo Juego, arranca en Big Picture.
#
# Variables opcionales (ponlas delante en las opciones de lanzamiento de Steam):
#   RECOMP_GRAFICOS=seguro   desactiva también el compositing de WebKit (si ves pantalla negra)
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

# WebKitGTK: el renderizador DMA-BUF suele dejar la ventana en negro bajo FEX/gamescope.
export WEBKIT_DISABLE_DMABUF_RENDERER=1
if [ "${RECOMP_GRAFICOS:-}" = "seguro" ]; then
    export WEBKIT_DISABLE_COMPOSITING_MODE=1
fi
# En el Modo Juego (gamescope) GTK funciona mejor por X11 (Xwayland de gamescope).
if [ "$desde_steam" = 1 ] && [ -n "${DISPLAY:-}" ]; then
    export GDK_BACKEND=x11
fi
export GDK_SCALE="${RECOMP_ESCALA:-1}"

{
    echo "$(date '+%F %T') Lanzando: $FEX $APPDIR/AppRun ${args[*]:-}"
    echo "  real: $(readlink -f "$APPDIR")  desde_steam=$desde_steam  DISPLAY=${DISPLAY:-}  WAYLAND=${WAYLAND_DISPLAY:-}"
} >>"$LOG"

cd "$HOME" || exit 1
exec "$FEX" "$APPDIR/AppRun" "${args[@]}" >>"$LOG" 2>&1
