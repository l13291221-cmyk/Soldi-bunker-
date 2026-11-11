"""
istruzioni.py - Legge ed esegue le istruzioni scritte nel file istruzioni.txt
(e le "macro" di impostazioni.yaml).

Una istruzione per riga:
    QUANDO <condizione> FAI <azione>, <azione>, ...

Esempio:
    QUANDO vedi squadra_eliminata FAI aspetta 3, clicca gioca_ancora

Le condizioni e le azioni possibili sono spiegate dentro istruzioni.txt.
"""

import re
import sys
import time


class ErroreIstruzione(ValueError):
    pass


class Interrotto(Exception):
    """L'azione e' stata fermata (pausa, uscita, finestra del gioco non in primo piano)."""


CATEGORIE_VISTE = {
    "nemico": "nemico", "nemici": "nemico", "un_nemico": "nemico",
    "cassa": "cassa", "casse": "cassa", "una_cassa": "cassa", "forziere": "cassa",
    "arma": "arma", "armi": "arma", "un'arma": "arma", "un_arma": "arma",
    "materiali": "materiali", "cassa_materiali": "materiali", "casse_materiali": "materiali",
    "una_cassa_materiali": "materiali", "una_cassa_dei_materiali": "materiali", "cassa_dei_materiali": "materiali",
}

_NUMERO = re.compile(r"^-?\d+(?:[.,]\d+)?$")


def numero(testo):
    t = str(testo).strip().lower().replace(",", ".")
    if not _NUMERO.match(t):
        raise ErroreIstruzione("mi aspettavo un numero, ho trovato '%s'" % testo)
    return float(t)


def _secondi(parole):
    """'3', '3 secondi', '2 minuti', '1.5s' -> secondi."""
    if not parole:
        raise ErroreIstruzione("manca il numero di secondi")
    p = parole[0].lower()
    moltiplica = 1.0
    for suff, m in (("ms", 0.001), ("s", 1.0), ("m", 60.0)):
        if p.endswith(suff) and _NUMERO.match(p[:-len(suff)].replace(",", ".") or "x"):
            p = p[:-len(suff)]
            moltiplica = m
            break
    valore = numero(p) * moltiplica
    if len(parole) > 1:
        u = parole[1].lower()
        if u.startswith("min"):
            valore *= 60.0
        elif u.startswith("mill"):
            valore /= 1000.0
    return valore


def _nome(testo):
    return testo.strip().lower().replace(" ", "_")


# ------------------------------------------------------------------ condizioni
class Condizione:
    def __init__(self, tipo, valore=None, negata=False, testo=""):
        self.tipo = tipo
        self.valore = valore
        self.negata = negata
        self.testo = testo

    def __repr__(self):
        return "Condizione(%s %r%s)" % (self.tipo, self.valore, " NO" if self.negata else "")


