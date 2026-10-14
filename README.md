# Mac Panel

Pantalla d'estat del Mac i **tauler de shortcuts** en una placa ESP32 amb pantalla
de 4" (LCDWiki **E32R40T** / ESP32-32E, panell **ST7796S 320×480** vertical, tàctil
**XPT2046**). El Mac envia el seu estat pel port sèrie USB i rep les comandes dels
botons que es premen a la pantalla.

```
   ┌──────────────┐   USB sèrie 115200      ┌────────────────────┐
   │     Mac      │ ──────────────────────► │      ESP32-32E     │
   │ panel_server │   S cpu=.. mem=.. ...   │  ST7796S 320x480   │
   │  (Python)    │ ◄────────────────────── │  + tàctil XPT2046  │
   └──────────────┘   C media_play ...      └────────────────────┘
```

## Maquinari

| Component | Detall | Pins |
|---|---|---|
| MCU | ESP32-WROOM-32E | — |
| Pantalla | ST7796S 320×480 (HSPI) | MISO 12 · MOSI 13 · SCLK 14 · CS 15 · DC 2 · RST −1 · BL 27 |
| Tàctil | XPT2046 resistiu (HSPI) | CS 33 · IRQ 36 |
| LED RGB | ànode comú (actiu baix) | R 22 · G 16 · B 17 |
| USB-sèrie | xip **CH340** (`/dev/cu.wchusbserial*`) | 460800 pujada / 115200 monitor |

La configuració de maquinari és la mateixa que la validada al projecte *Tamagoxi*,
així que funciona a la placa sense ajustos (vegeu `include/pins.h` i
`include/tft_setup.h`).

## Què fa la pantalla

- **Pantalla d'inici**: en engegar surt el **logo** (`MP` en una placa arrodonida
  amb un anell d'HUD), el nom del producte i una **barra de càrrega** que va
  avançant a cada pas de la inicialització (LED, tàctil, targeta SD,
  configuració, historial, xarxa). Serveix també per veure que la placa està
  fent mentre arrenca.
- **Capçalera**: hora del Mac · nom de l'equip · indicador `LINK` / `NO LINK` en
  una pastilla amb puntet de color. Si el nom de l'equip no hi cap, **no
  s'escurça**: va passant de costat a costat (marquesina), amb una aturada al
  començament de cada passada perquè es pugui llegir.
- **Files d'estat** (les que triïs al panell): CPU, RAM, Disc, Bateria, Xarxa,
  Load average, Temps ences, Hora, Nom del Mac. Les que són percentatge porten
  una barra rodona amb puntet de color.

> **Com es calcula la CPU**: es llegeixen els **comptadors del nucli** (Mach,
> `host_statistics`) i es fa la diferencia entre aquesta lectura i l'anterior, o
> sigui que és el consum **real d'aquest instant**. Amb `ps -o %cpu` sortia un
> valor molt més baix, perquè cada procés hi porta la *mitjana* des que va
> arrencar, no el que està consumint ara.
- **Graella de botons** (shortcuts) de 3 columnes que executen accions al Mac.
- **Menú** (☰, a dalt a l'esquerra) amb **tres pestanyes**: **Pantalles**
  (saltar a qualsevol pantalla), **Ajustos** (tot el que es pot configurar des
  de la placa) i **Sobre** (versió del firmware, estat i memòria).
- El **LED RGB** es posa verd amb enllaç i vermell sense Mac.

La configuració es desa a **SPIFFS** (la partició de 960 KB que ja ve amb la
taula de particions estàndard): si el Mac no hi és, la pantalla manté l'última
configuració. No s'hi fa servir la NVS perquè és petita (20 KB) i el WiFi i el
Bluetooth ja n'ocupen bona part.

### El menú (☰)

Ocupa tota la pantalla i té tres **pestanyes** a dalt (es pot canviar de
pestanya tocant-la, i arrossegar el dit per moure's per la llista):

| Pestanya | Què hi ha |
|---|---|
| **Pantalles** | la llista de pantalles, amb la icona i la disposició de cadascuna; la pantalla actual surt destacada |
| **Ajustos** | una fila per ajust, amb el **valor actual** a la dreta |
| **Sobre** | informació del firmware i de l'estat (nomes es mira) |

### Ajustos des de la mateixa pantalla

`☰` → **Ajustos**. Es canvia **tocant la fila** (cada toc passa al valor
següent) i s'aplica a l'instant: la placa ho envia al Mac, que ho apunta al
`panel_config.json` i torna a enviar la configuració.

| Fila | Valors |
|---|---|
| **Brillantor** | 10 % → 100 % (passos de 10 %) |
| **Tema** | Fosc · Clar · Neo · Grafite · Pastel · HUD |
| **Tema automàtic** | si / no (el tema segueix el clar/fosc del Mac) |
| **Orientació** | vertical ⇄ horitzontal |
| **Repòs de pantalla** | mai · 30 s · 1 · 2 · 5 · 10 · 30 min |
| **Rellotge si inactiu** | mai · 1 · 2 · 5 · 10 · 20 · 30 min · 1 h |
| **Navegació** | barra + lliscar · només barra · només lliscar · sense navegació |
| **Configuració de fàbrica** | torna tot als valors per defecte |
| **Reinicia la placa** | reinicia l'ESP32 |
| **Tanca el menú** | torna a la pantalla anterior |

> Les dues files que no es poden desfer (**fàbrica** i **reinicia**) surten
> destacades en groc.

### Sobre

`☰` → **Sobre** ensenya, d'un cop d'ull: la **versió del firmware**, el model de
xip, la **memòria lliure**, si hi ha **enllaç** amb el Mac (i com es diu), la
**IP del WiFi**, quantes **icones** hi ha a la targeta SD, quantes **apps** té
obertes el Mac, quantes **pantalles** té configurades, l'**hora** de la placa i
quant fa que està encesa.

### Repòs (estalvi de pantalla)

- **Si el Mac entra en repòs** (o apaga la pantalla), la pantalla s'apaga. El Mac
  ho detecta amb `pmset -g powerstate IODisplayWrangler` i ho envia al camp
  `dsp` de la línia d'estadístiques.
- **Quan el Mac es desperta**, la pantalla s'encén sola.
- **Sense enllaç** durant 45 s (Mac dormit o apagat) també s'apaga.
- **Tocant la pantalla** s'encén. El primer toc només la desperta: no activa cap
  botó (així no prems res sense voler).
- **Per inactivitat**: opcional, des de *Ajustos*. Per defecte és **mai** (0),
  perquè si estàs treballant amb el Mac la pantalla no s'ha d'apagar: ja
  s'apagarà quan ho faci la del Mac.

### Rellotge automàtic quan el Mac està inactiu

Si el Mac no rep cap input durant **X minuts** (configurable al panell, per
defecte 5), la placa passa tota sola a una **pantalla de rellotge amb la
previsió del temps**: hora enorme, data, el temps d'ara i els pròxims dies.

- Es detecta amb `ioreg -c IOHIDSystem` → `HIDIdleTime` (segons que fa que no
  es toca ni el teclat ni el ratolí) i s'envia al camp `idl` de les estadístiques.
- **Mentre el rellotge és a la pantalla, la pantalla es queda encesa**: si no fos
  així, en apagar-se la pantalla del Mac també s'apagaria la nostra i el rellotge
  no es veuria mai. Aquesta és l'única excepció a la regla de seguir el Mac.
- **Quan tornes a tocar el Mac**, la placa torna sola a la pantalla on eres.
- **Qualsevol toc a la placa** també el treu (i no activa cap botó).
- Es pot desactivar posant-ho a *Mai*.

### Sense enllaç amb el Mac

Quan la placa deixa de rebre estadístiques del Mac durant uns segons (el cable
s'ha desendollat, el Mac s'ha apagat, el pont no s'està executant...), **no té
sentit ensenyar pantalles amb dades velles ni botons que no poden fer res**. En
aquest cas la placa passa tota sola a un mode reduït:

- **Surt el rellotge** (la mateixa pantalla de repòs, amb la indicació
  *sense enllaç* a dalt).
- **El menú només té un apartat: Ajustos**. Les pantalles no hi són perquè no
  s'hi pot navegar.
- **No hi ha barra de navegació** ni es pot lliscar per canviar de pantalla.
- **Els botons no responen**: tocar-los no envia cap comanda ni cap tecla.
- **Els ajustos de la placa sí que funcionen** (tema, brillantor, repòs,
  orientació), que és l'únic que té sentit sense Mac.
- Quan l'enllaç torna, **es recuperen les pantalles normals tot sol**.

> **L'hora no es queda congelada.** Quan hi ha enllaç, l'hora ve del Mac i se
> sincronitza cada segon. Quan no n'hi ha, la placa **la segueix comptant ella
> mateixa** amb `millis()`, així que el rellotge continua essent correcte. El
> cristall de l'ESP32 va sobrat per a unes quantes hores.

## Avisos del Mac (notificacions)

Les notificacions de macOS surten a la placa com un **bàner**, igual que a la
cantonada del Mac: el nom de l'aplicació, el títol en negreta i una línia de
text. Surt 8 segons i es pot treure tocant la pantalla.

Com funciona: el Centre de Notificacions de macOS desa cada avís en una base de
dades SQLite dins del contenidor de l'usuari:

```
/private/var/folders/…/0/com.apple.notificationcenter/db2/db
```

Cada fila de la taula `record` porta un `bplist` amb `req` → `titl` (títol),
`subt` (subtítol), `body` (cos) i l'aplicació (per la taula `app`). El pont va
llegint les files **noves** (per `rec_id`) cada 2 segons i les envia:

```
N Correu|LALIGA|Plazas limitadas: prepara ELCLÁSICO…
```

- Només s'envien les que tenen `presented = 1` (les que el Mac ha mostrat de
  debò) i es descarten els avisos interns del sistema (`_system_center_:…`).
- Els camps es netegen (sense `|` ni salts de línia) i s'escurcen perquè càpiguen.
- Al panell web hi ha la llista de les últimes que han arribat i un botó per
  aturar-les o fer-ne una de prova.

> **No cal cap permís especial**: la base de dades del contenidor de l'usuari és
> llegible pel mateix usuari. Si algun dia macOS la protegeix, caldrà donar
> *Accés total al disc* al Terminal.

## Aplicació activa → pantalles automàtiques

El pont detecta **quina aplicació estàs fent servir** amb `lsappinfo` (una eina
del sistema que **no** necessita permisos d'Accessibilitat, al contrari que
AppleScript) i l'envia a la placa:

```
A com.microsoft.VSCode|Code
```

Cada pantalla pot tenir una llista d'**apps que la fan sortir** (bundle ids).
Quan canvies d'aplicació, la placa salta tota sola a la pantalla que li hagis
assignat: allà hi pots tenir **les dreceres d'aquella app** (botons amb `keys`).

Al panell, a *Aplicació que estàs fent servir*, surt l'app actual i una fila per
pantalla amb el camp d'apps. El botó **`+ Nom`** hi afegeix l'app que estàs fent
servir en aquell moment, sense haver d'escriure el bundle id.

Exemples de bundle ids:

| App | Bundle id |
|---|---|
| VS Code | `com.microsoft.VSCode` |
| Safari | `com.apple.Safari` |
| Chrome | `com.google.Chrome` |
| Terminal | `com.apple.Terminal` |
| Finder | `com.apple.finder` |
| Slack | `com.tinyspeck.slackmacgap` |
| Figma | `com.figma.Desktop` |

## Instal·lació

Només cal **pyserial** (la resta és Python estàndard i ordres natives de macOS):

```bash
python3 -m pip install -r mac/requirements.txt
```

## Posar-ho en marxa

1. **Puja el firmware** a la placa (amb el port sèrie lliure):

   ```bash
   pio run -t upload          # o: ~/.platformio/penv/bin/pio run -t upload
   ```

2. **Arrenca el panell de control** al Mac. Tens tres maneres:

   **a) Accés directe a l'Escriptori (el més fàcil):** fes doble clic a
   **`Mac Panel`** de l'Escriptori. S'obre el navegador sol i no apareix cap
   finestra de Terminal. Per aturar-lo, doble clic a **`Atura Mac Panel`**.

   > Si no els tens a l'Escriptori (o has mogut el projecte de lloc), regenera'ls amb:
   > ```bash
   > bash mac/crea-llancadors.sh
   > ```

   **b) Des del Finder:** obre la carpeta `mac/` i fes doble clic a
   **`EngegaPanell.command`**.

   **c) Des del terminal:**

   ```bash
   python3 mac/panel_server.py
   ```

   El panell és a **`http://127.0.0.1:8770/`** (el navegador s'obre sol).

   > ⚠️ La URL és `127.0.0.1` **sense** `www.` — `http://www.127.0.0.1:8770` no
   > funciona perquè `www.127.0.0.1` no és cap adreça real.

   El pont sèrie s'hi connecta sol (busca `/dev/cu.usbserial*` o
   `/dev/cu.wchusbserial*`); si cal, tria el port a la barra de dalt.

