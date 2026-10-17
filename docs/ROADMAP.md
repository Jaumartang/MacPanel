# Mac Panel — auditoria i pla d'evolució

> Resultat de la **FASE A** (auditoria) i pla de treball. Tot el que hi ha aquí
> està **verificat al codi**; el que és una proposta hi és marcat com a tal.

---

## 1. Arquitectura actual

El projecte no és una sola aplicació, sinó **tres peces que es parlen**:

```
   ┌────────────────────────┐   USB sèrie (115200)   ┌──────────────────────┐
   │  Mac (Python + web)    │ ─────────────────────► │  ESP32 (PlatformIO)  │
   │  mac/panel_server.py   │   CFG / S / T / B / …  │  src/*.cpp           │
   │  mac/bridge.py         │ ◄───────────────────── │  TFT_eSPI + SD       │
   │  mac/panel.html        │   H / C / X / A / …    │  tàctil XPT2046      │
   └────────────────────────┘                        └──────────────────────┘
```

| Peça | Fitxers | Tecnologia | Mida |
|---|---|---|---|
| **Firmware** | `src/*.cpp` (14 mòduls), `include/` | C++ / Arduino / PlatformIO / TFT_eSPI | ~4.000 línies |
| **Pont** | `mac/bridge.py` | Python 3 (pyserial, PyObjC opcional) | ~3.300 línies |
| **Panell** | `mac/panel.html`, `mac/panel_server.py` | HTML+JS+CSS, `http.server` | ~2.000 línies |
| **Eines** | `tools/*.py` (30) | Python | ~2.500 línies |
| **Dades** | `mac/panel_config.json`, `Assets/icons/` | JSON + PNG/BIN | 70 icones d'app + favicons |

**Entrada del Mac:** `mac/engega-panell.sh` → `panel_server.py` → arrenca el
`BRIDGE` (pont sèrie) i serveix `panel.html` a `http://127.0.0.1:8770`.

**Entrada de la placa:** `src/main.cpp` (`setup()` + `loop()`), amb
`src/maclink.cpp` llegint les línies del Mac i `src/ui.cpp` pintant.

**Com es prova:** `tools/test_*.py` (comandes de consola de la placa pel port
sèrie) i `tools/captura_pantalla.py` (baixa la pantalla real en PNG).

### Model de dades actual (`panel_config.json`)

```json
{ "port": "...", "orientation": "v", "theme": 1, "standby_s": 0, ...,
  "pages": [ { "name": "...", "icon": "...", "layout": "gauges",
               "widgets": ["cpu","mem"],
               "buttons": [ {"id":"app:x","label":"X","on":true} ],
               "apps": ["com.apple.Safari"] } ] }
```

- `layout` = com es pinta (9 valors: `status`, `buttons`, `gauges`, `graph`,
  `clock`, `numpad`, `launcher`, `tabs`, `favs`).
- `widgets` = **noms** de gadget (`cpu`, `mem`, `disk`, `bat`, `net`, `load`,
  `uptime`, `time`, `host`); l'ordre és la posició.
