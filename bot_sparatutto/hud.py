"""
hud.py - LEGGE L'INTERFACCIA DI FORTNITE DA SOLO, SENZA IA (in pochi millesimi di secondo).

Cosi' il bot non resta "cieco" quando le IA gratis finiscono le domande o ci mettono un minuto
a rispondere (e' successo nella partita registrata: fermo nella tempesta ad aspettare l'IA).

- BUSSOLA: il numero in alto al centro (0-359). Il bot sa SEMPRE dove guarda: 0 = nord,
  90 = est, 180 = sud, 270 = ovest. Le cifre le confronta con cifre_bussola.py.
- MINIMAPPA (in alto a destra, il nord e' sempre in alto, io sono al centro): dove sono la
  TEMPESTA (viola), il MARE (blu) e la TERRA. Da li' capisce da che parte uscire dalla tempesta,
  da che parte c'e' la terra quando e' in acqua e se davanti c'e' il mare.
- BARRA DELLE ARMI (in basso a destra): se non c'e' ma la bussola si', sono sul BUS.
- COMPAGNI sulla bussola: i triangolini bianchi sopra la bussola sono i compagni lontani:
  da quanto sono spostati dal centro capisco in che direzione sono.

Tutte le misure sono in proporzione allo schermo (16:9): funziona a 720p, 1080p, 540p...
"""

import math

import cv2
import numpy as np

from cifre_bussola import CIFRE

# ------------------------------------------------------------------ la bussola
# la striscia col numero, riportata sempre alla stessa grandezza (come su uno schermo 960x540)
B_X0, B_X1, B_Y1 = 0.44, 0.56, 0.06
B_LARGO, B_ALTO = 115, 32
B_CENTRO = 480.0 - B_X0 * 960.0          # dove sta il centro del numero (sopra la freccina)
LARGHEZZA_CIFRA = {"1": 3.5}             # le altre cifre sono larghe 6
SPAZIO = 1.0
T_LARGO, T_ALTO = 12, 16
BIANCO = 185
PUNTEGGIO_MINIMO = 0.62
_MODELLI = {k: np.array(v, np.float32) for k, v in CIFRE.items()}
PIXEL_PER_GRADO = 1.78                   # sulla bussola (schermo largo 960): 45 gradi = 80 pixel


def _striscia_bussola(img):
    H, W = img.shape[:2]
    c = img[0:max(1, int(round(B_Y1 * H))), int(round(B_X0 * W)):int(round(B_X1 * W))]
    if c.size == 0:
        return None
    c = cv2.resize(c, (B_LARGO, B_ALTO), interpolation=cv2.INTER_AREA)
    return c.min(axis=2).astype(np.float32)          # quanto e' bianco (bianco = alto in tutti i colori)


def _riga_del_numero(g):
    """I pezzi bianchi del numero: -> ((y0, y1), [componenti]) oppure (None, [])."""
    m = (g > BIANCO).astype(np.uint8)
    n, _, st, _ = cv2.connectedComponentsWithStats(m, 8)
    pezzi = []
    for k in range(1, n):
        x, y, w, h, a = (int(v) for v in st[k])
        if x >= B_CENTRO - 22 and x + w <= B_CENTRO + 23 and 6 <= y <= 15 and h <= 12:
            pezzi.append((x, y, w, h, a))
    grandi = [p for p in pezzi if p[3] >= 5]
    if not grandi:
        return None, []
    y0 = int(np.median([p[1] for p in grandi]))
    y1 = int(np.median([p[1] + p[3] for p in grandi]))
    scelti = [p for p in pezzi if p[1] >= y0 - 2 and p[1] + p[3] <= y1 + 2]
    return (y0, y1), scelti


def _ncc(a, b):
    a = a - a.mean()
    b = b - b.mean()
    d = math.sqrt(float((a * a).sum() * (b * b).sum()))
    return float((a * b).sum() / d) if d > 0 else 0.0