3. Fes clic a **Desa i envia a la pantalla**.

Opcions útils:

```bash
python3 mac/panel_server.py --port /dev/cu.wchusbserial1410   # forçar el port
python3 mac/panel_server.py --headless                        # només el pont, sense web
python3 mac/panel_server.py --no-browser                      # no obrir el navegador
```

## El panell de control

- **Pantalla**: marca quins widgets surten i ordena'ls amb ▲ ▼.
- **Shortcuts**: afegeix/treu botons, canvia'n el text (màx. 12 caràcters), tria
  l'acció i ordena'ls. Cada botó té un **▶** per provar-lo al Mac sense tocar la placa.
- **Arrossegar i deixar anar** (drag & drop):
  - **Icones**: a dalt de tot de la llista de botons hi ha una **paleta amb totes
    les icones** de la placa. Arrossega'n una sobre un botó i se li assigna.
  - **Reordenar**: arrossega un botó pel símbol **⠿** (a l'esquerra) i deixa'l
    anar damunt d'un altre: una línia blava indica on quedarà.
  - Els botons ▲ ▼ segueixen funcionant per moure'ls d'un en un.
- **Estat del Mac (en viu)**: CPU, RAM, disc, bateria, **corrent** (si està
  endollat o amb bateria, amb el text en verd quan ho està), xarxa, càrrega i
  **temps d'inactivitat**.
- **Previsualització**: una aproximació de com quedarà la pantalla de 320×480.
- **Desa i envia a la pantalla** desa `mac/panel_config.json` i envia la
  configuració a l'ESP32 pel sèrie.

També s'hi configura la **navegacio** (barra + lliscar / només barra / només
lliscar / res) i el **temps de repos** de la pantalla.

### Els apartats es poden plegar, moure i redimensionar

El panell té 11 apartats i queda molt llarg, així que:

- **Plegar**: fes clic a qualsevol títol i s'amaga el contingut (la fletxa ▾
  gira). El botó **Plegar-ho tot** ho fa de cop.
- **Moure**: arrossega la nansa **⠿** de la dreta del títol. Una línia blava
  indica on quedarà l'apartat.
- **Amplada**: el desplegable **Columnes** (50/50, 65/35, 35/65, 75/25, una sola
  columna) o arrossega la **nansa vertical** entre les dues columnes.
- **Ordre original**: torna a l'ordre de sempre.

Tot queda desat al `localStorage` del navegador, així que la propera vegada ho
trobes tal com ho vas deixar. No afecta la placa: és només com es veu el panell.

## Shortcuts

Cada botó executa una acció al Mac. Les accions d'estoc són:

| Categoria | Accions |
|---|---|
| Mitjans | `media_prev`, `media_play`, `media_next` (app Música) |
| Volum | `vol_down`, `vol_up`, `mute` |
| Apps | `app_terminal`, `app_safari`, `app_vscode`, `app_music`, `app_finder` |
| Sistema | `sys_lock` (bloquejar), `sys_sleep` (dormir), `sys_shot` (captura), `sys_dark` (clar/fosc) |

### Afegir una acció pròpia

