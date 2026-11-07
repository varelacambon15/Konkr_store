#!/bin/sh
# Cómo ejecutar un programa Linux x86_64 en esta consola ARM64. Imprime una línea:
#   una ruta (FEXInterpreter, FEXLoader o box64): ponerla delante del programa
#   directo   el kernel lo traduce solo (binfmt: Box64 o FEX registrados); ejecutar el programa tal cual
# y sale con 1 si no hay ninguno. KONKR_X86=<ruta|directo> manda sobre lo detectado.
if [ -n "${KONKR_X86:-}" ]; then echo "$KONKR_X86"; exit 0; fi
for c in FEXInterpreter FEXLoader box64; do
    p="$(command -v "$c" 2>/dev/null)" && { echo "$p"; exit 0; }
done
for f in /proc/sys/fs/binfmt_misc/*; do
    case "$(basename "$f")" in register|status) continue ;; esac
    [ -r "$f" ] || continue
    # una entrada x86_64: su «magic» es la cabecera ELF de x86-64 (…02 01 01 … 3e 00), o se llama box64/FEX
    if grep -q '^enabled' "$f" && { grep -qi '3e00' "$f" || basename "$f" | grep -qiE 'box64|fex|x86'; }; then
        i="$(sed -n 's/^interpreter //p' "$f")"
        if [ -n "$i" ] && [ -x "$i" ]; then echo "$i"; else echo directo; fi
        exit 0
    fi
done
for p in /usr/local/bin/box64 /usr/lib/box64/box64 /opt/box64/box64 "$HOME/.local/bin/box64"; do
    [ -x "$p" ] && { echo "$p"; exit 0; }
done
exit 1
