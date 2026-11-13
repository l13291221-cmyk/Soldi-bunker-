"""
cervello.py - Il "cervello" del bot: ogni fotogramma decide cosa fare.

=====================================================================
  OBIETTIVO DEL BOT
    1. VINCERE LA PARTITA: restare vivo ed eliminare i nemici
    2. APRIRE PIU' CASSE POSSIBILI: le casse delle armi e quelle dei materiali
       (e raccogliere le armi che trova per terra)
=====================================================================

Per riuscirci, ogni fotogramma segue questo ordine (il primo che vale vince):
  1. ISTRUZIONI  : le tue regole di istruzioni.txt (es. squadra morta -> partita successiva)
  2. IMPARA      : all'inizio misura da solo come si muove la visuale in QUESTO gioco
  3. COMBATTI    : se vede un nemico lo mira e spara; se lo colpiscono forte costruisce un muro
  4. CURA        : se ha poca vita e nessun nemico in giro
  5. CASSE       : va verso casse delle armi (prima), casse dei materiali e armi, e le apre
  6. ESPLORA     : corre in giro per trovare nuove casse, si guarda intorno, se si blocca salta e gira
"""

import math
import random
import time

import cv2
import numpy as np

import impostazioni
from obiettivo import Obiettivo
from stile import STILI

OBIETTIVO = ("vincere la partita (restare vivo ed eliminare i nemici) e aprire piu' casse possibili "
             "(casse delle armi e casse dei materiali)")

# quanto vale ogni cosa da raccogliere (piu' alto = ci va prima): nome dell'impostazione in "raccolta"
VALORE_RACCOLTA = {"cassa": "priorita_casse", "materiali": "priorita_materiali", "arma": "priorita_armi"}


def _cfg(cfg, sezione):
    return cfg.get(sezione, {}) or {}


