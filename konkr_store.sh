#!/usr/bin/env bash
# Abre el panel «Konkr Store» (ventana con botones grandes). Para Steam o el menú del escritorio.
# Usa el Python de ~/Konkr_store/.venv si existe (con Pillow, para las portadas JPEG/WebP: instalar.sh, paso 9), si no el del sistema.
unset LD_PRELOAD LD_LIBRARY_PATH
DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
PY="$DIR/.venv/bin/python"; [ -x "$PY" ] || PY=python3
mkdir -p "$HOME/recomp/logs"
exec "$PY" "$DIR/konkr_store.py" "$@" 2>>"$HOME/recomp/logs/panel.log"
