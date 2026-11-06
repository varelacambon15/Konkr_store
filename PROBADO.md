# Qué se ha probado y qué no

Fecha: 2026-11-06. RecompLauncher revisado: código fuente `0.90.0-beta.19` (commit `e6a3165`).

Las pruebas se hicieron en un contenedor Linux **x86_64** (no en la KONKR), con un usuario sin
privilegios, un HOME aislado y un **FEX simulado** (un script que imita `--appimage-extract` y muestra
con qué argumentos y variables se le llama).

## Probado ✅

- `instalar.sh --si --appimage …` de principio a fin: crea solo las carpetas previstas en el HOME,
  copia el AppImage, detecta x86_64, «extrae» (con el FEX simulado), crea el enlace `actual`, el enlace
  `~/Applications/lanzar_recomp.sh` y el `.desktop`. Repetirlo no rompe nada.
- `instalar.sh` se niega a ejecutarse como root.
- `lanzar_recomp.sh`:
  - Desde Steam/gamescope sin argumentos → añade `--bigpicture`, quita `LD_PRELOAD` y
    `LD_LIBRARY_PATH`, pone `WEBKIT_DISABLE_DMABUF_RENDERER=1` y `GDK_BACKEND=x11`.
  - Con su propia ruta como argumento (caso `%command%`) → la descarta.
  - En escritorio → sin Big Picture; `RECOMP_ESCALA=2` → `GDK_SCALE=2`.
  - Sin FEX → mensaje de error claro y código de salida 1.
  - Rota el registro (`lanzar_recomp.log` → `.anterior`).
- `diagnostico.sh`: se ejecuta sin errores y no escribe nada.
- `revisar_binarios.py` (modo terminal): distingue bien un ELF **aarch64 real** (de un paquete
  `manylinux_aarch64` de PyPI), un ELF x86_64, un `.exe` de Windows y un script; lee
  `recomplauncher.json`; encuentra el rootfs de FEX en `~/.fex-emu/Config.json` y detecta las
  librerías que faltan; calcula bien el offset de squashfs (= fin de la tabla de secciones ELF).
- `shellcheck -S warning` sin avisos en los tres `.sh`.

## NO probado ❌ (no lo doy por hecho)

- **Nada se ha ejecutado en la KONKR** ni con FEX real.
- **No se ha descargado el AppImage real**: la red de esta sesión no llega a las descargas de GitHub
  ni a recomplauncher.com. No he comprobado su arquitectura con `file` (por el código, la
  configuración de Tauri y el nombre habitual `_amd64.AppImage`, casi seguro que es **x86_64**;
  lo comprueba el paso 3 del instalador).
- La descarga automática con la API de GitHub (`instalar.sh` sin `--appimage`) y la verificación
  SHA-256 con el campo `digest`.
- `FEXInterpreter RecompLauncher.AppImage --appimage-extract` con FEX real, y el método alternativo con
  `unsquashfs` (no estaba instalado aquí).
- Que WebKitGTK x86_64 dibuje bien bajo FEX en gamescope, la aceleración gráfica y el rendimiento.
- Que el mando funcione dentro de RecompLauncher bajo FEX.
- La ventana Tkinter de `revisar_binarios.py` (este contenedor no tiene Tkinter) y el modo zenity.
- Instalar o jugar ninguna recomp concreta: no sé todavía qué recomps tienen build aarch64 ni qué
  archivo exacto pide cada una (lo indica `revisar_binarios.py` tras instalarla, si trae
  `recomplauncher.json`; también se ve en la ficha del juego en la app).
- Recomps solo de Windows mediante Proton bajo FEX.

## Hallazgos de la lectura del código de RecompLauncher

- `shortcuts.rs`: «Add to Steam» escribe `shortcuts.vdf` y cierra y reabre Steam → no usarlo.
- `proton.rs`: botón GE-Proton → escribe en `compatibilitytools.d` → no usarlo.
- `assets.rs`: la arquitectura se fija al compilar (`arch_now`). Bajo FEX elige builds x64; compilado
  ARM64, descartaría las builds marcadas x64.
- `sysenv.rs`: desde Steam/gamescope ya activa `WEBKIT_DISABLE_DMABUF_RENDERER=1` y limpia el
  runtime de Steam de `LD_LIBRARY_PATH`.
- Argumento `--bigpicture`: abre directamente la vista para mando y TV.
- Datos en `~/.local/share/com.recomplauncher.app` (o en `data/` junto al programa si hay un archivo
  `portable`).