def viola(img):
    """Quanta parte dello schermo e' viola (0-1): la tempesta di Fortnite colora tutto di viola."""
    piccola = cv2.resize(img, (96, 54), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(piccola, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    m = (h >= 125) & (h <= 165) & (s >= 60) & (v >= 40)
    return float(np.count_nonzero(m)) / m.size


def trova_pulsante_giallo(img):
    """Il pulsante grande e giallo ("Gioca di nuovo", "Gioca"): un rettangolo giallo pieno,
    largo, nella meta' bassa dello schermo. -> (cx, cy, w, h) in pixel, oppure None."""
    H, W = img.shape[:2]
    lw = 320
    lh = max(1, int(round(H * lw / float(W))))
    piccola = cv2.resize(img, (lw, lh), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(piccola, cv2.COLOR_BGR2HSV)
    m = cv2.inRange(hsv, (20, 150, 170), (36, 255, 255))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7)))  # via le lettere
    n, _, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    migliore = None
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        frazione = (w * h) / float(lw * lh)
        if not (0.006 <= frazione <= 0.2) or not (1.6 <= w / max(1.0, h) <= 9.0):
            continue
        if area / float(max(1, w * h)) < 0.6 or (y + h / 2.0) / lh < 0.5:
            continue
        # un pulsante ha la SCRITTA sopra (lettere scure): un muro o un oggetto giallo no
        k = W / float(lw)
        x1, y1 = int(x * k), int(y * k)
        x2, y2 = int((x + w) * k), int((y + h) * k)
        grigio = cv2.cvtColor(img[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
        scuro = float(np.count_nonzero(grigio < 90)) / max(1, grigio.size)
        if not (0.02 <= scuro <= 0.45):
            continue
        if migliore is None or w * h > migliore[2] * migliore[3]:
            migliore = (x, y, w, h)
    if migliore is None:
        return None
    k = W / float(lw)
    x, y, w, h = migliore
    return ((x + w / 2.0) * k, (y + h / 2.0) * k, w * k, h * k)


class Conferma:
    """Una cassa (o un'arma) conta solo se la vedo in piu' fotogrammi di fila nello stesso
    posto (tenendo conto di quanto ho girato la visuale): cosi' un riflesso giallo di un
    attimo non diventa una cassa."""

    def __init__(self, volte=3, raggio=0.08, memoria=0.5):
        self.volte = max(1, int(volte))
        self.raggio = raggio
        self.memoria = memoria
        self.tracce = []              # [x, y, volte viste, ultima volta]

    def filtra(self, oggetti, t, spostamento, larghezza):
        if self.volte <= 1:
            return list(oggetti)
        self.tracce = [tr for tr in self.tracce if t - tr[3] <= self.memoria]
        raggio = self.raggio * larghezza
        usate = set()
        confermati = []
        for b in oggetti:
            migliore, dmin = None, raggio
            for i, tr in enumerate(self.tracce):
                if i in usate:
                    continue
                # se ho girato la visuale a destra, le cose sullo schermo vanno a sinistra
                d = math.hypot(b.cx - (tr[0] - spostamento[0]), b.cy - (tr[1] - spostamento[1]))
                if d < dmin:
                    migliore, dmin = i, d
            if migliore is None:
                self.tracce.append([b.cx, b.cy, 1, t])
                usate.add(len(self.tracce) - 1)
                volte = 1
            else:
                tr = self.tracce[migliore]
                if t > tr[3]:
                    tr[2] += 1
                tr[0], tr[1], tr[3] = b.cx, b.cy, t
                usate.add(migliore)
                volte = tr[2]
            if volte >= self.volte:
                confermati.append(b)
        return confermati


class Cervello:
    def __init__(self, cfg, mani, occhi, esecutore, istruzioni, log=print, apprendimento=None, schermo=None,
                 obiettivo=None, stile=None, ia=None):
        self.cfg = cfg
        self.ia = ia                      # il cervello lento che guarda (ia.py), se collegato
        self.ultimo_consiglio = 0
        self.ultimo_consiglio_menu = 0
        self.prossimo_salto_bus = 0.0
        self.fort = _cfg(cfg, "fortnite")
        self.in_partita = False           # per contare le partite (l'IA dice quando finiscono)
        self.in_auto_da = None            # da quando sto guidando
        self.niente_auto_fino = 0.0       # appena sceso non risalgo subito
        self.cursore_atteso = None        # nei menu: dov'era il cursore e quanto l'ho spostato
        self.scappo_fino = 0.0            # tempesta: fino a quando corro verso la zona sicura
        self.prossimo_giallo = 0.0        # pulsante giallo "Gioca di nuovo"
        self.giallo_visto = None          # (cx, cy, miniatura) dell'ultima volta che l'ho visto
        self.giallo_tentativo = None      # (quando ho cliccato, passi per pixel usati)
        self.giallo_indice = 0
        self.pc = None                    # il mouse del PC e la finestra di PS Remote Play (remote_play.py)
        self.ultimo_consiglio_schermo = 0
        self.volte_chi = 0                # quante volte ho risposto a "Chi sta usando...?"
        self.prossimo_avviso_schermo = 0.0
        self.prossimo_davanti = 0.0
        self.fase_lunga = (None, 0.0)     # (bus/caduta, da quando l'IA lo dice senza smettere)
        self.ignora_fase_fino = 0.0
        self.attesa_da = None             # da quando aspetto nei menu / da eliminato
        self.morto_da = None              # da quando sono stato eliminato (per il furgone del riavvio)
        self.prossimo_avviso_attesa = 0.0
        self.ultima_partita_contata = -1000.0
        self.prossimo_controllo_tempesta = 0.0
        self.obiettivo = obiettivo if obiettivo is not None else Obiettivo()
        self.stile = stile if stile is not None else STILI["pro"]     # come gioca (stile.py)
        self.mani = mani
        self.occhi = occhi
        self.esecutore = esecutore
        self.istruzioni = istruzioni
        self.log = log
        self.apprendimento = apprendimento
        self.schermo = schermo if schermo is not None else getattr(esecutore, "schermo", None)
        self.mira = _cfg(cfg, "mira")
        self.comb = _cfg(cfg, "combattimento")
        self.racc = _cfg(cfg, "raccolta")
        self.espl = _cfg(cfg, "esplorazione")
        self.vita_cfg = _cfg(cfg, "vita")
        self.regole_cfg = _cfg(cfg, "regole")
        self.mirino_frazione = (_cfg(cfg, "schermo").get("mirino") or [0.5, 0.5])
        self._ppp = max(0.01, float(self.mira.get("pixel_per_passo", 1.0) or 1.0))
        self._forza = float(self.mira.get("forza", 0.6))

        adesso = time.monotonic()
        self.statistiche = esecutore.statistiche
        for k in ("casse", "materiali", "armi", "casse_tentate", "partite", "combattimenti", "nemici_colpiti",
                  "casse_partita", "casse_fallite", "bloccato", "lasciate_perdere"):
            self.statistiche.setdefault(k, 0)
        self.stato = {"ultimo_nemico": adesso, "fermo_da": 0.0, "casse": 0}
        self.t_prec = adesso
        # combattimento
        self.bersaglio = None             # (x, y) sullo schermo al fotogramma prima
        self.errore_prec = None
        self.velocita = (0.0, 0.0)
        self.mosso_px = (0.0, 0.0)        # quanto ho spostato la visuale dal fotogramma prima
        self.ultimo_visto_nemico = 0.0
        self.sparando_da = None
        self.raffica_fine = 0.0
        self.prossima_schivata = 0.0
        self.lato_schivata = "sinistra"
        self.ha_sparato = False
        self.storia_vita = []
        self.prossimo_muro = 0.0
        self.prossima_cura = 0.0
        self.ultimo_colpo = 0.0           # quando mi hanno colpito l'ultima volta
        self.prossimo_cambio_arma = 0.0
        self.reazione_fino = 0.0          # stile: prima di questo momento non spara al nemico appena visto
        self.errore_mira = (0.0, 0.0)     # stile: di quanto sbaglia la mira adesso
        self.prossimo_errore = 0.0
        self.avvisato_casse = False
        # raccolta
        self.inseguo_da = None
        self.ignora_raccolta_fino = 0.0
        volte = int(self.racc.get("conferma_fotogrammi", 3) or 1)
        self.conferma = {cat: Conferma(volte) for cat in ("cassa", "materiali", "arma")}
        self.fallite_di_fila = 0          # casse che "non si aprono" una dopo l'altra
        # esplorazione
        self.prossimo_guardarsi = adesso + float(self.espl.get("guarda_intorno_ogni", 12) or 12)
        self.giro_fino = 0.0              # fino a quando si sta guardando intorno (giro fluido)
        self.dt_medio = 1.0 / 30          # quanto dura in media un fotogramma (per la visuale fluida)
        self.deriva = 0.0
        self.prossima_deriva = adesso
        self.pitch = 0.0                  # quanto ho alzato/abbassato la visuale (passi)
        self.mini_prec = None
        self.t_mini = adesso
        self.fermo_conta = 0
        self.ultimo_mosso = adesso
        self.ultimo_sblocco = -100.0      # quando mi sono sbloccato l'ultima volta
        self.verso_sblocco = 1            # da che parte ho girato (se mi riblocco giro dall'altra)
        self.prossimo_controllo_regole = 0.0

    # ------------------------------------------------------------------ valori imparati
    @property
    def ppp(self):
        """Pixel di spostamento dello schermo per ogni passo del mouse (imparato da solo)."""
        return self.apprendimento.ppp if self.apprendimento is not None else self._ppp

    @property
    def forza(self):
        return self.apprendimento.forza if self.apprendimento is not None else self._forza

    @property
    def passi_per_giro(self):
        if self.apprendimento is not None:
            return self.apprendimento.passi_per_giro
        return float(self.mira.get("passi_per_giro", 3600) or 3600)

    # ------------------------------------------------------------------ utilita'
    def _muovi(self, dx, dy, fluido=False):
        """Muove la visuale. fluido=True: a passettini fino al prossimo fotogramma (niente scatti)
        e mai piu' veloce di mira -> velocita_massima_gradi."""
        massimo = float(self.mira.get("massimo_passi", 400) or 400)
        durata = min(0.12, max(0.02, self.dt_medio))
        if fluido:
            gradi_al_secondo = float(self.mira.get("velocita_massima_gradi", 540) or 540)
            massimo = min(massimo, self.passi_per_giro * gradi_al_secondo / 360.0 * durata)
        dx = max(-massimo, min(massimo, dx))
        dy = max(-massimo, min(massimo, dy))
        limite = self.passi_per_giro / 4
        if self.pitch + dy > limite:
            dy = limite - self.pitch
        elif self.pitch + dy < -limite:
            dy = -limite - self.pitch
        if fluido:
            self.mani.mira_fluida(dx, dy, durata)
        else:
            self.mani.muovi(dx, dy)
        self.pitch += dy
        self.mosso_px = (self.mosso_px[0] + dx * self.ppp, self.mosso_px[1] + dy * self.ppp)

    def _cammina(self, avanti=False, corri=False, sinistra=False, destra=False, indietro=False):
        for nome, valore in (("avanti", avanti), ("corri", corri), ("sinistra", sinistra),
                             ("destra", destra), ("indietro", indietro)):
            if self.mani.esiste(nome):
                self.mani.imposta(nome, valore)

    def _spara(self, valore):
        self.mani.imposta("spara", valore)
        if valore:
            self.ha_sparato = True

    def ferma_tutto(self):
        self.mani.rilascia_tutto()
        self.sparando_da = None
        self.bersaglio = None
        self.errore_prec = None
        self.inseguo_da = None
        self.giro_fino = 0.0

    def _mirino(self, vis):
        return (self.mirino_frazione[0] * vis.larghezza, self.mirino_frazione[1] * vis.altezza)

    def _esegui_macro(self, nome, motivo):
        nome = str(nome or "").strip().lower()
        if not nome:
            return False
        if nome in self.esecutore.macro:
            azioni = self.esecutore.macro[nome]
        elif self.mani.esiste(nome):
            self.log("%s -> premo %s" % (motivo, nome))
            self.mani.premi(nome)
            return True
        else:
            return False
        self.log("%s -> %s" % (motivo, nome))
        self._spara(False)
        self.esecutore.esegui(azioni)
        return True

    # ------------------------------------------------------------------ fotogramma
    def passo(self, vis, img=None, t=None):
        """Decide e fa la mossa per questo fotogramma. Restituisce una scritta su cosa sta facendo."""
        t = time.monotonic() if t is None else t
        dt = max(1e-3, min(0.2, t - self.t_prec))
        self.t_prec = t
        self.dt_medio = 0.8 * self.dt_medio + 0.2 * dt
        if vis.nemici:
            self.stato["ultimo_nemico"] = t
        self.stato["casse"] = self.statistiche.get("casse", 0) + self.statistiche.get("materiali", 0)
        if vis.vita is not None:
            self.storia_vita.append((t, vis.vita))
            self.storia_vita = [(tt, v) for tt, v in self.storia_vita if t - tt <= 1.5]

        # 1. istruzioni
        if t >= self.prossimo_controllo_regole and self.istruzioni is not None:
            self.prossimo_controllo_regole = t + float(self.regole_cfg.get("controlla_ogni", 0.2) or 0.2)
            regola = self.istruzioni.controlla(vis, self.stato, t)
            if regola is not None:
                self.log("Istruzione (riga %d): %s" % (regola.riga, regola.testo))
                self.ferma_tutto()
                try:
                    self.esecutore.esegui(regola.azioni)
                finally:
                    self._dopo_pausa()
                return "istruzione riga %d" % regola.riga

        # 1a. finita la partita: il pulsante giallo "Gioca di nuovo" (senza bisogno dell'IA)
        scritta = self._pulsante_giallo(vis, img, t)
        if scritta:
            return scritta

        # 1b. l'IA che guarda: sul bus, in caduta, nei menu (logica Fortnite)
        scritta = self._fase_ia(img, t, vis)
        if scritta:
            return scritta

        # 2. impara come si muove la visuale in questo gioco
        if self.apprendimento is not None and self.schermo is not None and self.apprendimento.serve_calibrare(t):
            self.ferma_tutto()
            try:
                scritta = self.apprendimento.calibra(self.mani, self.schermo, self.esecutore)
            finally:
                self._dopo_pausa()
            return scritta

        if self.apprendimento is not None and img is not None:
            self.apprendimento.forse_salva_foto(img, vis, t)

        # l'obiettivo decide quali nemici affrontare
        if self._vita_persa() >= 5:
            self.ultimo_colpo = t
        if vis.nemici and self._solo_nemici_vicini() and t - self.ultimo_colpo > 3.0:
            vicino = float(self.comb.get("nemico_vicino", 0.22)) * vis.altezza
            vis.oggetti["nemico"] = [b for b in vis.nemici if b.h >= vicino]

        # le casse e le armi contano solo se le vedo per qualche fotogramma di fila
        for cat, conferma in self.conferma.items():
            vis.oggetti[cat] = conferma.filtra(vis.oggetti.get(cat, []), t, self.mosso_px, vis.larghezza)

        # l'IA che guarda: casse finte, muri, tempesta
        scritta = self._tattica_ia(vis, t)
        if scritta:
            return scritta

        # 3. combattimento
        if self.comb.get("attivo", True):
            scritta = self._combatti(vis, t, dt)
            if scritta:
                return scritta

        # dopo un combattimento: ricarica
        if self.ha_sparato and t - self.ultimo_visto_nemico > 1.0:
            self.ha_sparato = False
            if self.comb.get("ricarica_dopo", True) and self.mani.esiste("ricarica"):
                self.mani.premi("ricarica")

        # 3b. tempesta (si vede dal viola): scappo verso dove c'e' meno viola
        scritta = self._tempesta(img, t)
        if scritta:
            return scritta

        # 4. cura
        scritta = self._cura(vis, t)
        if scritta:
            return scritta

        # 5. casse e armi
        scritta = self._raccogli(vis, t, img)
        if scritta:
            self.mosso_px = (0.0, 0.0)
            return scritta

        # 6. esplora
        scritta = self._esplora(vis, t, dt, img)
        self.mosso_px = (0.0, 0.0)
        return scritta

    # ------------------------------------------------------------------ l'IA che guarda
    def _fase_ia(self, img, t, vis=None):
        """Logica Fortnite con l'IA: sul bus salta, in caduta va avanti, nei menu aspetta."""
        if self.ia is None:
            return None
        if img is not None:
            self.ia.guarda(img)
        c = self.ia.consiglio(t, self.ia.validita_fase)
        if c is None:
            return None
        if c.fase != "playing" and not self._ancora_valido(c, img, t):
            # l'IA (lenta) parlava di uno schermo che ormai e' cambiato: non le credo e gioco
            return None
        scritta = self._schermo_ia(c, img, t)
        if scritta:
            return scritta
        if c.fase != "dead":
            self.morto_da = None              # vivo (o riportato in partita col furgone del riavvio)
        if c.fase in ("bus", "falling"):
            # sul bus o in caduta non si sta per minuti: se l'IA lo dice da troppo, sbaglia
            if self.fase_lunga[0] != c.fase:
                self.fase_lunga = (c.fase, t)
            elif t - self.fase_lunga[1] > float(self.fort.get("fase_massima_secondi", 120) or 120):
                self.log("L'IA dice '%s' da troppo tempo: non le credo e gioco" % c.descrizione())
                self.ignora_fase_fino = t + 60.0
                self.fase_lunga = (None, t)
            if t < self.ignora_fase_fino:
                return None
        else:
            self.fase_lunga = (None, t)
        if c.fase in ("menu", "dead"):
            if self.attesa_da is None:
                self.attesa_da = t
        else:
            self.attesa_da = None
        if c.fase in ("bus", "falling", "playing"):
            self.in_partita = True
        if c.fase == "bus":
            self._spara(False)
            self._cammina()
            if t >= self.prossimo_salto_bus and self.mani.esiste("salta"):
                self.prossimo_salto_bus = t + 3.0
                self.log("IA: sono sul bus -> salto giu'")
                self.mani.premi("salta")
            return "sul bus"
        if c.fase == "falling":
            self._spara(False)
            self._cammina(avanti=True)           # in caduta: avanti (il deltaplano si apre da solo)
            return "cado verso terra"
        if c.fase in ("menu", "dead"):
            self._spara(False)
            self._cammina()
            if c.fase == "dead" and vis is not None and img is not None and self.apprendimento is not None:
                # da eliminato guardo i compagni che giocano: le foto servono ad addestrare gli occhi
                self.apprendimento.forse_salva_foto(img, vis, t)
            if c.fase == "dead" and self.morto_da is None:
                self.morto_da = t
                self.log("Sono stato eliminato" + (": il personaggio che vedo adesso e' un ALTRO giocatore "
                                                   "(non sono io): non lo comando" if c.osservo else ""))
            if self.in_partita:
                self._partita_finita(t, sicuro=True)
            if c.fase == "dead" and c.osservo:
                # in squadra un compagno puo' riportarmi in partita col furgone del riavvio (la carta
                # dura circa 90 secondi): aspetto un po', poi torno alla lobby per la partita dopo
                attesa = float(self.fort.get("aspetta_riavvio_secondi", 90) or 0)
                if t - self.morto_da < attesa:
                    return "eliminato: guardo un compagno, aspetto il furgone del riavvio"
            return self._prossima_partita(c, img, t)
        return None

    def _schermo_ia(self, c, img, t):
        """Quando non si vede il gioco: il riquadro della PS5 "Chi sta usando...?", PS Remote Play
        scollegato, il desktop di Windows. Mi fermo (niente casse finte sul desktop!) e provo a
        tornare a giocare."""
        if c.schermo == "game":
            self.volte_chi = 0
            return None
        self._spara(False)
        self._cammina()
        nuovo = c.numero != self.ultimo_consiglio_schermo
        self.ultimo_consiglio_schermo = c.numero
        if c.schermo == "ps5_who_is_using":
            if nuovo:
                # di solito e' gia' scelto il tuo utente: INVIO. Se non basta, ogni tanto ESC
                self.volte_chi += 1
                tasto = "esc" if self.volte_chi % 4 == 0 else "invio"
                if self.mani.esiste(tasto):
                    self.log("PS5: 'Chi sta usando questo controller?' -> premo %s" % tasto.upper())
                    self.mani.premi(tasto, 0.1)
            return "la PS5 chiede chi sta giocando"
        if c.schermo == "remote_play":
            if nuovo and c.pulsante_pc is not None and self.pc is not None and img is not None:
                H, W = img.shape[:2]
                ox, oy = self.schermo.origine if self.schermo is not None else (0, 0)
                self.log("PS Remote Play si e' scollegato: clicco per ricollegarmi")
                self.pc.clicca(ox + c.pulsante_pc[0] * W, oy + c.pulsante_pc[1] * H)
                self.prossimo_avviso_schermo = t + 60.0
            elif t >= self.prossimo_avviso_schermo:
                self.prossimo_avviso_schermo = t + 60.0
                self.log("PS Remote Play e' scollegato. Se chiede il codice della PS5 o un aggiornamento, "
                         "fallo tu: poi riparto da solo")
            return "PS Remote Play scollegato"
        # desktop o un altro programma davanti al gioco
        if self.pc is not None and t >= self.prossimo_davanti:
            self.prossimo_davanti = t + 10.0
            if self.pc.porta_davanti():
                self.log("Non vedo il gioco: riporto davanti PS Remote Play")
                return "non vedo il gioco"
        if t >= self.prossimo_avviso_schermo:
            self.prossimo_avviso_schermo = t + 60.0
            self.log("Non vedo il gioco (c'e' il desktop o un altro programma): aspetto che torni")
        return "non vedo il gioco"

    def _partita_finita(self, t, sicuro=False):
        """Conta la partita (una volta sola) e fa scrivere il riepilogo all'allenamento.
        sicuro=True: l'IA ha visto una partita cominciare e finire. Senza IA (pulsante giallo)
        conto solo se e' passato un po' dall'ultima, cosi' non la conto due volte."""
        giocata = self.in_partita
        self.in_partita = False
        self.in_auto_da = None
        if not (sicuro or giocata) and t - self.ultima_partita_contata < 90.0:
            return
        self.ultima_partita_contata = t
        self.statistiche["partite"] = self.statistiche.get("partite", 0) + 1
        self.log("Partita finita (%d). Passo alla prossima." % self.statistiche["partite"])
        self.esecutore._fine_partita()

    def _pulsante_giallo(self, vis, img, t):
        """Finita la partita (tutta la squadra eliminata) c'e' il pulsante grande e giallo
        "Gioca di nuovo" (e nella lobby "Gioca"): lo clicco. Lo schermo deve essere fermo e il
        pulsante visto due volte nello stesso posto (cosi' in partita non clicca a caso).
        Sulla Play non so dove sia il cursore: se dopo il click il pulsante c'e' ancora, riprovo
        con un'altra 'velocita' del cursore' finche' non lo prendo, e me la ricordo."""
        if img is None or not self.fort.get("pulsante_giallo", True) or t < self.prossimo_giallo:
            return None
        self.prossimo_giallo = t + 1.0
        from ia import miniatura
        trovato = trova_pulsante_giallo(img)
        if trovato is None:
            if self.giallo_tentativo is not None:
                # dopo il click e' sparito: ha funzionato. Mi ricordo come muovere il cursore
                ppm = self.giallo_tentativo[1]
                self.esecutore.passi_per_pixel_menu = ppm
                if self.apprendimento is not None:
                    impostazioni.salva_calibrazione(self.apprendimento.base, ["menu", "passi_per_pixel"],
                                                    round(ppm, 3))
                self.log("Gioca di nuovo: cliccato! (cursore: %.2f passi per pixel)" % ppm)
                self.giallo_tentativo = None
                self.giallo_indice = 0
            self.giallo_visto = None
            return None
        cx, cy, w, h = trovato
        mini = miniatura(img)
        prima = self.giallo_visto
        fermo = prima is not None and math.hypot(cx - prima[0], cy - prima[1]) < 0.05 * img.shape[1] and \
            float(np.mean(np.abs(mini - prima[2]))) < 8.0
        volte = prima[3] + 1 if fermo else 1
        self.giallo_visto = (cx, cy, mini, volte)
        # lo devo vedere 3 volte di fila, a schermo fermo. Se mi sembra di vedere un "nemico" (nella
        # schermata finale c'e' il TUO personaggio, e lo scambiavo per un nemico: non cliccava mai)
        # aspetto 5 volte: in partita, con un nemico vero, lo schermo non sta fermo cosi' a lungo
        if volte < (5 if vis.nemici else 3):
            return None
        if self.giallo_tentativo is not None:
            if t - self.giallo_tentativo[0] < 2.5:
                return "aspetto che riparta"
            self.giallo_indice += 1          # c'e' ancora: il cursore non ci era arrivato. Riprovo
        attuale = float(getattr(self.esecutore, "passi_per_pixel_menu", 1.0) or 1.0)
        candidati = [attuale] + [v for v in (1.0, 0.5, 1.5, 0.75, 2.0, 3.0, 0.35, 4.0) if abs(v - attuale) > 0.01]
        ppm = candidati[self.giallo_indice % len(candidati)]
        self.esecutore.passi_per_pixel_menu = ppm
        self._spara(False)
        self._cammina()
        if self.giallo_indice == 0:
            self.log("Vedo il pulsante giallo (Gioca di nuovo): clicco")
            self._partita_finita(t)
        ox, oy = self.schermo.origine if self.schermo is not None else (0, 0)
        self.esecutore.porta_cursore(ox + cx, oy + cy)
        self.esecutore.dormi(0.1)
        self.mani.premi("mouse_sinistro", 0.08)
        self.giallo_tentativo = (t, ppm)
        return "clicco Gioca di nuovo"

    def _ancora_valido(self, c, img, t):
        """Un consiglio vale se e' fresco, oppure se lo schermo e' quasi uguale a quello della foto
        (i menu stanno fermi: anche se l'IA ci ha messo un minuto a rispondere va bene)."""
        if t - c.quando <= 6.0:
            return True
        prima = getattr(c, "miniatura", None)
        if prima is None or img is None:
            return False
        from ia import miniatura
        return float(np.mean(np.abs(miniatura(img) - prima))) < 10.0

    def _prossima_partita(self, c, img, t=None):
        """Nei menu e da eliminato: preme il tasto o clicca il pulsante che porta alla partita dopo.
        Un'azione per ogni risposta dell'IA, poi guarda di nuovo (cosi' si corregge)."""
        aspetto = "aspetto (%s)" % ("menu" if c.fase == "menu" else "eliminato")
        adesso = time.monotonic() if t is None else t
        if self.attesa_da is not None and adesso - self.attesa_da > 60 and adesso >= self.prossimo_avviso_attesa:
            self.prossimo_avviso_attesa = adesso + 60.0
            self.log("Aspetto da %d secondi (%s): l'IA non vede ancora un pulsante per la partita dopo"
                     % (adesso - self.attesa_da, "menu" if c.fase == "menu" else "eliminato"))
        if not self.fort.get("partite_in_loop", True) or c.numero == self.ultimo_consiglio_menu:
            return aspetto
        self.ultimo_consiglio_menu = c.numero
        if c.tasto != "none":
            from ia import NOMI_TASTI
            nome = NOMI_TASTI.get(c.tasto, c.tasto)
            if self.mani.esiste(nome):
                self.log("IA: la schermata dice di premere %s" % nome.upper())
                self.mani.premi(nome, 0.1)
                return "premo %s per continuare" % nome
        if c.pulsante is None or img is None:
            return aspetto
        H, W = img.shape[:2]
        bx, by = c.pulsante[0] * W, c.pulsante[1] * H
        ppm = float(getattr(self.esecutore, "passi_per_pixel_menu", 1.0) or 1.0)
        if c.cursore is None:
            # non vedo il cursore: ci vado "alla cieca" (o con la freccia del PC se il gioco e' qui)
            ox, oy = self.schermo.origine if self.schermo is not None else (0, 0)
            self.log("IA: clicco il pulsante per la partita dopo")
            self.esecutore.porta_cursore(ox + bx, oy + by)
            self.mani.premi("mouse_sinistro", 0.08)
            self.cursore_atteso = None
            return "clicco per la partita dopo"
        cx, cy = c.cursore[0] * W, c.cursore[1] * H
        if self.cursore_atteso is not None:
            # l'ultima volta l'ho spostato io: imparo di quanto si muove davvero il cursore
            (px, py), (dx0, dy0) = self.cursore_atteso
            mosso = math.hypot(cx - px, cy - py)
            voluto = math.hypot(dx0, dy0)
            if voluto > 20 and mosso > 3:
                ppm = min(5.0, max(0.2, 0.5 * ppm + 0.5 * ppm * voluto / mosso))
                self.esecutore.passi_per_pixel_menu = ppm
        dx, dy = bx - cx, by - cy
        if math.hypot(dx, dy) <= 0.025 * W:
            self.log("IA: il cursore e' sul pulsante -> clicco")
            self.mani.premi("mouse_sinistro", 0.08)
            self.cursore_atteso = None
            return "clicco per la partita dopo"
        self.mani.muovi(dx * ppm, dy * ppm)
        self.cursore_atteso = ((cx, cy), (dx, dy))
        return "porto il cursore sul pulsante"

    def _tattica_ia(self, vis, t):
        """In partita: l'IA dice se le casse sono vere, se c'e' un muro, dov'e' la tempesta."""
        if self.ia is None:
            return None
        c = self.ia.consiglio(t)
        if c is None or c.fase not in ("playing", "unknown"):
            return None
        scritta = self._auto(c, vis, t)
        if scritta:
            return scritta
        if c.cassa == "none" and self.ia.fidati_casse and vis.casse:
            vis.oggetti["cassa"] = []            # l'IA non vede casse: quelle trovate col colore sono finte
        nuovo = c.numero != self.ultimo_consiglio
        self.ultimo_consiglio = c.numero
        if not nuovo or vis.nemici:
            return None                          # ogni consiglio si usa una volta, e i nemici vengono prima
        if c.compagno != "none" and self.fort.get("rianima_compagni", True):
            if c.compagno == "close" and self.mani.esiste("interagisci"):
                self.log("IA: un compagno e' a terra vicino -> lo rianimo")
                self._cammina()
                self.mani.giu("interagisci")
                try:
                    self.esecutore.dormi(float(self.fort.get("rianima_secondi", 10) or 10))
                finally:
                    self.mani.su("interagisci")
                return "rianimo un compagno"
            if c.compagno in ("left", "right"):
                self.esecutore.gira(-35 if c.compagno == "left" else 35)
                self._cammina(avanti=True, corri=True)
                return "vado dal compagno a terra"
        if c.poca_vita and self.fort.get("cura_con_ia", True) and t >= self.prossima_cura:
            self.prossima_cura = t + 10.0
            self._cammina()
            if self._esegui_macro(self.vita_cfg.get("macro_cura", "cura"), "IA: ho poca vita"):
                return "mi curo"
        if (c.veicolo == "close" and self.fort.get("usa_veicoli", True) and t >= self.niente_auto_fino
                and not vis.casse and self.mani.esiste("interagisci")):
            self.log("IA: c'e' una macchina vicina -> salgo")
            self._cammina()
            self.mani.premi("interagisci", 0.1)
            self.niente_auto_fino = t + 5.0
            return "salgo in macchina"
        if c.tempesta and c.direzione in ("left", "right", "behind"):
            gradi = {"left": -90, "right": 90, "behind": 180}[c.direzione]
            self.log("IA: la tempesta e' vicina -> vado verso la zona sicura")
            self._cammina()
            self.esecutore.gira(gradi)
            self._cammina(avanti=True, corri=True)
            self.giro_fino = 0.0
            self.prossimo_guardarsi = t + 10.0
            return "scappo dalla tempesta"
        if c.muro and not vis.casse:
            self.log("IA: ho un muro davanti -> giro")
            self._cammina()
            self.esecutore.gira(random.choice((-1, 1)) * random.uniform(70, 120))
            return "evito il muro"
        if c.cassa in ("left", "right") and not vis.casse:
            self.esecutore.gira(-35 if c.cassa == "left" else 35)
            return "giro verso la cassa che vede l'IA"
        return None

    def _auto(self, c, vis, t):
        """In macchina: guida (verso la zona sicura se c'e' la tempesta) e scende quando serve."""
        if not c.in_veicolo or not self.fort.get("usa_veicoli", True):
            self.in_auto_da = None
            return None
        if self.in_auto_da is None:
            self.in_auto_da = t
            self.log("IA: sono in macchina, guido")
        troppo = t - self.in_auto_da > float(self.fort.get("guida_secondi_massimi", 25) or 25)
        if troppo or vis.nemici or c.cassa != "none":
            motivo = "c'e' un nemico" if vis.nemici else ("vedo una cassa" if c.cassa != "none" else "basta guidare")
            self.log("IA: scendo dalla macchina (%s)" % motivo)
            self._cammina()
            if self.mani.esiste("interagisci"):
                self.mani.premi("interagisci", 0.1)
            self.in_auto_da = None
            self.niente_auto_fino = t + 60.0
            return "scendo dalla macchina"
        sinistra = destra = False
        if c.tempesta and c.direzione in ("left", "right"):
            sinistra, destra = c.direzione == "left", c.direzione == "right"
        elif c.muro:
            sinistra = True
        self._cammina(avanti=True, sinistra=sinistra, destra=destra)    # con un muro davanti sterza
        return "guido"

    def _tempesta(self, img, t):
        """Nella tempesta lo schermo diventa viola: giro su me stesso guardando 8 direzioni,
        mi giro verso quella con meno viola e corro."""
        if img is None or not self.fort.get("tempesta_dal_colore", True):
            return None
        if t < self.scappo_fino:
            self._cammina(avanti=True, corri=True)
            if abs(self.pitch) > 3:
                self._muovi(0, -self.pitch * 0.15, fluido=True)
            self._controlla_blocco(img, t)
            return "corro via dalla tempesta"
        if t < self.prossimo_controllo_tempesta:
            return None
        self.prossimo_controllo_tempesta = t + 1.0
        quanto = viola(img)
        if quanto < float(self.fort.get("tempesta_soglia_viola", 0.35) or 0.35):
            return None
        self.log("Sono nella tempesta (%.0f%% viola): cerco la zona sicura" % (quanto * 100))
        self._cammina()
        direzioni = 8
        migliore, minimo = 0, quanto
        for i in range(1, direzioni):
            self.esecutore.gira(360.0 / direzioni, durata=0.15)
            self.esecutore.dormi(0.3)
            q = viola(self.esecutore.foto_fresca())
            if q < minimo:
                migliore, minimo = i, q
        self.esecutore.gira(360.0 / direzioni, durata=0.15)      # di nuovo dove ero partito
        if migliore:
            self.esecutore.gira(migliore * 360.0 / direzioni)
        self.scappo_fino = t + float(self.fort.get("corsa_fuori_tempesta", 10) or 10)
        self.giro_fino = 0.0
        self.prossimo_guardarsi = t + 15.0
        self.mini_prec = None
        return "scappo dalla tempesta"

    def _solo_nemici_vicini(self):
        """Con l'obiettivo delle casse (o sopravvivere, o lo stile Tranquillo) i nemici lontani si ignorano."""
        if self.stile.solo_vicini or self.obiettivo.tipo == "sopravvivere":
            return True
        return self.obiettivo.pensa_alle_casse(self.statistiche.get("casse_partita", 0))

    def _dopo_pausa(self):
        """Dopo un'azione lunga (istruzione, misura): riparto pulito."""
        self.mani.rilascia_tutto()
        adesso = time.monotonic()
        self.pitch = 0.0
        self.mini_prec = None
        self.stato["fermo_da"] = 0.0
        self.ultimo_mosso = adesso
        self.t_prec = adesso
        self.mosso_px = (0.0, 0.0)
        self.bersaglio = None
        self.errore_prec = None

    # ------------------------------------------------------------------ combattimento
    def _punto_mira(self, b, vis):
        """Dove mirare su un nemico: verso la testa (se l'IA vede la testa, proprio li')."""
        for testa in vis.oggetti.get("testa", []):
            if b.contiene(testa.cx, testa.cy):
                return testa.cx, testa.cy
        if b.fonte == "universale":
            alt = float(self.mira.get("altezza_mira_universale", 0.15))
        else:
            alt = float(self.mira.get("altezza_mira", 0.2))
        return b.cx, b.y + alt * b.h + float(self.mira.get("spostamento_y", 0) or 0)

    def _scegli_bersaglio(self, nemici, vis, mx, my):
        """Restituisce (bersaglio, nuovo?). Resta sul bersaglio di prima se c'e' ancora."""
        if self.bersaglio is not None:
            # dove dovrebbe essere ora il bersaglio di prima: spostato dal mio movimento
            # (se e' una cosa del mondo) oppure fermo nello stesso punto (se e' attaccato allo schermo)
            px = self.bersaglio[0] - self.mosso_px[0]
            py = self.bersaglio[1] - self.mosso_px[1]
            vicino = None
            dist_min = 0.12 * vis.larghezza
            for b in nemici:
                ax, ay = self._punto_mira(b, vis)
                d = min(math.hypot(ax - px, ay - py), math.hypot(ax - self.bersaglio[0], ay - self.bersaglio[1]))
                if d < dist_min:
                    dist_min, vicino = d, b
            if vicino is not None:
                return vicino, False

        # nuovo bersaglio: il piu' vicino al mirino (quelli grandi = vicini = pericolosi contano di piu')
        def punteggio(b):
            ax, ay = self._punto_mira(b, vis)
            return math.hypot(ax - mx, ay - my) / (1.0 + 4.0 * b.h / vis.altezza) / max(0.3, b.punteggio)
        return min(nemici, key=punteggio), True

    def _combatti(self, vis, t, dt):
        mx, my = self._mirino(vis)
        memoria = float(self.comb.get("memoria_secondi", 0.35))
        if not vis.nemici:
            if self.sparando_da is not None and t - self.ultimo_visto_nemico > memoria:
                self._spara(False)
                self.sparando_da = None
            if t - self.ultimo_visto_nemico > memoria:
                if self.bersaglio is not None:
                    self.bersaglio = None
                    self.errore_prec = None
                    self._cammina()
                    if self.mira.get("mira_col_tasto_destro") and self.mani.esiste("mira"):
                        self.mani.su("mira")
                return None
            return "cerco il nemico perso"

        b, nuovo = self._scegli_bersaglio(vis.nemici, vis, mx, my)
        ax, ay = self._punto_mira(b, vis)

        # il bersaglio si muove insieme alla visuale? Allora e' il mio personaggio o un'icona: lo ignoro
        if self.apprendimento is not None:
            mosso = math.hypot(self.mosso_px[0], self.mosso_px[1])
            if self.apprendimento.controlla_bersaglio(b, (ax - mx, ay - my), mosso, nuovo,
                                                      vis.larghezza, vis.altezza, (mx, my)):
                self._spara(False)
                self.sparando_da = None
                self.bersaglio = None
                self.errore_prec = None
                return "imparo cosa ignorare"

        if t - self.ultimo_visto_nemico > 2.0:
            self.statistiche["combattimenti"] = self.statistiche.get("combattimenti", 0) + 1
        self.ultimo_visto_nemico = t
        self.ultimo_mosso = t
        self.stato["fermo_da"] = 0.0
        self.inseguo_da = None
        self.giro_fino = 0.0

        # velocita' del nemico sullo schermo (senza il mio movimento) -> anticipo
        if self.bersaglio is not None and not nuovo:
            vx = (ax - self.bersaglio[0] + self.mosso_px[0]) / dt
            vy = (ay - self.bersaglio[1] + self.mosso_px[1]) / dt
            lim = vis.larghezza * 2.0
            vx = max(-lim, min(lim, vx))
            vy = max(-lim, min(lim, vy))
            self.velocita = (0.5 * self.velocita[0] + 0.5 * vx, 0.5 * self.velocita[1] + 0.5 * vy)
        else:
            self.velocita = (0.0, 0.0)
            self.errore_prec = None
        if self.bersaglio is None:
            # nemico appena visto: con lo stile Normale/Tranquillo ci mette un attimo a reagire
            self.reazione_fino = t + self.stile.reazione
            # in mano un'arma, non il piccone (se ce l'ha)
            if self.comb.get("prendi_arma", True) and t >= self.prossimo_cambio_arma and \
                    self.mani.esiste("arma_1"):
                self.prossimo_cambio_arma = t + 8.0
                self.mani.premi("arma_1")
        self.bersaglio = (ax, ay)
        self.mosso_px = (0.0, 0.0)
        anticipo = float(self.mira.get("anticipo", 0.05) or 0.0)
        tx = ax + self.velocita[0] * anticipo
        ty = ay + self.velocita[1] * anticipo
        if self.stile.errore > 0:
            # stile Normale/Tranquillo: la mira non e' perfetta e ogni tanto il colpo va fuori
            if t >= self.prossimo_errore:
                self.prossimo_errore = t + random.uniform(0.3, 0.8)
                e = self.stile.errore
                self.errore_mira = (random.uniform(-e, e), random.uniform(-e, e) * 0.5)
            tx += self.errore_mira[0] * b.w
            ty += self.errore_mira[1] * b.h

        # impara la forza giusta della mira (se va oltre o e' lenta): solo con la mira "vera"
        ex, ey = tx - mx, ty - my
        if self.apprendimento is not None and self.errore_prec is not None and self.stile.mira_perfetta:
            self.apprendimento.osserva_mira(self.errore_prec, (ex, ey))
        self.errore_prec = (ex, ey)

        # muovi la visuale verso il bersaglio (lo stile Normale e' piu' lento)
        forza = self.forza * self.stile.forza
        self._muovi(ex / self.ppp * forza, ey / self.ppp * forza, fluido=True)

        # spara se il mirino e' sopra il nemico
        tol_min = float(self.mira.get("tolleranza_minima_px", 4))
        tol = float(self.mira.get("tolleranza", 0.35))
        tol_x = max(tol_min, b.w * tol)
        tol_y = max(tol_min, b.h * tol * 0.5)
        if self.sparando_da is not None:      # gia' sparo: un po' piu' di margine
            tol_x *= 1.5
            tol_y *= 1.5
        allineato = abs(ex) <= tol_x and abs(ey) <= tol_y and t >= self.reazione_fino
        if self.mira.get("mira_col_tasto_destro") and self.mani.esiste("mira"):
            self.mani.giu("mira")
        if allineato:
            if self.sparando_da is None:
                self.sparando_da = t
                self.statistiche["nemici_colpiti"] = self.statistiche.get("nemici_colpiti", 0) + 1
                self.raffica_fine = t + float(self.comb.get("raffica_secondi", 0.25))
            if str(self.comb.get("spara", "tieni")).lower() == "raffica":
                pausa = float(self.comb.get("pausa_raffica_secondi", 0.12))
                if t < self.raffica_fine:
                    self._spara(True)
                elif t < self.raffica_fine + pausa:
                    self._spara(False)
                else:
                    self.raffica_fine = t + float(self.comb.get("raffica_secondi", 0.25))
                    self._spara(True)
            else:
                self._spara(True)
            rinculo = float(self.mira.get("rinculo", 0) or 0)
            if rinculo:
                self._muovi(0, rinculo * dt)
        else:
            self._spara(False)
            self.sparando_da = None

        # movimento: schiva a destra/sinistra, insegui se e' lontano
        distanza = float(self.comb.get("distanza_insegui", 0.08))
        if self.obiettivo.tipo == "nemici":
            distanza = max(distanza, 0.3)
        lontano = b.h < distanza * vis.altezza
        avanti = (bool(self.comb.get("insegui", True)) and lontano and self.obiettivo.tipo != "sopravvivere"
                  and self.stile.insegui)
        sinistra = destra = False
        if self.comb.get("schiva", True):
            if t >= self.prossima_schivata:
                self.lato_schivata = "destra" if self.lato_schivata == "sinistra" else "sinistra"
                self.prossima_schivata = t + random.uniform(0.35, 0.9)
            sinistra = self.lato_schivata == "sinistra"
            destra = not sinistra
        self._cammina(avanti=avanti, sinistra=sinistra, destra=destra)
        if self.comb.get("salta_ogni_tanto") and random.random() < 0.01:
            self.mani.premi("salta")

        # se perdo tanta vita in fretta: muro!
        persa = self._vita_persa()
        soglia = float(self.comb.get("vita_persa_per_costruire", 15) or 0)
        if self.fort.get("zero_costruzioni", True):
            soglia = 0.0                      # in "Zero Costruzioni" non si costruisce: niente muri
        if self.obiettivo.tipo == "sopravvivere" and soglia > 0:
            soglia = min(soglia, 10.0)
        if soglia > 0 and persa >= soglia and t >= self.prossimo_muro:
            self.prossimo_muro = t + float(self.comb.get("attesa_tra_muri", 3.0))
            self._cammina()
            if self._esegui_macro(self.comb.get("macro_quando_colpito", "muro"), "Mi colpiscono (-%.0f vita)" % persa):
                self.storia_vita = []
                self.sparando_da = None
                self.bersaglio = None
                self.errore_prec = None
                return "costruisco"
        return "combatto (%s)" % ("sparo" if allineato else "miro")

    def _vita_persa(self):
        if len(self.storia_vita) < 2:
            return 0.0
        massimo = max(v for _, v in self.storia_vita)
        return massimo - self.storia_vita[-1][1]

    # ------------------------------------------------------------------ cura
    def _cura(self, vis, t):
        if vis.vita is None:
            return None
        sotto = float(self.vita_cfg.get("cura_sotto", 0) or 0)
        if self.obiettivo.tipo == "sopravvivere" and sotto > 0:
            sotto = max(sotto, 60.0)
        if vis.vita >= sotto or t < self.prossima_cura or t - self.ultimo_visto_nemico < 2.0:
            return None
        self.prossima_cura = t + 10.0
        self._cammina()
        if self._esegui_macro(self.vita_cfg.get("macro_cura", "cura"), "Poca vita (%.0f%%)" % vis.vita):
            return "mi curo"
        return None

    # ------------------------------------------------------------------ casse e armi
    def _raccogli(self, vis, t, img):
        if t < self.ignora_raccolta_fino:
            return None
        candidati = []
        for tipo, attivo in (("cassa", "casse"), ("materiali", "casse_materiali"), ("arma", "armi")):
            if self.racc.get(attivo, True):
                candidati += [(b, tipo) for b in vis.oggetti.get(tipo, [])]
        interazione = self.occhi.controlla_interazione(vis) if self.racc.get("immagine_interazione") else False
        if not candidati and not interazione:
            self.inseguo_da = None
            return None
        mx, my = self._mirino(vis)
        W, H = vis.larghezza, vis.altezza

        if interazione and not candidati:
            return self._interagisci("cassa", t, None, img)

        def costo(c):
            b, tipo = c
            d = math.hypot(b.cx - mx, b.fondo - H) / max(W, H)        # vicino ai miei piedi = vicino
            d /= (1.0 + 3.0 * b.h / H)
            valore = float(self.racc.get(VALORE_RACCOLTA[tipo], 1.0) or 1.0)
            return d / max(0.05, valore)
        b, tipo = min(candidati, key=costo)

        if self.inseguo_da is None:
            self.inseguo_da = t
        elif t - self.inseguo_da > float(self.racc.get("tempo_massimo_avvicinamento", 10.0)):
            # non ci arrivo: lascio perdere per un po' e giro da un'altra parte
            self.log("Non riesco a raggiungere %s: lascio perdere" % tipo)
            self.statistiche["lasciate_perdere"] = self.statistiche.get("lasciate_perdere", 0) + 1
            self.inseguo_da = None
            self.ignora_raccolta_fino = t + 6.0
            self._cammina()
            self.esecutore.gira(random.choice((-1, 1)) * random.uniform(120, 200))
            return "lascio perdere"

        ex = b.cx - mx
        ey = b.cy - my
        forza = float(self.racc.get("forza_giro", 0.35))
        self._muovi(ex / self.ppp * forza, ey / self.ppp * forza * 0.5, fluido=True)

        vicino = (interazione or b.h >= float(self.racc.get("vicino_altezza", 0.12)) * H
                  or b.fondo >= float(self.racc.get("vicino_fondo", 0.85)) * H)
        if vicino and abs(ex) < 0.18 * W:
            return self._interagisci(tipo, t, b, img)
        allineato = abs(ex) < 0.12 * W
        lontano = b.h < 0.05 * H
        corri = bool(self.espl.get("corri", True)) and lontano and allineato
        self._cammina(avanti=abs(ex) < 0.25 * W, corri=corri)
        self._controlla_blocco(img, t, sto_camminando=abs(ex) < 0.25 * W)
        return "vado verso %s" % tipo

    def _interagisci(self, tipo, t, box, img):
        """Apre la cassa / raccoglie l'arma, poi controlla se ha funzionato davvero."""
        self._cammina()
        if not self.mani.esiste("interagisci"):
            return None
        prima = None
        zona = None
        if box is not None and img is not None:
            zona = (box.x - 0.3 * box.w, box.y - 0.3 * box.h, 1.6 * box.w, 1.6 * box.h)
            prima = self.occhi.pixel_colore(img, tipo, *zona)
        if tipo in ("cassa", "materiali"):
            durata = float(self.racc.get("tempo_apertura_cassa", 1.2))
            self.statistiche["casse_tentate"] = self.statistiche.get("casse_tentate", 0) + 1
        else:
            durata = float(self.racc.get("tempo_raccolta_arma", 0.1))
        self.mani.giu("interagisci")
        try:
            self.esecutore.dormi(max(0.06, durata))
        finally:
            self.mani.su("interagisci")
        riuscito = True
        if prima:      # c'era il colore della cassa: e' sparito? allora l'ho aperta davvero
            try:
                self.esecutore.dormi(0.25)
                dopo = self.occhi.pixel_colore(self.esecutore.foto_fresca(), tipo, *zona)
                riuscito = dopo is None or dopo <= 0.5 * prima
            except Exception:
                riuscito = True
        chiave = {"cassa": "casse", "materiali": "materiali", "arma": "armi"}[tipo]
        nome = {"cassa": "Cassa armi", "materiali": "Cassa materiali", "arma": "Arma"}[tipo]
        if riuscito:
            self.statistiche[chiave] = self.statistiche.get(chiave, 0) + 1
            if tipo in ("cassa", "materiali"):
                self.statistiche["casse_partita"] = self.statistiche.get("casse_partita", 0) + 1
                if self.obiettivo.tipo == "casse_n":
                    n = self.statistiche["casse_partita"]
                    self.log("Casse in questa partita: %d/%d" % (n, self.obiettivo.casse))
                    if n == self.obiettivo.casse:
                        self.log("Obiettivo raggiunto: %d casse! Ora gioco per vincere." % n)
            self.log("%s presa! (casse armi %d, casse materiali %d, armi %d)" % (
                nome, self.statistiche.get("casse", 0), self.statistiche.get("materiali", 0),
                self.statistiche.get("armi", 0)))
            self.ignora_raccolta_fino = t + 0.8
            self.fallite_di_fila = 0
            if tipo in ("cassa", "materiali") and self.racc.get("raccogli_dopo_cassa", True):
                self._raccogli_bottino()
        else:
            self.statistiche["casse_fallite"] = self.statistiche.get("casse_fallite", 0) + 1
            self.fallite_di_fila += 1
            if self.fallite_di_fila >= int(self.racc.get("tentativi_per_cassa", 2) or 2):
                # non si apre mai: non e' una cassa vera (o non ci arrivo). La lascio stare e giro
                self.log("%s: non si apre, forse non e' vera. La lascio stare e vado altrove" % nome)
                self.fallite_di_fila = 0
                if box is not None:
                    W, H = self.occhi_dimensioni(img)
                    margine = 0.03
                    zona = [box.x / W - margine, box.y / H - margine, box.w / W + 2 * margine,
                            box.h / H + 2 * margine]
                    self.occhi.zone_temporanee.append((zona, time.monotonic() + 3.0))
                self.ignora_raccolta_fino = t + 2.0
                self.inseguo_da = None
                self._cammina()
                self.esecutore.gira(random.choice((-1, 1)) * random.uniform(90, 150))
                return "lascio stare %s" % tipo
            self.log("%s: non si e' aperta, mi avvicino di piu'" % nome)
            self._cammina(avanti=True)
            self.esecutore.dormi(0.25)
            self._cammina()
        self.inseguo_da = None
        return "apro %s" % tipo

    def _raccogli_bottino(self):
        """Come in Fortnite: la cassa butta le armi per terra davanti. Guardo un po' in giu',
        premo 'interagisci' qualche volta facendo un passettino, poi prendo l'arma in mano."""
        giu = self.passi_per_giro * 15.0 / 360.0
        self._muovi(0, giu)
        for _ in range(int(self.racc.get("raccogli_volte", 4) or 4)):
            self.mani.premi("interagisci", 0.08)
            self._cammina(avanti=True)
            self.esecutore.dormi(0.15)
            self._cammina()
            self.esecutore.dormi(0.1)
        self._muovi(0, -giu)
        if self.mani.esiste("arma_1"):
            self.mani.premi("arma_1")

    @staticmethod
    def occhi_dimensioni(img):
        if img is None:
            return 1.0, 1.0
        return float(img.shape[1]), float(img.shape[0])

    # ------------------------------------------------------------------ esplorazione
    def _controlla_blocco(self, img, t, sto_camminando=True):
        """Se cammino ma il CENTRO dello schermo (quello che ho davanti) non cambia,
        sono bloccato contro qualcosa."""
        if img is None or t - self.t_mini < 0.25:
            return False
        self.t_mini = t
        H, W = img.shape[:2]
        centro = img[int(0.3 * H):int(0.8 * H), int(0.25 * W):int(0.75 * W)]
        mini = cv2.resize(cv2.cvtColor(centro, cv2.COLOR_BGR2GRAY), (48, 28), interpolation=cv2.INTER_AREA)
        if not sto_camminando:
            self.ultimo_mosso = t
            self.fermo_conta = 0
            self.stato["fermo_da"] = 0.0
            self.mini_prec = mini
            return False
        if self.mini_prec is not None:
            diff = float(np.mean(cv2.absdiff(mini, self.mini_prec)))
            if diff >= float(self.espl.get("sensibilita_blocco", 2.5)):
                self.ultimo_mosso = t
                self.fermo_conta = 0
            else:
                self.fermo_conta += 1
        self.mini_prec = mini
        self.stato["fermo_da"] = t - self.ultimo_mosso
        if self.fermo_conta < int(self.espl.get("controlli_blocco", 3) or 3):
            return False
        # bloccato: salto, faccio un passo indietro e giro. Se mi ero gia' bloccato da poco,
        # giro dall'altra parte e di piu' (cosi' non torno contro lo stesso muro)
        di_nuovo = t - self.ultimo_sblocco < 4.0
        self.ultimo_sblocco = t
        self.statistiche["bloccato"] = self.statistiche.get("bloccato", 0) + 1
        self.fermo_conta = 0
        if not di_nuovo and self.fort.get("piccona_i_muri", True) and self.mani.esiste("piccone"):
            # come un giocatore di Fortnite: salto in avanti (ci si arrampica sugli ostacoli bassi);
            # se non passo, il muro lo sfondo col piccone (e prendo materiali). Poi riprendo l'arma
            self.log("Sono bloccato: salto e sfondo col piccone")
            self._cammina(avanti=True)
            if self.mani.esiste("salta"):
                self.mani.premi("salta")
            self.esecutore.dormi(0.35)
            self.mani.premi("piccone")
            self.mani.imposta("spara", True)
            try:
                self.esecutore.dormi(float(self.fort.get("piccona_secondi", 1.5) or 1.5))
            finally:
                self.mani.imposta("spara", False)
                self._cammina()
            if self.mani.esiste("arma_1"):
                self.mani.premi("arma_1")
            self.mini_prec = None
            return True
        self.verso_sblocco = -self.verso_sblocco if di_nuovo else random.choice((-1, 1))
        gradi = random.uniform(150, 210) if di_nuovo else random.uniform(80, 140)
        self.log("Sono ancora bloccato: salto, torno indietro e giro" +
                 (" dall'altra parte" if di_nuovo else ""))
        if self.mani.esiste("salta"):
            self.mani.premi("salta")
        self._cammina(indietro=True)
        self.esecutore.dormi(0.4)
        self._cammina()
        self.esecutore.gira(self.verso_sblocco * gradi)
        self.mini_prec = None
        return True

    def _esplora(self, vis, t, dt, img):
        # giro intorno a se', lento e fluido, cosi' guarda in ogni direzione (cerca casse e nemici)
        velocita_giro = float(self.espl.get("velocita_giro_gradi", 120) or 120)
        if t < self.giro_fino:
            self._cammina(avanti=True)            # si guarda intorno senza fermarsi
            self._muovi(self.passi_per_giro * velocita_giro / 360.0 * dt, 0, fluido=True)
            return "mi guardo intorno"
        ogni = float(self.espl.get("guarda_intorno_ogni", 12) or 0)
        if ogni > 0 and t >= self.prossimo_guardarsi:
            self.prossimo_guardarsi = t + ogni
            self.giro_fino = t + 360.0 / velocita_giro
            return "mi guardo intorno"

        # corre con una leggera curva che cambia ogni tanto (cosi' scopre posti nuovi)
        if t >= self.prossima_deriva:
            self.prossima_deriva = t + random.uniform(1.5, 4.0)
            self.deriva = random.uniform(-1.0, 1.0) * self.passi_per_giro / 360.0 * 15.0   # fino a 15 gradi/s
        dy = 0.0
        if self.espl.get("rimetti_visuale_dritta", True) and abs(self.pitch) > 3:
            dy = -self.pitch * 0.15
        self._muovi(self.deriva * dt, dy, fluido=True)
        self._cammina(avanti=True, corri=bool(self.espl.get("corri", True)))
        self._controlla_blocco(img, t)
        return "esploro"
