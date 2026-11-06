#!/usr/bin/env bash
# Pide a Steam que añada un «juego que no es de Steam». Steam escribe el acceso ÉL MISMO
# (como «Add to Steam» de Discover o steamos-add-to-steam): este script NO toca shortcuts.vdf.
#
#   anadir_a_steam.sh ARCHIVO.desktop|ARCHIVO.sh [--sin-respaldo]
#
# Antes ejecuta tu copia de seguridad (~/iw6x-steamos/tools/respaldo_steam.sh). Si no existe, se para
# (salvo con --sin-respaldo). Steam tiene que estar abierto.
# Salida: 0 pedido a Steam · 2 archivo no válido · 3 Steam no está abierto · 4 falló la copia · 5 no hay copia
set -u
RESPALDO="${KONKR_RESPALDO:-$HOME/iw6x-steamos/tools/respaldo_steam.sh}"
REGISTRO="$HOME/recomp/accesos/anadidos.txt"

f="${1:-}"
sin_respaldo=0
[ "${2:-}" = "--sin-respaldo" ] && sin_respaldo=1
[ -n "$f" ] || { echo "Uso: $0 ARCHIVO.desktop|ARCHIVO.sh [--sin-respaldo]"; exit 2; }
f="$(readlink -f "$f")"
[ -f "$f" ] || { echo "No existe: $f"; exit 2; }
case "$f" in
    "$HOME"/.local/share/Steam/*|"$HOME"/.steam/*) echo "No añado archivos de dentro de Steam."; exit 2 ;;
    "$HOME"/*) ;;
    *) echo "Solo añado archivos de tu carpeta de usuario."; exit 2 ;;
esac
case "$f" in
    *.desktop|*.sh) ;;
    *) echo "Solo .desktop o .sh"; exit 2 ;;
esac

if ! pgrep -x steam >/dev/null 2>&1 && ! pgrep -x steamwebhelper >/dev/null 2>&1; then
    echo "Steam no está abierto: ábrelo y vuelve a intentarlo."; exit 3
fi

if [ -f "$RESPALDO" ]; then
    echo "Copia de seguridad de Steam: $RESPALDO"
    bash "$RESPALDO" || { echo "La copia de seguridad falló: no sigo."; exit 4; }
elif [ "$sin_respaldo" = 0 ]; then
    echo "No encuentro $RESPALDO. No añado nada sin copia de seguridad (usa --sin-respaldo si aun así quieres)."
    exit 5
fi

if command -v steamos-add-to-steam >/dev/null 2>&1; then
    echo "Usando steamos-add-to-steam"
    steamos-add-to-steam "$f"
else
    # Lo mismo que hace steamos-add-to-steam: marca en /tmp que la petición es local y abre el enlace.
    url="steam://addnonsteamgame/$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$f")"
    touch /tmp/addnonsteamgamefile
    echo "Pidiendo a Steam: $url"
    if command -v steam >/dev/null 2>&1; then
        setsid steam "$url" >/dev/null 2>&1 </dev/null &
    else
        setsid xdg-open "$url" >/dev/null 2>&1 </dev/null &
    fi
fi
mkdir -p "$(dirname "$REGISTRO")"
grep -qxF "$f" "$REGISTRO" 2>/dev/null || echo "$f" >>"$REGISTRO"
echo "Hecho. Si en unos segundos no aparece en tu biblioteca de Steam, añádelo a mano:"
echo "  Steam > Añadir un juego que no es de Steam > Explorar > $f"
