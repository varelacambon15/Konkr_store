#!/usr/bin/env bash
# Instalador / actualizador de RecompLauncher para la KONKR Pocket FIT (SteamOS ARM + FEX).
#
#   ./instalar.sh                    pregunta antes de cada paso
#   ./instalar.sh --si               no pregunta (lo usa el panel tras confirmar en su ventana)
#   ./instalar.sh --appimage RUTA    usa un AppImage ya descargado en vez de bajarlo
#   ./instalar.sh --comprobar        solo dice si hay versión nueva (no cambia nada)
#                                    salida: 0 = al día, 10 = hay versión nueva, 2 = error
#
# Qué crea (todo dentro de tu carpeta de usuario):
#   ~/Applications/RecompLauncher/descargas/   el AppImage descargado
#   ~/Applications/RecompLauncher/<versión>/   el AppImage extraído (las versiones viejas se quedan)
#   ~/Applications/RecompLauncher/actual       enlace a la versión en uso
#   ~/Applications/RecompLauncher/arte-steam/  imágenes oficiales para ponerlas tú en Steam
#   ~/Applications/lanzar_recomp.sh            enlace al lanzador de este repo
#   ~/recomp/{biblioteca,logs,informes}        carpetas de trabajo
#   ~/.local/share/applications/*.desktop      accesos en el menú (opcional)
# NO usa sudo, NO toca Steam, NO borra nada.
set -euo pipefail

DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
PY="$DIR/herramientas/revisar_binarios.py"
REL="$DIR/herramientas/releases.py"
ARTE_URL="https://raw.githubusercontent.com/elripalda/RecompLauncher/main/src-tauri/steam-art"
APPS="$HOME/Applications"
BASE="$APPS/RecompLauncher"
SI=0
COMPROBAR=0
APPIMAGE_LOCAL=""

while [ $# -gt 0 ]; do
    case "$1" in
        --si|-y) SI=1 ;;
        --comprobar) COMPROBAR=1 ;;
        --appimage) APPIMAGE_LOCAL="$(readlink -f "${2:?Falta la ruta del AppImage}")"; shift ;;
        -h|--help) sed -n 2,19p "$0"; exit 0 ;;
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
instalada() { [ -L "$BASE/actual" ] && basename "$(readlink "$BASE/actual")" || true; }

# ---------------------------------------------------------------- solo comprobar
if [ "$COMPROBAR" = 1 ]; then
    YA="$(instalada)"
    echo "Instalada:  ${YA:-ninguna}"
    INFO="$(python3 "$REL" ultima)" || exit 2
    IFS=$'\t' read -r TAG NOMBRE _ _ <<<"$INFO"
    echo "Disponible: $TAG ($NOMBRE)"
    if [ "$(python3 "$REL" comparar "${YA:-}" "$NOMBRE")" = "nueva" ]; then
        echo "HAY VERSIÓN NUEVA"; exit 10
    fi
    echo "Estás al día"; exit 0
fi

# ---------------------------------------------------------------- 0. comprobaciones
paso "0/8 Comprobaciones (solo lectura)"
if [ "$(id -u)" = 0 ]; then mal "No ejecutes esto como root ni con sudo."; exit 1; fi
echo "    Arquitectura: $(uname -m)"
FEX="$(command -v FEXInterpreter || command -v FEXLoader || true)"
if [ -z "$FEX" ]; then mal "No encuentro FEXInterpreter. Sin FEX no se puede ejecutar RecompLauncher (x86_64)."; exit 1; fi
ok "FEX: $FEX"
for b in curl python3; do
    command -v "$b" >/dev/null || { mal "Falta $b"; exit 1; }
done
ok "curl y python3 presentes"
YA="$(instalada)"
[ -n "$YA" ] && echo "    Versión instalada ahora: $YA"

# ---------------------------------------------------------------- 1. carpetas
paso "1/8 Carpetas en tu usuario: $BASE y ~/recomp"
if [ -d "$BASE/descargas" ] && [ -d "$HOME/recomp/logs" ]; then
    ok "Ya existen"
elif preguntar "Crear las carpetas"; then
    mkdir -p "$BASE/descargas" "$HOME/recomp/biblioteca" "$HOME/recomp/logs" "$HOME/recomp/informes"
    ok "Hecho"
else
    echo "    Cancelado."; exit 0
fi

# ---------------------------------------------------------------- 2. descarga
paso "2/8 Obtener el AppImage de RecompLauncher"
if [ -n "$APPIMAGE_LOCAL" ]; then
    [ -f "$APPIMAGE_LOCAL" ] || { mal "No existe $APPIMAGE_LOCAL"; exit 1; }
    APPIMAGE="$BASE/descargas/$(basename "$APPIMAGE_LOCAL")"
    if [ "$APPIMAGE_LOCAL" != "$APPIMAGE" ]; then
        cp -f "$APPIMAGE_LOCAL" "$APPIMAGE"
    fi
    ok "Uso el archivo indicado (copiado a $APPIMAGE)"
    sha256sum "$APPIMAGE"
else
    echo "    Consultando las releases de github.com/elripalda/RecompLauncher (incluye betas)…"
    INFO="$(python3 "$REL" ultima)" \
        || { mal "No pude consultar GitHub. Descarga el AppImage a mano y usa --appimage RUTA."; exit 1; }
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
paso "3/8 Arquitectura del AppImage"
if command -v file >/dev/null; then file -b "$APPIMAGE" | cut -c1-90 | sed 's/^/    file: /'; fi
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
paso "4/8 Extraer el AppImage en $DEST (evita depender de FUSE)"
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
[ -n "$YA" ] && [ "$YA" != "$VERSION" ] && echo "    (La versión anterior, $YA, se queda por si quieres volver: panel > Cambiar de versión)"
python3 "$PY" "$DEST" | grep -E 'VEREDICTO|FALTAN|FEX:|no comprobadas' | head -15 | sed 's/^/    /' || true