def leggi_bussola_dettagli(img):
    """-> (numero 0-359, punteggio 0-1) oppure (None, 0)."""
    if img is None:
        return None, 0.0
    g = _striscia_bussola(img)
    if g is None:
        return None, 0.0
    riga, pezzi = _riga_del_numero(g)
    if riga is None or not pezzi:
        return None, 0.0
    y0, y1 = riga
    x0 = min(p[0] for p in pezzi)
    x1 = max(p[0] + p[2] for p in pezzi)
    if abs((x0 + x1) / 2.0 - B_CENTRO) > 2.5:
        return None, 0.0                          # non e' centrato: un'icona copre il numero
    largo = float(x1 - x0)
    memoria = {}

    def somiglia(cifra, a, b):
        chiave = (cifra, a, b)
        if chiave not in memoria:
            pezzo = g[max(0, y0 - 1):y1 + 1, max(0, a - 1):b + 1]
            if pezzo.size == 0 or b - a < 2:
                memoria[chiave] = -1.0
            else:
                pezzo = cv2.resize(pezzo, (T_LARGO, T_ALTO), interpolation=cv2.INTER_AREA)
                memoria[chiave] = _ncc(pezzo, _MODELLI[cifra])
        return memoria[chiave]

    migliore, punti_migliori = None, -9.0
    for numero in range(360):
        s = str(numero)
        teorico = sum(LARGHEZZA_CIFRA.get(c, 6.0) for c in s) + SPAZIO * (len(s) - 1)
        scala = largo / teorico
        if not 0.8 <= scala <= 1.25:
            continue
        x, totale = float(x0), 0.0
        for c in s:
            w = LARGHEZZA_CIFRA.get(c, 6.0) * scala
            totale += max(somiglia(c, int(round(x + dx)), int(round(x + w + dx))) for dx in (-1, 0, 1))
            x += w + SPAZIO * scala
        punti = totale / len(s)
        if punti > punti_migliori:
            migliore, punti_migliori = numero, punti
    return migliore, punti_migliori


def leggi_bussola(img):
    """Il numero della bussola (0 = nord, 90 = est...) oppure None se non si legge bene."""
    numero, punti = leggi_bussola_dettagli(img)
    return numero if numero is not None and punti >= PUNTEGGIO_MINIMO else None


def compagni_sulla_bussola(img):
    """I triangolini bianchi sopra la bussola (i compagni lontani davanti a me):
    -> lista di gradi rispetto a dove guardo (negativo = a sinistra)."""
    if img is None:
        return []
    H, W = img.shape[:2]
    x0, x1, y1 = 0.28, 0.72, 0.034
    c = img[0:max(1, int(round(y1 * H))), int(round(x0 * W)):int(round(x1 * W))]
    if c.size == 0:
        return []
    largo = int(round((x1 - x0) * 960))
    c = cv2.resize(c, (largo, int(round(y1 * 540))), interpolation=cv2.INTER_AREA)
    m = (c.min(axis=2) > 200).astype(np.uint8)
    n, _, st, _ = cv2.connectedComponentsWithStats(m, 8)
    gradi = []
    for k in range(1, n):
        x, y, w, h, a = (int(v) for v in st[k])
        # i triangolini stanno piu' in alto delle cifre (le cifre partono dalla riga 10)
        if not (4 <= h <= 8 and 8 <= w <= 34 and y <= 8 and w >= 1.3 * h):
            continue
        quanti = max(1, int(round(w / 11.0)))     # due triangoli attaccati
        pieno = a / float(w * h)
        if not 0.3 <= pieno <= 0.8:
            continue
        for i in range(quanti):
            cx = x0 * 960 + x + (i + 0.5) * w / quanti
            gradi.append((cx - 480.0) / PIXEL_PER_GRADO)
    return sorted(gradi)