- `buttons` = `id` (l'acció), `label`, `on` (visibilitat), `icon`, `keys`.

---

## 2. Funcionalitats a preservar (i com es proven)

| Funcionalitat | On és | Com es prova |
|---|---|---|
| Pintar la pantalla (9 disposicions, 8 temes) | `src/ui.cpp`, `src/theme.cpp` | `tools/captura_pantalla.py`, `tools/test_tema.py` |
| Protocol sèrie (CFG/S/T/B/… + icones amb ack) | `src/maclink.cpp`, `mac/bridge.py` | `tools/test_*.py` |
| Icones a la SD (pujada, LRU, favicons, apps) | `src/icons.cpp`, `src/sdcard.cpp` | `tools/test_launcher.py` |
| Tàctil, menú, ajustos, numpad, Bluetooth | `src/touch.cpp`, `src/keys.cpp` | `tools/test_tecles.py`, `tools/test_menu.py` |
| Pestanyes i favorits del navegador | `bridge.py` | `/tmp/prova_favorits.py` |
| Avisos (notificacions del Mac) | `bridge.py` + `ui.cpp` (bàner) | `/tmp/baner_test.py` |
| Repòs, brillantor, tema automàtic | `ui.cpp`, `bridge.py` | `/tmp/prova_e2e.py` |
| Panell web (config, icones, apps, estat) | `mac/panel.html` | `curl /api/state` + manual |

**Regla d'or:** el format que viatja pel port sèrie **no es toca** sense una
estratègia de compatibilitat. El firmware és el que té menys marge de canvi.

---

## 3. Problemes detectats (verificats al codi)

### 3.1 Portabilitat (bloquejant per distribuir)

1. **`port` amb ruta local** (`/dev/cu.usbserial-1420`) dins de la configuració:
   es desa amb el disseny, així que un altre usuari rep un port que no existeix.
2. **`mac/panel.log`, `mostra_*.png`, `preview_*.png`** a l'arrel: brossa de
   treball mesclada amb el producte.
3. Cap **versió de format** ni migracions: qualsevol canvi futur trenca les
   configuracions desades.
4. Cap manera d'**exportar/importar** un disseny.

### 3.2 Model de dades

5. Els elements **no tenen identitat**: un gadget és una cadena i un boto un
   objecte; no hi ha `id` estable, ni tipus, ni visibilitat comuna.
6. La **posició no es guarda** (es dedueix de l'ordre): no es pot oferir
   "col·loca-ho aquí" sense un model nou.
7. La **validació és inexistent**: un `layout` desconegut, un tema fora de rang
   o 40 botons arriben a la placa i es comporten de manera impredictible.

### 3.3 Interfície

8. La pestanya "Pantalles" és una **llista de formularis** + una previsualització
   de només lectura: no es pot clicar res ni veure què és cada element.
9. La previsualització era un `<canvas>` de ~170 línies amb la geometria
   **reimplementada a mà**, que ja no coincidia amb el firmware.
10. 15 seccions en 5 pestanyes, sense jerarquia: l'editor no és el centre.
11. Els 12 botons desactivats de "Principal" són brossa que el firmware ignora.

### 3.4 Firmware (arreglat en aquesta sessió)


---

## 4. Arquitectura objectiu

**Decisió: no es canvia de tecnologia en aquesta fase.** El panell ja és
HTML/CSS/JS sobre un servidor local de Python, i això dona: reutilització total
de la interfície, zero instal·lació, i accés directe als serveis del Mac des del
Python (que és on han de viure: sèrie, AppleScript, PyObjC). La migració a un
contenidor d'escriptori es valora a la fase F, amb costos.

```
mac/
  panel_model.py     ◄── NOU: l'únic lloc on es decideix què és una configuració
                         vàlida (catàleg, normalització, migracions, portabilitat)
  panel_server.py        servei HTTP: estat, config validada, model, export/import
  bridge.py              pont sèrie + integració amb el Mac
  panel.html             banner + pestanyes + EDITOR VISUAL
docs/
  ROADMAP.md         ◄── aquest document
```

**Capa de model:** `panel_model.py` és la font de veritat. El navegador no
duplica regles: les demana a `GET /api/model`.

**Separació dades / representació:** la configuració desada descriu **què hi ha**
(pantalles, elements, accions); **com es pinta** ho decideix el firmware
(`layout()`), i l'editor ho **simula** amb les mateixes fórmules.

---

## 5. Fases

| Fase | Contingut | Estat |
|---|---|---|
| **A** | Auditoria i pla (aquest document) | ✅ feta |
| **B** | Model de dades + validació + migracions + portabilitat | ✅ feta |
| **C** | Editor visual: simulador fidel + biblioteca + propietats | ✅ 1a iteració |
| **D** | Banner, navegació per pestanyes i identitat visual | ⏳ següent |
| **E** | Graella automàtica, posicions fixes, apps i favorits a l'editor | ⏳ |
| **F** | Empaquetat, llicències, actualització de firmware, multi-plataforma | ⏳ |

---

## 6. Criteris de validació

- `python3 tools/test_model.py` → **tot OK** (migracions, límits, portabilitat).
- `pio run` → compila.
- El panell respon a `http://127.0.0.1:8770` i serveix l'editor.
- Desar una configuració dolenta **avisa** i **desa la versió arreglada**.
- La placa rep exactament el mateix format de sempre.
- `tools/test_model.py` no necessita ni placa ni pont.

---

## 7. Decisions tècniques (justificades)

1. **El format sèrie no es toca.** El firmware continua llegint `widgets`
   (cadenes) i `buttons` (objectes); el model nou hi **converteix**.
2. **Camps nous opcionals + `version`.** Una configuració vella es migra sola en
   carregar-la; l'usuari no ha de fer res.
3. **Normalitzar, no rebutjar.** Un valor dolent es corregeix (o cau al defecte)

---

## 8. Què s'ha fet en aquesta sessió

**Firmware (3 bugs reals, tots verificats amb captures de la pantalla real):**

| Bug | Causa | Solució |
|---|---|---|
| Gargots sota la capçalera | TFT_eSPI pinta text fora de la pantalla i deixa la finestra del controlador invàlida | `marqueeCopia()`: la marquesina es pinta **caràcter a caràcter** i només els que hi caben sencers |
| Text amb mida d'una altra font | la caché `gFontAra` i les mètriques globals de TFT_eSPI podien divergir | `setFontN()` **verifica l'alçada real** de la font carregada |
| Glifs equivocats | `font_b` tenia la taula **desordenada** i TFT_eSPI fa cerca binària | `fes_fonts.py` **ordena** els glifs; fonts regenerades |

**Model de dades (nou):** `mac/panel_model.py` — catàleg (9 gadgets, 9
disposicions, 6 tipus d'acció), normalització, migració v1→v2, export/import
portable, `valida()`.

**Servidor:** `/api/config` valida i torna la configuració arreglada + avisos;
`/api/model` (catàleg), `/api/elements?p=N` (elements tipats), `/api/exporta`,
`/api/importa`.

**Editor visual:** la pestanya Pantalles ara té un **simulador clicable** amb la
geometria del firmware (capçalera, barra de navegació, gauges, files de gadgets i
graella de botons), selecció, graella d'alineació, zoom, **biblioteca** per
afegir gadgets i botons, **propietats** de l'element seleccionat i
**arrossegar per reordenar**.

**Proves:** `tools/test_model.py` (40 comprovacions: migració, límits,
portabilitat, disc) — **tot OK**.

---

## 9. Següent tasca recomanada (fase D)

1. **Banner i pestanyes**: agrupar les 15 seccions en les 7 pestanyes objectiu
   (Pantalla, Aplicacions, Favorits, Shortcuts, Utilitats, Dispositiu i
   firmware, Configuració) amb un banner compacte (identitat, estat de connexió,
   configuració, navegació ràpida, ajuda). Les pestanyes sense contingut han de
   dir-ho clarament, no inventar-se funcions.
2. **Posicions explícites** (fase E): aprofitar el camp `pos` que el model ja
   valida per poder fixar un element on l'usuari el deixi anar, i que el
   firmware ho respecti (requereix canviar `layout()` amb compatibilitat).
3. **Exportar/importar des de la interfície** (els endpoints ja hi són).
4. **Neteja del repo**: treure `panel.log`, `mostra_*.png` i `preview_*.png`
   de l'arrel i afegir-los al `.gitignore`.
5. **Empaquetat** (fase F): valorar un `.app`/instal·lador i l'actualització de
   firmware des del panell (amb validació del dispositiu abans de flashejar).

   i s'avisa; rebutjar deixaria el panell sense poder desar res.
4. **La geometria és compartida.** Les constants del simulador (`F` a
   `panel.html`) porten el nom de les del firmware; si canvien allà, aquí també.
5. **El simulador és DOM, no canvas.** És l'única manera raonable de poder
   clicar, seleccionar i arrossegar elements sense reimplementar un editor.
6. **Res de xarxa.** El servidor escolta només a `127.0.0.1`; les accions
   s'executen només quan l'usuari les demana explícitament (cap ordre arbitrària
   vinguda d'un widget).

12. **Gargots sota la capçalera**: TFT_eSPI corromp la finestra d'escriptura del
    controlador quan es pinta text que surt de la pantalla (la marquesina).
13. **Caché de fonts insegura**: `gFontAra` podia quedar desincronitzada de les
    mètriques globals de TFT_eSPI → text amb la mida d'una altra font.
14. **`font_b` desordenat**: TFT_eSPI cerca els glifs amb cerca binària i el
    generador els escrivia en l'ordre d'un `set` de Python → glifs equivocats.

- El **repartiment** (on cau cada element) **no es guarda**: el calcula el
  firmware a cada `layout()`.
