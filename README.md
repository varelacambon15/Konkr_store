# Konkr_store: RecompLauncher en la KONKR Pocket FIT

Scripts para usar [RecompLauncher](https://github.com/elripalda/RecompLauncher) (gestor de
*recomps*: versiones nativas de PC de juegos de consola) en una **KONKR Pocket FIT**
(Snapdragon 8 Gen 3, ARM64) con **SteamOS ARM** (port de hashtagbasit) y **FEX**, y abrirlo desde
Steam como «juego que no es de Steam», con el mando y en Big Picture.

> RecompLauncher no incluye juegos ni los descarga. Cada recomp necesita **tu propia copia** del
> juego (tu disco o tu copia de seguridad).

## Qué hace y qué no

| Hace | No hace |
|---|---|
| Descarga el AppImage oficial de RecompLauncher desde GitHub y comprueba su SHA-256 | No usa `sudo`, `pacman` ni toca el sistema |
| Lo extrae en `~/Applications/RecompLauncher` (sin FUSE) | No escribe nada en Steam (ni `shortcuts.vdf`, ni `config.vdf`, ni carpetas de juegos) |
| Crea `~/Applications/lanzar_recomp.sh`, que lo ejecuta con FEX | No borra nada |
| (Opcional) Crea un acceso en `~/.local/share/applications` | No descarga juegos |

## Instalación (copiar y pegar en Konsole, en Modo Escritorio)

1) Descargar este repositorio (solo crea `~/Konkr_store`):

```bash
git clone https://github.com/varelacambon15/Konkr_store.git ~/Konkr_store
```

2) Diagnóstico de **solo lectura** (FEX, rootfs, herramientas de Steam, etc.). Si algo sale raro,
pásame la salida:

```bash
~/Konkr_store/diagnostico.sh
```

3) Instalar (pregunta antes de cada paso; responde `s` para seguir):

```bash
~/Konkr_store/instalar.sh
```

Si la descarga desde GitHub falla, baja tú el `.AppImage` desde
<https://github.com/elripalda/RecompLauncher/releases> y pásaselo:

```bash
~/Konkr_store/instalar.sh --appimage ~/Downloads/RecompLauncher_0.90.0-beta.19_amd64.AppImage
```

4) Probarlo en el escritorio antes de meterlo en Steam:

```bash
~/Applications/lanzar_recomp.sh
```

El registro queda en `~/recomp/logs/lanzar_recomp.log` (y el anterior, en `lanzar_recomp.log.anterior`).

## Añadirlo a Steam («juego que no es de Steam»)

Esto lo haces **tú** desde Steam; los scripts no tocan Steam. Steam escribirá el acceso en su
`shortcuts.vdf` por sí mismo, así que primero haz la copia de seguridad:

```bash
~/iw6x-steamos/tools/respaldo_steam.sh
```

Después, en **Modo Escritorio**:

1. Steam → **Juegos** → **Añadir un juego que no es de Steam a mi biblioteca…** → **Explorar…** →
   elige `/home/steamos/Applications/lanzar_recomp.sh` → **Añadir programas seleccionados**.
2. Botón derecho sobre el acceso → **Propiedades**:
   - **Destino**: `"/home/steamos/Applications/lanzar_recomp.sh"`
   - **Iniciar en**: `"/home/steamos"`
   - **Opciones de lanzamiento**, pega:

     ```
     --bigpicture
     ```

   - **Compatibilidad**: deja **desmarcado** «Forzar el uso de una herramienta de compatibilidad»
     (ni Proton ni ninguna otra). El script ya llama a FEX.
3. Opcional: cámbiale el nombre a `RecompLauncher`.

¿Por qué no `lanzar_recomp.sh %command%`? En un juego que no es de Steam, el destino *ya es* el
script, y `%command%` se sustituye por el destino. Pegarlo así haría que el script recibiera su
propia ruta como argumento. El script lo tolera (la descarta), pero no hace falta.

Variables opcionales, delante de `--bigpicture` en las opciones de lanzamiento:

