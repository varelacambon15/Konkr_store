# Instalar todo en la KONKR Pocket FIT (copiar y pegar)

Todo se hace en **Modo Escritorio**, en **Konsole**. Cada bloque es un comando: cópialo y pégalo (Ctrl+Mayús+V en Konsole).
Nada usa `sudo` ni toca el sistema: todo va a tu carpeta de usuario o a la SD que elijas.

## 0. Antes de empezar

- Si quieres guardar lo grande en la **tarjeta SD**, que esté insertada: el instalador la detecta solo. Si no sirve (exFAT/FAT/NTFS:
  ahí los programas no se pueden ejecutar), lo dice; Steam las formatea en ext4, que sí sirve.
- **Steam abierto** (para que los accesos se añadan solos).
- Tu copia de seguridad de Steam en `~/iw6x-steamos/tools/respaldo_steam.sh` (sin ella, la tienda no añade nada a Steam
  automáticamente).

## 1. Konkr Store (tienda, RecompLauncher, recomps, juegos de Switch, apps)

Descargar e instalar:

```bash
git clone https://github.com/varelacambon15/Konkr_store.git ~/Konkr_store && ~/Konkr_store/instalar.sh
```

El instalador pregunta paso a paso. Lo que conviene responder:

| Paso | Qué es | Respuesta |
|---|---|---|
| 1 | **Dónde guardar lo grande**: detecta la SD sola y pregunta «¿Guardar en la tarjeta SD …?» | **Intro** (sí). Si hay varias tarjetas, sale un menú con todas |
| 2–6 | Carpetas, RecompLauncher (descarga, comprobación y extracción) | `s` |
| 7 | Imágenes oficiales de RecompLauncher para Steam | `s` |
| 8 | Accesos en el menú del escritorio | `s` |
| 9 | **Juegos de Switch automáticos** (vigilar `~/juegos-switch`) | `s` |
| 10 | **Pillow** (portadas JPEG en la tienda) | `s` |

Comprobar cómo está la consola (solo lectura; pásame la salida si algo falla):

```bash
~/Konkr_store/diagnostico.sh
```

Abrir la tienda:

```bash
~/Konkr_store/konkr_store.sh
```

### Añadir la tienda y RecompLauncher a Steam

- **RecompLauncher**: en la tienda → Herramientas → «Añadir RecompLauncher a Steam».
- **La tienda**: en Steam, «Añadir un juego que no es de Steam» → Explorar → `/home/steamos/Konkr_store/konkr_store.sh`.
  En Propiedades → Compatibilidad, **sin** forzar ninguna herramienta.

Desde ahí, lo que instales (apps, recomps, programas desde archivo, juegos de Switch) se añade a Steam solo.

### La primera vez en RecompLauncher

En su asistente, como carpeta de la biblioteca elige **`/home/steamos/recomp/biblioteca`** (si elegiste la SD, ya apunta a ella).
No uses su botón «Add to Steam» ni el de GE-Proton: la tienda se encarga.

## 2. Juegos de Switch (nx2konkr)

El port se hace en el **PC** (Windows con WSL2): guía `KONKR.md` del repositorio privado `varelacambon15/nx2konkr`, rama
`linux-aarch64`. En la Konkr solo hay que **copiar la carpeta `<Juego>-konkr` entera a `~/juegos-switch/`** (con la SD elegida,
`~/juegos-switch` ya está en la SD): aparece en Steam sola.

Ver los juegos que hay:

```bash
~/Konkr_store/konkr_store.py switch
```

## 3. Chat de Claude en la Konkr (konkr-claude)

Cuando exista su repositorio en GitHub (`varelacambon15/konkr-claude`):

```bash
git clone https://github.com/varelacambon15/konkr-claude.git ~/konkr-claude && ~/konkr-claude/instalar_claude.sh
```

Primer arranque, para iniciar sesión con tu cuenta de Claude:

```bash
~/konkr-claude/claude_konkr.sh
```

## Actualizar

```bash
git -C ~/Konkr_store pull && ~/Konkr_store/instalar.sh
```

## Mover lo grande a la SD (o de vuelta) más adelante

En la tienda → Herramientas → «Dónde se guarda (SD)». O en la terminal:

```bash
python3 ~/Konkr_store/herramientas/almacen.py elegir
```

## Desinstalar

```bash
~/Konkr_store/desinstalar.sh
```

Pregunta por cada cosa y lo manda a la papelera (no borra). Los accesos de Steam se quitan desde Steam.
