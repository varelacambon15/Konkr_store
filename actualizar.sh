#!/usr/bin/env bash
# Actualiza Konkr_store (git pull) y, si hay versión nueva, RecompLauncher.
#   ./actualizar.sh        pregunta antes de instalar
#   ./actualizar.sh --si   no pregunta
# No toca Steam ni borra nada: cada versión de RecompLauncher queda en su carpeta.
set -u
DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
SI=""
TRAS_PULL=0
for a in "$@"; do
    case "$a" in
        --si|-y) SI="--si" ;;
        --tras-pull) TRAS_PULL=1 ;;
    esac
done

if [ "$TRAS_PULL" = 0 ]; then
    echo "==> 1/2 Actualizando los scripts (git pull en $DIR)"
    if [ -n "$(git -C "$DIR" status --porcelain --untracked-files=no 2>/dev/null)" ]; then
        echo "    Tienes cambios locales en $DIR: no hago git pull para no pisarlos."
        echo "    Míralos con:  git -C $DIR status"
    elif git -C "$DIR" pull --ff-only --quiet; then
        echo "    Scripts al día: $(git -C "$DIR" log -1 --format='%h %s')"
        # Se vuelve a lanzar con la versión recién descargada de este mismo script.
        exec "$DIR/actualizar.sh" --tras-pull ${SI:+"$SI"}
    else
        echo "    No pude hacer git pull (mira el mensaje de arriba: sin red, o archivos que se pisarían). Sigo con la versión actual."
    fi
fi

echo "==> 2/2 Buscando versión nueva de RecompLauncher"
"$DIR/instalar.sh" --comprobar
rc=$?
case "$rc" in
    0)  echo "Nada que actualizar." ;;
    10)
        if [ -z "$SI" ]; then
            read -r -p "¿Instalar la versión nueva? [s/N] " r </dev/tty || r=n
            [[ "$r" =~ ^[sSyY] ]] || { echo "Cancelado."; exit 0; }
        fi
        exec "$DIR/instalar.sh" --si ;;
    *)  echo "No pude comprobar las versiones (¿sin red o límite de la API de GitHub?). Prueba más tarde."; exit 2 ;;
esac