def leggi_condizione(testo, immagini_esiste=None):
    t = " ".join(testo.strip().lower().split())
    parole = t.split(" ")
    negata = False
    if parole[0] in ("non", "no"):
        negata = True
        parole = parole[1:]
        t = " ".join(parole)
    if not parole or not parole[0]:
        raise ErroreIstruzione("condizione vuota")

    if parole[0] in ("inizio", "all'inizio", "parte", "avvio"):
        return Condizione("inizio", testo=testo)
    if parole[0] == "ogni":
        return Condizione("ogni", _secondi(parole[1:]), testo=testo)
    if parole[0] in ("vedi", "vedo", "c'è", "c'e", "ce"):
        resto = [p for p in parole[1:] if p not in ("la", "il", "lo", "le", "i", "gli", "l'", "scritta", "immagine", "pulsante")]
        if not resto:
            raise ErroreIstruzione("dopo 'vedi' scrivi il nome dell'immagine")
        nome = _nome("_".join(resto))
        if nome in CATEGORIE_VISTE and not (immagini_esiste and immagini_esiste(nome)):
            return Condizione("vedi_categoria", CATEGORIE_VISTE[nome], negata, testo)
        return Condizione("vedi", nome, negata, testo)
    if parole[0] == "vita":
        if len(parole) < 3:
            raise ErroreIstruzione("scrivi ad esempio: vita sotto 30")
        verso = parole[1]
        n = numero(parole[2].rstrip("%"))
        if verso in ("sotto", "<", "minore", "meno"):
            return Condizione("vita_sotto", n, negata, testo)
        if verso in ("sopra", ">", "maggiore", "piu", "più"):
            return Condizione("vita_sopra", n, negata, testo)
        raise ErroreIstruzione("dopo 'vita' scrivi 'sotto' o 'sopra'")
    if parole[0] in ("nessun", "nessuno") and len(parole) >= 4 and parole[1].startswith("nemic"):
        # nessun nemico da 20 secondi
        i = parole.index("da") if "da" in parole else 2
        return Condizione("nessun_nemico", _secondi(parole[i + 1:]), negata, testo)
    if parole[0] in ("fermo", "bloccato", "incastrato"):
        if len(parole) >= 3 and parole[1] == "da":
            return Condizione("fermo", _secondi(parole[2:]), negata, testo)
        return Condizione("fermo", 3.0, negata, testo)
    if parole[0] in ("casse", "cassa") and len(parole) >= 3 and parole[1].startswith("apert"):
        n = parole[3] if parole[2] in ("almeno", ">=") and len(parole) > 3 else parole[2]
        return Condizione("casse_aperte", numero(n), negata, testo)
    raise ErroreIstruzione("condizione che non capisco: '%s'" % testo.strip())


# ------------------------------------------------------------------ azioni
class Azione:
    def __init__(self, tipo, *valori, testo=""):
        self.tipo = tipo
        self.valori = valori
        self.testo = testo

    def __repr__(self):
        return "Azione(%s %r)" % (self.tipo, self.valori)