# ---------------------------------------------------------------- 5. lanzador
paso "5/8 Lanzador: $APPS/lanzar_recomp.sh -> $DIR/lanzar_recomp.sh"
chmod u+x "$DIR"/*.sh "$DIR"/herramientas/*.py 2>/dev/null || true
if [ -e "$APPS/lanzar_recomp.sh" ] && [ ! -L "$APPS/lanzar_recomp.sh" ]; then
    mal "Ya existe un $APPS/lanzar_recomp.sh que no es un enlace: no lo toco."
else
    ln -sfn "$DIR/lanzar_recomp.sh" "$APPS/lanzar_recomp.sh"
    ok "Hecho"
fi

# ---------------------------------------------------------------- 6. arte para Steam
ARTE="$BASE/arte-steam"
paso "6/8 (Opcional) Imágenes oficiales para el acceso de Steam: $ARTE"
if [ -f "$ARTE/poster.jpg" ] && [ -f "$ARTE/hero.jpg" ] && [ -f "$ARTE/logo.png" ] && [ -f "$ARTE/header.jpg" ]; then
    ok "Ya están descargadas"
elif preguntar "Descargar portada, fondo, logo y cabecera (≈1 MB)"; then
    mkdir -p "$ARTE"
    for f in poster.jpg hero.jpg logo.png header.jpg; do
        curl -fsSL -o "$ARTE/$f" "$ARTE_URL/$f" && echo "    $f" || mal "No pude descargar $f"
    done
    ok "Ponlas tú en Steam: botón derecho en el acceso > Administrar > Personalizar arte (ver README)"
else
    echo "    Omitido."
fi

# ---------------------------------------------------------------- 7. .desktop
paso "7/8 (Opcional) Accesos en el menú del escritorio (~/.local/share/applications)"
D1="$HOME/.local/share/applications/recomplauncher-fex.desktop"
D2="$HOME/.local/share/applications/konkr-store.desktop"
if [ -f "$D1" ] && [ -f "$D2" ]; then
    ok "Ya existen"
elif preguntar "Crear los accesos «RecompLauncher (FEX)» y «Konkr Store»"; then
    mkdir -p "$(dirname "$D1")"
    ICONO="$ARTE/poster.jpg"; [ -f "$ICONO" ] || ICONO="applications-games"
    cat >"$D1" <<EOF
[Desktop Entry]
Type=Application
Name=RecompLauncher (FEX)
Comment=RecompLauncher x86_64 ejecutado con FEX
Exec=$APPS/lanzar_recomp.sh
Path=$HOME
Icon=$ICONO
Categories=Game;
Terminal=false
EOF
    cat >"$D2" <<EOF
[Desktop Entry]
Type=Application
Name=Konkr Store
Comment=Panel: abrir, actualizar y revisar RecompLauncher y tus recomps
Exec=$DIR/konkr_store.sh
Path=$HOME
Icon=system-software-install
Categories=Game;Utility;
Terminal=false
EOF
    ok "Creados"
else
    echo "    Omitido."
fi

# ---------------------------------------------------------------- 8. juegos de Switch automáticos
UD="$HOME/.config/systemd/user"
paso "8/8 (Opcional) Juegos de Switch (nx2konkr): al copiar una carpeta a ~/juegos-switch, se añade sola a Steam"
if ! command -v systemctl >/dev/null 2>&1; then
    echo "    Sin systemd: se añaden al abrir la tienda o al cerrar RecompLauncher."
elif [ -f "$UD/konkr-switch.path" ] && systemctl --user is-enabled konkr-switch.path >/dev/null 2>&1; then
    sed "s|@TIENDA@|$DIR/konkr_store.py|" "$DIR/herramientas/systemd/konkr-switch.service" >"$UD/konkr-switch.service"
    systemctl --user daemon-reload 2>/dev/null || true
    ok "Ya está activo (vigilando ~/juegos-switch)"
elif preguntar "Activar la vigilancia de ~/juegos-switch (servicio de systemd de tu usuario, sin sudo)"; then
    mkdir -p "$UD" "$HOME/juegos-switch" "$HOME/recomp/logs"
    cp "$DIR/herramientas/systemd/konkr-switch.path" "$UD/"
    sed "s|@TIENDA@|$DIR/konkr_store.py|" "$DIR/herramientas/systemd/konkr-switch.service" >"$UD/konkr-switch.service"
    if systemctl --user daemon-reload && systemctl --user enable --now konkr-switch.path; then
        ok "Activo: copia una carpeta <Juego>-konkr a ~/juegos-switch y aparecerá en Steam"
    else
        mal "systemctl --user falló: se añadirán al abrir la tienda o al cerrar RecompLauncher"
    fi
else
    echo "    Omitido: se añadirán al abrir la tienda (Juegos de Switch) o al cerrar RecompLauncher."
fi

cat <<EOF

$(printf '\033[1;32m')Instalación terminada: $VERSION$(printf '\033[0m')

Panel con botones grandes:   $DIR/konkr_store.sh
Abrir RecompLauncher:        $APPS/lanzar_recomp.sh
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
