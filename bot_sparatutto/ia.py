"""
ia.py - L'IA che GUARDA (il "cervello lento" del bot).

Ogni tanto (ia -> ogni_secondi) manda una foto piccola dello schermo a un'IA che sa
guardare le immagini e le chiede cosa sta succedendo nella partita:
  fase (bus, caduta, gioco, menu, morto), se c'e' una cassa vera e da che parte,
  se ha un muro davanti, se la tempesta e' vicina e da che parte e' la zona sicura.
Il bot veloce (mira, spara, si muove) NON la aspetta mai: usa l'ultima risposta.

Le IA si provano in ordine (ia -> fornitori): se una non risponde o ha finito le
richieste gratis, si passa alla prossima.
  ollama       sul TUO computer: gratis, senza chiave e senza account. Se c'e' il bot la
               collega DA SOLO; se non c'e' il menu "Collega le IA" la installa (con un
               modello che vede le immagini). Senza scheda video e' lenta (anche 30-60
               secondi a foto): va bene soprattutto per bus, menu e partita successiva.
  (Le IA online senza chiave provate a novembre 2026 - Pollinations, LLM7 - non accettano
   immagini: per questo non ci sono.)
  gemini       Google, gratis con chiave (aistudio.google.com)
  github       GitHub Models, gratis con un token di GitHub
  openrouter   modelli ":free" gratis con chiave (openrouter.ai)
  groq         gratis con chiave (console.groq.com)
  mistral      gratis con chiave (console.mistral.ai)
  zai          GLM-4.6V-Flash gratis con chiave (z.ai)
  personale    qualsiasi IA "compatibile OpenAI": indirizzo, modello e chiave in ia.yaml
Le chiavi stanno nel file ia.yaml (accanto al programma): lo scrive il menu
"Collega le IA". Attenzione: le foto del gioco vengono mandate al servizio scelto.

IA GRATIS PER GIOCARE GIORNI (menu 15, e all'avvio se mancano), completamente gratuite:
  gemma/gemini  Google: la chiave la crei TU col tuo account Google su aistudio.google.com/apikey
                (email e password le scrivi solo a Google: il bot non le chiede e non le salva).
                Con la stessa chiave: Gemma 4 (circa 14.400 domande al giorno) e Gemini.
  nvidia        NVIDIA Build: chiave gratis su build.nvidia.com (senza carta), circa 40 domande
                al minuto senza limite al giorno; il modello che vede lo sceglie il bot provandoli.
  Se una finisce le domande gratis il bot passa all'altra.

COSA SA DEL GIOCO: il file fortnite.txt (come funziona Fortnite: comandi, casse, tempesta,
furgone del riavvio...) viene mandato insieme alla foto alle IA online, cosi' capiscono
meglio cosa vedono. Puoi aggiungerci quello che vuoi.
"""

import base64
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

import yaml

FORNITORI = {
    "ollama": {"url": "http://localhost:11434/api/chat", "modello": "qwen2.5vl:3b", "tipo": "ollama",
               "chiave": False, "attesa": 180, "dove": "sul tuo computer (ollama.com)"},
    # Google si chiama nel modo ufficiale (generateContent): la via "compatibile OpenAI" con Gemma e
    # le immagini dava "errore 500", e cosi' funzionano anche le chiavi nuove (AQ....)
    "gemini": {"url": "https://generativelanguage.googleapis.com/v1beta/models/{modello}:generateContent",
               "modello": "gemini-3.5-flash-lite", "tipo": "google", "chiave": True, "attesa": 60,
               "dove": "aistudio.google.com (chiave gratuita; Google chiede di avere 18 anni)",
               # provati a novembre 2026: le "Flash-Lite" rispondono in 1-3 secondi; ognuna ha il suo
               # limite al giorno. Il bot chiede comunque a Google quali ci sono (elenco_google)
               "candidati": ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-flash-lite-latest",
                             "gemini-3.1-flash-lite-preview", "gemini-3-flash-preview"]},
    "github": {"url": "https://models.github.ai/inference/chat/completions", "modello": "openai/gpt-4.1-mini",
               "tipo": "openai", "chiave": True, "attesa": 30,
               "dove": "github.com/settings/tokens (token con il permesso 'models')"},
    "openrouter": {"url": "https://openrouter.ai/api/v1/chat/completions", "modello": "",
                   "tipo": "openai", "chiave": True, "attesa": 40,
                   "dove": "openrouter.ai/keys (usa i modelli gratuiti ':free')"},
    "groq": {"url": "https://api.groq.com/openai/v1/chat/completions",
             "modello": "meta-llama/llama-4-scout-17b-16e-instruct", "tipo": "openai", "chiave": True,
             "attesa": 30, "dove": "console.groq.com/keys"},
    "mistral": {"url": "https://api.mistral.ai/v1/chat/completions", "modello": "mistral-small-latest",
                "tipo": "openai", "chiave": True, "attesa": 30, "dove": "console.mistral.ai"},
    "zai": {"url": "https://api.z.ai/api/paas/v4/chat/completions", "modello": "glm-4.6v-flash",
            "tipo": "openai", "chiave": True, "attesa": 40, "dove": "z.ai (GLM-4.6V-Flash gratis)"},
    # Gemma 4 di Google: GRATIS con la stessa chiave di Gemini, circa 14.400 richieste al giorno
    # (Gemini ne da' molte meno). Gemma non accetta il messaggio di sistema: la conoscenza va nella domanda.
    # Gemma 4 "pensa" prima di rispondere (20-70 secondi) ma ha tante domande al giorno: e' la riserva
    "gemma": {"url": "https://generativelanguage.googleapis.com/v1beta/models/{modello}:generateContent",
              "modello": "gemma-4-26b-a4b-it", "tipo": "google", "chiave": True, "attesa": 120,
              "dove": "la stessa chiave di Gemini (aistudio.google.com)", "stessa_chiave": "gemini",
              "sistema": False,
              # ogni modello ha il SUO limite al giorno: con la stessa chiave se ne usano tanti
              "candidati": ["gemma-4-26b-a4b-it", "gemma-4-31b-it"]},
    # NVIDIA Build: GRATIS, senza carta di credito, circa 40 richieste al minuto (novembre 2026)
    "nvidia": {"url": "https://integrate.api.nvidia.com/v1/chat/completions", "modello": "",
               "tipo": "openai", "chiave": True, "attesa": 45,
               "dove": "build.nvidia.com (gratis, senza carta di credito)"},
}
# l'ordine in cui le prova: prima quelle gratis che durano di piu', Ollama sul PC (lenta) dopo
ORDINE = ["gemini", "nvidia", "gemma", "zai", "github", "openrouter", "groq", "mistral", "ollama", "personale"]
# NVIDIA: i modelli che guardano le immagini, dal piu' adatto (si prova finche' uno funziona)
NVIDIA_PREFERITI = ("google/gemma-4-31b-it", "meta/llama-3.2-90b-vision-instruct", "google/gemma-3-12b-it",
                    "nvidia/nemotron-3.5-super-vl-120b-a12b", "meta/muse-glimmer-30b",
                    "microsoft/phi-3-vision-128k-instruct", "google/gemma-3-4b-it")
NVIDIA_PAROLE_VISTA = ("vision", "-vl", "omni", "glimmer", "gemma-3-", "gemma-4-", "vila", "multimodal")
OLLAMA_BASE = "http://localhost:11434"
OLLAMA_MODELLO = "qwen2.5vl:3b"          # piccolo, vede le immagini, risponde bene in JSON e trova i pulsanti
# nomi dei modelli di Ollama che sanno guardare le immagini (il primo trovato si usa)
OLLAMA_CHE_VEDONO = ("qwen2.5vl", "qwen3-vl", "gemma3", "llava", "minicpm-v", "llama3.2-vision",
                     "granite3.2-vision", "moondream", "bakllava")
