# Qué se ha probado y qué no

Última revisión: 2026-11-06. RecompLauncher revisado: código fuente `0.90.0-beta.19` (commit `e6a3165`).

Todas las pruebas se hicieron en un contenedor Linux **x86_64** (no en la KONKR), con un usuario sin
privilegios y un HOME aislado. FEX, Flatpak, Steam y su copia de seguridad fueron **simulados** con
scripts que imitan lo justo y registran con qué se les llama.

## Probado ✅

### Tienda (`konkr_store.py`), en una pantalla virtual de 1920×1080, solo con teclado
- Pantalla de inicio con Aplicaciones, Recompilaciones y Herramientas; flechas, Intro y Esc.
- **Aplicaciones**: destacadas con marca ✔ en las instaladas, detalle de la app; Instalar → comprobación
  ARM64 (`flatpak remote-info --user`) → confirmación → `flatpak install --user` → «¿Añadir a Steam?» →
  copia de seguridad → petición a Steam; «Abrir» sin instalar → aviso.
- **Recompilaciones**: lee `library.json` de RecompLauncher; aviso de recomps nuevas sin acceso (una sola
  vez); Sí → confirmación → acceso añadido y marcado con ★.
- **Herramientas**: se muestra; «Cambiar de versión» cambia el enlace `actual` de forma atómica.
- Diálogos **dentro de la ventana**: se encontraron y corrigieron dos fallos de foco (con diálogos de Tk el
  teclado se iba a la ventana de detrás, y tras cerrar un diálogo no quedaba nada seleccionado).
- Esc en el inicio → «¿Salir?» → Sí cierra.
- Modo terminal: `estado`, `versiones`, `usar`, `graficos`, `recomps`, `acceso-recomp`, `acceso-app`,
  `acceso-launcher`; rechaza `usar ../../etc` y ids como `x;rm`.

### `herramientas/anadir_a_steam.sh`
- Steam cerrado → se para (se corrigió un fallo: la comprobación se detectaba a sí misma como «Steam»).
- Sin copia de seguridad → se para; copia que falla → se para; copia bien → pide a Steam.
- Sin `steamos-add-to-steam`: crea `/tmp/addnonsteamgamefile` y llama a `steam steam://addnonsteamgame/<ruta codificada>`.
- Con `steamos-add-to-steam`: lo usa.
- Rechaza archivos fuera de tu carpeta personal o dentro de Steam; no duplica el registro.

### Lanzador, instalador y actualizador
- `lanzar_recomp.sh`: con un FEX simulado que falla al instante en modo normal → reintenta en modo seguro,
  funciona y lo recuerda en `~/recomp/ajustes/graficos`; la segunda vez arranca directamente en seguro.
- `instalar.sh --si --appimage …`: los 7 pasos, incluida la **descarga real del arte de Steam** (4 imágenes
  válidas desde raw.githubusercontent.com) y los accesos «RecompLauncher (FEX)» y «Konkr Store».
- `instalar.sh --comprobar` sin acceso a la API → código 2 y mensaje claro.
- `actualizar.sh` contra un repo git local: sin cambios → `git pull` y se relanza con la versión nueva; con
  cambios locales → no hace pull; con un archivo que se pisaría → git se niega y el script sigue.

### Recompilaciones con portadas
- Con un `library.json` y un `pc-catalog.json` simulados (4 recomps; portada, banner y logo PNG/JPEG para unas, una dirección
  inaccesible y una sin arte): cuadrícula con portadas, tarjetas con iniciales («MK64») cuando no hay imagen, navegación con flechas
  (y bajando desde la última fila, a los botones), desplazamiento, panel con banner, logo, metadatos y descripción. Sin Pillow:
  PNG con Tk y JPEG a través de `ffmpeg` (este contenedor lo tiene).
