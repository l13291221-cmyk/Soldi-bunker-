"""
occhi.py - Gli "occhi" del bot: catturano lo schermo e trovano cosa c'e'.

Come riconosce le cose:
  0. OCCHIO UNIVERSALE : una rete neurale gia' addestrata (YOLOX, su milioni di foto)
                che riconosce le persone/personaggi in QUALSIASI gioco, senza
                calibrare niente. E' quella che fa adattare il bot a ogni gioco.
  1. COLORI   : casse, casse dei materiali, armi (e anche nemici) hanno spesso un
                colore tipico (luce dorata delle casse...). Si calibrano col menu
                "Calibra colori" oppure il bot li impara guardando te ("Impara").
  2. IA DEL TUO GIOCO : (facoltativa, la piu' forte) una rete YOLO addestrata sulle
                foto del TUO gioco, salvata come file .onnx nella cartella modelli.
  3. IMMAGINI : pezzetti di schermo salvati (pulsanti, scritte tipo "Squadra
                eliminata") da usare nelle istruzioni: "QUANDO vedi ... FAI ...".
  4. VITA     : la barra della vita, letta guardando quanto e' piena.

Le zone dello schermo si scrivono come frazioni: [x, y, larghezza, altezza]
dove 0 = bordo sinistro/alto e 1 = bordo destro/basso. Cosi' valgono a ogni risoluzione.
"""

import os
import time

import cv2
import numpy as np

# nemico, cassa (casse delle armi), materiali (casse dei materiali/munizioni), arma (armi per terra),
# testa (facoltativa, per mirare meglio), alleato (segni dei compagni di squadra: non sparargli)
CATEGORIE = ("nemico", "cassa", "materiali", "arma", "testa", "alleato")


# ------------------------------------------------------------------ oggetti trovati
class Box:
    __slots__ = ("x", "y", "w", "h", "punteggio", "categoria", "fonte")

    def __init__(self, x, y, w, h, punteggio=1.0, categoria="", fonte=""):
        self.x = float(x)
        self.y = float(y)
        self.w = float(w)
        self.h = float(h)
        self.punteggio = float(punteggio)
        self.categoria = categoria
        self.fonte = fonte

    @property
    def cx(self):
        return self.x + self.w / 2

    @property
    def cy(self):
        return self.y + self.h / 2

    @property
    def fondo(self):
        return self.y + self.h

    def contiene(self, px, py):
        return self.x <= px <= self.x + self.w and self.y <= py <= self.y + self.h

    def __repr__(self):
        return "Box(%s %.0f,%.0f %.0fx%.0f p=%.2f)" % (self.categoria, self.x, self.y, self.w, self.h, self.punteggio)


class Visione:
    """Quello che il bot vede in un fotogramma."""

    def __init__(self, larghezza, altezza):
        self.larghezza = larghezza
        self.altezza = altezza
        self.oggetti = {c: [] for c in CATEGORIE}
        self.vita = None            # 0-100, oppure None se la barra non e' configurata
        self.interazione = False    # True se si vede la scritta "premi E" (se configurata)
        self.t = time.monotonic()

    @property
    def nemici(self):
        return self.oggetti["nemico"]

    @property
    def casse(self):
        return self.oggetti["cassa"]

    @property
    def materiali(self):
        return self.oggetti["materiali"]

    @property
    def armi(self):
        return self.oggetti["arma"]


# ------------------------------------------------------------------ cattura dello schermo
class Schermo:
    """Cattura lo schermo con mss (veloce, funziona su Windows/Mac/Linux)."""

    def __init__(self, monitor=1, zona=None):
        import mss
        self._mss = mss.mss()
        monitors = self._mss.monitors
        if monitor < 1 or monitor >= len(monitors):
            monitor = 1
        m = monitors[monitor]
        if zona:
            zx, zy, zw, zh = zona
            self.area = {"left": int(m["left"] + zx * m["width"]), "top": int(m["top"] + zy * m["height"]),
                         "width": max(16, int(zw * m["width"])), "height": max(16, int(zh * m["height"]))}
        else:
            self.area = {"left": m["left"], "top": m["top"], "width": m["width"], "height": m["height"]}

    @property
    def origine(self):
        """Dove si trova (in pixel del desktop) l'angolo in alto a sinistra dell'immagine catturata."""
        return self.area["left"], self.area["top"]

    def foto(self):
        img = np.asarray(self._mss.grab(self.area))
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    def chiudi(self):
        try:
            self._mss.close()
        except Exception:
            pass