OLLAMA_INSTALLATORE = "https://ollama.com/download/OllamaSetup.exe"
PAGINA_CHIAVE_GEMINI = "https://aistudio.google.com/apikey"   # si entra col proprio account Google
PAGINA_CHIAVE_NVIDIA = "https://build.nvidia.com/settings/api-keys"
FILE_CONOSCENZA = "fortnite.txt"                              # come funziona il gioco (per le IA)
CONOSCENZA_MASSIMA = 24000                                    # caratteri: oltre si taglia

DOMANDA = (
    "You help a bot play a Fortnite-like third-person shooter. Look at this game screenshot and "
    "answer ONLY with one JSON object, no other text:\n"
    '{"phase": "bus|falling|playing|menu|dead|unknown", '
    '"chest": "none|left|center|right", "wall_ahead": true|false, '
    '"storm_near": true|false, "safe_direction": "left|right|ahead|behind|unknown", '
    '"enemy": true|false, "low_health": true|false, '
    '"vehicle": "none|left|center|right|close", "in_vehicle": true|false, '
    '"button": {"x": 0.5, "y": 0.9} or null, "cursor": {"x": 0.5, "y": 0.5} or null, '
    '"key": "none|space|enter|esc|e|f", "downed_teammate": "none|left|center|right|close", '
    '"screen": "game|ps5_who_is_using|remote_play|desktop", "pc_button": {"x": 0.5, "y": 0.5} or null, '
    '"spectating": true|false, "holding": "pickaxe|weapon|healing|other|unknown", "has_weapon": true|false, '
    '"prompt": "none|open|pick_up|zipline|door|other", '
    '"target": {"what": "chest|weapon|ammo_box|building", "x": 0.5, "y": 0.7} or null, '
    '"current_slot": 1, "best_slot": 2, "heal_slot": null, '
    '"enemy_xy": {"x": 0.5, "y": 0.5, "close": false} or null, "explore": "ahead|left|right|behind", '
    '"compass": 195, "over_island": true|false, '
    '"teammate": {"x": 0.5, "y": 0.4, "side": "on_screen|left|right|behind", "distance": 25} or null}\n'
    "phase: bus = riding the battle bus, falling = skydiving or gliding, menu = lobby or menus, "
    "dead = the player was eliminated (elimination or end-of-match screen, or spectating). "
    "spectating = the player was eliminated and now the camera follows ANOTHER player (a teammate or the "
    "enemy who eliminated him): a different character is on screen, with texts like 'Stai osservando' / "
    "'Spectating', the name of the watched player, 'Ritorna alla lobby'; then phase is dead too. "
    "chest = a closed loot chest (golden glowing box) in the 3D world, "
    "NOT icons of the interface and NOT the glowing golden tip of the pickaxe the player holds; tell where it "
    "is on screen. wall_ahead = a wall, rock or obstacle "
    "right in front of the character, very close. storm_near = the storm (purple wall or purple sky) "
    "is close or the character is inside it; safe_direction = where to go to get away from it. "
    "low_health = the health or shield bar is low. vehicle = a car or other vehicle in the world "
    "(close = right next to the character); in_vehicle = the character is driving or riding one. "
    "button = ONLY in lobby, menus or after being eliminated: the one button to press to get to the "
    "NEXT MATCH (Return to Lobby, Play, Ready, Continue, Skip...), as fractions of screen width and "
    "height; never Quit or Exit game, never the battle pass or the shop ('Ottieni il pass battaglia', "
    "'Negozio'). cursor = where the mouse pointer is, if you see it. "
    "key = a key the screen says to press to continue (for example 'Press SPACE'), else none. "
    "downed_teammate = a knocked-down teammate (crawling, waiting to be revived), close = right next "
    "to the character. "
    "screen: game = Fortnite or the PS5 menus are visible normally; ps5_who_is_using = a PS5 panel asks "
    "'Who is using this controller/keyboard?' ('Chi sta usando questo controller/questa tastiera?') with "
    "round user pictures; remote_play = a window or message of the PS Remote Play app on the computer "
    "(lost connection 'Hai perso la connessione', select the console, connecting, enter a number, update "
    "question...) instead of the game; desktop = the Windows desktop, a terminal or another program: the "
    "game is not visible. pc_button = ONLY when screen is remote_play: where to click on the screen to "
    "connect again to the PS5 (the OK button of a message, the console name button like 'PS5-123', "
    "'Riprova'/'Retry'), as fractions of screen width and height; null if it asks for a number/code or "
    "for an update. "
    "holding = what the player's character has in hand now (the highlighted slot of the inventory at the "
    "bottom right; the first slot is the pickaxe). has_weapon = there is at least one gun in the inventory. "
    "prompt = the interaction prompt written near the center of the screen: open = 'Apri'/'Open' (chest, "
    "ammo box, supply drop), pick_up = 'Raccogli'/'Pick up' (an item on the ground), zipline = grab a "
    "zipline, door = open a door, other = anything else (talk, vehicles...). target = the most useful thing to go to "
    "now in the 3D world, with its center as fractions of screen width and height: the nearest CLOSED "
    "chest; if there is none, a weapon on the ground (when the player has few weapons) or an ammo box; "
    "if none of these is visible, the nearest house or building to search inside (chests are inside "
    "houses), also while skydiving or gliding (the nearest group of houses below); null if nothing. "
    "Inventory (bottom right): slot 1 is the pickaxe, slots 2-6 are weapons and items. current_slot = the "
    "highlighted slot now (1-6). best_slot = the slot of the best weapon to hold now (shotgun or SMG for "
    "close enemies, rifle for far ones, any gun if unsure; 1 only if there is no gun). heal_slot = the slot "
    "of a healing or shield item, or null. enemy_xy = the nearest enemy player in the 3D world (not the own "
    "character, not teammates), close = near the player; null if none. explore = which way to go to find "
    "houses and loot ON LAND: never toward the sea or a lake (ahead if unsure). compass = the number in "
    "the middle of the compass at the top center of the screen (degrees where the player looks), or null. "
    "over_island = ONLY on the bus or while skydiving/gliding: true if the island (land with trees, houses) is "
    "right below, false if below there is open sea. teammate = the nearest TEAMMATE (a player of the same "
    "squad: colored NAME TAG above the head, also while skydiving), NOT the player's own character: x,y = "
    "where on screen; side = on_screen if visible, or left/right/behind if only their marker with the name "
    "is at the edge or bottom of the screen; distance = the meters written under the name (number), or "
    "null; null if no teammate."
)

# la mappa: dove andare per la zona sicura (rispondono piu' IA e vince la maggioranza)
DOMANDA_MAPPA = (
    "The TOP image is the big map of Fortnite: NORTH IS UP. The player is the ARROW-shaped marker (white, "
    "with a colored outline). The safe zone is inside the WHITE circle (if there are two circles, the "
    "smaller one is the next safe zone); outside it there is the storm (purple). The BOTTOM strip is the "
    "game's COMPASS: the number in the middle is the direction the player is looking, in degrees "
    "(0 = north, 90 = east, 180 = south, 270 = west).\n"
    "Answer ONLY with one JSON object, no other text:\n"
    '{"heading": 195, "inside": true|false, "near_edge": true|false, '
    '"safe": "N|NE|E|SE|S|SW|W|NW|here"}\n'
    "heading = the number in the middle of the compass. inside = the player marker is inside the white "
    "circle. near_edge = it is close to the edge of the circle. safe = the direction ON THE MAP (north up) "
    "from the player marker to the CENTER of the white circle; if there is no white circle yet (on the bus, "
    "at the start), to the CENTER of the island. here = the player is already near that center."
)

