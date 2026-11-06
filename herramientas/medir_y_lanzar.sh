#!/usr/bin/env bash
# Lanza una build de una recomp (nativa ARM64 o x86_64 con FEX) y mide mientras juegas:
# consumo de batería (W), temperatura máxima (°C) y uso de CPU (%), cada 5 s, en un CSV.
# Al cerrar el juego añade una línea al resumen. Solo escribe en ~/recomp/comparar/.
#   medir_y_lanzar.sh arm64|x64 CARPETA PROGRAMA ETIQUETA
set -u
modo="${1:?arm64|x64}"; dir="${2:?carpeta}"; prog="${3:?programa}"; etiqueta="${4:-$modo}"
SYS="${KONKR_SYS:-/sys}"; PROC="${KONKR_PROC:-/proc}"; INTERVALO="${KONKR_INTERVALO:-5}"
base="$(dirname "$dir")"
mkdir -p "$base/medidas"
csv="$base/medidas/${modo}_$(date +%Y%m%d_%H%M%S).csv"
echo "segundos,vatios,temp_max_c,cpu_pct,bateria_pct" >"$csv"

vatios() {
    local b p c v
    for b in "$SYS"/class/power_supply/*; do
        [ "$(cat "$b/type" 2>/dev/null)" = "Battery" ] || continue
        p="$(cat "$b/power_now" 2>/dev/null)"
        if [ -n "$p" ]; then awk -v p="$p" 'BEGIN{printf "%.2f", (p<0?-p:p)/1e6}'; return; fi
        c="$(cat "$b/current_now" 2>/dev/null)"; v="$(cat "$b/voltage_now" 2>/dev/null)"
        if [ -n "$c" ] && [ -n "$v" ]; then awk -v c="$c" -v v="$v" 'BEGIN{printf "%.2f", (c<0?-c:c)*v/1e12}'; return; fi
    done
    echo ""
}
bateria() { local b; for b in "$SYS"/class/power_supply/*; do [ "$(cat "$b/type" 2>/dev/null)" = "Battery" ] && cat "$b/capacity" 2>/dev/null && return; done; echo ""; }
temp_max() { cat "$SYS"/class/thermal/thermal_zone*/temp 2>/dev/null | awk 'BEGIN{m=""} $1>m||m==""{m=$1} END{if(m!="")printf "%.1f", m/1000}'; }
cpu_tics() { awk '/^cpu /{t=0; for(i=2;i<=NF;i++)t+=$i; print t, $5+$6}' "$PROC/stat"; }

medir() {
    local inicio=$SECONDS prev_t prev_i t i
    read -r prev_t prev_i < <(cpu_tics)
    while sleep "$INTERVALO"; do
        read -r t i < <(cpu_tics)
        pct="$(awk -v dt=$((t - prev_t)) -v di=$((i - prev_i)) 'BEGIN{ if(dt>0) printf "%.1f", 100*(dt-di)/dt }')"
        prev_t=$t; prev_i=$i
        echo "$((SECONDS - inicio)),$(vatios),$(temp_max),$pct,$(bateria)" >>"$csv"
    done
}

cd "$dir" || exit 1
if [ "$modo" = "x64" ]; then
    FEX="$(command -v FEXInterpreter || command -v FEXLoader || true)"
    [ -n "$FEX" ] || { echo "No encuentro FEXInterpreter"; exit 1; }
    unset LD_PRELOAD LD_LIBRARY_PATH          # librerías ARM de Steam: un proceso x86 no puede cargarlas
    cmd=("$FEX" "./$prog")
else
    unset LD_LIBRARY_PATH                     # se conserva LD_PRELOAD: el overlay de Steam es ARM, como el juego
    cmd=("./$prog")
fi

medir & MEDIDOR=$!
inicio=$SECONDS
"${cmd[@]}" "${@:5}"
codigo=$?
kill "$MEDIDOR" 2>/dev/null; wait "$MEDIDOR" 2>/dev/null
dura=$((SECONDS - inicio))
resumen="$(awk -F, 'NR>1{ if($2!=""){w+=$2;nw++} if($3!=""&&$3>t)t=$3; if($4!=""){c+=$4;nc++} if(NR==2)b0=$5; b1=$5 }
    END{ printf "%s;%s;%s;%s", (nw?sprintf("%.2f",w/nw):"-"), (t!=""?t:"-"), (nc?sprintf("%.0f",c/nc):"-"), (b0!=""&&b1!=""?b0-b1:"-") }' "$csv")"
IFS=';' read -r w_med t_max cpu_med bat_gastada <<<"$resumen"
echo "$(date '+%F %T');$etiqueta;$modo;${dura};$w_med;$t_max;$cpu_med;$bat_gastada;$codigo;$(basename "$csv")" >>"$base/medidas/resumen.csv"
echo "Medido: ${dura}s · ${w_med} W de media · ${t_max} °C máx · CPU ${cpu_med}% · batería gastada ${bat_gastada}% → $csv"
exit "$codigo"