class SchermoFinto:
    """Per i test: restituisce immagini gia' pronte."""

    def __init__(self, immagini):
        self.immagini = list(immagini)
        self.i = 0
        self.origine = (0, 0)

    def foto(self):
        img = self.immagini[min(self.i, len(self.immagini) - 1)]
        self.i += 1
        return img.copy()

    def chiudi(self):
        pass


# ------------------------------------------------------------------ colori
def _intervallo(r):
    """Accetta {tinta: [a, b], saturazione: [a, b], luminosita: [a, b]} (anche h/s/v)."""
    def prendi(chiavi, predefinito):
        for k in chiavi:
            if k in r and r[k] is not None:
                a, b = r[k]
                return int(a), int(b)
        return predefinito
    h = prendi(("tinta", "h", "hue"), (0, 179))
    s = prendi(("saturazione", "s", "sat"), (0, 255))
    v = prendi(("luminosita", "luminosità", "v", "val"), (0, 255))
    return h, s, v


def maschera_colori(hsv, intervalli):
    """Maschera bianca dove il colore e' dentro uno degli intervalli."""
    maschera = None
    for r in intervalli or []:
        (h1, h2), (s1, s2), (v1, v2) = _intervallo(r)
        if h1 <= h2:
            m = cv2.inRange(hsv, (h1, s1, v1), (h2, s2, v2))
        else:   # il rosso "fa il giro": es. da 170 a 10
            m = cv2.inRange(hsv, (h1, s1, v1), (179, s2, v2)) | cv2.inRange(hsv, (0, s1, v1), (h2, s2, v2))
        maschera = m if maschera is None else (maschera | m)
    if maschera is None:
        maschera = np.zeros(hsv.shape[:2], np.uint8)
    return maschera


def box_da_maschera(maschera, area_minima, unisci=5, categoria="", scala=1.0):
    """Dalle macchie bianche della maschera ai rettangoli (in pixel dell'immagine originale)."""
    if unisci > 0:
        k = cv2.getStructuringElement(cv2.MORPH_RECT, (unisci, unisci))
        maschera = cv2.morphologyEx(maschera, cv2.MORPH_CLOSE, k)
    n, _, stats, _ = cv2.connectedComponentsWithStats(maschera, connectivity=8)
    risultato = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < area_minima:
            continue
        riempimento = area / float(max(1, w * h))
        risultato.append(Box(x / scala, y / scala, w / scala, h / scala,
                             punteggio=min(1.0, 0.3 + riempimento), categoria=categoria, fonte="colore"))
    return risultato


# ------------------------------------------------------------------ IA (YOLO in formato ONNX)
class RilevatoreIA:
    """
    Usa un modello YOLO (v5, v8, v11...) esportato in ONNX, con OpenCV (niente
    altro da installare). Addestralo sulle foto del tuo gioco: vedi GUIDA.txt.
    """

    def __init__(self, percorso, dimensione=640, confidenza=0.4, classi=None):
        self.net = cv2.dnn.readNetFromONNX(percorso)
        self.dimensione = int(dimensione)
        self.confidenza = float(confidenza)
        self.classi = [str(c).strip().lower() for c in (classi or [])]

    def _nome_classe(self, i):
        return self.classi[i] if i < len(self.classi) else "classe_%d" % i

    def rileva(self, img):
        h0, w0 = img.shape[:2]
        d = self.dimensione
        scala = min(d / w0, d / h0)
        nw, nh = int(round(w0 * scala)), int(round(h0 * scala))
        px, py = (d - nw) // 2, (d - nh) // 2
        tela = np.full((d, d, 3), 114, np.uint8)
        tela[py:py + nh, px:px + nw] = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
        blob = cv2.dnn.blobFromImage(tela, 1 / 255.0, (d, d), swapRB=True, crop=False)
        self.net.setInput(blob)
        uscita = self.net.forward()
        return decodifica_yolo(uscita, self.confidenza, scala, px, py, self._nome_classe)