- Paleta de RecompLauncher en toda la tienda.
- No probado: el catálogo y la caché reales de RecompLauncher (las direcciones salen de su código: `cache/pc-catalog.json`, campos
  `cover`, `hero`, `logo`, relativos a recomplauncher.com), ni la red de la Konkr.

### Instalar desde archivo local
- `instalar_local.py` con archivos de prueba hechos aquí: `.tar.gz` (binario aarch64 + `start.sh` + `lib/`: elige el binario por su nombre,
  ARM64, icono); `.zip` x86_64 (lanzador con FEX y sin `LD_PRELOAD`, ejecutado con un FEX simulado); `.deb` con xz y con zstd (construidos
  con `dpkg-deb`; lanzador con sus librerías en `LD_LIBRARY_PATH`); AppImage (cabecera ELF + squashfs; extraído con `unsquashfs`, la
  arquitectura sale de su contenido); `.zip` con `../` → rechazado; `.exe` → explicado; `.sh` → Konsole.
- Se corrigieron dos fallos: la arquitectura del AppImage se tomaba de su cabecera y no de su contenido; los `.zst` necesitaban el
  programa `zstd` (ahora, primero el zstd de Python).
- En la tienda: «Instalar archivo…» → lista → confirmación → instalado → en «Instaladas» → a Steam automáticamente.
- No probado: AppImages reales (ni su extracción con `--appimage-extract` cuando no hay `unsquashfs`), `.pkg.tar.zst` de Arch,
  `.flatpak`, y que los programas instalados así funcionen en la Konkr.

### Juegos de Switch (nx2konkr) a Steam automáticamente
- `konkr_store.py switch` / `auto-steam` con un `~/juegos-switch` falso: un juego completo sin permisos de ejecución (como tras un USB)
  → permisos devueltos, acceso con nombre e icono, una copia de seguridad y la petición a Steam; uno a medio copiar → INCOMPLETO, ignorado.
- `auto-steam --esperar`: esperó a que una copia en curso terminara (26 s con 10 s de calma) y luego lo añadió.
- La sección «Juegos de Switch» en la tienda (pantalla virtual) y el inicio en 2 × 2 (con 4 recuadros, el cuarto se cortaba a 1280 px).
  Herramientas pasa a 2 columnas (también se cortaba).
- No probado: las unidades de systemd (`konkr-switch.path` y `.service`; este contenedor no tiene systemd de usuario) y que Steam
  acepte la petición lanzada desde un servicio en segundo plano.

### Recomps a Steam automáticamente y Linux/Windows
- Apps: tras «Instalar» (flatpak simulado), se añaden a Steam sin diálogo (copia de seguridad y petición a Steam), con
  «A Steam: automático» activado; desactivado, pregunta como antes.
- `jugar_recomp.py` con un `library.json` simulado de 4 recomps (aarch64 real, x86_64 real con `recomplauncher.json`,
  Windows con `proton: true`, sin ejecutable): las clasifica bien; vía RecompLauncher por defecto (`--play id`);
  directo x86_64 → FEX con la carpeta del ejecutable (la misma que usa RecompLauncher), argumentos del manifiesto,
  `{install}` sustituido, `RECOMPLAUNCHER_*` sin pasar, sin `LD_PRELOAD` ni el `LD_LIBRARY_PATH` de Steam; el modo
  directo no se permite en Windows.
- `konkr_store.py auto-steam`: Steam cerrado → pendientes; abierto → una copia de seguridad y una petición por recomp;
  la segunda vez, nada; desactivado → no hace nada.
- `lanzar_recomp.sh`: al cerrarse RecompLauncher lanza la tanda en segundo plano (se corrigió un fallo: con una ruta
  relativa no encontraba la tienda tras su `cd`).
- En la tienda (pantalla virtual): etiquetas por recomp y tanda automática al entrar.
- No probado: que Steam de este port acepte las peticiones; el modo directo con una recomp real (RecompLauncher puede
  necesitar preparar algo que el modo directo no hace: por eso es opcional).