def _pezzi_bianchi(img, x0, x1, y0, y1, soglia=205):
    """I pezzi bianchi in una striscia dello schermo, misurati come su uno schermo 960x540."""
    H, W = img.shape[:2]
    c = img[int(round(y0 * H)):int(round(y1 * H)), int(round(x0 * W)):int(round(x1 * W))]
    if c.size == 0:
        return []
    largo = max(1, int(round((x1 - x0) * 960)))
    alto = max(1, int(round((y1 - y0) * 540)))
    c = cv2.resize(c, (largo, alto), interpolation=cv2.INTER_AREA)
    m = (c.min(axis=2) > soglia).astype(np.uint8)
    n, _, st, _ = cv2.connectedComponentsWithStats(m, 8)
    return [tuple(int(v) for v in st[k]) for k in range(1, n) if st[k][4] >= 8]


def compagni_ai_bordi(img):
    """Le frecce bianche dei compagni che NON vedo: "<" sul bordo sinistro, ">" sul bordo destro,
    "v" in basso (sono dietro di me). -> lista di gradi (circa) rispetto a dove guardo."""
    if img is None:
        return []
    gradi = []
    for x0, x1, verso in ((0.0, 0.022, -100.0), (0.978, 1.0, 100.0)):
        for x, y, w, h, a in _pezzi_bianchi(img, x0, x1, 0.15, 0.85):
            if 3 <= w <= 9 and 9 <= h <= 16:
                gradi.append(verso)
    for x, y, w, h, a in _pezzi_bianchi(img, 0.25, 0.68, 0.962, 0.995):
        if 4 <= y <= 8 and 5 <= h <= 9 and 9 <= w <= 27:
            quanti = max(1, int(round(w / 12.5)))
            for i in range(quanti):
                cx = 0.25 * 960 + x + (i + 0.5) * w / quanti
                # dietro: a sinistra in basso = dietro a sinistra
                gradi.append(differenza(180.0 - (cx / 960.0 - 0.5) * 160.0, 0.0))
    return gradi