def leggi_azione(testo, tasto_esiste=None, macro=None):
    originale = testo.strip()
    t = " ".join(originale.lower().split())
    if not t:
        raise ErroreIstruzione("azione vuota")
    parole = t.split(" ")
    p0 = parole[0]
    macro = macro or {}

    def controlla_tasto(nome):
        if tasto_esiste is not None and not tasto_esiste(nome):
            raise ErroreIstruzione("tasto sconosciuto: '%s'" % nome)
        return nome

    if p0 == "premi":
        if len(parole) < 2:
            raise ErroreIstruzione("dopo 'premi' scrivi il tasto, es: premi x")
        volte = 1
        resto = parole[1:]
        if len(resto) >= 3 and resto[-1].startswith("volt"):
            volte = int(numero(resto[-2]))
            resto = resto[:-2]
        return Azione("premi", controlla_tasto(_nome(" ".join(resto))), max(1, volte), testo=originale)
    if p0 == "tieni":
        resto = [p for p in parole[1:] if p not in ("premuto", "giu", "giù", "per")]
        unita = ("secondi", "secondo", "sec", "s", "minuti", "minuto", "millisecondi")
        if resto and resto[-1] in unita:
            resto = resto[:-1]
        if len(resto) < 2:
            raise ErroreIstruzione("scrivi ad esempio: tieni e 2   (tiene premuto E per 2 secondi)")
        return Azione("tieni", controlla_tasto(_nome(" ".join(resto[:-1]))), _secondi([resto[-1]]), testo=originale)
    if p0 in ("clicca", "click", "clic"):
        resto = [p for p in parole[1:] if p not in ("su", "sul", "sulla", "sullo", "il", "la", "pulsante", "immagine", "scritta")]
        pulsante = "mouse_sinistro"
        if resto and resto[0] in ("destro", "dx"):
            pulsante = "mouse_destro"
            resto = resto[1:]
        elif resto and resto[0] in ("sinistro", "sx"):
            resto = resto[1:]
        if not resto:
            return Azione("clicca", pulsante, testo=originale)
        return Azione("clicca_immagine", _nome("_".join(resto)), pulsante, testo=originale)
    if p0 in ("aspetta", "attendi"):
        resto = [p for p in parole[1:] if p not in ("di", "che", "vedere", "compaia", "finche", "finché")]
        if not resto:
            raise ErroreIstruzione("scrivi ad esempio: aspetta 2")
        if _NUMERO.match(resto[0].replace(",", ".")) or re.match(r"^\d+(?:[.,]\d+)?(ms|s|m)$", resto[0]):
            return Azione("aspetta", _secondi(resto), testo=originale)
        # aspetta NOME [massimo N]: aspetta di vedere un'immagine
        massimo = 30.0
        if len(resto) >= 2 and _NUMERO.match(resto[-1].replace(",", ".")):
            massimo = numero(resto[-1])
            resto = [p for p in resto[:-1] if p not in ("massimo", "max", "per")]
        return Azione("aspetta_immagine", _nome("_".join(resto)), massimo, testo=originale)
    if p0 in ("gira", "girati", "ruota"):
        resto = [p for p in parole[1:] if p not in ("di", "a", "verso", "gradi", "°")]
        if p0 == "girati" and not resto:
            return Azione("gira", 180.0, testo=originale)
        if not resto:
            raise ErroreIstruzione("scrivi ad esempio: gira 90  (negativo = a sinistra)")
        if resto[0] == "destra":
            return Azione("gira", 90.0, testo=originale)
        if resto[0] == "sinistra":
            return Azione("gira", -90.0, testo=originale)
        if resto[0] in ("indietro", "dietro"):
            return Azione("gira", 180.0, testo=originale)
        return Azione("gira", numero(resto[0].rstrip("°")), testo=originale)
    if p0 == "scrivi":
        return Azione("scrivi", originale.split(" ", 1)[1] if " " in originale else "", testo=originale)
    if p0 == "conta":
        cosa = _nome(" ".join(parole[1:])) or "partita"
        return Azione("conta", cosa, testo=originale)
    if t in ("pausa", "metti in pausa", "fermati"):
        return Azione("pausa", testo=originale)
    if t in ("esci", "chiudi", "ferma bot", "chiudi bot", "spegni"):
        return Azione("esci", testo=originale)
    if t in ("rilascia", "rilascia tutto", "lascia tutto"):
        return Azione("rilascia", testo=originale)
    if p0 in ("salta", "ricarica", "costruisci", "cura", "accovacciati", "interagisci", "apri") and len(parole) == 1 \
            and _nome(t) not in macro:
        nome = "interagisci" if p0 == "apri" else p0
        return Azione("premi", controlla_tasto(nome), 1, testo=originale)
    nome = _nome(t)
    if p0 in ("macro", "azione", "fai") and len(parole) >= 2:
        nome = _nome(" ".join(parole[1:]))
    if nome in macro:
        return Azione("macro", nome, testo=originale)
    if tasto_esiste is not None and tasto_esiste(nome):
        return Azione("premi", nome, 1, testo=originale)
    raise ErroreIstruzione("azione che non capisco: '%s'" % originale)


_SEPARA_AZIONI = re.compile(r"\s*(?:,|;|\bpoi\b)\s*", re.IGNORECASE)


def _togli_e_finale(pezzo):
    """'premi x e' (da 'premi x e poi ...') -> 'premi x'. Ma 'premi e' resta 'premi e' (il tasto E)."""
    parole = pezzo.split()
    if len(parole) >= 2 and parole[-1].lower() == "e":
        if parole[0].lower() not in ("premi", "tieni") or len(parole) >= 3:
            return " ".join(parole[:-1])
    return pezzo


def leggi_azioni(testo, tasto_esiste=None, macro=None):
    pezzi = [_togli_e_finale(p.strip()) for p in _SEPARA_AZIONI.split(testo) if p and p.strip()]
    if not pezzi:
        raise ErroreIstruzione("nessuna azione dopo FAI")
    return [leggi_azione(p, tasto_esiste, macro) for p in pezzi]