Al panell, tria **Personalitzat...** al desplegable d'un botó i escriu-hi una
**ordre de shell** (s'executa tal qual). Exemples:

| Text del botó | Ordre |
|---|---|
| `MAIL` | `open -a Mail` |
| `MUTE` | `osascript -e 'set volume output muted true'` |
| `FOCUS` | `shortcuts run "Mode feina"` |
| `Xcode` | `open -a Xcode` |

### Afegir una acció d'estoc nova (al codi)

Edita el diccionari `ACTIONS` de `mac/bridge.py` i afegeix l'id corresponent a
`ACTION_IDS` de `include/panel_config.h` (així el firmware la reconeix com a
d'estoc). Les accions personalitzades **no** necessiten tocar el firmware: només
envien `C custom:N` i l'ordre viu al Mac.

## Enllac per WiFi (alternativa al cable)

La placa pot parlar amb el Mac **per WiFi** en comptes del port sèrie. Fa servir
**exactament el mateix protocol** (les mateixes línies de text), així que tot
funciona igual (estadístiques, configuració, botons, icones).

### Posar-lo en marxa (des del panell)

A la secció **"Enllaç amb la placa"**:

1. Escriu el **nom de la xarxa** i la **contrasenya** de casa teva.
2. Clic a **"Envia a la placa"** (va pel cable; la placa es connectarà a la WiFi).
3. Canvia el **Mode** a **WiFi** i clic a **"Aplica i reconnecta"**.

La placa s'anuncia per **mDNS** com a **`macpanel.local`**, així que el Mac no cal
que sàpiga la IP. Si el mDNS no et funciona, posa la IP directament al camp
**Host** (la trobaràs al registre: `[NET] WiFi OK: IP 192.168.1.xx`).

### Notes

- El **WiFi i el Bluetooth comparteixen ràdio** a l'ESP32. Com que el teclat BLE
  és de baix ample de banda, conviuen bé; si notes el teclat lent, torna al cable.
- Amb WiFi, **el cable només cal per carregar firmware**.
- Si el Mac no troba `macpanel.local`, comprova que estiguis a la mateixa xarxa.

## Temes i estetica

### Temes de color

Hi ha **6 temes** que es canvien des del panell (selector **Tema**, al costat de
l'orientacio) o des de *Ajustos* a la mateixa pantalla, i s'apliquen a l'instant:

| # | Tema | Estil |
|---|---|---|
| 0 | **Fosc** | Blau-nit |
| 1 | **Clar** | Fons clar, text fosc |
| 2 | **Neo** | Negre amb accents magenta/cian |
| 3 | **Grafite** | Gadget sobri amb accent teal |
| 4 | **Pastel** | To suau |
| 5 | **HUD** | Cian sobre negre, estil panell de control (per defecte) |

### Tema automàtic (clar/fosc segons el Mac)

La placa pot **seguir el mode clar/fosc del Mac**. El pont el detecta amb
`defaults read -g AppleInterfaceStyle` i l'envia al camp `dk` de la línia
d'estadístiques (`dk=1` fosc, `dk=0` clar).

Amb el tema automàtic activat es trien **dos temes**: un per quan el Mac està en
fosc i un per quan està en clar (es configuren al panell, o des d'*Ajustos* amb
els botons **Tema <** / **Tema >**, que canvien el de l'aparença que té el Mac
**en aquell moment**). Quan canvies d'aparença al Mac — o prems l'acció
**Clar/Fosc** (`sys_dark`) d'una pantalla de botons — la placa canvia de tema
tota sola.

> Sense enllaç (o abans de saber com té el Mac l'aparença) mana el **tema
> manual**, així la pantalla no es queda mai amb colors que no toquen.

Al `panel_config.json` són les claus `theme_auto`, `theme_dark` i `theme_light`;
cap a la placa viatgen com a `ta`, `td` i `tl` dins del `CFG`.

Cada tema té **dos colors de fons** (`bg` i `bg2`) i el fons es construeix amb
**cinc capes**, totes amb `alphaBlend` sobre `bg` perquè s'adaptin a qualsevol
tema:

1. **Degradat vertical** amb el centre més clar (efecte de *glow*).
2. **Trama de punts amb halo radial**: més brillants al centre i més fluixos a
   les vores, com un HUD.
3. **Graella en perspectiva** a la part de baix, amb **línia d'horitzó**: és el
   detall que dona l'aire futurista (un terra infinit).
4. **Cantons de reticle**, com els marcs dels HUD de les pel·lícules.
5. **Marques de regla** a les dues vores.

Nomes es dibuixa **en canviar de pantalla** (no a cada refresc): són unes 40
línies i 600 punts, uns 15 ms.

> Per provar canvis de fons **sense gravar-los a la placa**, hi ha
> `tools/preview_fons.py`: replica exactament el mateix algorisme (fins i tot
> l'`alphaBlend` de TFT_eSPI) i desa un PNG amb una aproximació del contingut a
> sobre, per poder comparar.
>
> ```bash
> python3 tools/preview_fons.py        # preview_fons_actual_v.png i _nou_v.png
> python3 tools/preview_fons.py --h    # tambe en horitzontal
> ```

### Mides de lletra i superposicions

Hi ha **quatre mides** i cadascuna té un paper fix, perquè tot quedi coherent:

| Font | Mida | Es fa servir a |
|---|---|---|
| `S` | 9 pt | etiquetes, text secundari, capçalera, cos del bàner |
| `M` | 12 pt negreta | **valors** dels gadgets, noms de pantalla, títol del bàner |
| `L` | 18 pt negreta | temperatura, números dels gauges mitjans |
| `B` | 24 pt negreta | hora del rellotge, números dels gauges grans |

**Regla d'or: res es dibuixa mai a cegues.** Cada text es mesura abans de
pintar-lo i, si no hi cap, s'escurça o s'adapta:

- **Capçalera**: la pastilla `LINK` es mesura primer, l'hora després, i el nom
  del Mac s'escurça amb `...` a l'espai que queda de veritat entre tots dos.
  Abans es dibuixava centrat i un nom com `MacBook_Pro_de_Jaume` (163 px a font
  `S`) tapava l'hora. Els guions baixos es converteixen en espais, que es
  llegeix millor.
- **Gauges**: el gruix de l'anell i el disc del mig **s'adapten al radi**
  (`gaugeGeom()`). Un gauge petit (r=37) deixava un disc de 28 px i el número a
  18 pt en demanava 44: se'n sortia i tapava l'anell. Ara la lletra s'escull
  provant de gran a petita fins que el text hi cap, i el `%` només es deixa
  fora si ni amb la lletra més petita hi cap. El número s'esborra amb un
  `fillCircle` del disc interior, així **mai** no toca l'anell ni el resplendor.

A `tools/mides_fonts.py` hi ha un extractor que llegeix les taules de glifs de
TFT_eSPI i calcula les amplades reals de cada text, per comprovar-ho sense
haver-ho de gravar a la placa.

### Sense parpelleig (com es repinta)

Un TFT per SPI es veu **parpellejar** si a cada actualitzacio s'esborra una zona
i s'hi torna a dibuixar a sobre (es veu el fons buit entremig). Com que les dades
del Mac arriben **un cop per segon**, aixo passava a totes les pantalles.

La regla que se segueix a `src/ui.*` es: **cada pixel es pinta un sol cop per
fotograma**, mai esborrar-i-redibuixar.

| Element | Com s'evita el parpelleig |
|---|---|
| **Files de gadgets** | el marc de la targeta nomes es pinta en entrar a la pantalla; despres s'actualitza **nomes el valor** (esborrant exactament el requadre del text anterior) |
| **Mini-grafics** | cada columna es pinta d'un sol cop: primer el buit de dalt i despres la barra |
| **Barres LED** | nomes es repinten els 22 segments (molt rapid) |
| **Gauges** | l'arc es repinta **nomes del valor vell al nou** (si puja es pinta el tros nou, si baixa es torna a deixar de fons). El numero esborra nomes el disc del mig |
| **Grafics** | cada columna de la grafica es pinta d'un sol cop (buit de dalt + area + punt de la linia); la quadricula va a sobre amb puntets |
| **Rellotge** | nomes es repinta quan canvia la firma (hora, data, meteo o previsio) |

> El degradat de l'arc del gauge depen de l'**angle** i no del valor: aixi
> repintar nomes un tros queda sempre del mateix color que la resta.

### Detalls visuals de tota la interficie

| Element | Com es dibuixa |
|---|---|
| **Capçalera** | filet d'accent fi sota la barra, pastilla de LINK amb puntet de color |
| **Files de gadgets** | targeta amb vora, puntet de color, **sparkline** al mig i **barra segmentada** estil LED a baix |
| **Botons** | cantonades de 12 px, filet de relleu a dalt, **placa fosca darrere la icona** (queden com tecles) i accent en prémer |
| **Teclat numèric** | els dígits en **font gran** i els operadors (`+ - * / = C`) en color d'accent |
| **Gauges** | anells concèntrics, marques radials, halo, arc amb degradat |
| **Gràfics** | quadrícula horitzontal i vertical, àrea, **halo sota la línia** i **puntet a l'extrem** |
| **Rellotge** | hora gran, data en pastilla, meteo amb icona i la previsió en **targetes arrodonides** |
| **Menú** | pantalla completa, files de 38 px, scroll i fletxes |

Els colors de suport (halos, trames, degradats) es calculen amb `alphaBlend()`
sobre els colors del tema, així que **tots els temes queden bé** sense afegir
colors nous a la paleta.

Els colors son **variables en temps d'execucio** (`src/theme.*`), aixi que no cal
refer el firmware per canviar-los.

### Fonts suaus

La UI fa servir les fonts **FreeSans** de TFT_eSPI (antialiasades) en comptes de
les fonts de mapa de bits: molt mes agradables a la vista. Quatre mides:

- **S** (`FreeSans9pt`) — capcalera, etiquetes, botons
- **M** (`FreeSansBold12pt`) — valors i titols
- **L** (`FreeSansBold18pt`) — temperatura, numeros dels gauges mitjans
- **B** (`FreeSansBold24pt`) — el rellotge gran

> Aquestes fonts només cobreixen **ASCII** (`0x20..0x7E`), així que caràcters com
> el símbol de graus (`°`) no hi són: sortirien en blanc. Per això la temperatura
> es dibuixa amb un **cerclet** pintat a mà (`drawTemp()`), que a més queda més
> fi que la lletra. El número i el `°C` es col·loquen amb datum de **línia base**
> (`L_BASELINE`) perquè no es trepitgin mai, sigui quin sigui el valor.

### Brillantor del Mac

Dos botons d'estoc per apujar/abaixar la **brillantor de la pantalla del Mac**
(`bright_up`, `bright_down`).

## Problemes coneguts i solucions

### macOS demana "prem una tecla" en emparellar el teclat Bluetooth

Es l'**assistent de configuració de teclat** de macOS, que surt el **primer cop**
que connectes un teclat nou (per identificar la disposicio ANSI/ISO/JIS).

- Fes clic a **Omet** (Skip) o tanca la finestra: **el teclat funciona igual**.
- Tambe pots satisfer-lo prement el boto corresponent a la pantalla (per exemple
  el **Numpad**, que envia digits reals).
- Nomes surt un cop: despres macOS ja recorda el teclat.

### El tactil no responia en horitzontal

Arreglat: les coordenades del tactil ara es giren amb l'orientacio del display.

### La barra de baix se solapava amb els botons

Arreglat: s'ha substituit per un **menu desplegable a dalt** (boto ☰) i el
repartiment d'espai reserva primer els botons.

### El WiFi i el Bluetooth alhora

Comparteixen radio. Si el teclat va lent, canvia l'enllac a **cable** des del
panell (seccio "Enllaç amb la placa").

### El Bluetooth es menja mes de 100 KB de memoria

La pila de Bluetooth de l'ESP32 ocupa mes de **100 KB** i deixa el heap molt
just (uns 20 KB, i molt fragmentats). Com que la configuracio que envia el Mac
pot fer varis kilobytes, **no es pot fer servir una llibreria JSON normal**:
ArduinoJson necessitava ~10 KB i la lectura fallava amb `NoMemory` tot i que el
JSON nomes fa 3 KB. I, pitjor encara, qualsevol solucio que es quedi memoria
permanent fa que el Bluetooth no pugui arrencar (necessita ~119 KB lliures).

Solucio: **`src/cfg_parse.h`**, un parser del JSON escrit a ma que **no demana
ni un byte de memoria dinamica** — va omplint la configuracio directament. Aixi
la configuracio s'aplica sempre, passi el que passi amb la memoria, i el
Bluetooth pot encendre's quan vulgui.

Com a extra, tambe s'encen el Bluetooth amb una mica de retard
(`BT_START_DELAY_MS`, 6 s) i abans de fer-ho es comprova que hi hagi prou
memoria contigua (`BT_MIN_FREE_HEAP`): es millor quedar-se sense tecles que no
pas quedar-se en bucle de reinicis.

*(Al registre hi havia hagut `[MAC] JSON llegit (pool: 9792 de 13140 bytes)`
quan es feia servir ArduinoJson amb un pool propi. Ja no cal.)*

### El Mac enviava linies trencades en connectar

Quan el Mac obre el port, la placa es reinicia (ho fa el senyal DTR/RTS del
xip CH340). Els primers bytes que s'hi enviaven es perdien i arribaven comandes
estranyes, com ara `chg=1`. Arreglat: el Mac **no envia res** fins que la placa
no li diu "hola" (`H`), i la placa **descarta les linies amb bytes de control**
(que son el soroll del propi xip en arrencar).

## Posar les teves icones

1. Posa els PNG a **`Assets/icons/`** (64×64 o mes grans, noms en minuscules).
2. Converteix-los: `python3 tools/png2bin.py`
3. Comprova com han quedat: `python3 tools/analitza_icones.py`
4. Puja'ls a la placa: `python3 tools/puja-icones.py` (amb el panell en marxa).

O, mes facil: **des del panell**, seccio "Icones (PNG → SD)", puja'ls d'un en un.

### Com es treu el fons

El format es **RGB565 big-endian** amb el **magenta `0xF81F` com a transparent**.
El firmware, quan dibuixa una icona, canvia tots els pixels magenta pel color de
fons de destí (el boto, la targeta, el menu...), aixi que les icones queden bé
sobre qualsevol fons.

> **Compte amb l'ordre dels bytes!** El `.bin` es **big-endian** i `pushImage`
> envia els bytes tal com son (per aixo els colors es veuen bé). Pero al buffer,
> llegit com a `uint16_t` en una maquina little-endian, cada valor queda amb els
> bytes girats: per **comparar** amb el magenta o per **escriure-hi** un color
> cal girar-lo. Aixo era el motiu que les icones sortissin amb el fons magenta.

La conversio (`tools/png2bin.py`) distingeix **dos tipus d'icona**:

**Simbols** (wifi, volum, llum, play...): un dibuix sobre un fons pla, i el que
volem es que sobre el boto quedi **nomes el dibuix**.

1. **Si el PNG te canal alfa**, l'usa directament. Es el cas ideal.
2. Si no, fa un **flood fill des de les vores** amb dues condicions: el pixel ha
   de ser semblant al del costat (aixi funciona amb fons **amb degradat**) i no
   allunyar-se massa del color de fons general (aixi no s'escola dins la icona).
3. Si el detector s'ha menjat **mes del 98 %** de la imatge, es deixa la imatge
   sencera.

**Icones d'app** (Finder, Notes, Chrome, VS Code...): son **quadres arrodonits
amb fons propi**, amb el dibuix fins a les vores. Aqui el flood fill fa un
desastre: a Notes li queda nomes la tira groga, a TextEdit nomes la ploma.
Aquestes es converteixen **senceres** i nomes se'ls arrodoneixen les cantonades,
com fa el macOS.

Qui es qui ho diu **`Assets/icons/apps.txt`** (un nom per linia, `#` per
comentar). Si una icona te la veus trencada, afegeix-la-hi; si una icona d'app
la vols com a simbol, treu-la.

```bash
python3 tools/png2bin.py          # converteix (marca les que son d'app)
python3 tools/mostra_icones.py    # full de contacte: com queden a la placa
python3 tools/puja-icones.py      # les puja a la SD
```

Per diagnostico hi ha eines que diuen **per que** una icona surt malament:

| Eina | Que et diu |
|---|---|
| `tools/mostra_icones.py` | Full de contacte amb totes les icones **a 64 px i a 40 px** sobre el fons de la targeta. Es la manera mes rapida de veure quina queda malament. |
| `tools/mostra_originals.py` | El mateix, pero amb els **PNG d'origen**: per comparar abans/despres. |
| `tools/diagnostic_png.py` | Quins PNG tenen **transparència de veritat** (surten sempre bé) i quins son **opacs** (cal endevinar el fons). |
| `tools/diagnostic_cantonades.py` | Que hi ha a les **cantonades** dels PNG: si son transparents la icona ja ve retallada. |
| `tools/diagnostic_anell.py` | Prova d'endevinar quines son d'app mirant l'anell exterior. **No es fiable**: per aixo hi ha `apps.txt`. |
| `tools/analitza_icones.py` | Comprova les icones que **fa servir la configuracio**: si hi son, si son buides... |

> **Consell**: per a les icones de tipus símbol (un dibuix sobre un fons),
> el millor es un **PNG amb transparència** de veritat. Aixi no cal endevinar
> res.

> **Atencio**: les icones d'apps (Mail, Calendar, Notes, Finder...) **tenen fons
> propi** i s'ha de conservar; es correcte que no siguin transparents. Han
> d'anar a `apps.txt`.

## Pantalles modulars (pages) — `src/ui.*`

La pantalla de la placa es divideix en **pantalles** (fins a **12**), cadascuna
amb els seus gadgets i botons.

```
┌──────────────────────────────┐
│ ☰ │ 19:20   MacBook   ● LINK │  ← capçalera amb el boto de menu
├──────────────────────────────┤
│  ● CPU  ⣿⣿⣿⣿⣿⣿⣿        42%  │
│    ▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░ │
│  ● RAM  ⣿⣿⣿⣿⣿⣿          38%  │  ← gadgets amb mini-gràfic
│    ▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░░░ │
│  ● DISC ⣿⣿⣿⣿⣿⣿⣿⣿        61%  │
│    ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░ │
├──────────────────────────────┤
│  [ ⏯ ]  [ ⏭ ]  [ 🔒 ]       │  ← botons amb icones
│  [ 💤 ] [ 📸 ]  [ 🌙 ]       │
├──────────────────────────────┤
│ ‹        ● ● ○ ○ ○        ›  │  ← barra de navegacio
└──────────────────────────────┘
```

### Menu de pantalles (boto ☰)

Tocant **☰** (a l'esquerra de la capçalera) s'obre un **menu a pantalla
completa**:

```
┌────────────────────────────────┐
│ ▎Pantalles                tanca│
├────────────────────────────────┤
│ ▎⚙ Grafics           graph     │  ← pantalla actual (ressaltada)
│  ⚙ Estat             status    │
│  ⚙ Mitjans           buttons   │
│  …                             │
├────────────────────────────────┤
│   ▲     pantalla 1 de 12    ▼  │
└────────────────────────────────┘
```

- **Files grans de 38 px** amb la icona, el nom i el tipus de disposició.
- **Es pot lliscar** la llista amb el dit, o tocar les fletxes **▲ ▼**.
- Si hi ha moltes pantalles **no queda mai tallat**: en vertical se'n veuen 11 i
  en horitzontal 6 (la resta amb scroll).
- Al final hi ha **Ajustos**.

> **Nota**: abans era un desplegable petit a la cantonada i, en horitzontal, amb
> 12 pantalles quedava tallat i no s'hi podia arribar. Ara ocupa tota la pantalla.

### Navegacio entre pantalles

Es pot configurar des del panell (*Navegacio*):

| Mode | Que fa |
|---|---|
| **Barra + lliscar** (per defecte) | barra de baix **‹ ● ● ○ ›** i lliscament horitzontal |
| **Nomes barra** | nomes els botons ‹ › de la barra |
| **Nomes lliscar** | nomes el gest de lliscar el dit |
| **Sense navegacio** | nomes el menu ☰ |

- **Lliscar**: arrossega el dit horitzontalment (> 45 px). Si comences sobre un
  botó, el gest cancel·la el botó (no s'executa res).
- **Barra**: els **puntets** et diuen on ets (o `3/12` si hi ha més de 12
  pantalles).
- La barra **es reserva abans de repartir l'espai**, aixi mai no tapa cap botó.

### Com es reparteix l'espai

El firmware **reserva primer l'espai dels botons** i dona la resta als gadgets:
si una pantalla te moltes files d'estat i molts botons, les files s'apreten
(alcada minima) perque **mai** se solapin.

### Tactil i orientacio

El panell tactil es **fix** a la placa: quan el display gira (vertical ↔
horitzontal), les coordenades del tactil es giren tambe automaticament
(`Touch::setRotation`), aixi que els botons responen igual en les dues
orientacions.

### Des del panell de control

A la secció **"Pantalles"**:

- **+ Afegeix pantalla** (fins a 8).
- Canvia el **nom**, la **icona** de la pestanya i la **disposició**:
  - *Gadgets + botons* — files d'estat a dalt i botons a sota.
  - *Només botons* — tota la pantalla per als botons.
  - *Gauges circulars* — rellotges de CPU/RAM/disc/bateria (2×2) + botons.
  - *Rellotge + meteo* — hora gran, data i temps exterior amb icona.
  - *Teclat numèric* — numpad 4×4 que envia els digits per Bluetooth.
- **▲ ▼** per ordenar, **⧉** per duplicar, **✕** per esborrar.
- Fes clic a **○** per seleccionar quina pantalla edites.

### Grafics (historial)

La disposició *graph* dibuixa **grafics de linia** amb l'historial de les
ultimes **2 minuts** (120 mostres, una per segon). Es trien els gadgets de la
pantalla (CPU, RAM, Disc, Bateria, Load, Xarxa) i s'apilen:

```
┌──────────────────────────────────────────┐
│ ▎CPU                                42%  │
│    ⣀⣀⣤⣤⣤⣤⣤⣤⣤⣶⣶⣶⣶⣶⣶⣶⣤⣤⣤⣀⣀⣀⣀      │
│  min 3    mitjana 28    max 78           │
└──────────────────────────────────────────┘
```

- **Área** sota la linia, del color de la serie (CPU accent, RAM verd, disc
  groc...) i **quadricula** discontinua de fons (horitzontal i vertical).
- La linia porta un **halo** a sota i un **puntet** a l'extrem que marca on ets
  ara mateix.
- **Valor actual** gran a dalt a la dreta, i **min / mitjana / màx** de tota la
  finestra a baix.
- Els percentatges sempre s'escalen de 0 a 100; la resta (load, xarxa)
  s'adapta al màxim.
- Nomes es repinta el gràfic que ha canviat, aixi no parpelleja.

L'historial viu a `src/history.*` (buffers circulars a la RAM de l'ESP32). Amb
1, 2, 3 o 4 grafics es reparteixen sols: apilats en vertical, o en 2 columnes si
la pantalla és horitzontal i n'hi ha 3 o més.

### Mini-grafics a les files d'estat

A la disposició *status*, cada fila que tingui historial hi dibuixa una
**sparkline** al mig (el valor, la barra i el puntet de color es mantenen). Aixi
es veu la forma de l'última estona d'un cop d'ull, sense canviar de pantalla.

### Gauges

La disposició *gauges* dibuixa **rellotges circulars** amb un estil de **panell de
control** (HUD):

```
        ╭─────────────╮
      ╱  · · · · · ·  ╲        ← marques radials cada 15°
     │   ╭─────────╮   │       ← anell exterior + interior
     │  │           │  │
     │  │    42     │  │       ← halo de llum darrere l'arc
     │  │     %     │  │
     │   ╰─────────╯   │
      ╲   CPU  ·  12-78 ╱     ← etiqueta i min-màx de l'historial
        ╰─────────────╯
```

- **Anells concèntrics** fins i **marques radials** (més llargues cada 45°).
- Un **halo de llum** darrere l'arc del valor (un arc més ample i translúcid).
- L'arc té **degradat**: comença amb el color de la sèrie i acaba amb el color
  d'alerta. Així, com més valor, més "calent" es veu (i queda com els panells de
  control dels PCs).
- El **número gran** al mig (font de 24 pt als anells grans) amb el `%` petit.
- Un **puntet blanc** sobre l'anell que marca el **màxim de l'historial**.
- El **color base de l'arc** va canviant: verd < 70 %, groc < 90 %, vermell ≥ 90 %.

Com es reparteixen segons quants gauges triïs:

| Gauges | Disposició |
|---|---|
| **1** | Un **anell gran** que ocupa tota la pantalla |
| **2** | Dos costat a costat |
| **3** | Tres en una fila |
| **4** | **Un anell gran a dalt + tres de petits a sota** (com els panells de control dels PCs) |

S'actualitzen **sense parpelleig**: només es repinta el gauge que canvia.

### Rellotge i meteo

La disposició *clock* mostra l'**hora gran** (font de 48 px), el **dia i la data**,
el **temps exterior** (icona + temperatura), la **previsió de 3 dies** (icona i
max/min de cada dia) i el **proper esdeveniment de l'agenda** del Mac.

La meteo ve d'**Open-Meteo** (sense clau d'API), actualitzada cada 20 min per
Barcelona; es pot canviar a `Weather(lat, lon)` de `mac/bridge.py`. L'agenda es
llegeix del **Calendar** del Mac cada 5 min (el primer cop et demanara permis
d'automatitzacio).

### Ajustos de la placa (des del panell)

A la secció **"Ajustos de la placa"**:

- **Brillantor** — control lliscant (5-100 %) que s'aplica a l'instant.
- **Calibrar tactil** — llança l'assistent de calibratge a la pantalla de la placa.
- **Config per defecte** — torna la placa a la configuracio d'inici.
- **Reinicia la placa** — reinicia l'ESP32.

Son comandes normals (`bl 70`, `cal`, `reset`, `restart`) que van pel cable o pel
WiFi, i tambe es poden escriure a la consola serie.

### Numpad

La disposició *numpad* dibuixa un teclat 4×4 (`7 8 9 -`, `4 5 6 +`, `1 2 3 *`,
`DEL 0 . OK`) que envia cada tecla per **Bluetooth** a l'aplicació que tinguis
en primer pla.

### Launcher (apps obertes)

La disposició *launcher* mostra **les aplicacions que tens obertes al Mac** com a
botons (2 columnes) amb **la seva icona**. El Mac envia la llista cada 5 s (nomes
si canvia) amb la línia `L Safari=safari|Mail=mail|Finder=finder|...`; en tocar
una app, la placa respon `C focus:N` i el Mac la porta al davant
(`tell application ... to activate`).

La icona la tria **el Mac** (es qui sap de quina app es): a `mac/bridge.py` hi ha
la taula `APP_ICONS` (nom de l'app del Mac → nom de la icona de la placa). Si una
app no hi es, es prova de trobar una icona que es digui igual; si no se'n troba
cap, el boto surt nomes amb el nom (com abans).

Les icones de les apps son mes grans que les dels altres botons (56 px en lloc de
40) perque es reconeguin millor, i el nom s'escurça amb `...` si no hi cap.

> Per aixo les icones d'app **no** han de tenir el fons transparent: han d'anar a
> `Assets/icons/apps.txt` (mirau "Posar les teves icones").

### Espais i finestres

A la pantalla *Espais* hi ha botons per controlar els **escriptoris** de macOS
(tecles reals per Bluetooth):

| Boto | Tecles | Que fa |
|---|---|---|
| ESQ / DRETA | `ctrl+left` / `ctrl+right` | Canviar d'escriptori |
| MISSION | `ctrl+up` | Mission Control (veure tots els escriptoris) |
| FINESTRES | `ctrl+down` | Finestres de l'app actual |
| CERCAR | `cmd+space` | Spotlight |
| LAUNCHPAD | `f4` | Launchpad |

### Avisos a la pantalla

El Mac pot enviar missatges que surten a la **capçalera** de la placa uns segons
(`N <text>`). Des del panell, secció **"Avisos a la pantalla"**, n'hi ha un camp
per enviar-los. Tambe n'hi ha d'**automatics**: si la bateria baixa del 20 %,
surt un avis tot sol.

### FaceTime, calendari i mes

Hi ha accions d'estoc per obrir **FaceTime**, **Calendari**, **Mail**, **Notes** i
**Fotos**. Per **trucar a un contacte** concret, afegeix un boto personalitzat
amb l'ordre:

```
open facetime://nom@icloud.com
```

Les seccions "Gadgets de la pantalla" i "Botons de la pantalla" sempre editen la
**pantalla seleccionada**.

### Orientació

Al mateix panell pots triar **Vertical (320×480)** o **Horitzontal (480×320)**.
La placa gira de debò (rotació del controlador).

### Pantalla fosca mentre es dibuixa

Quan es repinta (canvi de pantalla o de configuració), la **retroil·luminació
s'apaga** mentre es pinta i es torna a encendre al final: no es veu mai res a mig
fer.

### Protocol (resum)

El Mac envia tota la configuració en una línia `CFG`:

```json
{"o":"v","t":0,"s":120,
 "p":[{"n":"Estat","i":"grid","l":"status",
       "w":["cpu","mem"],"b":[["media_play","PLAY","play","media_playpause"]]}]}
```

| Clau | Significat |
|---|---|
| `o` | orientació (`v` / `h`) |
| `t` | tema de colors (0-4) |
| `s` | segons sense tocar abans d'entrar en repòs (0 = mai) |
| `p` | llista de pantalles |
| `n` `i` `l` | nom, icona, disposició |
| `w` | gadgets |
| `b` | botons: `[id, text, icona, tecles]` |

L'ESP32 també pot demanar coses al Mac (quan canvia un ajust des de la pantalla):

| Missatge | Significat |
|---|---|
| `X theme=2` | canvia el tema |
| `X orient=h` | gira la pantalla |
| `X standby=300` | temps de repòs, en segons |
| `X bright=70` | brillantor (només informatiu; ho aplica la placa) |

I el Mac informa de l'estat de la seva pantalla dins la línia `S`:

| Camp | Significat |
|---|---|
| `dsp=1` | la pantalla del Mac està encesa |
| `dsp=0` | el Mac ha apagat la pantalla: l'ESP32 també s'apaga |

## Teclat Bluetooth (tecles de debò) — `src/keys.*`

L'ESP32 clàssic (WROOM-32E) **no té USB natiu** (el port USB de la placa va al
xip CH340), així que **no pot fer d'HID per USB**. El que sí que pot fer és
presentar-se com a **teclat Bluetooth**: la placa s'anuncia com a **"Mac Panel"**
i el Mac s'hi emparella un cop.

Per què és millor que `osascript`:

- Surt el **requadre del volum** del macOS i funciona a **qualsevol aplicació**.
- **No cal cap permís** d'Accessibilitat.
- Permet **combinacions de tecles** (Cmd+C, Cmd+V, Shift+Cmd+Z...), que és
  justament el que necessites per a eines tipus Corel.

### Emparellar-lo (un sol cop)

1. *Ajustos del Sistema → Bluetooth*.
2. Busca **"Mac Panel"** i clica **Connecta**.

Fet això, els botons amb **tecles** les envien per Bluetooth. Si no està
emparellat, al registre del panell hi surt:
`[BT] teclat no connectat: emparella 'Mac Panel' al Mac`.

### Quins botons fan servir tecles

Els botons amb `keys` (no buit) envien **tecles de debò** per Bluetooth en lloc
d'una comanda al Mac. El format es `[modificadors+]tecla`:

| Escrit | Que envia |
|---|---|
| `cmd+c` | Cmd+C (copiar) |
| `shift+cmd+z` | Maj+Cmd+Z (refer) |
| `media_playpause` | tecla de mitjans (play/pausa) |
| `7` | el digit 7 |
| `+` | el signe mes |

> **Important**: la llibreria `BleKeyboard` espera **caracters ASCII** per a les
> tecles normals (ella ja sap quin modificador cal: `+` = Maj+=) i els valors
> `KEY_*` per a les especials. **No s'hi poden passar codis HID directament**:
> amb `write(0x24)` la llibreria ho interpreta com el caracter ASCII `$` i
> escriu un `$`. Aixo era el motiu que el teclat numeric escrivís coses estranyes.

Llista completa de noms especials: `space`, `enter`, `tab`, `esc`, `backspace`,
`delete`, `up`, `down`, `left`, `right`, `home`, `end`, `pageup`, `pagedown`,
`f1`..`f12`, i els de mitjans (`media_playpause`, `media_next`, `media_prev`,
`media_volumedown`, `media_volumeup`, `media_mute`).

#### Compte amb la distribució de teclat!

El protocol HID de Bluetooth **no envia caràcters, envia posicions físiques del
teclat**. La tecla que en un teclat dels EUA és el `-` (codi `0x2D`), en un Mac
amb la distribució **"Spanish - ISO"** escriu un **apòstrof**; i la del `+`
escriu un `¡`. El mateix problema tindries amb qualsevol distribució que no
sigui QWERTY (AZERTY, Dvorak...).

Per això hi ha els noms del **bloc numèric**, que són l'única part del teclat on
el sistema tradueix sempre al mateix caràcter:

| Nom | Escriu | Nom | Escriu |
|---|---|---|---|
| `kp_0`..`kp_9` | els dígits | `kp_plus` | `+` |
| `kp_dot` | vegeu la nota | `kp_minus` | `-` |
| `kp_star` | `*` | `kp_slash` | `/` |
| `kp_enter` | Intro del bloc numèric | `kp_equal` | `=` |

El **teclat numèric de la pantalla** ja fa servir aquests codis (excepte el
punt, vegeu a sota). Si vols escriure un signe de puntuació concret que a la
teva distribució no surt, fes servir aquests noms.

> **El punt és un cas a part.** macOS tradueix el punt DEL BLOC NUMÈRIC al
> separador decimal de la distribució: en un Mac en castellà, `kp_dot` escriu
> una **coma**. Per això el botó `.` del teclat numèric de la pantalla envia el
> punt normal (`.`) en lloc de `kp_dot`, que sí que dona un punt a tot arreu.
>
> Ho pots comprovar amb `python3 tools/test_tecles.py`, que obre un TextEdit, hi
> envia les tecles des de la placa i llegeix el que s'ha escrit de debò.

> Les **lletres** (`cmd+c`, `cmd+v`...) sí que funcionen a qualsevol distribució
> basada en QWERTY, perquè les lletres hi són a les mateixes posicions. Amb
> Dvorak o AZERTY caldria canviar-les.

Al panell, cada botó té un camp **"(tecles BLE)"**. Si hi ha un valor, la placa
l'envia per Bluetooth; si està buit, s'executa una **comanda al Mac**.

| Acció | Tecles |
|---|---|
| Volum, silenci, mitjans | `media_volumeup`, `media_volumedown`, `media_mute`, `media_playpause`, `media_next`, `media_prev` |
| Edició | `cmd+c`, `cmd+v`, `cmd+x`, `cmd+z`, `shift+cmd+z`, `cmd+a`, `cmd+f`, `cmd+s`, `cmd+d` |
| Corel / dibuix | `cmd+g` (agrupar), `shift+cmd+g` (desagrupar), `shift+cmd+e` (exportar), `shift+cmd+i` (importar) |
| Zoom / finestres | `cmd+=`, `cmd+-`, `cmd+0`, `cmd+w`, `ctrl+cmd+f` |

Pots escriure qualsevol combinació: modificadors `cmd`, `shift`, `alt`, `ctrl`
(+`+`) i una tecla (`a`..`z`, `0`..`9`, `f1`..`f12`, `space`, `enter`, `tab`,
`esc`, fletxes, `media_*`...).

## Icones dels botons (PNG -> SD)

Els botons poden portar una **icona**. Les icones viuen a la targeta SD dins
`/icons/<nom>.bin` i s'assignen des del panell de control (desplegable "Icona").

### Pujar una icona des del panell (el mes facil)

Al panell de control, seccio **"Icones (PNG -> SD)"**:

1. Tria un **fitxer PNG** (idealment 64×64 o mes gran, amb **fons transparent**).
2. Posa-li un **nom** (minuscules, sense accents).
3. Clic a **"Puja a la pantalla"**.

El Mac el converteix i l'escriu directament a la SD de l'ESP32 pel port sèrie
(1 segon). Tambe desa el PNG a `Assets/icons/` per si el vols recuperar.

Pots **esborrar** una icona fent clic sobre seu a la llista "Icones a la placa".

### Format dels `.bin`

RGB565 **big-endian**, quadrats de **64×64** px (8.192 bytes). El color magenta
`0xF81F` es tracta com a transparent. Si no hi ha SD o falta una icona, el boto
mostra nomes el text (no peta res).

### Alternativa per terminal

```bash
python3 tools/gen_sample_icons.py    # (opcional) icones de mostra
python3 tools/png2bin.py             # PNG de Assets/icons -> Assets/icons/bin
bash tools/installa-icones-sd.sh     # copia els .bin a la SD (amb la SD al Mac)
```

## Full de ruta

Aixo es el que ja funciona i el que ve a continuacio:

**Fet**

- Panell d'estat del Mac (CPU, RAM, disc, bateria, xarxa, load, uptime, hora, host)
- Botons (shortcuts) configurables i execucio d'accions al Mac
- Panell de control web + acces directe a l'Escriptori (dobles clics)
- **Icones als botons des de la SD**, **pujables en PNG des del panell**
  (es converteixen i s'escriuen a la SD pel port serie), amb esborrat
- **Teclat Bluetooth (BLE HID)**: els botons envien **tecles de debò** (volum,
  mitjans, Cmd+C/V/Z, combinacions) — surt el requadre del volum i funciona a
  qualsevol app, sense permisos

**Fase 2 — Pantalles modulars ✅ (feta)**

- Concepte de **pantalles**: cada pantalla te els seus gadgets i botons
- Navegacio amb **barra de pestanyes** tactil
- El panell de control permet **crear, duplicar, ordenar i esborrar pantalles**
- **Orientacio horitzontal i vertical** (gira de debo)
- Pantalla **fosca mentre es redibuixa** (sense veure mig pintat)

**Fase 3 — Pantalles d'eines ✅ (feta)**

- **Gauges** circulars (CPU/RAM/disc/bateria) amb color segons el valor
- **Rellotge + meteo** (Open-Meteo) amb icona del temps
- **Numpad** numeric (tecles per Bluetooth)
- **Launcher** d'apps obertes al Mac **amb la icona de cada app** (es toquen i
  es porten al davant). El Mac tria la icona (`APP_ICONS` a `mac/bridge.py`).
- **Espais/escriptoris**: canviar d'escriptori, Mission Control, Spotlight, Launchpad
- **Avisos** a la pantalla (manuals i automatics, p. ex. bateria baixa)
- Pantalles "Corel" i similars: export, import, group, save, cut, copy, paste,
  undo, redo... amb **combinacions de tecles configurables** per app
- **FaceTime**, Calendari, Mail, Notes, Fotos (i trucades amb `facetime://...`)

**Fase 4 — Connectivitat i acabat ✅**

- **WiFi** ✅ (alternativa al cable; mateix protocol, mDNS `macpanel.local`)
- **5 temes de color** ✅ (Fosc, Clar, Neo, Grafite, Pastel)
- **Fonts suaus** FreeSans ✅ (antialiasades)
- **Brillantor** de la pantalla del Mac ✅ (botons d'estoc)
- **Previsio de 3 dies** ✅ (a la pantalla de rellotge)
- **Agenda** ✅ (proper esdeveniment del Calendar del Mac)
- **Ajustos de la placa** des del panell ✅ (brillantor, calibratge, reset, reinici)
- Estat de **Bloq Maj / Bloq Num** (pendent: l'ESP32 no pot llegir-ho per BLE)

## Protocol sèrie (115200 bauds, línies de text)

| Direcció | Missatge |
|---|---|
| Mac → ESP32 | `OK Mac-Panel v1` (handshake) |
| Mac → ESP32 | `S cpu=42.1 mem=38 disk=61 bat=88 chg=1 up=1.2 dn=0.3 load=1.8 host=MacBook time=14:32 uptime=8040 dsp=1 idl=95` |
| Mac → ESP32 | `CFG {"o":"v","t":5,"s":0,"ic":5,"nv":"both","p":[{"n":"Estat","i":"grid","l":"status","ap":["com.apple.Safari"],"w":["cpu"],"b":[]}]}` |
| Mac → ESP32 | `N Correu\|LALIGA\|Plazas limitadas…` (avís → bàner) |
| Mac → ESP32 | `A com.microsoft.VSCode\|Code` (aplicació activa) |
| Mac → ESP32 | `L Terminal=terminal\|Safari=safari\|Finder=finder` (apps obertes, launcher) |
| Mac → ESP32 | `F 3,18,11\|61,20,13` (previsió: codi WMO, màx, mín) |
| Mac → ESP32 | `E Reunió 15:00` (proper esdeveniment) |
| ESP32 → Mac | `H` (hola, a l'arrencada) |
| ESP32 → Mac | `C media_play` · `C custom:3` |
| ESP32 → Mac | `X theme=2` · `X orient=h` · `X standby=60` · `X bright=80` |
| ESP32 → Mac | `A` (ack de configuració) |

Camps de la línia `S`: `dsp` = la pantalla del Mac és encesa · `idl` = segons que
fa que el Mac no rep cap input.

Camps de `CFG`: `o` orientació · `t` tema · `s` repòs (s) · `ic` rellotge si
inactiu (min) · `nv` navegació · `p` pantalles (amb `ap` = bundle ids que fan
sortir aquella pantalla).

## Consola de l'ESP32

Connecta el monitor sèrie (`pio device monitor`) i escriu:

| Comanda | Què fa |
|---|---|
| `help` | ajuda |
| `info` | estat del sistema i de l'enllaç |
| `bl <0-100>` | brillantor de la retroil·luminació |
| `cal` | calibratge del tàctil (assistent a pantalla) |
| `cfg` / `pages` | mostra la configuració actual |
| `page <n>` | canvia de pantalla (0 = la primera) |
| `menu` | obre/tanca el menú de pantalles |
| `hist` | mostra l'historial dels gràfics (min/mitjana/màx) |
| `toca <x> <y>` | **simula un toc** a la pantalla (per provar) |
| `llisca x1 y1 x2 y2` | **simula un lliscament** de dit |
| `tecla <nom>` | **envia una tecla pel Bluetooth** (per provar: `tecla kp_plus`) |
| `tecles` | llista de noms de tecles disponibles |
| `apps` | apps obertes al Mac i la icona que els toca (launcher) |
| `splash` | torna a mostrar la pantalla d'inici |
| `ajust <id>` | prem un botó dels ajustos de la pantalla (per provar: `ajust theme+`) |
| `bt` | estat del teclat Bluetooth i memòria lliure |
| `reset` | torna a la configuració per defecte |
| `h` | reenvia el handshake `H` al Mac |

> Nota: si el Mac està connectat i envies estadístiques, la consola comparteix el
> port. Atura `panel_server.py` si vols escriure comandes amb calma.

Les comandes `toca` i `llisca` són molt útils per provar la interfície sense
tocar la pantalla. Es poden fer servir des de l'eina `tools/consola.py`:

```bash
python3 tools/consola.py "toca 15 15"        # toca el boto de menú
python3 tools/consola.py "llisca 260 200 80 205"   # llisca per canviar de pantalla
```

> **`toca` activa botons de debò.** El toc simulat passa exactament pel mateix
> camí que un dit (`Ui::touch()`): prem el botó, el deixa anar i executa la seva
> acció (comanda al Mac, tecles BLE o acció local). Per això les proves poden
> comprovar que prémer un botó envia el que toca. Quan escriguis una prova,
> recorda que un `toca` sobre un botó de tecles **escriurà de debò** al Mac.

### Proves automàtiques

| Eina | Què comprova |
|---|---|
| `tools/test_menu.py` | el menú: s'obre, es tanca, fa scroll, i les pestanyes **Pantalles / Ajustos / Sobre** (incloent-hi els ajustos nous) |
| `tools/test_navegacio.py` | la barra ‹ › i el lliscament canvien de pantalla |
| `tools/test_pantalles.py` | recorre les 12 pantalles buscant errors |
| `tools/test_grafics.py` | que els càlculs de l'historial siguin correctes |
| `tools/test_sense_enllac.py` | el mode reduït sense enllaç (rellotge, només Ajustos, botons morts) |
| `tools/test_launcher.py` | el launcher d'apps: rep `nom=icona`, comprova les icones a la SD i que tocar una app envia `C focus:N` |
| `tools/test_inici.py` | la pantalla d'inici (a l'engegada i amb `splash`) i la marquesina d'un nom de Mac llarg |
| `tools/test_tema.py` | el tema automàtic: que segueixi el clar/fosc del Mac i que el tema manual no es mogui |
| `tools/test_tecles.py` | **quina tecla escriu de debò al Mac** (obre TextEdit, envia les tecles i llegeix el porta-retalls) |
| `tools/test_estabilitat.py` | que no es reiniciï amb canvis de configuració |
| `tools/canvia_orientacio.py` | canvia entre vertical i horitzontal |

Totes funcionen **sense el Mac** (obren el port sèrie directament), així que
atura abans `panel_server.py`.

> **Compte amb el mode sense enllaç.** Com que la placa només ensenya les
> pantalles si té enllaç, les proves que les toquen necessiten **algú que enviï
> línies `S`** com fa el pont. D'això se n'encarrega `tools/comu.py`
> (`Enllac`), que les envia en un fil de fons amb un pany perquè no es barregin
> amb les comandes de la prova. Sense això, les proves passarien però no
> provarien res: la placa dibuixaria el rellotge en lloc de la pantalla.
> `test_grafics.py` no el fa servir perquè ja envia les seves pròpies línies
> `S` amb valors de CPU concrets.

## Compilar el firmware

```bash
pio run                 # compila
pio run -t upload       # compila i puja
pio device monitor      # monitor sèrie
```

Llibreries: `TFT_eSPI@2.5.43` i `ArduinoJson@^7.0.0` (les baixa PlatformIO).

## Estructura

```
include/pins.h            mapa de pins (ESP32-32E)
include/tft_setup.h       configuració de TFT_eSPI (ST7796S + XPT2046)
include/panel_config.h    geometria, colors, catàleg de widgets i accions
src/display.*             init TFT + backlight PWM
src/touch.*               XPT2046 + calibratge a NVS
src/led.*                 LED RGB (indicador d'enllaç)
src/sdcard.*              targeta SD (bus VSPI)
src/icons.*               icones .bin de /icons de la SD
src/maclink.*             protocol sèrie + configuració (NVS)
src/ui.*                  dibuix dinàmic de la pantalla + hit-test
src/main.cpp              setup()/loop() + consola sèrie
tools/png2bin.py          PNG -> .bin RGB565 big-endian (icones)
tools/mostra_icones.py    full de contacte: com queden les icones a la placa
tools/mostra_originals.py full de contacte amb els PNG d'origen
tools/diagnostic_png.py   quins PNG tenen alfa i quins son opacs
tools/diagnostic_anell.py  intent d'endevinar quines icones son d'app
tools/gen_sample_icons.py icones de mostra (blanc sobre transparent)
tools/installa-icones-sd.sh  copia els .bin a la targeta SD
Assets/icons/             PNG originals (bin/ = .bin convertits)
Assets/icons/apps.txt     quines icones son d'app (es queden senceres)
mac/bridge.py             motor: estadístiques + accions + sèrie
mac/panel_server.py       servidor web del panell de control
mac/panel.html            la interfície del panell
mac/panel_config.json     configuració desada (es crea/actualitza sol)
mac/engega-panell.sh      arrenca el panell (servidor + navegador)
mac/atura-panell.sh       atura el panell
mac/crea-llancadors.sh    crea els accessos directes de l'Escriptori
mac/EngegaPanell.command  llançador de doble clic (Finder)
```

## Notes i permisos de macOS

- **Bloquejar pantalla i mode clar/fosc** (`osascript` amb *System Events*)
  necessiten permís d'**Accessibilitat**: *Ajustos del Sistema → Privadesa i
  seguretat → Accessibilitat* → afegeix-hi el terminal (o Python) que executa el pont.
- **Captura de pantalla** desa un `macpanel_shot.png` a l'Escriptori.
- La **CPU** es calcula sumant l'ús de `ps` i dividint pel nombre de nuclis: és una
  aproximació ràpida (no bloqueja el bucle).
- La **xarxa** es calcula amb deltes de `netstat -ib` entre mostres (el primer cop
  dona 0).

