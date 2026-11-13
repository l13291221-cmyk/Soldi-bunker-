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

GEMINI CON L'ACCOUNT GOOGLE: quando avvii il bot e non c'e' ancora Gemini, il bot apre da
solo la pagina di Google (aistudio.google.com/apikey): ENTRI TU con il tuo account Google
nel browser, premi "Create API key", copi la chiave e la incolli nel bot. Email e password
le scrivi solo a Google: il bot non le chiede e non le salva (Google non lascia entrare i
programmi con la password: la chiave e' il modo che Google da' ai programmi).

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
    "gemini": {"url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
               "modello": "gemini-flash-lite-latest", "tipo": "openai", "chiave": True, "attesa": 30,
               "dove": "aistudio.google.com (chiave gratuita; Google chiede di avere 18 anni)"},
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
}
ORDINE = ["ollama", "gemini", "github", "openrouter", "groq", "mistral", "zai", "personale"]
OLLAMA_BASE = "http://localhost:11434"
OLLAMA_MODELLO = "qwen2.5vl:3b"          # piccolo, vede le immagini, risponde bene in JSON e trova i pulsanti
# nomi dei modelli di Ollama che sanno guardare le immagini (il primo trovato si usa)
OLLAMA_CHE_VEDONO = ("qwen2.5vl", "qwen3-vl", "gemma3", "llava", "minicpm-v", "llama3.2-vision",
                     "granite3.2-vision", "moondream", "bakllava")
OLLAMA_INSTALLATORE = "https://ollama.com/download/OllamaSetup.exe"
PAGINA_CHIAVE_GEMINI = "https://aistudio.google.com/apikey"   # si entra col proprio account Google
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
    '"key": "none|space|enter|esc|e|f", "downed_teammate": "none|left|center|right|close"}\n'
    "phase: bus = riding the battle bus, falling = skydiving or gliding, menu = lobby or menus, "
    "dead = eliminated or spectating. chest = a closed loot chest (golden glowing box) in the 3D world, "
    "NOT icons of the interface; tell where it is on screen. wall_ahead = a wall, rock or obstacle "
    "right in front of the character, very close. storm_near = the storm (purple wall or purple sky) "
    "is close or the character is inside it; safe_direction = where to go to get away from it. "
    "low_health = the health or shield bar is low. vehicle = a car or other vehicle in the world "
    "(close = right next to the character); in_vehicle = the character is driving or riding one. "
    "button = ONLY in lobby, menus or after being eliminated: the one button to press to get to the "
    "NEXT MATCH (Return to Lobby, Play, Ready, Continue, Skip...), as fractions of screen width and "
    "height; never Quit or Exit game. cursor = where the mouse pointer is, if you see it. "
    "key = a key the screen says to press to continue (for example 'Press SPACE'), else none. "
    "downed_teammate = a knocked-down teammate (crawling, waiting to be revived), close = right next "
    "to the character."
)

FASI = ("bus", "falling", "playing", "menu", "dead", "unknown")
LATI = ("none", "left", "center", "right")
VEICOLO = ("none", "left", "center", "right", "close")
TASTI = ("none", "space", "enter", "esc", "e", "f")
NOMI_TASTI = {"space": "spazio", "enter": "invio", "esc": "esc", "e": "e", "f": "f"}
DIREZIONI = ("left", "right", "ahead", "behind", "unknown")


class Consiglio:
    """Quello che l'IA ha visto in una foto."""

    def __init__(self, fase="unknown", cassa="none", muro=False, tempesta=False, direzione="unknown",
                 nemico=False, quando=0.0, fornitore="", poca_vita=False, veicolo="none", in_veicolo=False,
                 pulsante=None, cursore=None, tasto="none", compagno="none"):
        self.fase = fase
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


def leggi_risposta(testo, quando=0.0, fornitore=""):
    """Dal testo dell'IA a un Consiglio (anche se aggiunge parole o ```json intorno). None se non capisce."""
    if not testo:
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
        compagno=_scegli(dati.get("downed_teammate"), VEICOLO, "none"))


# ------------------------------------------------------------------ come si parla a ogni IA
def richiesta(fornitore, jpeg_base64, domanda=DOMANDA, conoscenza="", lunghezza=260):
    """-> (url, intestazioni, corpo in bytes) per chiedere all'IA di guardare la foto.
    conoscenza = come funziona il gioco (fortnite.txt): va alle IA online come messaggio di
    sistema. A Ollama sul PC no: senza scheda video un testo lungo la rallenta troppo."""
    intestazioni = {"Content-Type": "application/json", "User-Agent": "BotSparatutto"}
    if fornitore["chiave"]:
        intestazioni["Authorization"] = "Bearer " + fornitore["chiave"]
    if fornitore["tipo"] == "ollama":
        corpo = {"model": fornitore["modello"], "stream": False, "format": "json",
                 "options": {"temperature": 0.1, "num_predict": lunghezza},
                 "messages": [{"role": "user", "content": domanda, "images": [jpeg_base64]}]}
    else:
        messaggi = []
        if conoscenza:
            messaggi.append({"role": "system", "content": "What you know about the game (from the player, "
                             "in Italian):\n" + conoscenza})
        messaggi.append({"role": "user", "content": [
            {"type": "text", "text": domanda},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + jpeg_base64}}]})
        corpo = {"model": fornitore["modello"], "temperature": 0.1, "max_tokens": lunghezza, "messages": messaggi}
    return fornitore["url"], intestazioni, json.dumps(corpo).encode("utf-8")


