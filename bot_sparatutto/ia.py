"""
ia.py - L'IA che GUARDA (il "cervello lento" del bot).

Ogni tanto (ia -> ogni_secondi) manda una foto piccola dello schermo a un'IA che sa
guardare le immagini e le chiede cosa sta succedendo nella partita:
  fase (bus, caduta, gioco, menu, morto), se c'e' una cassa vera e da che parte,
  se ha un muro davanti, se la tempesta e' vicina e da che parte e' la zona sicura.
Il bot veloce (mira, spara, si muove) NON la aspetta mai: usa l'ultima risposta.

Le IA si provano in ordine (ia -> fornitori): se una non risponde o ha finito le
richieste gratis, si passa alla prossima.
  ollama       sul TUO computer: gratis, senza chiave e senza account. Va installato
               Ollama (ollama.com) e un modello che vede (es. "ollama pull moondream").
               Senza scheda video e' lento (anche 20-30 secondi a foto).
  pollinations online, senza chiave (gratis ma limitato: a volte non risponde)
  gemini       Google, gratis con chiave (aistudio.google.com)
  github       GitHub Models, gratis con un token di GitHub
  openrouter   modelli ":free" gratis con chiave (openrouter.ai)
  groq         gratis con chiave (console.groq.com)
  mistral      gratis con chiave (console.mistral.ai)
  zai          GLM-4.6V-Flash gratis con chiave (z.ai)
  personale    qualsiasi IA "compatibile OpenAI": indirizzo, modello e chiave in ia.yaml
Le chiavi stanno nel file ia.yaml (accanto al programma): lo scrive il menu
"Collega le IA". Attenzione: le foto del gioco vengono mandate al servizio scelto.
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
    "ollama": {"url": "http://localhost:11434/api/chat", "modello": "moondream", "tipo": "ollama",
               "chiave": False, "attesa": 90, "dove": "sul tuo computer (ollama.com)"},
    "pollinations": {"url": "https://text.pollinations.ai/openai", "modello": "openai", "tipo": "openai",
                     "chiave": False, "attesa": 30, "dove": "pollinations.ai"},
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
ORDINE = ["ollama", "pollinations", "gemini", "github", "openrouter", "groq", "mistral", "zai", "personale"]

DOMANDA = (
    "You help a bot play a Fortnite-like third-person shooter. Look at this game screenshot and "
    "answer ONLY with one JSON object, no other text:\n"
    '{"phase": "bus|falling|playing|menu|dead|unknown", '
    '"chest": "none|left|center|right", "wall_ahead": true|false, '
    '"storm_near": true|false, "safe_direction": "left|right|ahead|behind|unknown", '
    '"enemy": true|false}\n'
    "phase: bus = riding the battle bus, falling = skydiving or gliding, menu = lobby or menus, "
    "dead = eliminated or spectating. chest = a closed loot chest (golden glowing box) in the 3D world, "
    "NOT icons of the interface; tell where it is on screen. wall_ahead = a wall, rock or obstacle "
    "right in front of the character, very close. storm_near = the storm (purple wall or purple sky) "
    "is close or the character is inside it; safe_direction = where to go to get away from it."
)

FASI = ("bus", "falling", "playing", "menu", "dead", "unknown")
LATI = ("none", "left", "center", "right")
DIREZIONI = ("left", "right", "ahead", "behind", "unknown")


class Consiglio:
    """Quello che l'IA ha visto in una foto."""

    def __init__(self, fase="unknown", cassa="none", muro=False, tempesta=False, direzione="unknown",
                 nemico=False, quando=0.0, fornitore=""):
        self.fase = fase
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
        quando=quando, fornitore=fornitore)


# ------------------------------------------------------------------ come si parla a ogni IA
def richiesta(fornitore, jpeg_base64, domanda=DOMANDA):
    """-> (url, intestazioni, corpo in bytes) per chiedere all'IA di guardare la foto."""
    intestazioni = {"Content-Type": "application/json", "User-Agent": "BotSparatutto"}
    if fornitore["chiave"]:
        intestazioni["Authorization"] = "Bearer " + fornitore["chiave"]
    if fornitore["tipo"] == "ollama":
        corpo = {"model": fornitore["modello"], "stream": False,
                 "options": {"temperature": 0.1, "num_predict": 160},
                 "messages": [{"role": "user", "content": domanda, "images": [jpeg_base64]}]}
    else:
        corpo = {"model": fornitore["modello"], "temperature": 0.1, "max_tokens": 160,
                 "messages": [{"role": "user", "content": [
                     {"type": "text", "text": domanda},
                     {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + jpeg_base64}}]}]}
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


def jpeg_base64(img, larghezza=512, qualita=70):
    import cv2
    h, w = img.shape[:2]
    if w > larghezza:
        img = cv2.resize(img, (larghezza, max(1, int(h * larghezza / w))), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), qualita])
    if not ok:
        raise RuntimeError("non riesco a comprimere la foto")
    return base64.b64encode(buf.tobytes()).decode("ascii")


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
    def __init__(self, cfg, log=print, invia=None):
        c = cfg.get("ia", {}) or {}
        self.log = log
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
        adesso = time.monotonic() if adesso is None else adesso
        scattata = adesso                     # il consiglio vale per il momento della foto
        for f in self.fornitori:
            if self.errori.get(f["nome"], 0) > adesso:
                continue
            try:
                url, intest, corpo = richiesta(f, foto)
                testo = testo_della_risposta(f, self.invia(url, intest, corpo, f["attesa"]))
                c = leggi_risposta(testo, scattata, f["nome"])
                if c is None:
                    raise RuntimeError("risposta che non capisco: %r" % str(testo)[:80])
                self.numero += 1
                c.numero = self.numero
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
    funzionano = []
    for nome in ORDINE:
        if nome == "personale":
            continue
        info = FORNITORI[nome]
        if info["chiave"]:
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
        if not ok and nome == "ollama":
            print("   (per usarla: installa Ollama da ollama.com, poi nel Prompt dei comandi scrivi:"
                  " ollama pull moondream)")
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
