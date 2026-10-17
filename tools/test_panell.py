"""Comprova que el panell te totes les seccions col.locades i que el JS es valid.

1) Cada <section id="s-..."> ha d'estar en alguna pestanya (si no, quedaria
   invisible i l'usuari perdria una funcio).
2) Cap pestanya no pot referenciar una seccio que no existeixi.
3) El JavaScript ha de passar el parser (fem servir el de macOS via osascript).
"""
import os
import re
import subprocess
import sys

HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mac", "panel.html")
html = open(HTML, encoding="utf-8").read()

seccions = set(re.findall(r'<section id="(s-[a-z0-9-]+)"', html))
bloc = re.search(r"const PESTANYES = \[(.*?)\n\];", html, re.S)
referides = set(re.findall(r'"(s-[a-z0-9-]+)"', bloc.group(1)))
pestanyes = re.findall(r'id: "([a-z0-9]+)"', bloc.group(1))

fallades = []
print("seccions al HTML: %d" % len(seccions))
print("pestanyes: %s" % ", ".join(pestanyes))
for s in sorted(seccions - referides):
    print("  FALLA la seccio %s no es a cap pestanya" % s)
    fallades.append(s)
for s in sorted(referides - seccions):
    print("  FALLA la pestanya referencia %s, que no existeix" % s)
    fallades.append(s)
if not fallades:
    print("  ok    totes les seccions son a una pestanya")

# El JS ha de ser valid: osascript dona SyntaxError si no ho es.
m = re.search(r"<script>(.*)</script>", html, re.S)
tmp = "/tmp/panel_check.js"
open(tmp, "w", encoding="utf-8").write(m.group(1))
r = subprocess.run(["osascript", "-l", "JavaScript", tmp],
                   capture_output=True, text=True, timeout=30)
sortida = (r.stderr or "") + (r.stdout or "")
if "SyntaxError" in sortida or "Can't find variable" not in sortida:
    print("  FALLA el JavaScript no passa el parser: %s" % sortida.strip()[:300])
    fallades.append("js")
else:
    print("  ok    el JavaScript es valid (nomes falta el DOM, que es normal)")

print()
if fallades:
    print("=== HI HA %d PROBLEMES ===" % len(fallades))
    sys.exit(1)
print("=== TOT OK ===")
