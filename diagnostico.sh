#!/usr/bin/env bash
# Diagnóstico de SOLO LECTURA para RecompLauncher en la KONKR Pocket FIT.
# No escribe ningún archivo: solo imprime. Para guardarlo:  ./diagnostico.sh > ~/diagnostico.txt
set -u
DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
PY="$DIR/herramientas/revisar_binarios.py"
t() { printf '\n===== %s =====\n' "$1"; }

t "Sistema"
uname -a
grep -E '^(NAME|VERSION_ID|BUILD_ID)=' /etc/os-release 2>/dev/null
echo "Usuario: $(id -un)   HOME: $HOME"
echo "Escritorio: ${XDG_CURRENT_DESKTOP:-?}   DISPLAY=${DISPLAY:-}   WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-}"
df -h "$HOME" | tail -1

t "Traductor x86_64 (Box64 / FEX / binfmt)"
echo "Elegido por la tienda: $(sh "$DIR/herramientas/x86.sh" 2>/dev/null || echo '-- ninguno --')"
for b in box64 FEXInterpreter FEXLoader FEXBash unsquashfs; do
    printf '%-18s %s\n' "$b" "$(command -v "$b" || echo '-- no encontrado --')"
done
command -v box64 >/dev/null && box64 --version 2>/dev/null | head -1
command -v FEXInterpreter >/dev/null && FEXInterpreter --version 2>/dev/null | head -1
command -v FEXBash >/dev/null && file -L "$(command -v FEXBash)" 2>/dev/null
ls -la ~/.fex-emu 2>/dev/null || echo "$HOME/.fex-emu no existe"
echo "binfmt_misc (x86 automático por el kernel):"
for e in /proc/sys/fs/binfmt_misc/*; do
    case "${e##*/}" in register|status) continue ;; esac
    echo "  ${e##*/}:"; sed 's/^/      /' "$e" 2>/dev/null
done

t "Steam: herramientas de compatibilidad (solo listado)"
ls -la ~/.local/share/Steam/compatibilitytools.d/ 2>/dev/null || echo "no existe"
ls -d ~/.local/share/Steam/steamapps/common/Proton* 2>/dev/null

t "Steam y Flatpak (para la tienda)"
printf '%-22s %s\n' "steam" "$(command -v steam || echo '-- no --')"
printf '%-22s %s\n' "steamos-add-to-steam" "$(command -v steamos-add-to-steam || echo '-- no --')"
printf '%-22s %s\n' "Steam abierto" "$(pgrep -x steam >/dev/null && echo sí || echo no)"
printf '%-22s %s\n' "copia de Steam" "$( [ -f ~/iw6x-steamos/tools/respaldo_steam.sh ] && echo ~/iw6x-steamos/tools/respaldo_steam.sh || echo '-- no encontrada --')"
if command -v flatpak >/dev/null; then
    flatpak --version
    echo "Remotos de usuario:";  flatpak remotes --user --columns=name,url 2>/dev/null | sed 's/^/  /'
    echo "Remotos de sistema:";  flatpak remotes --system --columns=name,url 2>/dev/null | sed 's/^/  /'
    echo "Apps instaladas: $(flatpak list --app --columns=application 2>/dev/null | wc -l)"
else
    echo "flatpak: -- no --"
fi

t "Sensores (para comparar ARM64 vs x86 traducido)"
for b in /sys/class/power_supply/*; do
    [ -e "$b/type" ] || continue
    printf '  %-28s tipo=%s capacidad=%s power_now=%s current_now=%s voltage_now=%s\n' "$(basename "$b")" \
        "$(cat "$b/type" 2>/dev/null)" "$(cat "$b/capacity" 2>/dev/null)" "$(cat "$b/power_now" 2>/dev/null)" \
        "$(cat "$b/current_now" 2>/dev/null)" "$(cat "$b/voltage_now" 2>/dev/null)"
done
echo "  Zonas térmicas: $(ls -d /sys/class/thermal/thermal_zone* 2>/dev/null | wc -l)  máx: $(cat /sys/class/thermal/thermal_zone*/temp 2>/dev/null | sort -n | tail -1)"

t "Herramientas que usa el instalador"
for b in git curl python3 file unsquashfs zenity kdialog; do
    printf '%-12s %s\n' "$b" "$(command -v "$b" || echo '-- no --')"
done
python3 -c 'import tkinter; print("tkinter: sí")' 2>/dev/null || echo "tkinter: no (se usará zenity o la terminal)"
echo "libfuse2: $(ls /usr/lib/libfuse.so.2* 2>/dev/null | head -1 || true)"

t "RecompLauncher"
B="$HOME/Applications/RecompLauncher"
ls -la "$B" 2>/dev/null || echo "Aún no instalado ($B)"
DESC="$(python3 "$DIR/herramientas/almacen.py" descargas 2>/dev/null)/RecompLauncher"
echo "Descargas: $DESC   ·   Instalaciones: $(python3 "$DIR/herramientas/almacen.py" instalaciones 2>/dev/null)"
for f in "$DESC"/*.AppImage "$B"/descargas/*.AppImage; do
    [ -e "$f" ] || continue
    echo "AppImage: $f"
    command -v file >/dev/null && file -b "$f"
    python3 "$PY" arch "$f"
done
if [ -e "$B/actual/AppRun" ]; then
    python3 "$PY" "$B/actual"
fi
ls -la ~/.local/share/com.recomplauncher.app 2>/dev/null | head -20
echo
echo "Fin del diagnóstico (no se ha modificado nada)."