### Comparar ARM64 vs FEX
- Comprobado en el repositorio de Zelda 64: Recompiled (commit `b65c482`, 25-09-2026): su CI compila
  **Linux ARM64** (Ubuntu 22.04) y x86_64. Su README: «ARM64 builds will work on any ARM64 CPU».
- `comparar_recomp.py` con una release simulada que imita su empaquetado (un `.zip` con un `.tar.gz` dentro):
  elige bien las builds Linux ARM64 y X64 (descarta Windows, AppImage y Debug), verifica el SHA-256, extrae,
  comprueba la arquitectura real (aarch64 real / x86_64 real), crea los accesos y no repite trabajo la
  segunda vez. Se corrigió un fallo (la extracción del `.tar.gz` interior se llamaba a sí misma sin fin) y
  ahora una extracción a medias no se da por buena.
- Rechaza un `.zip` malicioso con rutas `../`.
- `medir_y_lanzar.sh` con batería, sensores y `/proc/stat` simulados: CSV cada N segundos, resumen
  (W, °C, CPU %); ARM conserva `LD_PRELOAD` (overlay de Steam), x86_64 lo quita y usa FEX.
- `resumen`: tabla y consumo medio ponderado.
- En la tienda (pantalla virtual, teclado): Comparar → confirmación → preparar → añadir los dos accesos a
  Steam uno tras otro. Se acortaron etiquetas porque un botón se cortaba a 1280 px.

### Resto
- `instalar.sh --si --appimage …` completo (versión anterior): carpetas, copia, arquitectura, extracción con
  FEX simulado, enlaces, `.desktop`. Se niega a ejecutarse como root.
- `releases.py`: la comparación de versiones acierta en 9 casos (betas, finales, `beta.3.1`, versiones
  mayores) y la selección de AppImage prefiere ARM64.
- `lanzar_recomp.sh` (versión anterior): Big Picture desde Steam, quita `LD_PRELOAD`, descarta su propia
  ruta, escala, error sin FEX.
- `revisar_binarios.py`: ELF aarch64 real, x86_64, `.exe`, scripts, `recomplauncher.json`, rootfs de FEX.
- `desinstalar.sh`: manda a la papelera solo los grupos confirmados (la biblioteca se quedó al decir «n»).
- `diagnostico.sh` sin errores; `shellcheck -S warning` sin avisos en todos los `.sh`.

## NO probado ❌ (no lo doy por hecho)

- **Nada en la KONKR**, ni con FEX, Flatpak o Steam reales.
- **Que Steam acepte `steam://addnonsteamgame`** en este port de SteamOS ARM, en el Modo Escritorio y en el
  Modo Juego. Si no funciona, la tienda te dice qué archivo añadir a mano.
- Que exista `steamos-add-to-steam` en este port.
- Flathub real: la red de esta sesión no llega a flathub.org. No sé qué apps destacadas tienen versión ARM64
  (la tienda lo comprueba antes de instalar).
- Que el Python de SteamOS tenga Tkinter (lo dirá `diagnostico.sh`).
- La tienda dentro de gamescope (Modo Juego) y con el mando real: el foco, la pantalla completa y la
  asignación de botones de Steam Input.
- Descargar el AppImage real de RecompLauncher (la red de esta sesión no llega a las descargas de GitHub) y
  `instalar.sh --comprobar` contra la API real.
- Las recomps en sí: ninguna instalada ni jugada.
- **Los nombres reales de los archivos de la release de Zelda 64** (las páginas de releases de GitHub están
  bloqueadas en esta sesión). Si no coinciden con los patrones de `datos/comparar.json`, la herramienta lo
  dice y muestra la lista de archivos de la release.
- Que la build ARM64 de Zelda 64 (compilada en Ubuntu 22.04) arranque en SteamOS ARM con Turnip (Vulkan), y
  que los sensores de batería y temperatura de la KONKR estén en las rutas estándar de `/sys`.