def compagni_sulla_minimappa(img):
    """Le frecce GIALLE dei compagni sulla minimappa (bordo nero intorno): dove sono e quanto
    lontano. -> lista di (gradi della bussola, distanza 0-1 dove 1 = bordo della minimappa)."""
    if img is None:
        return []
    H, W = img.shape[:2]
    cx, cy, mezzo = MM_X * W, MM_Y * H, MM_MEZZO * W
    c = img[max(0, int(round(cy - mezzo))):int(round(cy + mezzo)),
            max(0, int(round(cx - mezzo))):int(round(cx + mezzo))]
    if c.size == 0:
        return []
    lato = 128
    c = cv2.resize(c, (lato, lato), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(c, cv2.COLOR_BGR2HSV)
    h, s, v = (hsv[..., k].astype(np.int16) for k in range(3))
    giallo = ((h >= 21) & (h <= 35) & (s >= 140) & (v >= 190)).astype(np.uint8)
    scuro = v < 110
    n, lab, st, cen = cv2.connectedComponentsWithStats(giallo, 8)
    trovati = []
    for k in range(1, n):
        x, y, w, hh, a = (int(v_) for v_ in st[k])
        if not (5 <= a <= 90 and w <= 14 and hh <= 14):
            continue
        x0, y0, x1, y1 = max(0, x - 2), max(0, y - 2), min(lato, x + w + 2), min(lato, y + hh + 2)
        anello = np.zeros(giallo.shape, bool)
        anello[y0:y1, x0:x1] = True
        anello &= lab != k
        if not anello.any() or float(scuro[anello].mean()) < 0.2:
            continue                      # senza bordo scuro: e' un pezzo di sabbia, non un compagno
        dx, dy = float(cen[k][0]) - (lato - 1) / 2.0, float(cen[k][1]) - (lato - 1) / 2.0
        r = math.hypot(dx, dy)          # vicinissimo (sopra la mia freccia): distanza quasi 0
        trovati.append((math.degrees(math.atan2(dx, -dy)) % 360.0, min(1.0, r / (lato / 2.0))))
    return trovati


# ------------------------------------------------------------------ la scritta "E Apri" / "Raccogli"
def _pezzi_bianchi_tutti(img, x0, x1, y0, y1, soglia=200, area=3):
    H, W = img.shape[:2]
    c = img[int(round(y0 * H)):int(round(y1 * H)), int(round(x0 * W)):int(round(x1 * W))]
    if c.size == 0:
        return []
    c = cv2.resize(c, (max(1, int(round((x1 - x0) * 960))), max(1, int(round((y1 - y0) * 540)))),
                   interpolation=cv2.INTER_AREA)
    m = (c.min(axis=2) > soglia).astype(np.uint8)
    n, _, st, _ = cv2.connectedComponentsWithStats(m, 8)
    return [tuple(int(v) for v in st[k]) for k in range(1, n) if st[k][4] >= area]


def tipo_di_scritta(img):
    """La scritta di interazione a destra del mirino: None se non c'e'; "spazio" se il tasto e'
    SPAZIO (sul bus "PER SALTARE", in caduta "ENTRA IN CADUTA LIBERA"...: sono in aria); "e" se e'
    un'altra (davanti a una cassa "E Apri", "Raccogli", "Rianima", "Assolda"...)."""
    if img is None:
        return None
    riga = _riga_della_scritta(img)
    if riga is None:
        return None
    alto, basso = riga
    # "Spazio" e' una parola di lettere piccole a sinistra della scritta; la E e' un tasto solo
    piccole = [p for p in _pezzi_bianchi_tutti(img, 0.50, 0.80, 0.48, 0.66, soglia=160, area=2)
               if 66 <= p[0] <= 106 and p[3] <= 8 and alto - 3 <= p[1] + p[3] / 2.0 <= basso + 3]
    return "spazio" if len(piccole) >= 3 else "e"


def scritta_interazione(img):
    """C'e' una scritta di interazione a destra del mirino (es. "E Apri" vicino a una cassa,
    "Raccogli", "Rianima", "Assolda", "Spazio PER SALTARE")?"""
    return _riga_della_scritta(img) is not None


def _riga_della_scritta(img):
    """Cerco una RIGA di lettere bianche tutte alte uguali, che comincia poco a destra del centro.
    -> (y alto, y basso) della riga (su uno schermo 960x540, dentro la striscia) oppure None."""
    if img is None:
        return None
    x0, x1, y0, y1 = 0.50, 0.80, 0.48, 0.66
    lettere = [p for p in _pezzi_bianchi(img, x0, x1, y0, y1, soglia=200)
               if 5 <= p[3] <= 8 and 1 <= p[2] <= 12 and p[4] >= 5]
    migliore = []
    for l in lettere:
        riga = sorted((q for q in lettere if abs(q[1] - l[1]) <= 1 and abs(q[1] + q[3] - l[1] - l[3]) <= 1),
                      key=lambda q: q[0])
        catena = [riga[0]]
        for q in riga[1:]:
            if q[0] - (catena[-1][0] + catena[-1][2]) <= 9:
                catena.append(q)
            else:
                if len(catena) > len(migliore):
                    migliore = catena
                catena = [q]
        if len(catena) > len(migliore):
            migliore = catena
    if len(migliore) < 4 or migliore[-1][0] + migliore[-1][2] - migliore[0][0] < 15:
        return None
    if not 85 <= migliore[0][0] <= 165:      # la scritta comincia tra 0.59 e 0.67 della larghezza
        return None
    return min(p[1] for p in migliore), max(p[1] + p[3] for p in migliore)


def nome_sopra(img, x, y, w, h):
    """Sopra questa persona (rettangolo in pixel) c'e' un NOME scritto (es. "◆AgreeableEmu3207")?
    In Fortnite i nomi si vedono solo sopra i COMPAGNI (e i personaggi del gioco): i nemici no.
    Cerco una riga di almeno 4 lettere bianche appena sopra la testa."""
    if img is None:
        return False
    H, W = img.shape[:2]
    cx = x + w / 2.0
    x0 = max(0.0, (cx - max(0.09 * W, 0.8 * w)) / W)
    x1 = min(1.0, (cx + max(0.09 * W, 0.8 * w)) / W)
    y0 = max(0.0, (y - 0.08 * H) / H)
    y1 = min(1.0, (y + 0.03 * H) / H)
    if x1 - x0 < 0.02 or y1 - y0 < 0.02:
        return False
    lettere = [p for p in _pezzi_bianchi_tutti(img, x0, x1, y0, y1, soglia=175, area=4)
               if 4 <= p[3] <= 9 and 1 <= p[2] <= 12]
    for l in lettere:
        riga = sorted((q for q in lettere if abs(q[1] + q[3] - l[1] - l[3]) <= 2), key=lambda q: q[0])
        catena = 1
        for a, b in zip(riga, riga[1:]):
            catena = catena + 1 if b[0] - (a[0] + a[2]) <= 9 else 1
            if catena >= 5:
                # non la scritta "E Apri" / "Spazio ..." a destra del mirino
                gx = x0 + (b[0] / 960.0)
                gy = y0 + (b[1] / 540.0)
                if not (0.55 <= gx <= 0.82 and 0.50 <= gy <= 0.62):
                    return True
    return False


def spettatore(img):
    """In alto al centro c'e' la scritta grande "SPETTATORE" (sono stato eliminato e guardo un
    compagno)? Una riga di almeno 7 lettere grandi dove di solito c'e' il numero della bussola."""
    if img is None:
        return False
    grandi = [p for p in _pezzi_bianchi(img, 0.38, 0.62, 0.0, 0.09) if 9 <= p[3] <= 13 and p[2] <= 12]
    for p in grandi:
        if sum(1 for q in grandi if abs(q[1] - p[1]) <= 2) >= 7:
            return True
    return False


# ------------------------------------------------------------------ vita e scudo
def _riempita(img, y, colore):
    H, W = img.shape[:2]
    r = img[max(0, int(round((y - 0.006) * H))):int(round((y + 0.006) * H)) + 1,
            int(round(0.034 * W)):int(round(0.2125 * W))]
    if r.size == 0:
        return 0
    r = cv2.resize(r, (171, 3), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(r, cv2.COLOR_BGR2HSV)
    h, s, v = (hsv[..., k].astype(np.int16) for k in range(3))
    if colore == "vita":                  # verde (o rosso quando e' quasi finita)
        piena = ((h >= 22) & (h <= 85) & (s >= 110) & (v >= 120)) | \
            (((h <= 8) | (h >= 165)) & (s >= 110) & (v >= 110))
    else:                                 # scudo: azzurro
        piena = (h >= 90) & (h <= 112) & (s >= 110) & (v >= 150)
    colonne = piena.mean(axis=0) >= 0.5
    ultima, buco = -1, 0
    for i, c in enumerate(colonne):
        if c:
            ultima, buco = i, 0
        else:
            buco += 1
            if buco > 6:
                break
    return int(round(100.0 * (ultima + 1) / len(colonne)))


def leggi_vita(img):
    """La vita e lo scudo (0-100) dalle barre in basso a sinistra. -> (vita, scudo); vita None se
    la barra non si vede (menu, schermate)."""
    if img is None:
        return None, None
    vita = _riempita(img, 0.93, "vita")
    if vita <= 0:
        return None, None
    return vita, _riempita(img, 0.897, "scudo")


# ------------------------------------------------------------------ la barra delle armi
def barra_armi(img):
    """C'e' la barra delle armi in basso a destra (il quadrato grigio del piccone)?
    Non c'e' nei menu e sul BUS; c'e' quando cado, gioco o guardo un compagno."""
    if img is None:
        return False
    H, W = img.shape[:2]
    r = img[int(0.855 * H):int(0.935 * H), int(0.69 * W):int(0.735 * W)]
    if r.size == 0:
        return False
    hsv = cv2.cvtColor(r, cv2.COLOR_BGR2HSV)
    s, v = hsv[..., 1], hsv[..., 2]
    grigio = (s < 45) & (v > 110) & (v < 240)
    return float(grigio.mean()) >= 0.4


# ------------------------------------------------------------------ la minimappa
MM_X, MM_Y, MM_MEZZO = 0.918, 0.146, 0.0656    # centro (x in larghezze, y in altezze), mezzo lato
LATO = 64
IGNOTO, TERRA, ACQUA, TEMPESTA = 0, 1, 2, 3


def classi_minimappa(img):
    """La minimappa 64x64 divisa in: 0 non so (icone, scritte), 1 terra, 2 acqua, 3 tempesta."""
    H, W = img.shape[:2]
    cx, cy, mezzo = MM_X * W, MM_Y * H, MM_MEZZO * W
    c = img[max(0, int(round(cy - mezzo))):int(round(cy + mezzo)),
            max(0, int(round(cx - mezzo))):int(round(cx + mezzo))]
    if c.size == 0:
        return None
    c = cv2.resize(c, (LATO, LATO), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(c, cv2.COLOR_BGR2HSV)
    h = hsv[..., 0].astype(np.int16)
    s = hsv[..., 1].astype(np.int16)
    v = hsv[..., 2].astype(np.int16)
    tempesta = (h >= 132) & (h <= 175) & (s >= 90) & (v >= 70)
    acqua = (h >= 84) & (h <= 112) & (s >= 130) & (v >= 80) & ~tempesta
    terra = (s >= 45) & (v >= 60) & ~tempesta & ~acqua
    classi = np.zeros((LATO, LATO), np.uint8)
    classi[terra] = TERRA
    classi[acqua] = ACQUA
    classi[tempesta] = TEMPESTA
    return classi


def _media_angoli(gradi):
    if not gradi:
        return None
    x = sum(math.sin(math.radians(g)) for g in gradi)
    y = sum(math.cos(math.radians(g)) for g in gradi)
    if abs(x) < 1e-9 and abs(y) < 1e-9:
        return None
    return math.degrees(math.atan2(x, y)) % 360.0


def differenza(a, b):
    """Differenza tra due angoli, tra -180 e 180."""
    return (a - b + 180.0) % 360.0 - 180.0


class Minimappa:
    """Quello che dice la minimappa. Gli angoli sono come la bussola: 0 = nord (in alto), 90 = est."""
    PASSO = 10

    def __init__(self, classi):
        self.classi = classi
        self.ok = False
        self.tempesta = self.acqua = self.terra = 0.0
        self.qui = IGNOTO
        if classi is None:
            return
        conosciuti = classi > 0
        quanti = float(conosciuti.sum())
        self.ok = quanti / classi.size >= 0.55
        if quanti:
            self.tempesta = float((classi == TEMPESTA).sum()) / quanti
            self.acqua = float((classi == ACQUA).sum()) / quanti
            self.terra = float((classi == TERRA).sum()) / quanti
        self.centro = (LATO - 1) / 2.0
        yy, xx = np.mgrid[0:LATO, 0:LATO]
        self._dx = xx - self.centro
        self._dy = yy - self.centro
        self._r = np.hypot(self._dx, self._dy)
        vicino = (self._r >= 2) & (self._r <= 5) & conosciuti
        if vicino.any():
            valori = classi[vicino]
            self.qui = int(np.bincount(valori, minlength=4)[1:].argmax() + 1)
        self._raggi = {}

    # un raggio dal centro verso una direzione: le classi incontrate (distanza, classe)
    def raggio(self, gradi):
        g = int(round(gradi / self.PASSO) * self.PASSO) % 360
        if g not in self._raggi:
            dx, dy = math.sin(math.radians(g)), -math.cos(math.radians(g))
            punti = []
            for r in range(3, int(self.centro) + 1):
                x = int(round(self.centro + dx * r))
                y = int(round(self.centro + dy * r))
                if 0 <= x < LATO and 0 <= y < LATO:
                    punti.append((r, int(self.classi[y, x])))
            self._raggi[g] = punti
        return self._raggi[g]

    def primo(self, gradi, cerco, evito=(), di_fila=2):
        """Dopo quanti punti trovo (di fila) una delle classi cercate; None se non la trovo
        o se prima trovo una classe da evitare."""
        conta = 0
        for r, cl in self.raggio(gradi):
            if cl == IGNOTO:
                continue
            if cl in evito:
                return None
            if cl in cerco:
                conta += 1
                if conta >= di_fila:
                    return r
            else:
                conta = 0
        return None

    def _migliore(self, distanze):
        if not distanze:
            return None
        minimo = min(distanze.values())
        return _media_angoli([g for g, d in distanze.items() if d <= minimo + 1])

    def verso_fuori_tempesta(self):
        """Sono nella tempesta: la direzione per uscirne prima (la strada piu' corta)."""
        if not self.ok:
            return None
        distanze = {}
        for g in range(0, 360, self.PASSO):
            d = self.primo(g, (TERRA, ACQUA), di_fila=3)
            if d is not None:
                distanze[g] = d
        return self._migliore(distanze)

    def verso_terra(self, preferita=None, entro=70):
        """Sono in acqua (o sopra il mare): la terra piu' vicina che NON e' nella tempesta.
        preferita = una direzione (es. dov'e' il compagno): prima cerco la terra da quella parte."""
        if not self.ok:
            return None
        if preferita is not None:
            vicine = {}
            for g in range(0, 360, self.PASSO):
                if abs(differenza(g, preferita)) <= entro:
                    d = self.primo(g, (TERRA,), evito=(TEMPESTA,), di_fila=3)
                    if d is not None:
                        vicine[g] = d
            if vicine:
                return self._migliore(vicine)
        distanze = {}
        for g in range(0, 360, self.PASSO):
            d = self.primo(g, (TERRA,), evito=(TEMPESTA,), di_fila=3)
            if d is not None:
                distanze[g] = d
        if not distanze:                             # tutta la terra e' nella tempesta: almeno la terra
            for g in range(0, 360, self.PASSO):
                d = self.primo(g, (TERRA, TEMPESTA), di_fila=3)
                if d is not None:
                    distanze[g] = d
        return self._migliore(distanze)

    def lontano_dalla_tempesta(self, minimo=0.05):
        """La tempesta si vede sulla minimappa: la direzione OPPOSTA (pesando di piu' quella vicina)."""
        if not self.ok or self.tempesta < minimo:
            return None
        viola = (self.classi == TEMPESTA) & (self._r >= 2)
        if not viola.any():
            return None
        peso = 1.0 / np.maximum(self._r[viola], 1.0)
        x = float((self._dx[viola] * peso).sum())
        y = float((self._dy[viola] * peso).sum())
        if abs(x) < 1e-6 and abs(y) < 1e-6:
            return None
        verso_tempesta = math.degrees(math.atan2(x, -y)) % 360.0
        return (verso_tempesta + 180.0) % 360.0

    def pericolo_davanti(self, gradi, entro=12):
        """Nella direzione dove vado, entro poco, c'e' acqua o tempesta (e io sono sulla terra)?"""
        if not self.ok or self.qui != TERRA:
            return False
        for r, cl in self.raggio(gradi):
            if r > entro:
                break
            if cl in (ACQUA, TEMPESTA):
                return True
        return False

    def direzione_sicura(self, voluta, entro=12):
        """La direzione piu' vicina a quella voluta senza acqua ne' tempesta per un po'."""
        if not self.ok:
            return voluta
        for scarto in range(0, 181, self.PASSO):
            for segno in ((1,) if scarto in (0, 180) else (1, -1)):
                g = (voluta + segno * scarto) % 360
                libero = True
                for r, cl in self.raggio(g):
                    if r > entro:
                        break
                    if cl in (ACQUA, TEMPESTA):
                        libero = False
                        break
                if libero:
                    return g
        return voluta

    def terra_intorno(self, raggio=10, da=0):
        """Quanta terra (senza tempesta) c'e' qui intorno (0-1): per saltare dal bus sopra l'isola.
        da = quanto lasciare fuori al centro (sul bus c'e' il disegno grande del bus)."""
        if not self.ok:
            return 0.0
        dentro = (self._r <= raggio) & (self._r >= da) & (self.classi > 0)
        if not dentro.any():
            return 0.0
        return float((self.classi[dentro] == TERRA).mean())


def leggi_minimappa(img):
    if img is None:
        return Minimappa(None)
    return Minimappa(classi_minimappa(img))
