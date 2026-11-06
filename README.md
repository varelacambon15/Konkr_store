# Konkr Store

Tienda y panel para la **KONKR Pocket FIT** (Snapdragon 8 Gen 3, ARM64) con **SteamOS ARM** (port de
hashtagbasit) y **FEX**. Se maneja con el mando o el teclado, y lo que instales se puede añadir a Steam
para abrirlo desde el Modo Juego / Big Picture como «juego que no es de Steam».

Al abrirla aparecen tres secciones:

| Sección | Qué hace |
|---|---|
| **Aplicaciones** | Tipo Discover: aplicaciones **Flatpak de Flathub** (destacadas, búsqueda, instaladas, actualizar todas). Instala siempre **en tu usuario** (`flatpak --user`), sin sudo. Antes de instalar comprueba que la app exista para ARM64. |
| **Recompilaciones** | Al estilo de [RecompLauncher](https://github.com/elripalda/RecompLauncher): **cuadrícula de portadas** (las de su catálogo, o las que elegiste en él) y un **panel de detalle** con su banner, logo, juego, género y descripción. **Jugar**, **Añadir a Steam**, **Revisar binarios** y **Descargar recomps** (abre RecompLauncher). Las nuevas van a Steam solas. |
| **Juegos de Switch** | Los juegos portados con nx2konkr que copias a `~/juegos-switch`: se añaden a Steam solos. |
| **Herramientas** | Buscar actualizaciones, actualizar todo, cambiar de versión de RecompLauncher, modo gráfico, añadir RecompLauncher a Steam, copia de seguridad de Steam, diagnóstico, ver registro, guardar la salida. |

> RecompLauncher no incluye juegos ni los descarga: cada recomp necesita **tu propia copia** del juego.

## Instalación en un solo comando (Konsole, en Modo Escritorio)

```bash
git clone https://github.com/varelacambon15/Konkr_store.git ~/Konkr_store && ~/Konkr_store/instalar.sh
```

El instalador pregunta antes de cada paso (responde `s`). Todo va a tu carpeta de usuario y **no toca Steam**.

Si quieres ver antes cómo está la consola (solo lectura, no cambia nada):

```bash
~/Konkr_store/diagnostico.sh
```

## Abrir la tienda

```bash
~/Konkr_store/konkr_store.sh
```

También aparece en el menú del escritorio como **Konkr Store**, si aceptaste crear los accesos.

**Controles:** flechas o cruceta para moverse · Intro / A para elegir · Esc / B para volver · Steam + X para
el teclado en pantalla. Los avisos y confirmaciones salen dentro de la propia ventana, con botones grandes.

## Portadas de las recomps

La tienda usa el arte de RecompLauncher: primero el que elegiste en él, si no el de su catálogo. Busca la imagen en su caché y, si
no está, la descarga una vez a `~/recomp/cache/arte/`. Para ver portadas JPEG/WebP hace falta **Pillow**: el instalador (paso 9) la
pone en un entorno propio, `~/Konkr_store/.venv`, sin tocar el sistema. Sin ella, se ven las PNG (y las demás si hay `ffmpeg`), y
si no, tarjetas con iniciales.

## Instalar programas desde un archivo (AppImage, .tar.gz, .deb…)

Aplicaciones → **«Instalar archivo…»** muestra los instalables que hay en Descargas, Escritorio y memorias USB / microSD (o escribe
una ruta). Todo va a `~/Applications/Locales/<Nombre>/`, sin sudo, y se añade a Steam como el resto. Aparecen en «Instaladas»
(Abrir, Añadir a Steam, Desinstalar → a la papelera).

| Archivo | Qué hace |
|---|---|
| **AppImage** | Lo extrae (sin FUSE) y crea su lanzador: ARM64 nativo, o x86_64 con FEX |
| **.tar.gz / .tar.xz / .tar.zst / .zip** | Lo extrae (sin rutas peligrosas) y busca el programa principal y su arquitectura |
| **.deb** y **paquetes de Arch** (`.pkg.tar.zst`) | Extrae su contenido en tu carpeta, sin instalarlo en el sistema. Si necesita librerías que SteamOS no tiene, no arrancará |
| **.flatpak / .flatpakref** | `flatpak install --user` |
| **.sh** (instaladores tipo GOG) | Lo abre en Konsole para seguir sus pasos (instálalo dentro de `~/Applications`) |
| **.exe / .msi / .rpm** | No: explica qué hacer |

Desde la terminal: `~/Konkr_store/herramientas/instalar_local.py tipo ARCHIVO` (qué es, sin cambiar nada) o `instalar ARCHIVO`.

## Recomps en Steam: automático, y sin Proton

**Se añaden solas.** Al cerrar RecompLauncher (y al entrar en Recompilaciones), las recomps instaladas que aún no
tienen acceso en Steam se añaden automáticamente: primero tu copia de seguridad de Steam (una por tanda; si falla,
no se añade nada) y luego se le pide a Steam por la vía segura (`steam://addnonsteamgame`). Steam cerrado: quedan
pendientes para la próxima vez. Las **aplicaciones** se instalan cuando tú eliges una («Instalar») y, al terminar, también se añaden a Steam solas.
Las dos cosas se desactivan en Herramientas → «A Steam: automático sí/no» (entonces pregunta cada vez). Registro:
`~/recomp/logs/auto_steam.log`.

**Linux o Windows.** Cada recomp muestra qué build tiene instalada:

| Etiqueta | Qué es | Cómo se abre |
|---|---|---|
| `[Linux ARM64]` | Binario aarch64 | Nativo: sin FEX ni Proton |
| `[Linux x86·FEX]` | Binario Linux x86_64 | Con FEX, sin Proton |
| `[Windows·Proton]` | `.exe` | RecompLauncher con su propio Proton (no probado en ARM) |
| `[¿?]` | No se sabe qué programa es | RecompLauncher decide |

El acceso de Steam de cada recomp es un script de Linux (`herramientas/jugar_recomp.py <id>`), así que **en Steam
ninguna necesita Proton**: en Propiedades → Compatibilidad, deja sin marcar «Forzar herramienta de compatibilidad».

Por defecto el script la abre **a través de RecompLauncher** (`--play`), que la prepara como siempre (tu copia del
juego, sus ajustes y argumentos, efectos, partidas en la nube). Para las de Linux hay un **modo directo** opcional
(Recompilaciones → «Directo / Launcher»): se salta RecompLauncher, gasta menos memoria y, en las ARM64, conserva el
overlay de Steam. Úsalo después de haberla jugado una vez con RecompLauncher. Cambiar de modo no obliga a volver a
añadirla a Steam: el script decide al arrancar. Para ver qué haría con una recomp:

```bash
~/Konkr_store/herramientas/jugar_recomp.py ID --info
```

## Juegos de Switch (nx2konkr): copiar y listo

Los juegos de Switch que portes en tu PC con **nx2konkr** (repositorio privado `varelacambon15/nx2konkr`, guía `KONKR.md`) salen
como una carpeta `<Juego>-konkr`. **Cópiala entera a `~/juegos-switch/`** (por USB, la red o la microSD) y no hace falta ningún
comando: el servicio de vigilancia (instalar.sh, paso 8; un servicio de systemd de tu usuario, sin sudo) espera a que termine la copia,
devuelve al programa sus permisos de ejecución (se pierden al pasar por un USB de Windows), crea el acceso con su nombre e icono y lo
añade a Steam, con tu copia de seguridad antes. También se hace al entrar en la sección **Juegos de Switch** de la tienda (Jugar, Ver
registro, Partidas) y al cerrar RecompLauncher. No muevas la carpeta después: el acceso de Steam apunta a ella. En Steam, sin Proton.

Desde la terminal:

```bash
~/Konkr_store/konkr_store.py switch
```

## Comparar nativo ARM64 contra x86_64 + FEX

En Recompilaciones → **«Comparar ARM vs FEX»**. Por ahora está configurada **Zelda 64: Recompiled**, que
publica las dos builds de Linux. La tienda:

1. Descarga de su GitHub la build **ARM64** y la **x86_64** de la última release a `~/recomp/comparar/zelda64/`.
   Comprueba el SHA-256 si GitHub lo publica, y la arquitectura real de cada programa.
2. Crea dos accesos, «Zelda 64: Recompiled (ARM64 nativo)» y «Zelda 64: Recompiled (x86_64 + FEX)», y ofrece
   añadirlos a Steam.
3. Cada vez que juegas desde esos accesos, mide cada 5 s el **consumo de batería (W)**, la **temperatura
   máxima** y el **uso de CPU**, y lo guarda en `~/recomp/comparar/zelda64/medidas/`.
4. **«Resultados»** muestra la tabla de partidas y el consumo medio de cada versión.

Para que la comparación sea justa: juega lo mismo (misma zona, mismo tiempo) con cada versión, con el mismo
brillo y el mismo TDP. Los **FPS** se ven con el indicador de rendimiento de Steam (botón ··· → batería →
nivel de superposición). Las dos versiones comparten partidas (`~/.config/Zelda64Recompiled/saves`).

**Archivo del juego que pide:** tu copia de *Majora's Mask* de N64, **versión norteamericana (US)**. Mejor en
`.z64`; otros formatos los convierte sola. Ninguna otra versión ni ROM vale.

Desde la terminal:

```bash
~/Konkr_store/herramientas/comparar_recomp.py preparar zelda64
```

```bash
~/Konkr_store/herramientas/comparar_recomp.py resumen zelda64
```

Se pueden añadir más recomps a `datos/comparar.json` si publican build Linux ARM64 y x86_64.

## Añadir cosas a Steam (cómo funciona y por qué es seguro)

Cuando instalas una app o una recomp, la tienda pregunta si quieres añadirla a Steam. Si dices que sí:

1. Ejecuta tu copia de seguridad `~/iw6x-steamos/tools/respaldo_steam.sh`. Si falla o no existe, se para
   (y te avisa).
2. Prepara un acceso `.desktop` en `~/recomp/accesos/`. Para las apps Flatpak usa el `.desktop` que el
   propio Flatpak instala, igual que Discover.
3. **Se lo pide a Steam**: usa `steamos-add-to-steam` si existe, o si no el enlace
   `steam://addnonsteamgame/…`. Es el mismo mecanismo que el botón «Add to Steam» de Discover.
   **Steam añade el acceso él mismo**, sin cerrarse. La tienda **nunca escribe** `shortcuts.vdf` ni ningún
   archivo de Steam.

Steam tiene que estar abierto. Si en unos segundos no aparece el acceso, la tienda te dice qué archivo añadir
a mano (Steam → Añadir un juego que no es de Steam → Explorar).

Las recomps se añaden como `lanzar_recomp.sh --play <id>`: Steam abre directamente esa recomp, a través de
RecompLauncher (que se encarga del tiempo de juego y las copias de partidas).

### Añadir la tienda y RecompLauncher a Steam

- **RecompLauncher**: Tienda → Herramientas → «Añadir RecompLauncher a Steam».
- **La propia tienda**: en Steam (Modo Escritorio), «Añadir un juego que no es de Steam» → Explorar →
  `/home/steamos/Konkr_store/konkr_store.sh`. En Compatibilidad, no fuerces ninguna herramienta.

Si prefieres hacerlo a mano para RecompLauncher:

- **Destino**: `"/home/steamos/Applications/lanzar_recomp.sh"`
- **Iniciar en**: `"/home/steamos"`
- **Opciones de lanzamiento**:

  ```
  --bigpicture
  ```

- **Compatibilidad**: sin forzar ninguna herramienta (ni Proton ni otra).

### Arte para Steam

El instalador puede descargar las imágenes oficiales de RecompLauncher a
`~/Applications/RecompLauncher/arte-steam/` (`poster.jpg`, `hero.jpg`, `logo.png`, `header.jpg`). Para
ponerlas: botón derecho en el acceso → Administrar → Personalizar arte. La tienda no toca la carpeta de arte
de Steam.

## Actualizar

Desde la tienda (Herramientas → Actualizar todo), o:

```bash
~/Konkr_store/actualizar.sh
```

Hace `git pull` de los scripts y, si hay versión nueva de RecompLauncher, la instala en su propia carpeta.
Las anteriores se quedan; puedes volver a una con Herramientas → «Cambiar de versión».

Para ver solo si hay versión nueva, sin cambiar nada:

```bash
~/Konkr_store/instalar.sh --comprobar
```

## Si RecompLauncher sale en negro o se cierra al arrancar

El lanzador lo detecta solo: si se cierra con error en menos de 20 segundos, lo reintenta en **modo gráfico
seguro** y, si así funciona, lo recuerda (`~/recomp/ajustes/graficos`). Puedes cambiarlo en Herramientas →
«Modo gráfico: cambiar». El registro está en Herramientas → «Ver registro»
(`~/recomp/logs/lanzar_recomp.log`).

Variables para las opciones de lanzamiento de Steam (con variables delante hace falta `%command%`):

| Si quieres… | Opciones de lanzamiento |
|---|---|
| Forzar el modo gráfico seguro | `RECOMP_GRAFICOS=seguro %command% --bigpicture` |
| Ignorar el modo seguro recordado | `RECOMP_GRAFICOS=normal %command% --bigpicture` |
| Interfaz más grande | `RECOMP_ESCALA=2 %command% --bigpicture` |

## Dentro de RecompLauncher: qué NO usar

Revisé su código fuente (0.90.0-beta.19):

- **«Add to Steam» de RecompLauncher**: escribe `shortcuts.vdf` directamente y cierra y reabre Steam.
  **No lo uses**: añade las recomps desde la tienda (Recompilaciones → Añadir a Steam).
- **Botón GE-Proton**: descarga Proton x86_64 en `compatibilitytools.d` de Steam. **No lo uses.**
- **Recomps solo de Windows**: necesitarían Proton bajo FEX. **No probado.**
- **Carpeta de la biblioteca**: elige `~/recomp/biblioteca`, nunca una carpeta dentro de `steamapps`.

## Cómo se ejecutan las recomps

RecompLauncher es x86_64 y corre con FEX, así que elige las builds de Linux x86_64 de cada recomp, que
deberían correr también con FEX (sin probar todavía en esta consola). Una recomp solo es nativa si su
proyecto publica un binario `aarch64`. Para comprobar qué trae una: Recompilaciones → «Revisar binarios»,
o la ventana

```bash
~/Konkr_store/herramientas/revisar_binarios.py
```

## Desinstalar

```bash
~/Konkr_store/desinstalar.sh
```

Pregunta por cada grupo y **mueve a la papelera** (no borra). Tus recomps y los datos de RecompLauncher
(copias de partidas incluidas) solo se quitan si lo confirmas expresamente. Los accesos de Steam se quitan
desde Steam.

## Dónde está cada cosa

| Qué | Dónde |
|---|---|
| RecompLauncher (cada versión en su carpeta) | `~/Applications/RecompLauncher/` |
| Lanzador | `~/Applications/lanzar_recomp.sh` |
| Datos de RecompLauncher | `~/.local/share/com.recomplauncher.app/` |
| Recomps | `~/recomp/biblioteca/` (la eliges en RecompLauncher) |
| Accesos preparados para Steam y registro de los añadidos | `~/recomp/accesos/` |
| Registros | `~/recomp/logs/` |
| Ajustes (modo gráfico) | `~/recomp/ajustes/` |
| Informes guardados | `~/recomp/informes/` |
| Apps Flatpak de usuario | `~/.local/share/flatpak/` |

## Archivos del repositorio

| Archivo | Para qué |
|---|---|
| `instalar.sh` | Instala o actualiza RecompLauncher (`--si`, `--appimage RUTA`, `--comprobar`) |
| `konkr_store.sh` / `konkr_store.py` | La tienda (ventana). `konkr_store.py estado` muestra el estado en la terminal |
| `lanzar_recomp.sh` | Abre RecompLauncher con FEX (lo usan Steam y la tienda) |
| `actualizar.sh` | `git pull` + versión nueva de RecompLauncher |
| `diagnostico.sh` | Diagnóstico de solo lectura |
| `desinstalar.sh` | Desinstalación a la papelera |
| `herramientas/anadir_a_steam.sh` | Pide a Steam que añada un acceso (copia de seguridad antes) |
| `herramientas/revisar_binarios.py` | Revisa la arquitectura y las librerías de una recomp |
| `herramientas/releases.py` | Consulta las versiones de RecompLauncher en GitHub |
| `datos/aplicaciones.json` | Lista de aplicaciones destacadas (edítala a tu gusto) |
| `herramientas/jugar_recomp.py` | Abre una recomp (vía RecompLauncher o directa; lo usan sus accesos de Steam) |
| `herramientas/comparar_recomp.py` | Descarga y prepara las builds ARM64 y x86_64 de una recomp para compararlas |
| `herramientas/medir_y_lanzar.sh` | Lanza una build (nativa o con FEX) midiendo batería, temperatura y CPU |
| `datos/comparar.json` | Recomps disponibles para comparar |

Qué se ha probado y qué no: [PROBADO.md](PROBADO.md).
