#!/usr/bin/env bash
# Instalador de RecompLauncher para la KONKR Pocket FIT (SteamOS ARM + FEX).
#
#   ./instalar.sh                    pregunta antes de cada paso
#   ./instalar.sh --si               no pregunta
#   ./instalar.sh --appimage RUTA    usa un AppImage ya descargado en vez de bajarlo
#
# Qué hace (todo dentro de tu carpeta de usuario):
#   ~/Applications/RecompLauncher/descargas/   el AppImage descargado
#   ~/Applications/RecompLauncher/<versión>/   el AppImage extraído
#   ~/Applications/RecompLauncher/actual       enlace a la versión en uso
#   ~/Applications/lanzar_recomp.sh            enlace al lanzador de este repo
#   ~/recomp/{biblioteca,logs,informes}        carpetas de trabajo
#   ~/.local/share/applications/recomplauncher-fex.desktop   (opcional)
# NO usa sudo, NO toca Steam, NO borra nada.
set -euo pipefail

REPO_LAUNCHER="elripalda/RecompLauncher"
DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
PY="$DIR/herramientas/revisar_binarios.py"
APPS="$HOME/Applications"
BASE="$APPS/RecompLauncher"
SI=0
APPIMAGE_LOCAL=""

while [ $# -gt 0 ]; do
    case "$1" in
        --si|-y) SI=1 ;;
        --appimage) APPIMAGE_LOCAL="$(readlink -f "$2")"; shift ;;
        -h|--help) sed -n 2,20p "$0"; exit 0 ;;
        *) echo "Opción desconocida: $1"; exit 1 ;;
    esac
    shift
done

paso() { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }
ok()   { printf '\033[1;32m    %s\033[0m\n' "$1"; }
mal()  { printf '\033[1;31m    %s\033[0m\n' "$1" >&2; }
preguntar() {
    [ "$SI" = 1 ] && return 0
    local r
    read -r -p "    ¿$1? [s/N] " r </dev/tty || return 1
    [[ "$r" =~ ^[sSyY] ]]
}

# ---------------------------------------------------------------- 0. comprobaciones
paso "0/6 Comprobaciones (solo lectura)"
if [ "$(id -u)" = 0 ]; then mal "No ejecutes esto como root ni con sudo."; exit 1; fi
echo "    Arquitectura: $(uname -m)"
FEX="$(command -v FEXInterpreter || command -v FEXLoader || true)"
if [ -z "$FEX" ]; then mal "No encuentro FEXInterpreter. Sin FEX no se puede ejecutar RecompLauncher (x86_64)."; exit 1; fi
ok "FEX: $FEX"
for b in curl python3; do
    command -v "$b" >/dev/null || { mal "Falta $b"; exit 1; }
done
ok "curl y python3 presentes"

# ---------------------------------------------------------------- 1. carpetas
paso "1/6 Crear carpetas en tu usuario: $BASE y ~/recomp"
if preguntar "Crear las carpetas"; then
    mkdir -p "$BASE/descargas" "$HOME/recomp/biblioteca" "$HOME/recomp/logs" "$HOME/recomp/informes"
    ok "Hecho"
else
    echo "    Cancelado."; exit 0
fi

# ---------------------------------------------------------------- 2. descarga
paso "2/6 Obtener el AppImage de RecompLauncher"
if [ -n "$APPIMAGE_LOCAL" ]; then
    [ -f "$APPIMAGE_LOCAL" ] || { mal "No existe $APPIMAGE_LOCAL"; exit 1; }
    APPIMAGE="$BASE/descargas/$(basename "$APPIMAGE_LOCAL")"
    if [ "$APPIMAGE_LOCAL" != "$APPIMAGE" ]; then
        cp -f "$APPIMAGE_LOCAL" "$APPIMAGE"
    fi
    ok "Uso el archivo indicado (copiado a $APPIMAGE)"
    sha256sum "$APPIMAGE"