# ------------------------------------------------------------------ regole
class Regola:
    def __init__(self, condizioni, azioni, riga=0, testo="", attesa=3.0):
        self.condizioni = condizioni
        self.azioni = azioni
        self.riga = riga
        self.testo = testo
        self.attesa = attesa
        self.prossima = 0.0          # prima di questo momento non si ripete
        self.fatta_inizio = False
        self.prossimo_ogni = None
        self.volte = 0

    def __repr__(self):
        return "Regola(riga %d: %s)" % (self.riga, self.testo)


_RIGA = re.compile(r"^\s*(?:quando|se)?\s*(.+?)\s+(?:fai|allora)\s*:?\s+(.+)$", re.IGNORECASE)
_DIVIDI_CONDIZIONI = re.compile(r"\s+e\s+", re.IGNORECASE)


def leggi_istruzioni(testo, tasto_esiste=None, macro=None, immagini_esiste=None, attesa=3.0):
    """Restituisce (regole, errori). Le righe sbagliate vengono saltate e segnalate."""
    regole, errori = [], []
    for n, riga in enumerate(testo.splitlines(), 1):
        pulita = riga.split("#", 1)[0].strip()
        if not pulita:
            continue
        m = _RIGA.match(pulita)
        if not m:
            errori.append("riga %d: manca 'QUANDO ... FAI ...': %s" % (n, pulita))
            continue
        try:
            condizioni = [leggi_condizione(c, immagini_esiste) for c in _DIVIDI_CONDIZIONI.split(m.group(1)) if c.strip()]
            azioni = leggi_azioni(m.group(2), tasto_esiste, macro)
        except ErroreIstruzione as e:
            errori.append("riga %d: %s" % (n, e))
            continue
        regole.append(Regola(condizioni, azioni, n, pulita, attesa))
    return regole, errori


def leggi_macro(dizionario, tasto_esiste=None):
    """Le macro di impostazioni.yaml: nome -> lista di azioni."""
    nomi = {_nome(k): str(v) for k, v in (dizionario or {}).items() if v}
    risultato, errori = {}, []
    for nome, testo in nomi.items():
        try:
            risultato[nome] = leggi_azioni(testo, tasto_esiste, nomi)
        except ErroreIstruzione as e:
            errori.append("macro '%s': %s" % (nome, e))
    return risultato, errori


# ------------------------------------------------------------------ cursore del mouse (per i menu)
def imposta_dpi():
    """Su Windows con lo schermo ingrandito (125%, 150%...) fa combaciare i pixel."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def leggi_cursore():
    """Posizione del cursore sul desktop, oppure None se non si riesce."""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            p = wintypes.POINT()
            if ctypes.windll.user32.GetCursorPos(ctypes.byref(p)):
                return (p.x, p.y)
        except Exception:
            return None
        return None
    try:
        from pynput.mouse import Controller
        return tuple(Controller().position)
    except Exception:
        return None


def cursore_visibile():
    """True/False se il cursore del mouse si vede (solo Windows), None se non si sa.
    Nei giochi il cursore sparisce mentre giochi e ricompare nei menu."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class CURSORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD),
                        ("hCursor", wintypes.HANDLE), ("ptScreenPos", wintypes.POINT)]
        info = CURSORINFO()
        info.cbSize = ctypes.sizeof(CURSORINFO)
        if ctypes.windll.user32.GetCursorInfo(ctypes.byref(info)):
            return bool(info.flags & 1)
    except Exception:
        pass
    return None


