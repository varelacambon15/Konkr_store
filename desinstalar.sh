#!/usr/bin/env bash
# Desinstala lo que instaló Konkr_store. NO borra: mueve a la papelera (o a ~/Papelera_konkr_store).
# Pregunta por cada grupo. Nunca toca Steam ni tus juegos de Steam.
# Los accesos que añadiste a Steam se quitan desde Steam (botón derecho > Administrar > Eliminar).
set -u
FECHA="$(date +%Y%m%d_%H%M%S)"
a_papelera() {
    local f
    for f in "$@"; do
        [ -e "$f" ] || [ -L "$f" ] || continue
        if command -v gio >/dev/null 2>&1 && gio trash "$f" 2>/dev/null; then
            echo "    a la papelera: $f"
        else
            mkdir -p "$HOME/Papelera_konkr_store/$FECHA"
            mv "$f" "$HOME/Papelera_konkr_store/$FECHA/" && echo "    movido a ~/Papelera_konkr_store/$FECHA: $f"
        fi
    done
}
preguntar() { local r; read -r -p "¿$1? [s/N] " r </dev/tty || return 1; [[ "$r" =~ ^[sSyY] ]]; }

echo "== RecompLauncher (programa, versiones guardadas, arte) y lanzador"
preguntar "Quitar ~/Applications/RecompLauncher y ~/Applications/lanzar_recomp.sh" \
    && a_papelera "$HOME/Applications/RecompLauncher" "$HOME/Applications/lanzar_recomp.sh"

echo "== Vigilancia de ~/juegos-switch (servicio de systemd de tu usuario)"
if [ -f "$HOME/.config/systemd/user/konkr-switch.path" ] && preguntar "Desactivar y quitar la vigilancia de ~/juegos-switch"; then
    systemctl --user disable --now konkr-switch.path 2>/dev/null || true
    a_papelera "$HOME/.config/systemd/user/konkr-switch.path" "$HOME/.config/systemd/user/konkr-switch.service"
    systemctl --user daemon-reload 2>/dev/null || true
fi

echo "== Accesos del menú y accesos preparados para Steam (~/recomp/accesos)"
preguntar "Quitar los .desktop de Konkr_store y ~/recomp/accesos" \
    && a_papelera "$HOME/.local/share/applications/recomplauncher-fex.desktop" \
                  "$HOME/.local/share/applications/konkr-store.desktop" "$HOME/recomp/accesos"

echo "== Datos de RecompLauncher (ajustes, biblioteca, COPIAS DE TUS PARTIDAS)"
preguntar "Quitar ~/.local/share/com.recomplauncher.app (piénsalo: incluye copias de partidas)" \
    && a_papelera "$HOME/.local/share/com.recomplauncher.app"

echo "== Tus recomps instaladas (~/recomp/biblioteca)"
preguntar "Quitar ~/recomp/biblioteca (tus recomps y sus archivos)" \
    && a_papelera "$HOME/recomp/biblioteca"

echo
echo "Las aplicaciones Flatpak se desinstalan desde la tienda (Aplicaciones > Instaladas > Desinstalar)."
echo "El repositorio sigue en $(cd "$(dirname "$(readlink -f "$0")")" && pwd): bórralo tú si quieres."