FASI = ("bus", "falling", "playing", "menu", "dead", "unknown")
LATI = ("none", "left", "center", "right")
VEICOLO = ("none", "left", "center", "right", "close")
TASTI = ("none", "space", "enter", "esc", "e", "f")
NOMI_TASTI = {"space": "spazio", "enter": "invio", "esc": "esc", "e": "e", "f": "f"}
DIREZIONI = ("left", "right", "ahead", "behind", "unknown")
SCHERMI = ("game", "ps5_who_is_using", "remote_play", "desktop")
IN_MANO = ("pickaxe", "weapon", "healing", "other", "unknown")
PROMPT = ("none", "open", "pick_up", "zipline", "door", "other")
OBIETTIVI = ("chest", "weapon", "ammo_box", "building")
DIREZIONI_MAPPA = {"ahead": 0, "ahead_right": 45, "right": 90, "behind_right": 135, "behind": 180,
                   "behind_left": -135, "left": -90, "ahead_left": -45}
DOMANDA_BUSSOLA = (
    "This is the compass strip at the top of the Fortnite screen. Answer ONLY with one JSON object: "
    '{"heading": 195} where heading is the number written in the middle (the degrees where the player '
    "looks: 0 north, 90 east, 180 south, 270 west)."
)
# la bussola: dove sta la zona sicura sulla mappa (nord in alto) -> gradi
BUSSOLA = {"N": 0, "NE": 45, "E": 90, "SE": 135, "S": 180, "SW": 225, "W": 270, "NW": 315}


class Consiglio:
    """Quello che l'IA ha visto in una foto."""

    def __init__(self, fase="unknown", cassa="none", muro=False, tempesta=False, direzione="unknown",
                 nemico=False, quando=0.0, fornitore="", poca_vita=False, veicolo="none", in_veicolo=False,
                 pulsante=None, cursore=None, tasto="none", compagno="none", schermo="game", pulsante_pc=None,
                 osservo=False, in_mano="unknown", ha_arma=None, prompt="none", obiettivo=None,
                 slot=None, slot_arma=None, slot_cura=None, nemico_xy=None, esplora="ahead", bussola=None,
                 sopra_isola=None, compagno_xy=None):
        self.fase = fase
        self.compagno_xy = compagno_xy    # (x, y, lato, metri) del compagno piu' vicino, oppure None
        self.sopra_isola = sopra_isola    # sul bus / in caduta: sotto c'e' l'isola (True) o il mare (False)
        self.bussola = bussola            # il numero della bussola in alto (gradi dove guardo), o None
        self.slot = slot                  # lo slot dell'inventario evidenziato adesso (1-6)
        self.slot_arma = slot_arma        # lo slot dell'arma migliore per adesso (1 = piccone)
        self.slot_cura = slot_cura        # lo slot di una cura o di uno scudo
        self.nemico_xy = nemico_xy        # (x, y, vicino) del nemico piu' vicino, oppure None
        self.esplora = esplora            # da che parte andare per trovare case e bottino
        self.in_mano = in_mano            # pickaxe / weapon / healing / other / unknown
        self.ha_arma = ha_arma            # True/False: ha almeno un'arma nell'inventario (None = non so)
        self.prompt = prompt              # scritta sullo schermo: open / pick_up / zipline / other / none
        self.obiettivo = obiettivo        # (cosa, x, y): la cassa (o l'arma) piu' utile, dove sta
        self.osservo = osservo            # eliminato: guardo un ALTRO giocatore (non sono io!)
        self.schermo = schermo            # game / ps5_who_is_using / remote_play / desktop
        self.pulsante_pc = pulsante_pc    # dove cliccare col mouse del PC (Remote Play), oppure None
        self.compagno = compagno          # compagno a terra da rianimare (none/left/center/right/close)
        self.poca_vita = poca_vita
        self.veicolo = veicolo
        self.in_veicolo = in_veicolo
        self.pulsante = pulsante          # (x, y) in frazioni dello schermo, oppure None
        self.cursore = cursore            # (x, y) in frazioni dello schermo, oppure None
        self.tasto = tasto
        self.cassa = cassa
        self.muro = muro
        self.tempesta = tempesta
        self.direzione = direzione
        self.nemico = nemico
        self.quando = quando
        self.fornitore = fornitore
        self.numero = 0               # cresce a ogni risposta: cosi' il bot usa ogni consiglio una volta

    def __repr__(self):
        return "Consiglio(%s, cassa=%s, muro=%s, tempesta=%s->%s, da %s)" % (
            self.fase, self.cassa, self.muro, self.tempesta, self.direzione, self.fornitore)

    def descrizione(self):
        parti = {"bus": "sul bus", "falling": "in caduta", "playing": "in gioco", "menu": "nei menu",
                 "dead": "eliminato", "unknown": "non so"}[self.fase]
        if self.osservo:
            parti += " (guardo un altro giocatore)"
        if self.cassa != "none":
            parti += ", cassa a " + {"left": "sinistra", "center": "davanti", "right": "destra"}[self.cassa]
        if self.muro:
            parti += ", muro davanti"
        if self.tempesta:
            parti += ", tempesta vicina"
        if self.in_veicolo:
            parti += ", in macchina"
        elif self.veicolo != "none":
            parti += ", macchina " + {"left": "a sinistra", "center": "davanti", "right": "a destra",
                                      "close": "vicina"}[self.veicolo]
        if self.pulsante is not None:
            parti += ", pulsante per continuare in %.2f,%.2f" % self.pulsante
        if self.schermo != "game":
            parti += ", " + {"ps5_who_is_using": "la PS5 chiede chi sta giocando",
                             "remote_play": "PS Remote Play scollegato", "desktop": "non si vede il gioco"}[self.schermo]
        return parti


def _si(v):
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("true", "yes", "si", "1")


def _scegli(v, ammessi, predefinito):
    t = str(v or "").strip().lower()
    for a in ammessi:
        if t == a or t.startswith(a):
            return a
    return predefinito


def _compagno(v):
    """{"x":0.6,"y":0.4,"side":"on_screen","distance":25} -> (0.6, 0.4, "on_screen", 25.0), oppure None."""
    if not isinstance(v, dict):
        return None
    lato = _scegli(v.get("side"), ("on_screen", "left", "right", "behind"), "")
    punto = _punto(v)
    if not lato:
        lato = "on_screen" if punto is not None else ""
    if not lato or (lato == "on_screen" and punto is None):
        return None
    try:
        metri = float(v.get("distance"))
    except (TypeError, ValueError):
        metri = None
    x, y = punto if punto is not None else (0.5, 0.5)
    return (x, y, lato, metri)


def _gradi(v):
    """Il numero della bussola (0-360), oppure None."""
    try:
        g = float(v)
    except (TypeError, ValueError):
        return None
    return g % 360.0 if 0 <= g <= 360 else None


def _slot(v):
    """Un numero di slot dell'inventario (1-6), oppure None."""
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        return None
    return n if 1 <= n <= 6 else None


def _nemico(v):
    """{"x": 0.6, "y": 0.4, "close": true} -> (0.6, 0.4, True), oppure None."""
    punto = _punto(v) if isinstance(v, dict) else None
    if punto is None:
        return None
    return punto + (_si(v.get("close", False)),)


def _obiettivo(v):
    """{"what": "chest", "x": 0.4, "y": 0.7} -> ("chest", 0.4, 0.7), oppure None."""
    if not isinstance(v, dict):
        return None
    cosa = _scegli(v.get("what"), OBIETTIVI, "")
    punto = _punto(v)
    if not cosa or punto is None:
        return None
    return (cosa,) + tuple(punto)


def _punto(v):
    """{"x": 0.5, "y": 0.9} oppure [0.5, 0.9] -> (0.5, 0.9); None se non e' un punto dello schermo."""
    try:
        if isinstance(v, dict):
            x, y = float(v["x"]), float(v["y"])
        elif isinstance(v, (list, tuple)) and len(v) == 2:
            x, y = float(v[0]), float(v[1])
        else:
            return None
    except (KeyError, TypeError, ValueError):
        return None
    if 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0:
        return (x, y)
    return None