def finestra_in_primo_piano():
    """Titolo della finestra in primo piano (solo Windows), oppure None."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        u = ctypes.windll.user32
        h = u.GetForegroundWindow()
        n = u.GetWindowTextLengthW(h)
        buf = ctypes.create_unicode_buffer(n + 1)
        u.GetWindowTextW(h, buf, n + 1)
        return buf.value
    except Exception:
        return None


# ------------------------------------------------------------------ chi esegue le azioni
class Esecutore:
    def __init__(self, mani, occhi, schermo, cfg, controllo, log=print, statistiche=None, macro=None):
        self.mani = mani
        self.occhi = occhi
        self.schermo = schermo
        self.cfg = cfg
        self.controllo = controllo        # oggetto con .deve_fermarsi() e .pausa()/.esci()
        self.log = log
        self.statistiche = statistiche if statistiche is not None else {}
        self.macro = macro or {}
        mira = cfg.get("mira", {}) or {}
        self.passi_per_giro = float(mira.get("passi_per_giro", 3600) or 3600)
        menu = cfg.get("menu", {}) or {}
        self.passi_per_pixel_menu = float(menu.get("passi_per_pixel", 1.0) or 1.0)

    # ---- attese che si possono interrompere ----
    def dormi(self, secondi):
        fine = time.monotonic() + max(0.0, secondi)
        while True:
            if self.controllo is not None and self.controllo.deve_fermarsi():
                raise Interrotto()
            rimasto = fine - time.monotonic()
            if rimasto <= 0:
                return
            time.sleep(min(rimasto, 0.02))

    def foto_fresca(self):
        img = self.schermo.foto()
        self.occhi._img = img
        self.occhi.ultima_piccola = None
        return img

    # ---- singole azioni ----
    def gira(self, gradi, durata=0.25):
        passi = gradi / 360.0 * self.passi_per_giro
        pezzi = max(1, int(durata / 0.01))
        for _ in range(pezzi):
            self.mani.muovi(passi / pezzi, 0)
            self.dormi(0.01)

    def porta_cursore(self, x, y):
        """Porta il cursore nel punto (x, y) del desktop, controllando dov'e' arrivato."""
        pos = leggi_cursore()
        if pos is None:
            return self._porta_cursore_alla_cieca(x, y)
        guadagno = self.passi_per_pixel_menu
        for i in range(25):
            dx, dy = x - pos[0], y - pos[1]
            if abs(dx) <= 2 and abs(dy) <= 2:
                return True
            cx, cy = dx * guadagno, dy * guadagno
            self.mani.muovi(cx, cy)
            self.dormi(0.035)
            nuova = leggi_cursore()
            if nuova is None:
                return False
            mosso = max(abs(nuova[0] - pos[0]), abs(nuova[1] - pos[1]))
            comandato = max(abs(cx), abs(cy))
            if mosso == 0 and i == 0:
                # il cursore non si muove: il gioco lo blocca, vado alla cieca
                return self._porta_cursore_alla_cieca(x, y)
            if mosso > 0 and comandato >= 8:
                rapporto = mosso / comandato
                guadagno = min(5.0, max(0.2, guadagno / max(0.2, rapporto) * 0.9))
            pos = nuova
        return abs(x - pos[0]) <= 6 and abs(y - pos[1]) <= 6

    def _porta_cursore_alla_cieca(self, x, y):
        """Spinge il cursore nell'angolo in alto a sinistra e poi conta i passi."""
        ox, oy = self.schermo.origine
        for _ in range(40):
            self.mani.muovi(-127, -127)
            self.dormi(0.004)
        self.dormi(0.05)
        tx = (x - ox) * self.passi_per_pixel_menu
        ty = (y - oy) * self.passi_per_pixel_menu
        passi = int(max(abs(tx), abs(ty)) // 20) + 1
        for _ in range(passi):
            self.mani.muovi(tx / passi, ty / passi)
            self.dormi(0.008)
        return True

    def clicca_immagine(self, nome, pulsante):
        self.foto_fresca()
        trovato = self.occhi.vedi(nome)
        if trovato is None:
            self.log("   non vedo '%s' sullo schermo: non clicco" % nome)
            return False
        ox, oy = self.schermo.origine
        self.porta_cursore(ox + trovato[0], oy + trovato[1])
        self.dormi(0.08)
        self.mani.premi(pulsante, 0.08)
        self.statistiche["casse_partita"] = 0      # un menu = la partita e' finita: si ricomincia a contare
        return True

    def aspetta_immagine(self, nome, massimo):
        fine = time.monotonic() + massimo
        while time.monotonic() < fine:
            self.foto_fresca()
            if self.occhi.vedi(nome) is not None:
                return True
            self.dormi(0.25)
        self.log("   '%s' non e' comparsa entro %.0f secondi" % (nome, massimo))
        return False

    def esegui(self, azioni, profondita=0):
        if profondita > 6:
            self.log("   troppe macro una dentro l'altra: mi fermo")
            return
        for a in azioni:
            if self.controllo is not None and self.controllo.deve_fermarsi():
                raise Interrotto()
            tipo, v = a.tipo, a.valori
            if tipo == "premi":
                for i in range(v[1]):
                    self.mani.premi(v[0], 0.07)
                    if i + 1 < v[1]:
                        self.dormi(0.08)
            elif tipo == "tieni":
                self.mani.giu(v[0])
                try:
                    self.dormi(v[1])
                finally:
                    self.mani.su(v[0])
            elif tipo == "clicca":
                self.mani.premi(v[0], 0.07)
            elif tipo == "clicca_immagine":
                self.clicca_immagine(v[0], v[1])
            elif tipo == "aspetta":
                self.dormi(v[0])
            elif tipo == "aspetta_immagine":
                self.aspetta_immagine(v[0], v[1])
            elif tipo == "gira":
                self.gira(v[0])
            elif tipo == "scrivi":
                self.mani.scrivi(v[0])
            elif tipo == "conta":
                chiave = {"partita": "partite", "partite": "partite"}.get(v[0], v[0])
                self.statistiche[chiave] = self.statistiche.get(chiave, 0) + 1
                if chiave == "partite":
                    self.statistiche["casse_partita"] = 0
            elif tipo == "rilascia":
                self.mani.rilascia_tutto()
            elif tipo == "pausa":
                if self.controllo is not None:
                    self.controllo.pausa()
                raise Interrotto()
            elif tipo == "esci":
                if self.controllo is not None:
                    self.controllo.esci()
                raise Interrotto()
            elif tipo == "macro":
                if v[0] in self.macro:
                    self.esegui(self.macro[v[0]], profondita + 1)
            self.dormi(0.02)


# ------------------------------------------------------------------ controllo delle regole
class Istruzioni:
    def __init__(self, regole, occhi, log=print):
        self.regole = regole
        self.occhi = occhi
        self.log = log
        self.inizio = time.monotonic()
        for r in regole:
            for c in r.condizioni:
                if c.tipo == "ogni":
                    r.prossimo_ogni = self.inizio + c.valore

    def _vera(self, c, vis, stato, t):
        if c.tipo == "inizio":
            ris = True
        elif c.tipo == "ogni":
            return True   # gestita a parte (prossimo_ogni)
        elif c.tipo == "vedi":
            ris = self.occhi.vedi(c.valore) is not None
        elif c.tipo == "vedi_categoria":
            ris = len(vis.oggetti.get(c.valore, [])) > 0
        elif c.tipo == "vita_sotto":
            ris = vis.vita is not None and vis.vita < c.valore
        elif c.tipo == "vita_sopra":
            ris = vis.vita is not None and vis.vita > c.valore
        elif c.tipo == "nessun_nemico":
            ris = t - stato.get("ultimo_nemico", self.inizio) >= c.valore
        elif c.tipo == "fermo":
            ris = stato.get("fermo_da", 0.0) >= c.valore
        elif c.tipo == "casse_aperte":
            ris = stato.get("casse", 0) >= c.valore
        else:
            ris = False
        return (not ris) if c.negata else ris

    def controlla(self, vis, stato, t=None):
        """La prima regola che si avvera (in ordine di file), oppure None."""
        t = time.monotonic() if t is None else t
        for r in self.regole:
            if t < r.prossima:
                continue
            if r.fatta_inizio:
                continue
            if r.prossimo_ogni is not None and t < r.prossimo_ogni:
                continue
            # prima le condizioni veloci, poi quelle che cercano immagini
            ordinate = sorted(r.condizioni, key=lambda c: 1 if c.tipo == "vedi" else 0)
            if all(self._vera(c, vis, stato, t) for c in ordinate):
                r.prossima = t + r.attesa
                r.volte += 1
                for c in r.condizioni:
                    if c.tipo == "ogni":
                        r.prossimo_ogni = t + c.valore
                    if c.tipo == "inizio":
                        r.fatta_inizio = True
                return r
        return None
