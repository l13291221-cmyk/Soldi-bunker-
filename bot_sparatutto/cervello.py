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

from obiettivo import Obiettivo
from stile import STILI

OBIETTIVO = ("vincere la partita (restare vivo ed eliminare i nemici) e aprire piu' casse possibili "
             "(casse delle armi e casse dei materiali)")

# quanto vale ogni cosa da raccogliere (piu' alto = ci va prima): nome dell'impostazione in "raccolta"
VALORE_RACCOLTA = {"cassa": "priorita_casse", "materiali": "priorita_materiali", "arma": "priorita_armi"}


def _cfg(cfg, sezione):
    return cfg.get(sezione, {}) or {}


class Cervello:
    def __init__(self, cfg, mani, occhi, esecutore, istruzioni, log=print, apprendimento=None, schermo=None,
                 obiettivo=None, stile=None):
        self.cfg = cfg
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
        self.reazione_fino = 0.0          # stile: prima di questo momento non spara al nemico appena visto
        self.errore_mira = (0.0, 0.0)     # stile: di quanto sbaglia la mira adesso
        self.prossimo_errore = 0.0
        self.avvisato_casse = False
        # raccolta
        self.inseguo_da = None
        self.ignora_raccolta_fino = 0.0
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
        else:
            self.statistiche["casse_fallite"] = self.statistiche.get("casse_fallite", 0) + 1
            self.log("%s: non si e' aperta, mi avvicino di piu'" % nome)
            self._cammina(avanti=True)
            self.esecutore.dormi(0.25)
            self._cammina()
        self.inseguo_da = None
        return "apro %s" % tipo

    # ------------------------------------------------------------------ esplorazione
    def _controlla_blocco(self, img, t, sto_camminando=True):
        """Se cammino ma lo schermo non cambia, sono bloccato contro qualcosa."""
        if img is None or t - self.t_mini < 0.4:
            return False
        self.t_mini = t
        mini = cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (64, 36), interpolation=cv2.INTER_AREA)
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
        if self.fermo_conta < 4:
            return False
        # bloccato: salto, faccio un passo indietro e giro
        self.log("Sono bloccato: salto e giro")
        self.statistiche["bloccato"] = self.statistiche.get("bloccato", 0) + 1
        self.fermo_conta = 0
        if self.mani.esiste("salta"):
            self.mani.premi("salta")
        self._cammina(indietro=True)
        self.esecutore.dormi(0.3)
        self._cammina()
        self.esecutore.gira(random.choice((-1, 1)) * random.uniform(70, 160))
        self.mini_prec = None
        return True

    def _esplora(self, vis, t, dt, img):
        # giro intorno a se', lento e fluido, cosi' guarda in ogni direzione (cerca casse e nemici)
        velocita_giro = float(self.espl.get("velocita_giro_gradi", 120) or 120)
        if t < self.giro_fino:
            self._cammina()
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