def togli_pensieri(testo):
    """Alcune IA scrivono prima il loro ragionamento (<thought>...</thought>): lo tolgo."""
    testo = re.sub(r"<(thought|think|thinking)>.*?</\1>", " ", str(testo or ""), flags=re.S | re.I)
    return re.sub(r"<(thought|think|thinking)>.*", " ", testo, flags=re.S | re.I)   # pensiero non finito


def leggi_json(testo):
    """Il primo oggetto JSON nel testo dell'IA (anche dentro ```json ... ```), oppure None."""
    testo = togli_pensieri(testo)
    m = re.search(r"\{.*\}", testo, re.S)
    if not m:
        return None
    for prova in (m.group(0), m.group(0).replace("'", '"')):
        try:
            dati = json.loads(prova)
            return dati if isinstance(dati, dict) else None
        except ValueError:
            continue
    return None


def leggi_risposta(testo, quando=0.0, fornitore=""):
    """Dal testo dell'IA a un Consiglio (anche se aggiunge parole o ```json intorno). None se non capisce."""
    testo = togli_pensieri(testo)
    if not testo.strip():
        return None
    m = re.search(r"\{.*\}", str(testo), re.S)
    dati = None
    if m:
        pezzo = m.group(0)
        for prova in (pezzo, pezzo.replace("'", '"')):
            try:
                dati = json.loads(prova)
                break
            except ValueError:
                continue
    if not isinstance(dati, dict):
        # alcune IA piccole rispondono 'phase: playing, chest: left ...'
        dati = dict(re.findall(r'"?(\w+)"?\s*[:=]\s*"?([\w]+)"?', str(testo)))
        if "phase" not in dati and "chest" not in dati:
            return None
    return Consiglio(
        fase=_scegli(dati.get("phase"), FASI, "unknown"),
        cassa=_scegli(dati.get("chest"), LATI, "none"),
        muro=_si(dati.get("wall_ahead", False)),
        tempesta=_si(dati.get("storm_near", False)),
        direzione=_scegli(dati.get("safe_direction"), DIREZIONI, "unknown"),
        nemico=_si(dati.get("enemy", False)),
        quando=quando, fornitore=fornitore,
        poca_vita=_si(dati.get("low_health", False)),
        veicolo=_scegli(dati.get("vehicle"), VEICOLO, "none"),
        in_veicolo=_si(dati.get("in_vehicle", False)),
        pulsante=_punto(dati.get("button")),
        cursore=_punto(dati.get("cursor")),
        tasto=_scegli(dati.get("key"), TASTI, "none"),
        compagno=_scegli(dati.get("downed_teammate"), VEICOLO, "none"),
        schermo=_scegli(dati.get("screen"), SCHERMI, "game"),
        pulsante_pc=_punto(dati.get("pc_button")),
        osservo=_si(dati.get("spectating", False)),
        in_mano=_scegli(dati.get("holding"), IN_MANO, "unknown"),
        ha_arma=_si(dati["has_weapon"]) if "has_weapon" in dati else None,
        prompt=_scegli(dati.get("prompt"), PROMPT, "none"),
        obiettivo=_obiettivo(dati.get("target")),
        slot=_slot(dati.get("current_slot")),
        slot_arma=_slot(dati.get("best_slot")),
        slot_cura=_slot(dati.get("heal_slot")),
        nemico_xy=_nemico(dati.get("enemy_xy")),
        esplora=_scegli(dati.get("explore"), ("ahead", "left", "right", "behind"), "ahead"),
        bussola=_gradi(dati.get("compass")),
        sopra_isola=_si(dati["over_island"]) if dati.get("over_island") is not None else None,
        compagno_xy=_compagno(dati.get("teammate")))


# ------------------------------------------------------------------ come si parla a ogni IA
def richiesta(fornitore, jpeg_base64, domanda=DOMANDA, conoscenza="", lunghezza=260):
    """-> (url, intestazioni, corpo in bytes) per chiedere all'IA di guardare la foto.
    conoscenza = come funziona il gioco (fortnite.txt): va alle IA online come messaggio di
    sistema. A Ollama sul PC no: senza scheda video un testo lungo la rallenta troppo."""
    intestazioni = {"Content-Type": "application/json", "User-Agent": "BotSparatutto"}
    if fornitore["tipo"] == "google":
        # Google (Gemini, Gemma): il modo ufficiale, con la chiave nell'intestazione x-goog-api-key
        intestazioni["x-goog-api-key"] = fornitore["chiave"]
        testo = domanda
        corpo = {"contents": [{"role": "user", "parts": [
                     {"text": testo}, {"inline_data": {"mime_type": "image/jpeg", "data": jpeg_base64}}]}],
                 # piu' spazio: alcuni modelli prima "pensano" (anche 1000 parole) e il pensiero conta
                 "generationConfig": {"temperature": 0.1, "maxOutputTokens": max(3000, lunghezza)}}
        if conoscenza:
            sapere = "What you know about the game (from the player, in Italian):\n" + conoscenza
            if fornitore.get("sistema", True):
                corpo["systemInstruction"] = {"parts": [{"text": sapere}]}
            else:
                corpo["contents"][0]["parts"][0]["text"] = sapere + "\n\n" + testo   # Gemma: tutto nella domanda
        return fornitore["url"].format(modello=fornitore["modello"]), intestazioni, json.dumps(corpo).encode("utf-8")
    if fornitore["chiave"]:
        intestazioni["Authorization"] = "Bearer " + fornitore["chiave"]
    if fornitore["tipo"] == "ollama":
        corpo = {"model": fornitore["modello"], "stream": False, "format": "json",
                 "options": {"temperature": 0.1, "num_predict": lunghezza},
                 "messages": [{"role": "user", "content": domanda, "images": [jpeg_base64]}]}
    else:
        messaggi = []
        if conoscenza:
            sapere = "What you know about the game (from the player, in Italian):\n" + conoscenza
            if fornitore.get("sistema", True):
                messaggi.append({"role": "system", "content": sapere})
            else:
                domanda = sapere + "\n\n" + domanda      # es. Gemma: niente messaggio di sistema
        messaggi.append({"role": "user", "content": [
            {"type": "text", "text": domanda},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + jpeg_base64}}]})
        corpo = {"model": fornitore["modello"], "temperature": 0.1, "max_tokens": lunghezza, "messages": messaggi}
    return fornitore["url"], intestazioni, json.dumps(corpo).encode("utf-8")


def testo_della_risposta(fornitore, dati):
    if fornitore["tipo"] == "ollama":
        return ((dati or {}).get("message") or {}).get("content", "")
    if fornitore["tipo"] == "google":
        candidati = (dati or {}).get("candidates") or []
        if not candidati:
            return ""
        parti = ((candidati[0].get("content") or {}).get("parts")) or []
        return "".join(str(p.get("text", "")) for p in parti if isinstance(p, dict) and not p.get("thought"))
    scelte = (dati or {}).get("choices") or []
    if not scelte:
        return ""
    contenuto = (scelte[0].get("message") or {}).get("content", "")
    if isinstance(contenuto, list):                 # alcune IA rispondono a pezzi
        contenuto = " ".join(str(p.get("text", "")) for p in contenuto if isinstance(p, dict))
    return contenuto or ""