def decodifica_yolo(uscita, confidenza, scala, px, py, nome_classe):
    """Trasforma l'uscita grezza di YOLO in Box (gestisce sia v5 sia v8/v11)."""
    out = np.asarray(uscita)
    if out.ndim == 3:
        out = out[0]
    if out.ndim != 2:
        return []
    # v8/v11: (4 + classi, N) -> girato.  v5: (N, 5 + classi)
    if out.shape[0] < out.shape[1]:
        out = out.T
        xywh = out[:, :4]
        punteggi_classi = out[:, 4:]
    else:
        xywh = out[:, :4]
        punteggi_classi = out[:, 5:] * out[:, 4:5]
    if punteggi_classi.shape[1] == 0:
        return []
    classe = np.argmax(punteggi_classi, axis=1)
    punteggio = punteggi_classi[np.arange(len(classe)), classe]
    tieni = punteggio >= confidenza
    if not np.any(tieni):
        return []
    xywh, classe, punteggio = xywh[tieni], classe[tieni], punteggio[tieni]
    rettangoli = []
    for (cx, cy, w, h) in xywh:
        x = (cx - w / 2 - px) / scala
        y = (cy - h / 2 - py) / scala
        rettangoli.append([float(x), float(y), float(w / scala), float(h / scala)])
    indici = cv2.dnn.NMSBoxes(rettangoli, punteggio.astype(float).tolist(), confidenza, 0.45)
    risultato = []
    for i in np.array(indici).flatten():
        x, y, w, h = rettangoli[int(i)]
        risultato.append(Box(x, y, w, h, punteggio[int(i)], nome_classe(int(classe[int(i)])), "ia"))
    return risultato


# ------------------------------------------------------------------ occhio universale (YOLOX)
# Modelli YOLOX gia' addestrati sul dataset COCO (licenza Apache 2.0, Megvii).
# Riconoscono le "persone": in quasi tutti i giochi i personaggi sono persone.
MODELLI_UNIVERSALI = {
    "yolox_tiny": ("https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_tiny.onnx",
                   "427cc366d34e27ff7a03e2899b5e3671425c262ea2291f88bb942bc1cc70b0f7", 416),
    "yolox_nano": ("https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_nano.onnx",
                   "c789161ed43c8269fcd4e67c67eeeb4e80c622da2eb296a20bc6007bd18a0b7d", 416),
}


def scarica_modello(nome, cartella, log=print):
    """Scarica un modello universale se manca (controllando che sia quello giusto)."""
    import hashlib
    import urllib.request
    url, sha, _ = MODELLI_UNIVERSALI[nome]
    os.makedirs(cartella, exist_ok=True)
    percorso = os.path.join(cartella, nome + ".onnx")
    log("Scarico l'occhio universale %s (una volta sola)..." % nome)
    temporaneo = percorso + ".scarico"
    urllib.request.urlretrieve(url, temporaneo)
    with open(temporaneo, "rb") as f:
        if hashlib.sha256(f.read()).hexdigest() != sha:
            os.remove(temporaneo)
            raise RuntimeError("il modello scaricato non e' quello giusto")
    os.replace(temporaneo, percorso)
    return percorso


def decodifica_yolox(uscita, dimensione, confidenza, rapporto, classi_volute=(0,)):
    """Uscita grezza di YOLOX (1, N, 85) -> lista di (x, y, w, h, punteggio)."""
    out = np.asarray(uscita, dtype=np.float32)
    if out.ndim == 3:
        out = out[0]
    griglie, passi = [], []
    for passo in (8, 16, 32):
        n = dimensione // passo
        xv, yv = np.meshgrid(np.arange(n), np.arange(n))
        griglie.append(np.stack((xv, yv), 2).reshape(-1, 2))
        passi.append(np.full((n * n, 1), passo))
    griglie = np.concatenate(griglie, 0).astype(np.float32)
    passi = np.concatenate(passi, 0).astype(np.float32)
    if len(griglie) != len(out):
        return []
    xy = (out[:, :2] + griglie) * passi
    wh = np.exp(np.clip(out[:, 2:4], -10, 10)) * passi
    punteggi = out[:, 4:5] * out[:, 5:]
    punteggio = punteggi[:, list(classi_volute)].max(axis=1)
    tieni = punteggio >= confidenza
    if not np.any(tieni):
        return []
    xy, wh, punteggio = xy[tieni], wh[tieni], punteggio[tieni]
    rettangoli = [[float((cx - w / 2) / rapporto), float((cy - h / 2) / rapporto), float(w / rapporto), float(h / rapporto)]
                  for (cx, cy), (w, h) in zip(xy, wh)]
    indici = cv2.dnn.NMSBoxes(rettangoli, punteggio.astype(float).tolist(), confidenza, 0.45)
    return [tuple(rettangoli[int(i)]) + (float(punteggio[int(i)]),) for i in np.array(indici).flatten()]