else
    echo "    Consultando las releases de github.com/$REPO_LAUNCHER (incluye betas)…"
    JSON="$(curl -fsSL -H 'Accept: application/vnd.github+json' "https://api.github.com/repos/$REPO_LAUNCHER/releases?per_page=10")" \
        || { mal "No pude consultar GitHub. Descarga el AppImage a mano y usa --appimage RUTA."; exit 1; }
    # Elige el AppImage más reciente; si alguna release trae uno ARM64 (aarch64/arm64), lo prefiere.
    INFO="$(printf '%s' "$JSON" | python3 -c '
import json, sys
rels = json.load(sys.stdin)
for r in rels:
    if r.get("draft"): continue
    ais = [a for a in r.get("assets", []) if a["name"].lower().endswith(".appimage")]
    if not ais: continue
    arm = [a for a in ais if any(k in a["name"].lower() for k in ("aarch64", "arm64"))]
    a = (arm or ais)[0]
    print(r["tag_name"], a["name"], a["browser_download_url"], (a.get("digest") or "").replace("sha256:", "") or "-", sep="\t")
    break
')"
    [ -n "$INFO" ] || { mal "No encontré ningún AppImage en las últimas releases. Mira https://github.com/$REPO_LAUNCHER/releases"; exit 1; }
    IFS=$'\t' read -r TAG NOMBRE URL SHA <<<"$INFO"
    echo "    Release: $TAG"
    echo "    Archivo: $NOMBRE"
    echo "    SHA-256 publicado por GitHub: $SHA"
    APPIMAGE="$BASE/descargas/$NOMBRE"
    if [ -f "$APPIMAGE" ]; then
        ok "Ya estaba descargado"
    elif preguntar "Descargar $NOMBRE a $BASE/descargas"; then
        curl -fL --progress-bar -o "$APPIMAGE.parcial" "$URL"
        mv -f "$APPIMAGE.parcial" "$APPIMAGE"
        ok "Descargado"
    else
        echo "    Cancelado."; exit 0
    fi
    if [ "$SHA" != "-" ]; then
        REAL="$(sha256sum "$APPIMAGE" | cut -d' ' -f1)"
        if [ "$REAL" = "$SHA" ]; then ok "SHA-256 correcto"; else mal "¡SHA-256 NO coincide! ($REAL). No sigo."; exit 1; fi
    else
        echo "    (GitHub no publica SHA-256 para este archivo; compáralo con el de las notas de la release)"
        sha256sum "$APPIMAGE"
    fi
fi
chmod u+x "$APPIMAGE"

# ---------------------------------------------------------------- 3. arquitectura
paso "3/6 Arquitectura del AppImage"
command -v file >/dev/null && file -b "$APPIMAGE" | sed 's/^/    file: /'
ARCH="$(python3 "$PY" arch "$APPIMAGE")"
echo "    ELF: $ARCH"
case "$ARCH" in
    aarch64) ok "Es ARM64: correría nativo. (Este lanzador usa FEX igualmente; avísame y lo adaptamos.)" ;;
    x86_64)  ok "Es x86_64: se ejecutará con FEX." ;;
    *)       mal "Arquitectura inesperada ($ARCH). No sigo."; exit 1 ;;
esac

# ---------------------------------------------------------------- 4. extraer
VERSION="$(basename "$APPIMAGE" .AppImage)"
DEST="$BASE/$VERSION"
paso "4/6 Extraer el AppImage en $DEST (evita depender de FUSE)"
if [ -e "$DEST/AppRun" ]; then
    ok "Ya estaba extraído"