def invia_http(url, intestazioni, corpo, attesa):
    """Manda la richiesta e restituisce il JSON della risposta. Errori: eccezione con un messaggio chiaro."""
    req = urllib.request.Request(url, data=corpo, headers=intestazioni, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=attesa) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        try:
            dettaglio = e.read().decode("utf-8", "replace")[:200]
        except Exception:
            dettaglio = ""
        if e.code in (401, 403):
            raise RuntimeError("chiave sbagliata o senza permesso (%d)" % e.code)
        if e.code == 429:
            raise RuntimeError("troppe richieste: ha finito quelle gratis per adesso (429)")
        dettaglio = " ".join(dettaglio.split())          # una riga sola
        m = re.search(r'"message":\s*"([^"]*)"', dettaglio)
        if m:
            dettaglio = m.group(1)
        if e.code == 404:
            raise RuntimeError("modello o indirizzo non trovato (404): %s" % dettaglio)
        raise RuntimeError("errore %d: %s" % (e.code, dettaglio))
    except urllib.error.URLError as e:
        raise RuntimeError("non raggiungibile (%s)" % getattr(e, "reason", e))


def miniatura(img):
    """Lo schermo piccolissimo in grigio: serve a capire se e' cambiato dalla foto mandata all'IA."""
    import cv2
    import numpy as np
    grigio = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    return cv2.resize(grigio, (32, 18), interpolation=cv2.INTER_AREA).astype(np.float32)


def jpeg_base64(img, larghezza=512, qualita=70):
    import cv2
    h, w = img.shape[:2]
    if w > larghezza:
        img = cv2.resize(img, (larghezza, max(1, int(h * larghezza / w))), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), qualita])
    if not ok:
        raise RuntimeError("non riesco a comprimere la foto")
    return base64.b64encode(buf.tobytes()).decode("ascii")


def leggi_conoscenza(base):
    """Il testo di fortnite.txt (come funziona il gioco), senza le righe vuote doppie. "" se manca."""
    try:
        with open(os.path.join(base, FILE_CONOSCENZA), "r", encoding="utf-8-sig") as f:
            testo = f.read()
    except OSError:
        return ""
    testo = re.sub(r"\n{3,}", "\n\n", testo.replace("\r\n", "\n")).strip()
    return testo[:CONOSCENZA_MASSIMA]


# ------------------------------------------------------------------ impostazioni (ia.yaml)
def percorso_file(base):
    return os.path.join(base, "ia.yaml")


def leggi_file(base):
    try:
        with open(percorso_file(base), "r", encoding="utf-8") as f:
            dati = yaml.safe_load(f) or {}
        return dati if isinstance(dati, dict) else {}
    except (OSError, yaml.YAMLError):
        return {}


def scrivi_file(base, dati):
    with open(percorso_file(base), "w", encoding="utf-8") as f:
        f.write("# L'IA che guarda: lo scrive il menu 'Collega le IA'. Qui ci sono le TUE chiavi:\n"
                "# non mandare questo file a nessuno.\n")
        yaml.safe_dump(dati, f, allow_unicode=True, sort_keys=False)


def fornitori_da_cfg(cfg_ia):
    """La lista dei fornitori pronti (con chiave se serve), nell'ordine scelto."""
    chiavi = cfg_ia.get("chiavi") or {}
    modelli = cfg_ia.get("modelli") or {}
    risultato = []
    for nome in cfg_ia.get("fornitori") or ORDINE:
        nome = str(nome).strip().lower()
        if nome == "personale":
            p = cfg_ia.get("personale") or {}
            if not p.get("url") or not p.get("modello"):
                continue
            f = {"url": str(p["url"]), "modello": str(p["modello"]), "tipo": "openai",
                 "chiave": str(p.get("chiave") or "") or False, "attesa": 40, "dove": "personale"}
        elif nome in FORNITORI:
            f = dict(FORNITORI[nome])
            if f["chiave"]:
                chiave = str(chiavi.get(nome) or chiavi.get(f.get("stessa_chiave") or "") or "").strip()
                if not chiave:
                    continue                    # serve la chiave e non c'e': lo salto
                f["chiave"] = chiave
            if modelli.get(nome):
                f["modello"] = str(modelli[nome])
            if not f["modello"]:
                continue
        else:
            continue
        f["nome"] = nome
        risultato.append(f)
        # con la stessa chiave anche gli altri modelli che funzionano: ognuno ha il suo limite al giorno
        for altro in modelli.get(nome + "_tutti") or []:
            if str(altro) != f["modello"]:
                risultato.append(dict(f, modello=str(altro), nome="%s/%s" % (nome, altro)))
    return risultato


# ------------------------------------------------------------------ il cervello lento
class IA:
    def __init__(self, cfg, log=print, invia=None, conoscenza=""):
        c = cfg.get("ia", {}) or {}
        self.log = log
        self.conoscenza = conoscenza if c.get("usa_conoscenza", True) else ""
        self.attiva = bool(c.get("attiva", False))
        self.ogni = max(0.5, float(c.get("ogni_secondi", 3) or 3))
        self.validita = float(c.get("validita_secondi", 8) or 8)
        self.validita_fase = float(c.get("validita_fase_secondi", 45) or 45)
        self.fidati_casse = bool(c.get("fidati_delle_casse", True))
        self.fornitori = fornitori_da_cfg(c)
        self.invia = invia or invia_http
        self.ultimo = None
        self.numero = 0
        self.errori = {}               # fornitore -> fino a quando lo lascio riposare
        self.finite = {}               # fornitore -> quante volte di fila ha detto "finite le domande" (429)
        self._foto = None
        self._lock = threading.Lock()
        self._vivo = False
        self._thread = None
        if not self.attiva and c.get("auto_ollama", True):
            # nessuna IA collegata: se sul PC c'e' Ollama con un modello che vede, la collego da solo
            modello = ollama_pronto()
            if modello:
                f = dict(FORNITORI["ollama"], nome="ollama", modello=modello)
                self.fornitori = [f] + [x for x in self.fornitori if x["nome"] != "ollama"]
                self.attiva = True
                self.log("IA: ho trovato Ollama sul computer (%s): la collego da solo" % modello)
        if self.attiva and not self.fornitori:
            self.log("IA: e' accesa ma non c'e' nessuna IA collegata (menu 'Collega le IA').")
            self.attiva = False

    def avvia(self):
        if not self.attiva or self._thread is not None:
            return
        self._vivo = True
        self._thread = threading.Thread(target=self._lavora, daemon=True)
        self._thread.start()
        self.log("IA che guarda: accesa (%s)" % ", ".join(f["nome"] for f in self.fornitori))

    def ferma(self):
        self._vivo = False

    def guarda(self, img):
        """Il bot le passa l'ultima foto (costa niente: la guarda il thread quando e' libero)."""
        if self.attiva:
            with self._lock:
                self._foto = img

    def consiglio(self, adesso=None, validita=None):
        """L'ultimo consiglio se e' abbastanza fresco, altrimenti None."""
        c = self.ultimo
        if c is None:
            return None
        adesso = time.monotonic() if adesso is None else adesso
        if adesso - c.quando > (self.validita if validita is None else validita):
            return None
        return c

    def chiedi(self, img, adesso=None):
        """Chiede alle IA in ordine finche' una risponde. -> Consiglio oppure None."""
        foto = jpeg_base64(img)
        foto_piccola = None                   # per Ollama sul PC: piu' piccola = piu' veloce
        adesso = time.monotonic() if adesso is None else adesso
        scattata = adesso                     # il consiglio vale per il momento della foto
        for f in self.fornitori:
            if self.errori.get(f["nome"], 0) > adesso:
                continue
            try:
                if f["tipo"] == "ollama" and foto_piccola is None:
                    foto_piccola = jpeg_base64(img, 448)
                url, intest, corpo = richiesta(f, foto_piccola if f["tipo"] == "ollama" else foto,
                                               conoscenza=self.conoscenza)
                testo = testo_della_risposta(f, self.invia(url, intest, corpo, f["attesa"]))
                c = leggi_risposta(testo, scattata, f["nome"])
                if c is None:
                    raise RuntimeError("risposta che non capisco: %r" % str(testo)[:80])
                self.numero += 1
                self.finite.pop(f["nome"], None)
                c.numero = self.numero
                c.miniatura = miniatura(img)    # com'era lo schermo nella foto
                self.ultimo = c
                return c
            except Exception as e:
                if "429" in str(e):
                    # finite le domande gratis: aspetto sempre di piu' (fino a 30 minuti) se continua
                    volte = self.finite.get(f["nome"], 0) + 1
                    self.finite[f["nome"]] = volte
                    riposo = min(1800.0, 60.0 * 2 ** (volte - 1))
                else:
                    riposo = 20.0
                self.errori[f["nome"]] = adesso + riposo
                self.log("IA %s: %s (riprovo tra %d s, intanto uso le altre)" % (f["nome"], e, riposo))
        return None

    def chiedi_voto(self, img, domanda, quante=3, attesa=20.0):
        """Fa la stessa domanda a piu' IA veloci INSIEME e restituisce le risposte (dizionari):
        chi chiama decide a maggioranza. Le IA che riposano (finite le domande) non le chiede."""
        adesso = time.monotonic()
        pronte = [f for f in self.fornitori if self.errori.get(f["nome"], 0) <= adesso]
        veloci = [f for f in pronte if f["tipo"] != "ollama" and not f["nome"].startswith("gemma")]
        scelte = (veloci or pronte)[:max(1, int(quante))]
        if not scelte:
            return []
        foto = jpeg_base64(img, 1024, 80)
        risposte = []
        blocco = threading.Lock()

        def chiedi_a(f):
            try:
                url, intest, corpo = richiesta(f, foto, domanda, lunghezza=300)
                dati = leggi_json(testo_della_risposta(f, self.invia(url, intest, corpo, min(attesa, f["attesa"]))))
                if dati:
                    with blocco:
                        risposte.append(dict(dati, _ia=f["nome"]))
            except Exception as e:
                if "429" in str(e):
                    volte = self.finite.get(f["nome"], 0) + 1
                    self.finite[f["nome"]] = volte
                    self.errori[f["nome"]] = time.monotonic() + min(1800.0, 60.0 * 2 ** (volte - 1))
        fili = [threading.Thread(target=chiedi_a, args=(f,), daemon=True) for f in scelte]
        for filo in fili:
            filo.start()
        fine = time.monotonic() + attesa
        for filo in fili:
            filo.join(max(0.0, fine - time.monotonic()))
        with blocco:
            return list(risposte)

    def _lavora(self):
        prossima = 0.0
        while self._vivo:
            time.sleep(0.1)
            if time.monotonic() < prossima:
                continue
            with self._lock:
                img, self._foto = self._foto, None
            if img is None:
                continue
            prossima = time.monotonic() + self.ogni
            try:
                self.chiedi(img)
            except Exception as e:
                self.log("IA: %s" % e)