| Si ves… | Pega en Opciones de lanzamiento |
|---|---|
| Ventana en negro | `RECOMP_GRAFICOS=seguro %command% --bigpicture` |
| Interfaz demasiado pequeña | `RECOMP_ESCALA=2 %command% --bigpicture` |
| Quieres la vista normal, no Big Picture | `RECOMP_ESCRITORIO=1 %command%` |

(Con variables delante sí hace falta `%command%`: así Steam las aplica al lanzar el destino.)

## Dentro de RecompLauncher: qué NO usar en esta consola

Revisé el código fuente de RecompLauncher 0.90.0-beta.19 y estas funciones chocan con las reglas
de seguridad de esta consola:

- **«Add to Steam»** (en la app y en cada juego): escribe directamente en
  `userdata/*/config/shortcuts.vdf` y cierra y reabre Steam (`shortcuts.rs`). **No lo uses.**
  Añade los juegos tú a mano, como arriba.
- **Botón GE-Proton** (Ajustes → General): descarga GE-Proton x86_64 en
  `~/.local/share/Steam/compatibilitytools.d`. **No lo uses.**
- **Winetricks / recomps solo de Windows**: necesitarían Proton bajo FEX. **No probado**; evítalo
  y usa las versiones de Linux.
- **Carpeta de la biblioteca**: en el asistente inicial elige `~/recomp/biblioteca`. **Nunca**
  una carpeta dentro de `steamapps`.

## Cómo se ejecutan las recomps aquí

- RecompLauncher se compila para x86_64, así que bajo FEX se ve a sí mismo como «x64» y **elige
  las builds de Linux x86_64** de cada recomp. Esas deberían ejecutarse también con FEX, porque FEX
  emula los procesos hijos x86_64 (sin probar todavía en esta consola).
- Una recomp es **nativa** solo si su proyecto publica un binario `aarch64`/`arm64`. El launcher,
  bajo FEX, no lo elegirá solo: tendrías que instalarlo a mano.
- Para saber qué trae una recomp instalada (aarch64 o x86_64, qué librerías le faltan y qué
  archivo del juego pide según su `recomplauncher.json`):

```bash
~/Konkr_store/herramientas/revisar_binarios.py
```

  Abre una ventana para elegir la carpeta. Sin Tkinter usa zenity, y si no, la terminal:

```bash
~/Konkr_store/herramientas/revisar_binarios.py ~/recomp/biblioteca/NOMBRE_DE_LA_RECOMP
```

  Solo lee. Guarda un informe únicamente si pulsas «Guardar informe» (en `~/recomp/informes`).

## Actualizar

```bash
git -C ~/Konkr_store pull && ~/Konkr_store/instalar.sh
```

Cada versión nueva se extrae en su propia carpeta y `~/Applications/RecompLauncher/actual` pasa a
apuntar a ella; las anteriores se quedan por si hay que volver atrás.

## Desinstalar (a mano, tú decides qué borrar)

- `~/Applications/RecompLauncher/` y `~/Applications/lanzar_recomp.sh`
- `~/.local/share/applications/recomplauncher-fex.desktop`
- Datos de la app: `~/.local/share/com.recomplauncher.app/`
- Tus recomps: `~/recomp/`
- El acceso en Steam: bórralo desde Steam (botón derecho → Administrar → Eliminar de la biblioteca)

## Dónde guarda cosas

| Qué | Dónde |
|---|---|
| Programa | `~/Applications/RecompLauncher/<versión>/` |
| Configuración, biblioteca, copias de partidas | `~/.local/share/com.recomplauncher.app/` |
| Recomps instaladas | La carpeta que elijas (recomendado `~/recomp/biblioteca`) |
| Registros de este repo | `~/recomp/logs/` |

## Idea futura: RecompLauncher nativo ARM64

RecompLauncher es una app Tauri (Rust + WebKitGTK) con el código fuente público, así que se puede
compilar para ARM64 (por ejemplo, con GitHub Actions en un runner ARM). La diferencia importante
es que, compilado nativo, **solo ofrecería las recomps que publican build ARM64**, porque descarta
las x86_64 (`assets.rs`, `other_arch`). Con FEX ves todas las de Linux x86_64. Se puede tener
cada versión en una carpeta distinta. Ver [PROBADO.md](PROBADO.md).