elif preguntar "Extraer"; then
    [ -e "$DEST" ] && mv "$DEST" "$DEST.incompleto.$(date +%s)"
    TMP="$BASE/.extrayendo.$$"
    mkdir -p "$TMP"
    echo "    Método 1: $FEX $(basename "$APPIMAGE") --appimage-extract"
    if (cd "$TMP" && "$FEX" "$APPIMAGE" --appimage-extract >"$HOME/recomp/logs/extraer.log" 2>&1) && [ -e "$TMP/squashfs-root/AppRun" ]; then
        ok "Extraído con FEX"
    elif command -v unsquashfs >/dev/null; then
        echo "    Método 1 falló (ver ~/recomp/logs/extraer.log). Método 2: unsquashfs nativo."
        [ -e "$TMP/squashfs-root" ] && mv "$TMP/squashfs-root" "$TMP/fallido1"
        OFF="$(python3 "$PY" offset "$APPIMAGE")"
        unsquashfs -q -o "$OFF" -d "$TMP/squashfs-root" "$APPIMAGE" >>"$HOME/recomp/logs/extraer.log" 2>&1 \
            && ok "Extraído con unsquashfs (offset $OFF)" \
            || { mal "unsquashfs también falló. Revisa ~/recomp/logs/extraer.log"; exit 1; }
    else
        mal "No se pudo extraer y no hay unsquashfs. Revisa ~/recomp/logs/extraer.log"; exit 1
    fi
    mv "$TMP/squashfs-root" "$DEST"
    rmdir "$TMP" 2>/dev/null || echo "    (quedan restos en $TMP; puedes borrarlos tú)"
else
    echo "    Cancelado."; exit 0
fi
ln -sfn "$VERSION" "$BASE/actual"
ok "actual -> $VERSION"
python3 "$PY" "$DEST" | grep -E 'VEREDICTO|FALTAN|FEX:|no comprobadas' | head -15 | sed 's/^/    /' || true

# ---------------------------------------------------------------- 5. lanzador
paso "5/6 Lanzador: $APPS/lanzar_recomp.sh -> $DIR/lanzar_recomp.sh"
chmod u+x "$DIR/lanzar_recomp.sh" "$DIR/diagnostico.sh" "$PY" 2>/dev/null || true
if [ -e "$APPS/lanzar_recomp.sh" ] && [ ! -L "$APPS/lanzar_recomp.sh" ]; then
    mal "Ya existe un $APPS/lanzar_recomp.sh que no es un enlace: no lo toco."
else
    ln -sfn "$DIR/lanzar_recomp.sh" "$APPS/lanzar_recomp.sh"
    ok "Hecho"
fi

# ---------------------------------------------------------------- 6. .desktop
DESK="$HOME/.local/share/applications/recomplauncher-fex.desktop"
paso "6/6 (Opcional) Acceso en el menú del escritorio: $DESK"
if preguntar "Crear el acceso .desktop"; then
    mkdir -p "$(dirname "$DESK")"
    ICONO="$(ls "$BASE/actual"/*.png 2>/dev/null | head -1 || true)"
    cat >"$DESK" <<EOF
[Desktop Entry]
Type=Application
Name=RecompLauncher (FEX)
Comment=RecompLauncher x86_64 ejecutado con FEX
Exec=$APPS/lanzar_recomp.sh
Path=$HOME
Icon=${ICONO:-applications-games}
Categories=Game;
Terminal=false
EOF
    ok "Creado"
else
    echo "    Omitido."
fi

cat <<EOF

$(printf '\033[1;32m')Instalación terminada.$(printf '\033[0m')

Prueba en Modo Escritorio:   $APPS/lanzar_recomp.sh
Registro:                    ~/recomp/logs/lanzar_recomp.log

Para añadirlo a Steam (lo haces TÚ desde Steam; este script no toca Steam):
  1. ~/iw6x-steamos/tools/respaldo_steam.sh
  2. Steam > Juegos > «Añadir un juego que no es de Steam» > Explorar >
     $APPS/lanzar_recomp.sh
  3. Propiedades del acceso:
       Destino:     "$APPS/lanzar_recomp.sh"
       Iniciar en:  "$HOME"
       Opciones de lanzamiento:   --bigpicture
       Compatibilidad: SIN forzar ninguna herramienta (ni Proton ni FEX de Steam).
EOF