# ------------------------------------------------------------------ Ollama sul computer
def ollama_modelli(attesa=1.5):
    """I modelli scaricati in Ollama, oppure None se Ollama non e' acceso."""
    try:
        with urllib.request.urlopen(OLLAMA_BASE + "/api/tags", timeout=attesa) as r:
            dati = json.loads(r.read().decode("utf-8", "replace"))
        return [str(m.get("name") or m.get("model") or "") for m in dati.get("models") or []]
    except Exception:
        return None


def ollama_pronto():
    """Il nome del primo modello di Ollama che vede le immagini, oppure None."""
    modelli = ollama_modelli()
    if not modelli:
        return None
    for preferito in OLLAMA_CHE_VEDONO:
        for m in modelli:
            if m.lower().startswith(preferito):
                return m
    return None


def trova_ollama_exe():
    import shutil
    exe = shutil.which("ollama")
    if exe:
        return exe
    for cartella in (os.environ.get("LOCALAPPDATA", ""), os.environ.get("ProgramFiles", "")):
        for sotto in (os.path.join("Programs", "Ollama"), "Ollama"):
            p = os.path.join(cartella, sotto, "ollama.exe")
            if cartella and os.path.isfile(p):
                return p
    return None


def installa_ollama(log=print, modello=OLLAMA_MODELLO):
    """Scarica e installa Ollama (Windows), lo accende e scarica il modello che vede. -> True se ce la fa."""
    import subprocess
    import sys
    import tempfile
    if sys.platform != "win32":
        print("L'installazione automatica di Ollama funziona solo su Windows: vai su ollama.com")
        return False
    exe = trova_ollama_exe()
    if exe is None:
        setup = os.path.join(tempfile.gettempdir(), "OllamaSetup.exe")
        print("Scarico Ollama (circa 1 GB, ci vuole qualche minuto)...", flush=True)

        def avanzamento(blocchi, grandezza, totale):
            if totale > 0 and blocchi % 400 == 0:
                print("  %d%%" % min(100, blocchi * grandezza * 100 // totale), flush=True)
        urllib.request.urlretrieve(OLLAMA_INSTALLATORE, setup, avanzamento)
        print("Installo Ollama (se Windows chiede il permesso, rispondi Si')...", flush=True)
        subprocess.run([setup, "/SILENT", "/NORESTART"], check=False)
        exe = trova_ollama_exe()
        if exe is None:
            print("Non trovo Ollama dopo l'installazione: riavvia il computer e riprova il menu.")
            return False
    if ollama_modelli() is None:
        print("Accendo Ollama...", flush=True)
        try:
            subprocess.Popen([exe, "serve"], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception as e:
            print("Non riesco ad accendere Ollama: %s" % e)
        for _ in range(60):
            if ollama_modelli() is not None:
                break
            time.sleep(1)
    if ollama_pronto():
        return True
    print("Scarico il modello che guarda (%s, circa 3 GB, una volta sola)..." % modello, flush=True)
    subprocess.run([exe, "pull", modello], check=False)
    return ollama_pronto() is not None


# ------------------------------------------------------------------ menu "Collega le IA"
def scegli_modello_openrouter(chiave, invia_get=None):
    """Tra i modelli gratuiti di OpenRouter, il primo che sa guardare le immagini."""
    try:
        if invia_get is None:
            req = urllib.request.Request("https://openrouter.ai/api/v1/models",
                                         headers={"Authorization": "Bearer " + chiave,
                                                  "User-Agent": "BotSparatutto"})
            with urllib.request.urlopen(req, timeout=20) as r:
                dati = json.loads(r.read().decode("utf-8", "replace"))
        else:
            dati = invia_get()
    except Exception:
        return ""
    for m in (dati or {}).get("data") or []:
        ingressi = ((m.get("architecture") or {}).get("input_modalities")) or []
        prezzo = m.get("pricing") or {}
        gratis = str(m.get("id", "")).endswith(":free") or (
            str(prezzo.get("prompt", "1")) in ("0", "0.0") and str(prezzo.get("completion", "1")) in ("0", "0.0"))
        if gratis and "image" in ingressi:
            return str(m["id"])
    return ""


# le IA GRATUITE da collegare con una chiave: la pagina dove la crei e come si riconosce la chiave
GRATIS = {
    "gemini": {"pagina": PAGINA_CHIAVE_GEMINI, "nome": "GOOGLE (Gemma 4 e Gemini)", "inizio": "AIza o AQ.",
               "passi": ["entra con il tuo account Google (email e password le scrivi a Google, non al bot)",
                         "premi 'Create API key' (Crea chiave API) e copia la chiave (inizia con AIza o AQ.)",
                         "se 'Crea chiave' e' grigio, prima crea un progetto (gratis) e sceglilo"],
               "fornitori": ["gemini", "gemma"],
               "nota": "Gratis: con UNA chiave il bot usa tanti modelli di Google, ognuno col suo limite al giorno:\n"
                       "prima le Gemini Flash-Lite (veloci, 1-3 secondi), poi Gemma 4 (lenta ma con tante\n"
                       "domande al giorno). Google chiede di avere 18 anni."},
    "nvidia": {"pagina": PAGINA_CHIAVE_NVIDIA, "nome": "NVIDIA BUILD", "inizio": "nvapi-",
               "passi": ["entra o crea un account NVIDIA gratis (basta l'email, niente carta di credito)",
                         "premi 'Generate API Key' e copia la chiave (inizia con nvapi-...)"],
               "fornitori": ["nvidia"],
               "nota": "Gratis: circa 40 domande al minuto, senza limite al giorno (novembre 2026)."},
}


def serve_chiedere(nome, cfg):
    """All'avvio: chiedo di collegare questa IA gratis se manca la chiave e non hai detto 'mai'."""
    c = cfg.get("ia", {}) or {}
    return not str((c.get("chiavi") or {}).get(nome) or "").strip() and not c.get("non_chiedere_" + nome)


def serve_chiedere_gemini(cfg):
    return serve_chiedere("gemini", cfg)


def modelli_nvidia(invia_get=None):
    """I modelli di NVIDIA Build che guardano le immagini, dal piu' adatto (la lista e' pubblica)."""
    try:
        if invia_get is None:
            req = urllib.request.Request("https://integrate.api.nvidia.com/v1/models",
                                         headers={"User-Agent": "BotSparatutto"})
            with urllib.request.urlopen(req, timeout=20) as r:
                dati = json.loads(r.read().decode("utf-8", "replace"))
        else:
            dati = invia_get()
        tutti = [str(m.get("id", "")) for m in (dati or {}).get("data") or []]
    except Exception:
        tutti = []
    if not tutti:
        return list(NVIDIA_PREFERITI)
    vista = [m for m in tutti if any(p in m.lower() for p in NVIDIA_PAROLE_VISTA) and "embed" not in m.lower()]
    return [m for m in NVIDIA_PREFERITI if m in vista] + [m for m in vista if m not in NVIDIA_PREFERITI]


def prova_modelli(f, candidati, foto, invia=None, massimo=5):
    """Prova i modelli in ordine finche' uno guarda la foto e risponde bene. -> (modello, messaggio)."""
    ultimo = "nessun modello da provare"
    for modello in list(candidati)[:massimo]:
        ok, ultimo = prova_fornitore(dict(f, modello=modello), foto, invia)
        print("   %s %s: %s" % ("OK" if ok else "NO", modello, ultimo), flush=True)
        if ok:
            return modello, ultimo
    return None, ultimo


def elenco_google(chiave, invia_get=None):
    """I modelli che Google da' a questa chiave (solo quelli che rispondono a generateContent).
    None se non riesco a chiederlo (allora provo quelli che conosco)."""
    try:
        if invia_get is None:
            req = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models?pageSize=500",
                                         headers={"x-goog-api-key": chiave, "User-Agent": "BotSparatutto"})
            with urllib.request.urlopen(req, timeout=20) as r:
                dati = json.loads(r.read().decode("utf-8", "replace"))
        else:
            dati = invia_get()
        return [str(m.get("name", "")).replace("models/", "") for m in (dati or {}).get("models") or []
                if "generateContent" in (m.get("supportedGenerationMethods") or [])]
    except Exception:
        return None


def candidati_google(fornitore, disponibili):
    """I modelli da provare: quelli che conosco (se Google li da' ancora) e poi gli altri simili nuovi."""
    noti = FORNITORI[fornitore]["candidati"]
    if disponibili is None:
        return list(noti)
    scarta = ("tts", "image", "audio", "live", "embed", "transcribe", "robotics", "computer-use", "banana")
    if fornitore == "gemma":
        simili = [m for m in disponibili if m.startswith("gemma-") and m.endswith("-it")]
    else:
        simili = [m for m in disponibili if m.startswith("gemini-") and "flash-lite" in m]
    simili = [m for m in simili if not any(p in m for p in scarta)]
    return [m for m in noti if m in disponibili] + [m for m in simili if m not in noti]


def prova_tutti(f, candidati, foto, invia=None, dormi=time.sleep):
    """Prova TUTTI i modelli (stessa chiave): -> la lista di quelli che funzionano."""
    buoni = []
    for modello in candidati:
        ok, messaggio = prova_fornitore(dict(f, modello=modello), foto, invia)
        if not ok and ("500" in messaggio or "503" in messaggio):
            dormi(2)                                   # errore di Google passeggero: riprovo una volta
            ok, messaggio = prova_fornitore(dict(f, modello=modello), foto, invia)
        print("   %s %s: %s" % ("OK" if ok else "NO", modello, messaggio), flush=True)
        if ok:
            buoni.append(modello)
    return buoni


def collega_chiave(nome, base, cfg, log=print, foto=None, apri=None, chiedi=None, invia=None, modelli_get=None):
    """Collega un'IA GRATUITA con la sua chiave: apre la pagina dove la crei, tu la incolli qui.
    La prova con una foto e la salva in ia.yaml. -> True se funziona."""
    import numpy as np
    info = GRATIS[nome]
    chiedi = chiedi or input
    if apri is None:
        import webbrowser
        apri = webbrowser.open
    print("\n" + "=" * 70)
    print("  COLLEGA %s (IA gratis che guarda il gioco e aiuta il bot)" % info["nome"])
    print("=" * 70)
    print(info["nota"])
    print("Ti apro la pagina. Li':")
    for i, passo in enumerate(info["passi"], 1):
        print("  %d. %s" % (i, passo))
    print("  %d. torna qui, incollala (tasto destro o Ctrl+V) e premi INVIO" % (len(info["passi"]) + 1))
    print("Se la pagina non si apre, scrivi tu nel browser:  %s" % info["pagina"])
    print("ATTENZIONE: le foto del gioco vengono mandate a questo servizio.")
    try:
        apri(info["pagina"])
    except Exception:
        pass
    try:
        chiave = chiedi("\nIncolla la chiave e premi INVIO (solo INVIO = non adesso, mai = non chiederlo piu'): ")
    except (EOFError, KeyboardInterrupt):
        chiave = ""
    chiave = str(chiave or "").strip().strip('"').strip("'")
    dati = leggi_file(base)
    if chiave.lower() == "mai":
        dati["non_chiedere_" + nome] = True
        scrivi_file(base, dati)
        print("Va bene, non te lo chiedo piu' (si collega sempre dal menu 15).")
        return False
    if not chiave:
        print("Va bene, per ora niente. Te lo richiedo la prossima volta.")
        return False
    if "@" in chiave or " " in chiave:
        print("Questa non e' una chiave (sembra un'email o una password): non la salvo.")
        print("La chiave la trovi sulla pagina dopo averla creata e inizia con %s" % info["inizio"])
        return False
    if foto is None:
        try:
            from occhi import Schermo
            sch = cfg.get("schermo", {}) or {}
            s = Schermo(int(sch.get("monitor", 1) or 1), sch.get("zona_cattura"))
            foto = s.foto()
            s.chiudi()
        except Exception:
            foto = np.full((360, 640, 3), 90, np.uint8)
    modelli = dict(dati.get("modelli") or {})
    funzionano = []
    disponibili = elenco_google(chiave, modelli_get) if nome == "gemini" else None
    for fornitore in info["fornitori"]:
        f = dict(FORNITORI[fornitore], nome=fornitore, chiave=chiave)
        if fornitore == "nvidia":
            candidati = [modelli["nvidia"]] if modelli.get("nvidia") else modelli_nvidia(modelli_get)
        else:
            candidati = candidati_google(fornitore, disponibili)
        print("Provo %s..." % fornitore.upper(), flush=True)
        if f.get("candidati"):
            buoni = prova_tutti(f, candidati, foto, invia)
            if buoni:
                modelli[fornitore] = buoni[0]
                modelli[fornitore + "_tutti"] = buoni
                funzionano.append(fornitore)
            continue
        modello, _ = prova_modelli(f, candidati, foto, invia)
        if modello:
            modelli[fornitore] = modello
            funzionano.append(fornitore)
    if not funzionano:
        print("Con questa chiave non risponde nessuna IA: controlla di averla copiata tutta e riprova.")
        return False
    chiavi = dict(dati.get("chiavi") or {})
    chiavi[nome] = chiave
    dati["chiavi"] = chiavi
    dati["modelli"] = modelli
    insieme = set(dati.get("fornitori") or []) | set(funzionano)
    dati["fornitori"] = [n for n in ORDINE if n in insieme] + sorted(insieme - set(ORDINE))
    dati["attiva"] = True
    dati.pop("non_chiedere_" + nome, None)
    scrivi_file(base, dati)
    print("Collegate: %s. L'IA che guarda e' ACCESA (ordine: %s)." % (", ".join(funzionano),
                                                                     ", ".join(dati["fornitori"])))
    return True


def collega_gemini(base, cfg, log=print, foto=None, apri=None, chiedi=None, invia=None, modelli_get=None):
    """Google (Gemini e Gemma 4) con il tuo account Google."""
    return collega_chiave("gemini", base, cfg, log, foto, apri, chiedi, invia, modelli_get)


def collega_nvidia(base, cfg, log=print, foto=None, apri=None, chiedi=None, invia=None, modelli_get=None):
    """NVIDIA Build: gratis, senza carta di credito."""
    return collega_chiave("nvidia", base, cfg, log, foto, apri, chiedi, invia, modelli_get)


def collega_gratis(base, cfg, log=print, solo_se_mancano=False):
    """Menu 15 (e all'avvio): collega le IA gratuite, Google e NVIDIA. Insieme bastano per giorni."""
    collegate = False
    for nome in GRATIS:
        if solo_se_mancano and not serve_chiedere(nome, cfg):
            continue
        if collega_chiave(nome, base, cfg, log):
            collegate = True
    return collegate


def prova_fornitore(f, img, invia=None):
    """Prova un'IA con una foto: -> (ok, messaggio)."""
    invia = invia or invia_http
    try:
        inizio = time.monotonic()
        url, intest, corpo = richiesta(f, jpeg_base64(img))
        testo = testo_della_risposta(f, invia(url, intest, corpo, f["attesa"]))
        c = leggi_risposta(testo)
        secondi = time.monotonic() - inizio
        if c is None:
            return False, "risponde ma non come serve: %r" % str(testo)[:80]
        return True, "funziona (%.1f secondi): vede '%s'" % (secondi, c.descrizione())
    except Exception as e:
        return False, str(e)


def collega(base, cfg, log=print, foto=None):
    """Menu 'Collega le IA': prova quelle senza chiave, chiede le chiavi delle altre, salva ia.yaml."""
    import numpy as np
    dati = leggi_file(base)
    chiavi = dict(dati.get("chiavi") or {})
    modelli = dict(dati.get("modelli") or {})
    if foto is None:
        try:
            from occhi import Schermo
            sch = cfg.get("schermo", {}) or {}
            s = Schermo(int(sch.get("monitor", 1) or 1), sch.get("zona_cattura"))
            foto = s.foto()
            s.chiudi()
        except Exception:
            foto = np.full((360, 640, 3), 90, np.uint8)
    print("\n" + "=" * 70)
    print("  COLLEGA LE IA (il cervello che guarda)")
    print("=" * 70)
    print("Ogni tanto il bot manda una foto piccola dello schermo all'IA e le chiede cosa succede")
    print("(bus, caduta, casse vere, muri, tempesta). ATTENZIONE: le foto vanno al servizio scelto.")
    print("Apri prima il gioco (o Remote Play): le prove usano una foto dello schermo di adesso.\n")
    # 1) Ollama sul computer: gratis, senza chiave. Se non c'e', la installo (se vuoi)
    if not ollama_pronto():
        print("OLLAMA (l'IA gratis SENZA chiave, gira sul tuo computer): non e' ancora pronta.")
        try:
            r = input("La installo io? Scarica circa 4 GB una volta sola. Scrivi s e premi INVIO "
                      "(solo INVIO = no): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            r = ""
        if r.startswith("s"):
            installa_ollama(log)
    modello_ollama = ollama_pronto()
    if modello_ollama:
        modelli["ollama"] = modello_ollama
    print("\nProvo Ollama (se c'e'), poi le IA online: sono piu' veloci ma vogliono una chiave GRATUITA"
          " (INVIO = salta).")
    funzionano = []
    # prima Gemini e poi Gemma (usa la stessa chiave), poi le altre
    for nome in ["ollama", "gemini", "gemma", "nvidia"] + [n for n in ORDINE if n not in (
            "ollama", "gemini", "gemma", "nvidia", "personale")]:
        info = FORNITORI[nome]
        if nome == "ollama":
            if not modello_ollama:
                continue
            print("OLLAMA (%s): provo... (la prima volta puo' metterci un minuto)" % modello_ollama, flush=True)
        elif info.get("stessa_chiave"):
            if not chiavi.get(info["stessa_chiave"]):
                continue
            chiavi[nome] = chiavi[info["stessa_chiave"]]
            print("%s - con la stessa chiave di %s: provo..." % (nome.upper(), info["stessa_chiave"].upper()),
                  flush=True)
        elif info["chiave"]:
            vecchia = chiavi.get(nome, "")
            try:
                nuova = input("%s - chiave gratuita da %s\n   incollala e premi INVIO (solo INVIO = %s): " % (
                    nome.upper(), info["dove"], "tieni quella di prima" if vecchia else "salta")).strip()
            except (EOFError, KeyboardInterrupt):
                nuova = ""
            if nuova:
                chiavi[nome] = nuova
            if not chiavi.get(nome):
                continue
        else:
            print("%s - senza chiave (%s): provo..." % (nome.upper(), info["dove"]), flush=True)
        f = dict(info, nome=nome)
        if f["chiave"]:
            f["chiave"] = chiavi[nome]
        if nome == "openrouter" and not modelli.get(nome):
            modelli[nome] = scegli_modello_openrouter(chiavi[nome])
        if info.get("candidati"):
            buoni = prova_tutti(f, candidati_google(nome, elenco_google(f["chiave"])), foto)
            if buoni:
                modelli[nome] = buoni[0]
                modelli[nome + "_tutti"] = buoni
                funzionano.append(nome)
            continue
        if nome == "nvidia":
            candidati = ([modelli[nome]] if modelli.get(nome) else []) + [
                m for m in modelli_nvidia() if m != modelli.get(nome)]
            modello, _ = prova_modelli(f, candidati, foto)
            if modello:
                modelli[nome] = modello
                funzionano.append(nome)
            continue
        if modelli.get(nome):
            f["modello"] = modelli[nome]
        if not f["modello"]:
            print("   non trovo un modello gratuito che guarda le immagini")
            continue
        ok, messaggio = prova_fornitore(f, foto)
        print("   %s %s" % ("OK" if ok else "NO", messaggio))
        if ok:
            funzionano.append(nome)
    funzionano = [n for n in ORDINE if n in funzionano]
    chiavi.pop("gemma", None)                     # Gemma usa la chiave di Gemini: non la copio
    dati["chiavi"] = chiavi
    dati["modelli"] = modelli
    if funzionano:
        dati["attiva"] = True
        dati["fornitori"] = funzionano
        print("\nIA collegate: %s. L'IA che guarda e' ACCESA." % ", ".join(funzionano))
    else:
        dati["attiva"] = False
        print("\nNessuna IA funziona per ora: il bot gioca lo stesso, senza.")
    scrivi_file(base, dati)
    return funzionano
