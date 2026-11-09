#!/usr/bin/env python3
"""Consulta las releases de RecompLauncher en GitHub (solo lectura).

  releases.py ultima            -> TAG<TAB>ARCHIVO<TAB>URL<TAB>SHA256 (o "-")
  releases.py comparar A B      -> imprime "nueva" si B es más reciente que A, si no "igual"

Se usa desde instalar.sh y desde el panel konkr_store.py.
"""
import json
import platform
import re
import sys
import urllib.request

REPO = "elripalda/RecompLauncher"
API = f"https://api.github.com/repos/{REPO}/releases?per_page=10"
# RecompLauncher solo publica x86_64: en ARM64 se usa el que compila el workflow recomplauncher-arm64.yml de este repo.
REPO_ARM = "varelacambon15/Konkr_store"
API_ARM = f"https://api.github.com/repos/{REPO_ARM}/releases?per_page=10"


def elegir(releases):
    """La release más reciente que trae un AppImage; prefiere uno ARM64 si existe."""
    for r in releases:
        if r.get("draft"):
            continue
        ais = [a for a in r.get("assets", []) if a.get("name", "").lower().endswith(".appimage")]
        if not ais:
            continue
        arm = [a for a in ais if any(k in a["name"].lower() for k in ("aarch64", "arm64"))]
        a = (arm or ais)[0]
        sha = (a.get("digest") or "").replace("sha256:", "") or "-"
        return r["tag_name"], a["name"], a["browser_download_url"], sha
    return None


def elegir_arm(releases):
    """La release ARM64 más reciente compilada por este repo (etiqueta recomplauncher-arm64-<versión>)."""
    mejor = None
    for r in releases:
        if r.get("draft") or not str(r.get("tag_name", "")).startswith("recomplauncher-arm64-"):
            continue
        for a in r.get("assets", []):
            n = a.get("name", "")
            if n.lower().endswith(".appimage") and any(k in n.lower() for k in ("aarch64", "arm64")):
                sha = (a.get("digest") or "").replace("sha256:", "") or "-"
                cand = (r["tag_name"].replace("recomplauncher-arm64-", ""), n, a["browser_download_url"], sha)
                if mejor is None or clave(cand[0]) > clave(mejor[0]):
                    mejor = cand
    return mejor


def _json(url):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "Konkr_store"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def ultima(datos=None):
    if datos is None and platform.machine() in ("aarch64", "arm64"):
        try:
            nativa = elegir_arm(_json(API_ARM))
        except Exception:
            nativa = None
        if nativa:
            return nativa
    if datos is None:
        req = urllib.request.Request(API, headers={"Accept": "application/vnd.github+json", "User-Agent": "Konkr_store"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            datos = json.load(resp)
    return elegir(datos)


def clave(v):
    """'RecompLauncher_0.90.0-beta.19_amd64' o 'v0.90.0-beta.19' -> tupla comparable.
    Una versión final va después de sus betas: 0.90.0 > 0.90.0-beta.19."""
    m = re.search(r"(\d+(?:\.\d+)+)(?:[-_.]?(alpha|beta|rc)[-_.]?(\d+(?:\.\d+)*))?", v, re.I)
    if not m:
        return ()
    base = tuple(int(x) for x in m.group(1).split("."))
    base = base + (0,) * (4 - len(base))
    if m.group(2):
        orden = {"alpha": 0, "beta": 1, "rc": 2}[m.group(2).lower()]
        pre = tuple(int(x) for x in m.group(3).split("."))
        return base + (orden,) + pre
    return base + (9,)


def es_nueva(instalada, disponible):
    a, b = clave(instalada), clave(disponible)
    if not b:
        return False
    return not a or b > a


def main(argv):
    if argv[:1] == ["ultima"]:
        try:
            r = ultima()
        except Exception as e:  # sin red, límite de la API, etc.
            print(f"No pude consultar GitHub: {e}", file=sys.stderr)
            return 2
        if not r:
            print("No hay ningún AppImage en las últimas releases.", file=sys.stderr)
            return 3
        print(*r, sep="\t")
        return 0
    if argv[:1] == ["comparar"] and len(argv) == 3:
        print("nueva" if es_nueva(argv[1], argv[2]) else "igual")
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