class RilevatoreUniversale:
    """Riconosce i personaggi in qualsiasi gioco (persone del dataset COCO)."""

    def __init__(self, percorso, dimensione=416, confidenza=0.45, usa_gpu=False):
        self.net = cv2.dnn.readNetFromONNX(percorso)
        if usa_gpu:
            try:
                self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_OPENCL)
            except Exception:
                pass
        self.dimensione = int(dimensione)
        self.confidenza = float(confidenza)
        self.nome = os.path.basename(percorso)

    def rileva(self, img):
        h0, w0 = img.shape[:2]
        d = self.dimensione
        r = min(d / h0, d / w0)
        nw, nh = int(w0 * r), int(h0 * r)
        tela = np.full((d, d, 3), 114, np.uint8)
        tela[:nh, :nw] = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
        self.net.setInput(cv2.dnn.blobFromImage(tela, 1.0, (d, d), swapRB=False, crop=False))
        uscita = self.net.forward()
        return [Box(x, y, w, h, p, "nemico", "universale")
                for (x, y, w, h, p) in decodifica_yolox(uscita, d, self.confidenza, r)]

    def tempo_medio(self, ripetizioni=5):
        """Quanti secondi ci mette questo PC a guardare una foto."""
        prova = np.full((720, 1280, 3), 90, np.uint8)
        self.rileva(prova)
        inizio = time.perf_counter()
        for _ in range(ripetizioni):
            self.rileva(prova)
        return (time.perf_counter() - inizio) / ripetizioni


def crea_rilevatore_universale(cfg_ru, cartella_base, log=print):
    """Sceglie e carica l'occhio universale. file: auto = il piu' forte che questo PC fa girare veloce."""
    if not cfg_ru.get("attivo", True):
        return None
    cartella = os.path.join(cartella_base, "modelli")
    conf = float(cfg_ru.get("confidenza", 0.45))
    gpu = bool(cfg_ru.get("usa_gpu", False))
    scelta = str(cfg_ru.get("file") or "auto").strip()

    def percorso_di(nome):
        p = os.path.join(cartella, nome + ".onnx")
        if not os.path.isfile(p) and cfg_ru.get("scarica_se_manca", True):
            try:
                scarica_modello(nome, cartella, log)
            except Exception as e:
                log("ATTENZIONE: non riesco a scaricare %s: %s" % (nome, e))
        return p if os.path.isfile(p) else None

    try:
        if scelta.lower() != "auto":
            p = scelta if os.path.isabs(scelta) else os.path.join(cartella_base, scelta)
            if not os.path.isfile(p):
                log("ATTENZIONE: occhio universale non trovato: %s" % p)
                return None
            return RilevatoreUniversale(p, cfg_ru.get("dimensione", 416), conf, gpu)
        massimo = float(cfg_ru.get("tempo_massimo", 0.035))
        for nome in ("yolox_tiny", "yolox_nano"):
            p = percorso_di(nome)
            if p is None:
                continue
            r = RilevatoreUniversale(p, MODELLI_UNIVERSALI[nome][2], conf, gpu)
            t = r.tempo_medio()
            if t <= massimo or nome == "yolox_nano":
                log("Occhio universale: %s (%.0f ms a foto)" % (nome, t * 1000))
                return r
            log("%s e' troppo lento su questo PC (%.0f ms): provo quello piu' leggero" % (nome, t * 1000))
    except Exception as e:
        log("ATTENZIONE: occhio universale non disponibile: %s" % e)
    return None


