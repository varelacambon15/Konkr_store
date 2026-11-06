#!/usr/bin/env bash
# Abre el panel «Konkr Store» (ventana con botones grandes). Para Steam o el menú del escritorio.
unset LD_PRELOAD LD_LIBRARY_PATH
DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
mkdir -p "$HOME/recomp/logs"
exec python3 "$DIR/konkr_store.py" "$@" 2>>"$HOME/recomp/logs/panel.log"
