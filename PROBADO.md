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