# ------------------------------------------------------------------ immagini (pulsanti, scritte)
class Immagini:
    """Le immagini salvate nella cartella 'immagini' (es. squadra_eliminata.png)."""

    def __init__(self, cartella, scala=0.5, soglia=0.8):
        self.cartella = cartella
        self.scala = float(scala)
        self.soglia = float(soglia)
        self._cache = {}

    def percorso(self, nome):
        return os.path.join(self.cartella, nome + ".png")

    def esiste(self, nome):
        return os.path.isfile(self.percorso(nome))

    def nomi(self):
        if not os.path.isdir(self.cartella):
            return []
        return sorted(f[:-4] for f in os.listdir(self.cartella) if f.lower().endswith(".png"))

    def _carica(self, nome):
        p = self.percorso(nome)
        try:
            data = os.path.getmtime(p)
        except OSError:
            return None
        if nome in self._cache and self._cache[nome][0] == data:
            return self._cache[nome][1]
        img = cv2.imdecode(np.fromfile(p, dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            return None
        piccola = cv2.resize(img, None, fx=self.scala, fy=self.scala, interpolation=cv2.INTER_AREA)
        self._cache[nome] = (data, piccola)
        return piccola

    def trova(self, schermo_piccolo, nome, soglia=None):
        """Cerca l'immagine. Restituisce (x_centro, y_centro, somiglianza) in pixel
        dello schermo intero, oppure None. schermo_piccolo = schermo gia' rimpicciolito di 'scala'."""
        modello = self._carica(nome)
        if modello is None:
            return None
        mh, mw = modello.shape[:2]
        sh, sw = schermo_piccolo.shape[:2]
        if mh > sh or mw > sw or mh < 2 or mw < 2:
            return None
        ris = cv2.matchTemplate(schermo_piccolo, modello, cv2.TM_CCOEFF_NORMED)
        _, massimo, _, pos = cv2.minMaxLoc(ris)
        if massimo < (self.soglia if soglia is None else soglia):
            return None
        return ((pos[0] + mw / 2) / self.scala, (pos[1] + mh / 2) / self.scala, float(massimo))


def rimpicciolisci(img, scala):
    if scala == 1.0:
        return img
    return cv2.resize(img, None, fx=scala, fy=scala, interpolation=cv2.INTER_AREA)


# ------------------------------------------------------------------ barra della vita
def leggi_barra(img, zona, intervalli, percentuale_colonna=0.35):
    """Quanto e' piena la barra (0-100). zona = frazioni [x, y, l, a]."""
    h, w = img.shape[:2]
    x, y, zw, zh = zona
    x1, y1 = int(x * w), int(y * h)
    x2, y2 = int((x + zw) * w), int((y + zh) * h)
    pezzo = img[max(0, y1):max(y1 + 1, y2), max(0, x1):max(x1 + 1, x2)]
    if pezzo.size == 0:
        return None
    m = maschera_colori(cv2.cvtColor(pezzo, cv2.COLOR_BGR2HSV), intervalli)
    if pezzo.shape[1] >= pezzo.shape[0]:      # barra orizzontale: conta le colonne piene
        piene = (m > 0).mean(axis=0) >= percentuale_colonna
    else:                                       # barra verticale: conta le righe piene
        piene = (m > 0).mean(axis=1) >= percentuale_colonna
    return float(piene.mean() * 100.0)


def in_zona(box, zona, larghezza, altezza):
    x, y, zw, zh = zona
    return (x * larghezza <= box.cx <= (x + zw) * larghezza) and (y * altezza <= box.cy <= (y + zh) * altezza)


# Le parti dello schermo dove i giochi stile Fortnite mettono l'interfaccia (minimappa,
# vita e scudo, inventario, squadra): li' non ci sono mai casse o nemici veri.
ZONE_INTERFACCIA_FORTNITE = [
    [0.80, 0.00, 0.20, 0.33],     # minimappa (in alto a destra)
    [0.00, 0.86, 0.40, 0.14],     # vita e scudo (in basso a sinistra)
    [0.60, 0.86, 0.40, 0.14],     # inventario (in basso a destra)
    [0.00, 0.00, 0.22, 0.25],     # squadra e informazioni (in alto a sinistra)
]
CATEGORIE_OGGETTI = ("cassa", "materiali", "arma")


# ------------------------------------------------------------------ gli occhi
class Occhi:
    def __init__(self, cfg, cartella_base, log=print, universale=True):
        self.cfg = cfg
        self.log = log
        sch = cfg.get("schermo", {}) or {}
        ril = cfg.get("rilevamento", {}) or {}
        self.scala = float(sch.get("scala_analisi", 0.5) or 0.5)
        self.zone_ignorate = [z for z in (sch.get("zone_ignorate") or []) if z and len(z) == 4]
        if sch.get("zone_interfaccia_fortnite", True):
            self.zone_ignorate += [list(z) for z in ZONE_INTERFACCIA_FORTNITE]
        # oggetti trovati col colore troppo grandi o troppo strani: non sono casse (sabbia, cielo...)
        self.oggetto_larghezza_max = float(ril.get("oggetto_larghezza_massima", 0.25) or 1.0)
        self.oggetto_altezza_max = float(ril.get("oggetto_altezza_massima", 0.35) or 1.0)
        # zone imparate dal bot (es. il tuo personaggio in terza persona): le aggiorna apprendimento.py
        self.zone_apprese = [z for z in (sch.get("zone_apprese") or []) if z and len(z) == 4]
        self.zone_temporanee = []     # (zona, fino_a_quando)
        self.colori = {c: (cfg.get("colori", {}) or {}).get(c) or [] for c in CATEGORIE}
        self.area_minima = float(ril.get("area_minima", 0.00015))
        self.unisci = int(ril.get("unisci_pixel", 5))
        self.max_per_categoria = int(ril.get("massimo_per_categoria", 12))
        self.immagini = Immagini(os.path.join(cartella_base, "immagini"),
                                 float(ril.get("scala_immagini", 0.5)), float(ril.get("somiglianza_immagini", 0.8)))
        self.vita_cfg = cfg.get("vita", {}) or {}
        racc = cfg.get("raccolta", {}) or {}
        self.immagine_interazione = str(racc.get("immagine_interazione") or "").strip()
        self.ia = None
        ia = cfg.get("modello_ia", {}) or {}
        file_ia = str(ia.get("file") or "").strip()
        if not file_ia and os.path.isfile(os.path.join(cartella_base, "modelli", "gioco.onnx")):
            # l'occhio addestrato sul TUO gioco (arriva con l'aggiornamento): si usa da solo
            file_ia = os.path.join("modelli", "gioco.onnx")
        if file_ia:
            percorso = file_ia if os.path.isabs(file_ia) else os.path.join(cartella_base, file_ia)
            if os.path.isfile(percorso):
                try:
                    self.ia = RilevatoreIA(percorso, ia.get("dimensione", 640), ia.get("confidenza", 0.4),
                                           ia.get("classi") or ["nemico", "cassa", "materiali", "arma"])
                    self.log("IA del tuo gioco caricata: %s" % percorso)
                except Exception as e:
                    self.log("ATTENZIONE: non riesco a caricare il modello IA %s: %s" % (percorso, e))
            else:
                self.log("ATTENZIONE: modello IA non trovato: %s" % percorso)
        self.universale = None
        if universale:
            self.universale = crea_rilevatore_universale(cfg.get("rilevatore_universale", {}) or {},
                                                         cartella_base, log)
        self.ultima_piccola = None    # schermo rimpicciolito per cercare le immagini
        self._img = None

    def zone_da_saltare(self):
        adesso = time.monotonic()
        self.zone_temporanee = [(z, t) for z, t in self.zone_temporanee if t > adesso]
        return self.zone_ignorate + self.zone_apprese + [z for z, _ in self.zone_temporanee]

    def _e_alleato(self, b, hsv, w, h):
        """Un personaggio con sopra (o addosso) il colore dei compagni di squadra."""
        s = self.scala
        x1 = int(max(0, (b.x - 0.2 * b.w) * s))
        x2 = int(min(w, (b.x + 1.2 * b.w)) * s)
        y1 = int(max(0, (b.y - 0.6 * b.h) * s))
        y2 = int(min(h, (b.y + 0.5 * b.h)) * s)
        if x2 <= x1 or y2 <= y1:
            return False
        m = maschera_colori(hsv[y1:y2, x1:x2], self.colori["alleato"])
        return int(np.count_nonzero(m)) >= max(6, 0.004 * m.size)

    def analizza(self, img):
        h, w = img.shape[:2]
        vis = Visione(w, h)
        piccola = rimpicciolisci(img, self.scala)
        hsv = cv2.cvtColor(piccola, cv2.COLOR_BGR2HSV)
        area_min = self.area_minima * piccola.shape[0] * piccola.shape[1]
        for cat in CATEGORIE:
            if self.colori[cat] and cat != "alleato":
                m = maschera_colori(hsv, self.colori[cat])
                vis.oggetti[cat].extend(box_da_maschera(m, area_min, self.unisci, cat, self.scala))
        if self.ia is not None:
            for b in self.ia.rileva(img):
                if b.categoria in vis.oggetti:
                    vis.oggetti[b.categoria].append(b)
        if self.universale is not None:
            vis.oggetti["nemico"].extend(self.universale.rileva(img))
        if self.colori["alleato"]:
            vis.oggetti["nemico"] = [b for b in vis.oggetti["nemico"] if not self._e_alleato(b, hsv, w, h)]
        # via le "casse" trovate col colore che hanno una forma impossibile
        for cat in CATEGORIE_OGGETTI:
            vis.oggetti[cat] = [b for b in vis.oggetti[cat] if b.fonte != "colore" or self._forma_giusta(b, w, h)]
        # via le cose nelle zone da ignorare (minimappa, il tuo personaggio, icone...)
        zone = self.zone_da_saltare()
        for cat in CATEGORIE:
            lista = [b for b in vis.oggetti[cat] if not any(in_zona(b, z, w, h) for z in zone)]
            lista.sort(key=lambda b: -b.w * b.h * b.punteggio)
            vis.oggetti[cat] = lista[:self.max_per_categoria]
        # la vita
        zona = self.vita_cfg.get("zona")
        if zona and len(zona) == 4 and self.vita_cfg.get("colore"):
            vis.vita = leggi_barra(img, zona, self.vita_cfg.get("colore"))
        self.ultima_piccola = None
        self._img = img
        return vis

    def _forma_giusta(self, b, larghezza, altezza):
        if b.w > self.oggetto_larghezza_max * larghezza or b.h > self.oggetto_altezza_max * altezza:
            return False
        rapporto = b.w / max(1.0, b.h)
        return 0.2 <= rapporto <= 5.0

    def pixel_colore(self, img, categoria, x, y, w, h):
        """Quanti pixel del colore di una categoria ci sono in un rettangolo (per controllare le casse aperte)."""
        if not self.colori.get(categoria):
            return None
        H, W = img.shape[:2]
        x1, y1 = int(max(0, x)), int(max(0, y))
        x2, y2 = int(min(W, x + w)), int(min(H, y + h))
        if x2 <= x1 or y2 <= y1:
            return 0
        hsv = cv2.cvtColor(img[y1:y2, x1:x2], cv2.COLOR_BGR2HSV)
        return int(np.count_nonzero(maschera_colori(hsv, self.colori[categoria])))

    def schermo_piccolo(self):
        """Lo schermo rimpicciolito per cercare le immagini (calcolato solo se serve)."""
        if self.ultima_piccola is None and getattr(self, "_img", None) is not None:
            self.ultima_piccola = rimpicciolisci(self._img, self.immagini.scala)
        return self.ultima_piccola

    def vedi(self, nome, soglia=None):
        piccola = self.schermo_piccolo()
        if piccola is None:
            return None
        return self.immagini.trova(piccola, nome, soglia)

    def controlla_interazione(self, vis):
        if self.immagine_interazione:
            vis.interazione = self.vedi(self.immagine_interazione) is not None
        return vis.interazione


def disegna(img, vis, testo="", bersaglio=None, mirino=None):
    """Disegna sopra lo schermo quello che il bot vede (finestra di controllo)."""
    colori = {"nemico": (0, 0, 255), "cassa": (0, 215, 255), "materiali": (0, 200, 0), "arma": (255, 128, 0),
              "testa": (255, 0, 255), "alleato": (255, 255, 0)}
    out = img.copy()
    for cat, lista in vis.oggetti.items():
        for b in lista:
            cv2.rectangle(out, (int(b.x), int(b.y)), (int(b.x + b.w), int(b.y + b.h)), colori.get(cat, (255, 255, 255)), 2)
            cv2.putText(out, "%s %.2f" % (cat, b.punteggio), (int(b.x), int(b.y) - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, colori.get(cat, (255, 255, 255)), 1)
    if bersaglio is not None:
        cv2.circle(out, (int(bersaglio[0]), int(bersaglio[1])), 8, (0, 255, 0), 2)
    if mirino is not None:
        cv2.drawMarker(out, (int(mirino[0]), int(mirino[1])), (0, 255, 0), cv2.MARKER_CROSS, 20, 2)
    righe = [testo] if testo else []
    if vis.vita is not None:
        righe.append("vita %.0f%%" % vis.vita)
    for i, r in enumerate(righe):
        cv2.putText(out, r, (10, 30 + 28 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 4)
        cv2.putText(out, r, (10, 30 + 28 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    return out