def testo_della_risposta(fornitore, dati):
    if fornitore["tipo"] == "ollama":
        return ((dati or {}).get("message") or {}).get("content", "")
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
                chiave = str(chiavi.get(nome) or "").strip()
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
                c.numero = self.numero
                c.miniatura = miniatura(img)    # com'era lo schermo nella foto
                self.ultimo = c
                return c
            except Exception as e:
                riposo = 60.0 if "429" in str(e) else 20.0
                self.errori[f["nome"]] = adesso + riposo
                self.log("IA %s: %s (riprovo tra %d s, intanto uso le altre)" % (f["nome"], e, riposo))
        return None

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


def serve_chiedere_gemini(cfg):
    """All'avvio: chiedo di collegare Gemini se non c'e' la sua chiave e non hai detto 'mai'."""
    c = cfg.get("ia", {}) or {}
    return not str((c.get("chiavi") or {}).get("gemini") or "").strip() and not c.get("non_chiedere_gemini")


def collega_gemini(base, cfg, log=print, foto=None, apri=None, chiedi=None, invia=None):
    """Collega Gemini con il tuo account Google: apre la pagina di Google, tu entri e crei la
    chiave, la incolli qui. La prova e la salva in ia.yaml. -> True se funziona."""
    import numpy as np
    chiedi = chiedi or input
    if apri is None:
        import webbrowser
        apri = webbrowser.open
    print("\n" + "=" * 70)
    print("  COLLEGA GEMINI (l'IA di Google che guarda il gioco e aiuta il bot)")
    print("=" * 70)
    print("Ti apro la pagina di Google. Li':")
    print("  1. entra con il tuo account Google (email e password le scrivi a Google, non al bot)")
    print("  2. premi 'Create API key' (Crea chiave API) e poi copia la chiave (inizia con AIza...)")
    print("  3. torna qui, incollala (tasto destro o Ctrl+V) e premi INVIO")
    print("Se la pagina non si apre, scrivi tu nel browser:  %s" % PAGINA_CHIAVE_GEMINI)
    print("Google la da' gratis (con un limite di richieste al giorno) a chi ha almeno 18 anni.")
    print("ATTENZIONE: le foto del gioco vengono mandate a Google.")
    try:
        apri(PAGINA_CHIAVE_GEMINI)
    except Exception:
        pass
    try:
        chiave = chiedi("\nIncolla la chiave e premi INVIO (solo INVIO = non adesso, mai = non chiederlo piu'): ")
    except (EOFError, KeyboardInterrupt):
        chiave = ""
    chiave = str(chiave or "").strip().strip('"').strip("'")
    dati = leggi_file(base)
    if chiave.lower() == "mai":
        dati["non_chiedere_gemini"] = True
        scrivi_file(base, dati)
        print("Va bene, non te lo chiedo piu' (si collega sempre dal menu 14).")
        return False
    if not chiave:
        print("Va bene, il bot gioca senza Gemini. Te lo richiedo la prossima volta.")
        return False
    if "@" in chiave or " " in chiave:
        print("Questa non e' una chiave (sembra un'email o una password): non la salvo.")
        print("La chiave la trovi sulla pagina di Google dopo 'Create API key' e inizia con AIza.")
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
    f = dict(FORNITORI["gemini"], nome="gemini", chiave=chiave)
    modello = ((dati.get("modelli") or {}).get("gemini") or "").strip()
    if modello:
        f["modello"] = modello
    print("Provo Gemini...", flush=True)
    ok, messaggio = prova_fornitore(f, foto, invia)
    print("   %s %s" % ("OK" if ok else "NO", messaggio))
    if not ok:
        print("Gemini non risponde con questa chiave: controlla di averla copiata tutta e riprova.")
        return False
    chiavi = dict(dati.get("chiavi") or {})
    chiavi["gemini"] = chiave
    dati["chiavi"] = chiavi
    fornitori = [x for x in (dati.get("fornitori") or []) if x != "gemini"]
    dati["fornitori"] = ["gemini"] + fornitori              # Gemini per prima: e' la piu' brava
    dati["attiva"] = True
    dati.pop("non_chiedere_gemini", None)
    scrivi_file(base, dati)
    print("Gemini e' collegata: l'IA che guarda e' ACCESA.")
    return True


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
    for nome in ORDINE:
        if nome == "personale":
            continue
        info = FORNITORI[nome]
        if nome == "ollama":
            if not modello_ollama:
                continue
            print("OLLAMA (%s): provo... (la prima volta puo' metterci un minuto)" % modello_ollama, flush=True)
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
        if modelli.get(nome):
            f["modello"] = modelli[nome]
        if not f["modello"]:
            print("   non trovo un modello gratuito che guarda le immagini")
            continue
        ok, messaggio = prova_fornitore(f, foto)
        print("   %s %s" % ("OK" if ok else "NO", messaggio))
        if ok:
            funzionano.append(nome)
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
