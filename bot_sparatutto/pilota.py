"""
pilota.py - IL CERVELLO NUOVO (rifatto da zero, novembre 2026; sistemato dopo la partita registrata).

Fatto come i bot dei giochi fatti con Unreal Engine (Fortnite compreso): una LAVAGNA con quello
che il bot sa adesso e un ALBERO DI COMPORTAMENTI: un elenco di "rami" in ordine di importanza.
A ogni fotogramma si prende il PRIMO ramo che serve e si fa SOLO quello.

COSA HA INSEGNATO LA PARTITA REGISTRATA: le IA gratis finiscono le domande o rispondono dopo un
minuto, e il bot restava fermo nella tempesta ad aspettarle. Adesso le cose IMPORTANTI le legge
da solo dallo schermo, senza IA, in pochi millesimi di secondo (hud.py):
  - la BUSSOLA (il numero in alto): sa sempre dove guarda (0 nord, 90 est, 180 sud, 270 ovest)
    e misura da solo quanto si gira col mouse (sensibilita');
  - la MINIMAPPA: dov'e' la tempesta (viola), il mare (blu) e la terra -> esce dalla tempesta,
    torna a terra, non va verso il mare, salta dal bus quando sotto c'e' l'isola;
  - la BARRA DELLE ARMI: se non c'e' ma la bussola si', e' sul bus;
  - i COMPAGNI sulla bussola (i triangolini bianchi in alto): sa in che direzione sono.
L'IA serve per le cose "da capire" (casse, menu, scritte) e le sue risposte diventano DIREZIONI
DELLA BUSSOLA (es. "cassa a 250 gradi"): anche se arriva tardi, dopo che mi sono girato, so
ancora dove andare. La mappa grande (M) la guarda l'IA mentre il bot continua a giocare.

L'ORDINE (dal piu' importante):
  1. le tue istruzioni (istruzioni.txt) e il pulsante giallo "Gioca di nuovo"
  2. schermi strani: PS5 "Chi sta usando...?", PS Remote Play scollegato, desktop
  3. fasi: menu / eliminato / bus (salta sopra la terra) / caduta (verso la terra o il compagno)
  4. PERICOLO: tempesta o acqua -> fuori, con la minimappa, SENZA FERMARSI MAI
  5. NEMICO: arma in mano (vicino = pompa, slot 2; se no slot 1), mira, spara
  6. SCRITTA sullo schermo: Apri / Raccogli / porta / zipline -> E
  7. ARMA in mano (sempre lo slot 1, la mitra) e CURE
  8. ogni tanto: misura la sensibilita' con la bussola, guarda la mappa grande (con l'IA)
  9. BOTTINO: la cassa vista dall'IA -> ci va, la apre (E), raccoglie, poi torna dal compagno
 10. SEGUO IL COMPAGNO (uno a caso, come i bot che si assoldano in Fortnite)
 11. VIAGGIO: lontano dalla tempesta, verso la zona sicura, mai verso il mare

Il cervello vecchio (cervello.py) resta: in impostazioni.yaml -> fortnite -> cervello: vecchio
"""

import math
import random
import threading
import time
from collections import Counter

import cv2
import numpy as np

import hud
import impostazioni
from cervello import acqua, angolo_medio, mappa_con_bussola, trova_pulsante_giallo, viola
from obiettivo import Obiettivo
from stile import STILI

NOMI_COSE = {"chest": "una cassa", "weapon": "un'arma per terra", "ammo_box": "una cassa di munizioni",
             "building": "una casa (dentro ci sono le casse)"}
LATO_GRADI = {"left": -75.0, "right": 75.0, "behind": 180.0}


def _cfg(cfg, nome):
    return cfg.get(nome, {}) or {}


def avvolgi(gradi):
    """Un angolo tra -180 e 180."""
    return (gradi + 180.0) % 360.0 - 180.0


class Lavagna:
    """Quello che il bot sa adesso (come la Blackboard dei bot di Unreal Engine)."""

    def __init__(self):
        self.consiglio = None        # l'ultima risposta dell'IA ancora valida
        self.nuovo = False           # e' una risposta nuova (da usare una volta sola)?
        self.nemici = []             # nemici visti dagli occhi veloci (senza il mio personaggio)
        self.in_tempesta = False
        self.in_acqua = False
        self.guardo = None           # gradi della bussola dove guardo (o None)
        # letti dallo schermo senza IA (hud.py)
        self.bussola_hud = None      # il numero della bussola letto adesso (o None)
        self.mini = hud.Minimappa(None)
        self.barra = False           # si vede la barra delle armi
        self.bus = False             # bussola si', barra delle armi no: sono sul bus
        self.compagni = []           # triangolini dei compagni sulla bussola (gradi rispetto a dove guardo)
        self.compagni_bordi = []     # frecce dei compagni ai bordi / dietro (gradi rispetto a dove guardo)
        self.compagni_mini = []      # frecce gialle sulla minimappa: (gradi della bussola, distanza 0-1)
        self.scritta = False         # c'e' la scritta "E Apri" / "Raccogli" / ... a destra del mirino
        self.spettatore = False      # in alto c'e' "SPETTATORE": sono stato eliminato, guardo un compagno
        self.vita = None             # vita e scudo letti dalle barre in basso a sinistra (0-100)
        self.scudo = None


class Pilota:
    def __init__(self, cfg, mani, occhi, esecutore, istruzioni, log=print, apprendimento=None, schermo=None,
                 obiettivo=None, stile=None, ia=None):
        self.cfg = cfg
        self.mani = mani
        self.occhi = occhi
        self.esecutore = esecutore
        self.istruzioni = istruzioni
        self.log = log
        self.apprendimento = apprendimento
        self.schermo = schermo if schermo is not None else getattr(esecutore, "schermo", None)
        self.obiettivo = obiettivo if obiettivo is not None else Obiettivo()
        self.stile = stile if stile is not None else STILI["pro"]
        self.ia = ia
        self.pc = None
        self.fort = _cfg(cfg, "fortnite")
        self.mira = _cfg(cfg, "mira")
        self.comb = _cfg(cfg, "combattimento")
        self.racc = _cfg(cfg, "raccolta")
        self.espl = _cfg(cfg, "esplorazione")
        self.regole_cfg = _cfg(cfg, "regole")
        self.statistiche = esecutore.statistiche
        adesso = time.monotonic()
        self.stato = {"ultimo_nemico": adesso, "fermo_da": 0.0, "casse": 0}
        self.lavagna = Lavagna()
        self.t_prec = adesso
        self.dt_medio = 1.0 / 30
        self.bersaglio = None
        self.mosso_px = (0.0, 0.0)
        # tempi e memorie (ognuno usato da un ramo solo)
        self.prossimo_controllo_regole = 0.0
        self.ultimo_numero = 0
        self.in_partita = False
        self.ultima_partita_contata = -1000.0
        self.ultima_fase = None
        self.bus_da = None
        self.salto_da = None              # quando sono saltato dal bus (poi cado per un po')
        self.morto_da = None
        self.prossimo_salto = 0.0
        self.prossima_correzione = 0.0
        self.ultimo_schermo = 0
        self.volte_chi = 0
        self.prossimo_avviso = 0.0
        self.prossimo_davanti = 0.0
        self.giallo_visto = None
        self.giallo_tentativo = None
        self.giallo_indice = 0
        self.prossimo_giallo = 0.0
        self.ultimo_menu = 0
        # bussola e schermo letti senza IA
        self.prossima_bussola = 0.0
        self.prossima_minimappa = 0.0
        self.lettura_prec = None          # (t, gradi, passi) dell'ultima lettura (anche non accettata)
        self.ultima_accettata = None      # (t, gradi, passi) dell'ultima lettura accettata
        self.ultima_bussola_hud = -1e9    # quando ho preso per buona una lettura della bussola
        self.ultima_bussola_letta = -1e9  # quando ho visto il numero della bussola (anche se non lo uso)
        self.in_aria_t = -1e9             # quando ho visto la scritta col tasto SPAZIO (bus / caduta)
        self.stime_giro = []              # quanti passi del mouse per un giro, misurati con la bussola
        self.bus_conta = 0
        self.storia_guardo = []           # (t, gradi): dove guardavo (per le risposte dell'IA in ritardo)
        # navigazione
        self.rotta = None                 # gradi della bussola dove voglio andare
        self.rotta_ia = None              # la zona sicura vista dall'IA sulla mappa grande
        self.rotta_ia_t = -1e9
        self.bussola_rif = None           # (gradi letti, passi del mouse in quel momento)
        self.storia_passi = []
        self.prossima_mappa = 0.0
        self.prossima_mappa_periodica = adesso + 30.0
        self.filo_mappa = None
        self.risposte_mappa = None        # (risposte delle IA, quando ho fatto la foto)
        self.fuga_fino = 0.0              # dopo la tempesta/l'acqua corro ancora un po' sulla rotta
        self.prossimo_avviso_fuga = 0.0
        self.prossima_ricerca_terra = 0.0
        self.prossima_svolta = 0.0
        self.deviazione_fino = 0.0        # aggiro un ostacolo: per un po' non torno sulla rotta
        self.acqua_da = None
        self.nuoto_da = None
        self.calibra_da = None
        self.ultima_calibrazione = -1e9
        self.bussola_sbagliata = 0
        # mete date dall'IA, in gradi della bussola
        self.meta_compagno = None         # (gradi, metri o None, quando era la foto)
        self.meta_bottino = None          # (gradi, cosa, y sullo schermo, quando era la foto)
        self.bottino_usato = None
        self.compagno_hud = None          # il compagno che seguo (gradi), visto sullo schermo
        self.compagno_hud_t = -1e9
        self.compagno_dist = None         # quanto e' lontano sulla minimappa (0 = attaccato, 1 = al bordo)
        self.compagno_dist_t = -1e9
        self.compagno_fonte = ""
        self.salvo_memo = None            # (gradi, quando): l'ultima direzione "lontano dalla tempesta"
        # movimento
        self.cammino_fino = 0.0           # cammino avanti fino a (verso la cassa / il compagno)
        self.cammino_cosa = ""
        self.apri_all_arrivo = False
        self.fermo_fino = 0.0             # sto fermo accanto al compagno fino a
        self.t_mini = 0.0
        self.mini_prec = None
        self.fermo_conta = 0
        self.ultimo_mosso = adesso
        self.ultimo_sblocco = -100.0
        self.verso_sblocco = 1
        self.pitch = 0.0
        # combattimento
        self.mirando_da = None
        self.sparando = False
        self.prossima_schivata = 0.0
        self.lato = "sinistra"
        self.prossimo_cambio_arma = 0.0
        self.arma_vicina = None
        self.tentativi_arma = 0
        self.prossima_cura = 0.0
        self.prossima_scritta = 0.0
        self.prossimo_slot = adesso + 3.0
        # come le guardie di Fortnite: il "sospetto" si riempie prima di attaccare; poi, se il
        # nemico sparisce, lo cerco per un po' dove l'ho visto
        self.sospetto = 0.0
        self.t_sospetto = adesso
        self.nemico_gradi = None          # (gradi della bussola, quando) dell'ultimo nemico
        self.al_guinzaglio_fermo = False  # sono vicino al compagno e lo aspetto
        self.cure_fallite = 0
        # casse viste dagli occhi (luce dorata): ci vado incontro e la metto nel mirino
        self.cassa_conta = 0              # quante volte di fila ho visto una cassa
        self.cassa_da = None              # da quando sto andando verso una cassa
        self.cassa_ultima = None          # (x, y) sullo schermo (0-1) e quando l'ho vista
        self.casse_ignorate = []          # (gradi della bussola, fino a quando): "casse" che non si aprono
        self.casse_sbagliate = []         # quando ho trovato "casse" finte
        self.prossimo_impulso = adesso + 20.0
        self.casse_pausa_fino = 0.0

    # ================================================================== utilita'
    @property
    def ppp(self):
        if self.apprendimento is not None:
            return max(0.01, float(self.apprendimento.ppp))
        return max(0.01, float(self.mira.get("pixel_per_passo", 1.0) or 1.0))

    @property
    def passi_per_giro(self):
        if self.apprendimento is not None:
            return float(self.apprendimento.passi_per_giro)
        return float(self.mira.get("passi_per_giro", 3600) or 3600)

    def _imposta_passi_per_giro(self, nuovi):
        if self.apprendimento is not None:
            self.apprendimento.passi_per_giro = nuovi
            impostazioni.salva_calibrazione(self.apprendimento.base, ["mira", "passi_per_giro"], round(nuovi))
        else:
            self.mira["passi_per_giro"] = nuovi
        self.esecutore.passi_per_giro = nuovi

    def _mirino(self, vis):
        m = (self.cfg.get("schermo", {}) or {}).get("mirino") or [0.5, 0.5]
        return float(m[0]) * vis.larghezza, float(m[1]) * vis.altezza

    def _cammina(self, avanti=False, corri=False, sinistra=False, destra=False, indietro=False):
        for nome, valore in (("avanti", avanti), ("corri", corri), ("sinistra", sinistra),
                             ("destra", destra), ("indietro", indietro)):
            if self.mani.esiste(nome):
                self.mani.imposta(nome, valore)

    def _spara(self, valore):
        if self.sparando != valore and self.mani.esiste("spara"):
            self.mani.imposta("spara", valore)
        self.sparando = valore

    def ferma_tutto(self):
        self._spara(False)
        self._cammina()
        self.bersaglio = None
        try:
            self.mani.rilascia_tutto()
        except Exception:
            pass

    def _gira(self, gradi):
        if abs(gradi) > 2:
            self.esecutore.gira(gradi)

    def _gradi_schermo(self, x):
        """Un punto dello schermo (0-1) -> di quanti gradi girarmi per averlo davanti."""
        return (x - 0.5) * float(self.fort.get("campo_visivo_gradi", 80) or 80)

    def _tasto_slot(self, n):
        """Slot contando il piccone (1 = piccone, 2-6 = armi) -> nome del tasto (F, 1-5)."""
        if not n:
            return None
        nome = "piccone" if n == 1 else "arma_%d" % (n - 1)
        return nome if self.mani.esiste(nome) else None

    def _tasto_arma(self, k):
        """Slot delle armi come li vedi in Fortnite (1-5; il piccone e' F) -> nome del tasto."""
        nome = "arma_%d" % int(k)
        return nome if self.mani.esiste(nome) else None

    # ---- bussola e rotta
    def _passi_x(self):
        return getattr(self.mani, "passi_totali_x", 0)

    def guardo_verso(self):
        if self.bussola_rif is None:
            return None
        gradi, passi = self.bussola_rif
        return (gradi + (self._passi_x() - passi) * 360.0 / max(1.0, self.passi_per_giro)) % 360.0

    def guardo_al_tempo(self, quando):
        """Dove guardavo in quel momento (per le risposte dell'IA che arrivano in ritardo)."""
        for tt, g in reversed(self.storia_guardo):
            if tt <= quando:
                return g
        return self.storia_guardo[0][1] if self.storia_guardo else self.guardo_verso()

    def _leggi_bussola(self, gradi, quando=None):
        passi = self._passi_x()
        if quando is not None:
            for tt, pp in reversed(self.storia_passi):
                if tt <= quando:
                    passi = pp
                    break
        self.bussola_rif = (float(gradi) % 360.0, passi)

    # ================================================================== il passo (l'albero)
    def passo(self, vis, img=None, t=None):
        t = time.monotonic() if t is None else t
        self.dt_medio = 0.8 * self.dt_medio + 0.2 * max(1e-3, min(0.2, t - self.t_prec))
        self.t_prec = t
        self.storia_passi.append((t, self._passi_x()))
        if len(self.storia_passi) > 400:
            del self.storia_passi[:100]
        self._aggiorna_lavagna(vis, img, t)
        if self.lavagna.guardo is not None:
            self.storia_guardo.append((t, self.lavagna.guardo))
            if len(self.storia_guardo) > 1500:
                del self.storia_guardo[:300]
        for ramo in (self._ramo_istruzioni, self._ramo_pulsante_giallo, self._ramo_schermi, self._ramo_fasi,
                     self._ramo_fuori_partita, self._ramo_pericolo, self._ramo_nemico, self._ramo_scritta, self._ramo_arma_e_cure,
                     self._ramo_rianima, self._ramo_manutenzione, self._ramo_cassa_vista, self._ramo_bottino,
                     self._ramo_compagno, self._ramo_viaggio):
            scritta = ramo(vis, img, t)
            if scritta:
                if not scritta.startswith("combatto"):
                    if self.sparando:
                        self._spara(False)
                    self.bersaglio = None
                return scritta
        return "aspetto"

    # ================================================================== la lavagna
    def _aggiorna_lavagna(self, vis, img, t):
        lv = self.lavagna
        W, H = vis.larghezza, vis.altezza
        # i nemici visti dagli occhi veloci, senza il mio personaggio (in basso al centro, di spalle)
        lv.nemici = [b for b in vis.nemici
                     if not (b.fondo >= 0.85 * H and 0.25 * W <= b.cx <= 0.65 * W)]
        if lv.nemici:
            self.stato["ultimo_nemico"] = t
        self._aggiorna_hud(img, t)
        lv.consiglio, lv.nuovo = None, False
        if self.ia is not None:
            if img is not None:
                self.ia.guarda(img)
            c = self.ia.consiglio(t, getattr(self.ia, "validita_fase", 45))
            if c is not None and c.fase != "playing" and t - c.quando > 6.0 and not self._schermo_uguale(c, img):
                c = None                                  # parlava di uno schermo che e' cambiato
            scaduto = c is not None and c.fase == "playing" and t - c.quando > float(
                (self.cfg.get("ia", {}) or {}).get("validita_secondi", 8) or 8)
            if c is not None and c.numero != self.ultimo_numero:
                self.ultimo_numero = c.numero
                self._mete_dall_ia(c)                     # anche se e' in ritardo: diventa una direzione
                lv.nuovo = not scaduto
                if c.bussola is not None and t - self.ultima_bussola_hud > 10.0:
                    previsto = self.guardo_verso()        # la bussola letta dall'IA solo se io non la leggo
                    if previsto is not None and abs(avvolgi(c.bussola - previsto)) > 60:
                        self.bussola_sbagliata += 1
                        if self.bussola_sbagliata >= 3 and self.calibra_da is None:
                            self.log("I miei conti non tornano con la bussola: rimisuro quanto mi giro")
                            self.calibra_da = t
                            self.bussola_sbagliata = 0
                    else:
                        self.bussola_sbagliata = 0
                    self._leggi_bussola(c.bussola, c.quando)
            lv.consiglio = None if scaduto else c
        self._applica_mappa(t)
        lv.guardo = self.guardo_verso()
        # pericoli: tempesta (la minimappa, l'IA, o il TERRENO viola) e acqua (nuoto o minimappa)
        c = lv.consiglio
        m = lv.mini
        if m.ok:
            lv.in_tempesta = m.qui == hud.TEMPESTA
        else:
            lv.in_tempesta = bool(img is not None and self.fort.get("tempesta_dal_colore", True)
                                  and viola(img) >= float(self.fort.get("tempesta_soglia_viola", 0.35) or 0.35))
        if c is not None and c.fase == "playing" and c.tempesta:
            lv.in_tempesta = True
        evita = self.fort.get("evita_acqua", True)
        nuoto = bool(evita and img is not None and acqua(img) >= float(self.fort.get("acqua_soglia", 0.5) or 0.5))
        mare = bool(evita and m.ok and m.qui == hud.ACQUA)
        self.nuoto_da = (self.nuoto_da if self.nuoto_da is not None else t) if nuoto else None
        if nuoto or mare:
            self.acqua_da = self.acqua_da if self.acqua_da is not None else t
        else:
            self.acqua_da = None
        lv.in_acqua = self.acqua_da is not None and t - self.acqua_da >= 1.5

    def _aggiorna_hud(self, img, t):
        """Bussola, minimappa, barra delle armi e compagni: letti dallo schermo, senza IA."""
        lv = self.lavagna
        if img is None or not self.fort.get("leggi_lo_schermo", True):
            return
        if t >= self.prossima_bussola:
            self.prossima_bussola = t + float(self.fort.get("bussola_ogni_secondi", 0.15) or 0.15)
            g = hud.leggi_bussola(img)
            lv.bussola_hud = g
            if g is not None:
                self.ultima_bussola_letta = t
                self._nuova_lettura(g, t)
            tipo = hud.tipo_di_scritta(img) if (lv.barra or t - self.ultima_bussola_letta < 2.0) else None
            if tipo == "spazio":
                self.in_aria_t = t                  # "Spazio PER SALTARE", "ENTRA IN CADUTA LIBERA"...
            lv.scritta = bool(lv.barra and tipo == "e" and t - self.in_aria_t > 3.0)
        if t >= self.prossima_minimappa:
            self.prossima_minimappa = t + float(self.fort.get("minimappa_ogni_secondi", 0.4) or 0.4)
            lv.barra = hud.barra_armi(img)
            lv.spettatore = hud.spettatore(img)
            lv.mini = hud.leggi_minimappa(img)
            if not (lv.barra or t - self.ultima_bussola_letta < 2.0):
                lv.mini = hud.Minimappa(None)       # nei menu non c'e' la minimappa: non la invento
            lv.vita, lv.scudo = hud.leggi_vita(img) if lv.barra else (None, None)
            in_gioco = lv.barra and t - self.ultima_bussola_letta < 1.0 and not lv.spettatore
            lv.compagni = hud.compagni_sulla_bussola(img) if in_gioco else []
            lv.compagni_bordi = hud.compagni_ai_bordi(img) if in_gioco else []
            lv.compagni_mini = hud.compagni_sulla_minimappa(img) if in_gioco else []
            if lv.mini.ok and 0.05 <= lv.mini.tempesta <= 0.9:
                g = lv.mini.lontano_dalla_tempesta()
                if g is not None:
                    self.salvo_memo = (g, t)        # me lo ricordo per quando la minimappa e' tutta viola
            # sul bus: si legge la bussola, si vede la minimappa, ma la barra delle armi no
            if t - self.ultima_bussola_letta < 1.0 and lv.mini.ok and not lv.barra:
                self.bus_conta += 1
            else:
                self.bus_conta = 0
            lv.bus = self.bus_conta >= 2
            self._scegli_compagno(t)

    def _nuova_lettura(self, gradi, t):
        """Una lettura della bussola: la prendo se torna con i miei conti, o se due letture di fila
        dicono la stessa cosa (cosi' un'icona sopra il numero non mi inganna)."""
        passi = self._passi_x()
        previsto = self.guardo_verso()
        prec = self.lettura_prec
        self.lettura_prec = (t, gradi, passi)
        coerente = previsto is not None and abs(avvolgi(gradi - previsto)) <= 25
        confermata = prec is not None and t - prec[0] <= 1.0 and abs(avvolgi(
            gradi - prec[1] - (passi - prec[2]) * 360.0 / max(1.0, self.passi_per_giro))) <= 8
        if not (coerente or confermata):
            return
        self._leggi_bussola(gradi)
        self.ultima_bussola_hud = t
        self._misura_giro(t, gradi, passi)

    def _misura_giro(self, t, gradi, passi):
        """Tra due letture mi sono girato col mouse: quanti passi del mouse fanno un giro intero?
        Se tante misure dicono la stessa cosa (diversa da quella che uso) la correggo da solo."""
        a = self.ultima_accettata
        self.ultima_accettata = (t, gradi, passi)
        if a is None or t - a[0] > 1.5 or not self.fort.get("calibra_con_bussola", True):
            return
        dp = passi - a[2]
        dg = avvolgi(gradi - a[1])
        if abs(dg) < 15 or abs(dg) > 150 or abs(dp) < 1:
            return
        stima = dp * 360.0 / dg
        if stima <= 0:
            return
        self.stime_giro.append(stima)
        del self.stime_giro[:-7]
        if len(self.stime_giro) < 4:
            return
        mediana = float(np.median(self.stime_giro))
        vicine = [s for s in self.stime_giro if abs(s - mediana) <= 0.15 * mediana]
        vecchi = self.passi_per_giro
        if len(vicine) >= 4 and abs(mediana - vecchi) > 0.12 * vecchi and 0.2 <= mediana / vecchi <= 5:
            nuovi = float(np.mean(vicine))
            self.log("Bussola: misurato quanto mi giro col mouse -> passi per un giro %.0f -> %.0f" % (vecchi, nuovi))
            self._imposta_passi_per_giro(nuovi)
            self.ultima_calibrazione = t
            self.stime_giro = []

    def _scegli_compagno(self, t):
        """Il compagno da seguire (come i bot che si assoldano: "al guinzaglio"). Lo cerco sulla
        minimappa (freccia gialla: so anche quanto e' lontano), sopra la bussola (triangolini) e ai
        bordi dello schermo (frecce < > e v quando e' dietro). Seguo sempre lo stesso; se lo perdo
        per un po' ne scelgo un altro a caso."""
        lv = self.lavagna
        g = self.guardo_verso()
        if g is None:
            return
        candidati = [(b, d, "minimappa") for b, d in lv.compagni_mini]
        candidati += [((g + d) % 360.0, None, "bussola") for d in lv.compagni]
        candidati += [((g + d) % 360.0, None, "bordo") for d in lv.compagni_bordi]
        if not candidati:
            return
        ordine = {"minimappa": 0, "bussola": 1, "bordo": 2}
        scelto = None
        if self.compagno_hud is not None and t - self.compagno_hud_t < 20.0:
            tolleranza = {"minimappa": 45, "bussola": 45, "bordo": 90}
            vicini = [c for c in candidati if abs(avvolgi(c[0] - self.compagno_hud)) <= tolleranza[c[2]]]
            if vicini:
                scelto = min(vicini, key=lambda c: (ordine[c[2]], abs(avvolgi(c[0] - self.compagno_hud))))
            elif t - self.compagno_hud_t <= 6.0:
                return                              # per un po' resto fedele a quello di prima
        nuovo = scelto is None
        if nuovo:
            migliori = [c for c in candidati if ordine[c[2]] == min(ordine[x[2]] for x in candidati)]
            scelto = random.choice(migliori)
        self.compagno_hud, self.compagno_hud_t, self.compagno_fonte = scelto[0], t, scelto[2]
        if scelto[1] is not None:
            self.compagno_dist, self.compagno_dist_t = scelto[1], t
        if nuovo:
            self.log("Scelgo un compagno da seguire: e' verso %.0f gradi (%s)" % (scelto[0], scelto[2]))

    def _mete_dall_ia(self, c):
        """La risposta dell'IA (anche se arriva tardi) diventa una DIREZIONE DELLA BUSSOLA: dove
        guardavo quando ho fatto la foto + quanto era spostato dal centro."""
        allora = self.guardo_al_tempo(c.quando) if self.storia_guardo else None
        if allora is None:
            return
        if c.compagno_xy is not None:
            x, y, lato, metri = c.compagno_xy
            gradi = self._gradi_schermo(x) if lato == "on_screen" else LATO_GRADI.get(lato)
            if gradi is not None:
                self.meta_compagno = ((allora + gradi) % 360.0, metri, c.quando)
        if c.obiettivo is not None:
            cosa, x, y = c.obiettivo
            self.meta_bottino = ((allora + self._gradi_schermo(x)) % 360.0, cosa, y, c.quando)

    def _schermo_uguale(self, c, img):
        prima = getattr(c, "miniatura", None)
        if prima is None or img is None:
            return False
        from ia import miniatura
        return float(np.mean(np.abs(miniatura(img) - prima))) < 10.0

    def _in_pericolo(self, t):
        return self.lavagna.in_tempesta or self.lavagna.in_acqua or t < self.fuga_fino

    # ================================================================== 1. istruzioni e "Gioca di nuovo"
    def _ramo_istruzioni(self, vis, img, t):
        if self.istruzioni is None or t < self.prossimo_controllo_regole or self._in_pericolo(t):
            return None                  # nella tempesta o in acqua prima si scappa
        self.prossimo_controllo_regole = t + float(self.regole_cfg.get("controlla_ogni", 0.2) or 0.2)
        regola = self.istruzioni.controlla(vis, self.stato, t)
        if regola is None:
            return None
        self.log("Istruzione (riga %d): %s" % (regola.riga, regola.testo))
        self.ferma_tutto()
        try:
            self.esecutore.esegui(regola.azioni)
        finally:
            self.mani.rilascia_tutto()
            self.mini_prec = None
            self.ultimo_mosso = time.monotonic()
            self.stato["fermo_da"] = 0.0
        return "istruzione riga %d" % regola.riga

    def _ramo_pulsante_giallo(self, vis, img, t):
        """Il pulsante grande e giallo "Gioca di nuovo": visto 3 volte fermo (5 se credo di vedere
        un nemico) lo clicco. Sulla Play il cursore si muove "alla cieca": se resta, riprovo con
        un'altra velocita' del cursore e me la ricordo."""
        if img is None or not self.fort.get("pulsante_giallo", True) or t < self.prossimo_giallo:
            return None
        lv = self.lavagna
        if lv.barra or (lv.bussola_hud is not None and t - self.ultima_bussola_hud < 2.0):
            self.giallo_visto = None
            return None                  # c'e' la bussola o la barra delle armi: sto giocando, non e' un menu
        self.prossimo_giallo = t + 1.0
        from ia import miniatura
        trovato = trova_pulsante_giallo(img)
        if trovato is None:
            if self.giallo_tentativo is not None:
                ppm = self.giallo_tentativo[1]
                self.esecutore.passi_per_pixel_menu = ppm
                if self.apprendimento is not None:
                    impostazioni.salva_calibrazione(self.apprendimento.base, ["menu", "passi_per_pixel"], round(ppm, 3))
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
        if volte < (5 if self.lavagna.nemici else 3):
            return None
        if self.giallo_tentativo is not None:
            if t - self.giallo_tentativo[0] < 2.5:
                return "aspetto che riparta"
            self.giallo_indice += 1
        attuale = float(getattr(self.esecutore, "passi_per_pixel_menu", 1.0) or 1.0)
        candidati = [attuale] + [v for v in (1.0, 0.5, 1.5, 0.75, 2.0, 3.0, 0.35, 4.0) if abs(v - attuale) > 0.01]
        ppm = candidati[self.giallo_indice % len(candidati)]
        self.esecutore.passi_per_pixel_menu = ppm
        self.ferma_tutto()
        if self.giallo_indice == 0:
            self.log("Vedo il pulsante giallo (Gioca di nuovo): clicco")
            self._partita_finita(t)
        ox, oy = self.schermo.origine if self.schermo is not None else (0, 0)
        self.esecutore.porta_cursore(ox + cx, oy + cy)
        self.esecutore.dormi(0.1)
        self.mani.premi("mouse_sinistro", 0.08)
        self.giallo_tentativo = (t, ppm)
        return "clicco Gioca di nuovo"

    def _partita_finita(self, t, sicuro=False):
        if not (sicuro or self.in_partita) and t - self.ultima_partita_contata < 90.0:
            return
        self.in_partita = False
        self.ultima_partita_contata = t
        self.statistiche["partite"] = self.statistiche.get("partite", 0) + 1
        self.log("Partita finita (%d). Passo alla prossima." % self.statistiche["partite"])
        self.rotta = None
        self.rotta_ia = None
        self.salto_da = None
        self.compagno_hud = None
        self.meta_compagno = None
        self.meta_bottino = None
        self.esecutore._fine_partita()

    # ================================================================== 2. schermi strani
    def _ramo_schermi(self, vis, img, t):
        c = self.lavagna.consiglio
        if c is None or c.schermo == "game":
            if c is not None:
                self.volte_chi = 0
            return None
        self.ferma_tutto()
        nuovo = c.numero != self.ultimo_schermo
        self.ultimo_schermo = c.numero
        if c.schermo == "ps5_who_is_using":
            if nuovo:
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
                self.prossimo_avviso = t + 60.0
            elif t >= self.prossimo_avviso:
                self.prossimo_avviso = t + 60.0
                self.log("PS Remote Play e' scollegato. Se chiede il codice della PS5 o un aggiornamento, "
                         "fallo tu: poi riparto da solo")
            return "PS Remote Play scollegato"
        if self.pc is not None and t >= self.prossimo_davanti:
            self.prossimo_davanti = t + 10.0
            if self.pc.porta_davanti():
                self.log("Non vedo il gioco: riporto davanti PS Remote Play")
                return "non vedo il gioco"
        if t >= self.prossimo_avviso:
            self.prossimo_avviso = t + 60.0
            self.log("Non vedo il gioco (c'e' il desktop o un altro programma): aspetto che torni")
        return "non vedo il gioco"

    # ================================================================== 3. fasi
    def _fase(self, c, t):
        """La fase della partita: quella dell'IA se e' fresca, se no quella che leggo dallo schermo
        (bus = bussola senza barra delle armi; caduta = appena saltato dal bus)."""
        lv = self.lavagna
        fase = c.fase if c is not None else None
        if lv.spettatore and fase in (None, "unknown", "playing"):
            fase = "spettatore"           # in alto c'e' "SPETTATORE": sono stato eliminato
        if lv.bus and fase not in ("falling", "dead", "spettatore"):
            fase = "bus"                  # nei menu la bussola non c'e': lo schermo non sbaglia
        in_aria = t - self.in_aria_t < 3.0
        if fase in (None, "unknown") and in_aria:
            fase = "falling" if lv.barra else "bus"     # la scritta col tasto SPAZIO: bus o caduta
        if fase in (None, "unknown") and self.salto_da is not None:
            # in aria c'e' sempre la scritta col tasto SPAZIO: quando sparisce sono atterrato
            nuoto = self.nuoto_da is not None and t - self.nuoto_da >= 1.5
            ancora = t - self.salto_da < 8.0 or (in_aria and t - self.salto_da < float(
                self.fort.get("caduta_secondi", 60) or 60))
            if not self.fort.get("leggi_lo_schermo", True):
                ancora = t - self.salto_da < float(self.fort.get("caduta_secondi", 60) or 60)
            if ancora and not nuoto:
                fase = "falling"
        if fase in ("playing", "menu", "dead"):
            self.salto_da = None
        return fase

    def _ramo_fasi(self, vis, img, t):
        c = self.lavagna.consiglio
        fase = self._fase(c, t)
        if fase != "bus":
            self.bus_da = None
        if fase != "dead":
            self.morto_da = None
        if fase not in ("bus", "falling") and self.ultima_fase in ("bus", "falling"):
            self._atterrato(c, t)
        self.ultima_fase = fase
        if fase in ("bus", "falling", "playing"):
            self.in_partita = True
        if fase == "bus":
            return self._sul_bus(c, t)
        if fase == "falling":
            return self._in_caduta(c, t)
        if fase in ("menu", "dead") and c is not None:
            return self._menu_o_morto(c, vis, img, t)
        if fase == "spettatore":
            self.ferma_tutto()
            if self.in_partita:
                self.log("Sono stato eliminato: resto a guardare i compagni fino alla fine (per il token)")
                self._partita_finita(t, sicuro=True)
            return "eliminato: guardo i compagni fino alla fine della partita"
        return None

    def _ramo_fuori_partita(self, vis, img, t):
        """Senza la barra delle armi e senza la bussola non sono in partita (menu, caricamento,
        schermate finali): sto fermo, non cammino e non salto nei menu."""
        if img is None or not self.fort.get("leggi_lo_schermo", True):
            return None
        lv = self.lavagna
        if lv.barra or t - self.ultima_bussola_letta < 2.0:
            return None
        c = lv.consiglio
        if c is not None and c.fase == "playing":
            return None                  # l'IA (fresca) dice che sto giocando
        self.ferma_tutto()
        return "non sono in partita: aspetto"

    def _atterrato(self, c, t):
        self.log("Atterrato: prendo l'arma (slot 1) e controllo la bussola")
        self.salto_da = None
        self._prendi_arma(c, t, subito=True)
        self.prossima_mappa_periodica = t + 12.0
        if t - self.ultima_calibrazione > float(self.fort.get("ricalibra_bussola_secondi", 1200) or 1200):
            self.calibra_da = t + 2.0

    def _sul_bus(self, c, t):
        self.ferma_tutto()
        lv = self.lavagna
        if self.bus_da is None:
            self.bus_da = t
            self.rotta = None
            self.rotta_ia = None
            self.log("Sono sul bus: salto quando sotto c'e' l'isola")
        attesa = t - self.bus_da
        if lv.mini.ok:
            sopra = lv.mini.terra_intorno(22, 12) >= float(self.fort.get("bus_terra_minima", 0.7) or 0.7)
        else:
            sopra = c is not None and c.sopra_isola is not False
        # all'inizio il bus vola sul MARE: aspetto di essere sopra l'isola
        if not sopra and attesa < float(self.fort.get("bus_attesa_massima", 60) or 60):
            return "sul bus: aspetto di essere sopra l'isola"
        if t >= self.prossimo_salto and self.mani.esiste("salta"):
            self.prossimo_salto = t + 3.0
            self.salto_da = t
            self.log("Salto dal bus%s" % (" (sotto c'e' l'isola)" if sopra else " (non posso aspettare di piu')"))
            self.mani.premi("salta")
        return "sul bus"

    def _in_caduta(self, c, t):
        """Cado: verso il compagno (atterro dove atterra lui), e MAI sul mare (minimappa)."""
        self._spara(False)
        lv = self.lavagna
        m = lv.mini
        meta, motivo = None, ""
        compagno = self._direzione_compagno(t)
        if compagno is not None and self.fort.get("segui_compagno", True):
            meta, motivo = compagno, "verso il compagno"
        if m.ok and (m.qui == hud.ACQUA or m.terra_intorno(12) < 0.5):
            terra = m.verso_terra()
            if terra is not None:
                meta, motivo = terra, "verso la terra"
        if meta is not None and lv.guardo is not None:
            if t >= self.prossima_correzione and abs(avvolgi(meta - lv.guardo)) > 25:
                self.prossima_correzione = t + 3.0
                self.log("In caduta: vado %s (%.0f gradi)" % (motivo, meta))
            self._vai_verso(meta, t)
        elif c is not None and lv.nuovo and t >= self.prossima_correzione:
            # senza bussola: come prima, con quello che vede l'IA sullo schermo
            gradi = None
            if c.compagno_xy is not None and c.compagno_xy[2] == "on_screen" and self.fort.get("segui_compagno", True):
                gradi, motivo = self._gradi_schermo(c.compagno_xy[0]), "verso il compagno"
            elif c.obiettivo is not None and c.obiettivo[0] in ("building", "chest"):
                gradi, motivo = self._gradi_schermo(c.obiettivo[1]), "verso le case"
            if gradi is not None and abs(gradi) > 10:
                self.prossima_correzione = t + 1.5
                self.log("In caduta: giro %s (%.0f gradi)" % (motivo, gradi))
                self._gira(gradi)
        self._cammina(avanti=True)
        return "cado verso terra"

    def _menu_o_morto(self, c, vis, img, t):
        self.ferma_tutto()
        if c.fase == "dead":
            if self.morto_da is None:
                self.morto_da = t
                self.log("Sono stato eliminato" + (": il personaggio che vedo adesso e' un ALTRO giocatore"
                                                   if c.osservo else ""))
            if self.apprendimento is not None and img is not None:
                self.apprendimento.forse_salva_foto(img, vis, t)
        if self.in_partita:
            self._partita_finita(t, sicuro=True)
        if c.fase == "dead" and c.osservo and self.fort.get("resta_fino_alla_fine", True):
            # come per il token: se un compagno lo trova vale anche per me, ma solo se resto in
            # partita (collegato) fino alla fine. Il pulsante "Gioca di nuovo" lo clicco alla fine.
            return "eliminato: guardo i compagni fino alla fine della partita"
        if c.fase == "dead" and c.osservo and \
                t - self.morto_da < float(self.fort.get("aspetta_riavvio_secondi", 90) or 0):
            return "eliminato: guardo un compagno, aspetto il furgone del riavvio"
        aspetto = "aspetto (%s)" % ("menu" if c.fase == "menu" else "eliminato")
        if not self.fort.get("partite_in_loop", True) or c.numero == self.ultimo_menu:
            return aspetto
        self.ultimo_menu = c.numero
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
        ox, oy = self.schermo.origine if self.schermo is not None else (0, 0)
        self.log("IA: clicco il pulsante per la partita dopo")
        self.esecutore.porta_cursore(ox + c.pulsante[0] * W, oy + c.pulsante[1] * H)
        self.mani.premi("mouse_sinistro", 0.08)
        return "clicco per la partita dopo"

    # ================================================================== 4. pericolo: tempesta / acqua
    def _ramo_pericolo(self, vis, img, t):
        """Tempesta o acqua: corro SUBITO dalla parte giusta (minimappa) e non mi fermo mai.
        L'IA che guarda la mappa grande aiuta solo se la minimappa non basta, e intanto corro."""
        lv = self.lavagna
        pericolo = lv.in_tempesta or lv.in_acqua
        if not pericolo and t >= self.fuga_fino:
            return None
        if pericolo:
            self.fuga_fino = max(self.fuga_fino, t + float(self.fort.get("corsa_dopo_pericolo", 3) or 3))
        rotta, perche = self._rotta_di_fuga(t)
        if rotta is None and pericolo:
            if self._mappa_in_sottofondo(t, "Sono nella tempesta" if lv.in_tempesta else "Sono in acqua"):
                rotta, perche = self._rotta_di_fuga(t)
        if rotta is not None:
            if self.rotta is None or abs(avvolgi(rotta - self.rotta)) > 30 or t >= self.prossimo_avviso_fuga:
                self.prossimo_avviso_fuga = t + 10.0
                self.log("%s: %s -> vado a %.0f gradi" % (
                    "Tempesta" if lv.in_tempesta else ("Acqua" if lv.in_acqua else "Quasi fuori"), perche, rotta))
            self.rotta = rotta
        elif self.rotta is None and lv.guardo is None and lv.in_acqua and t >= self.prossima_ricerca_terra:
            self.prossima_ricerca_terra = t + 12.0
            if self.ia is None or not hasattr(self.ia, "chiedi_voto"):
                return self._cerca_terra(t)                # niente bussola e niente IA: guardo l'orizzonte
        girato = self._vai_verso(self.rotta, t)
        self._cammina(avanti=True, corri=True)
        self._controlla_blocco(img, t)
        if lv.in_tempesta and not lv.in_acqua and not lv.nemici and self._uscita_lontana(t):
            if self._lancio_impulso(t, "la tempesta finisce lontano"):
                return "volo con l'impulso fuori dalla tempesta"
        if lv.nemici:
            return None                          # se mi sparano mi difendo (ramo nemico)
        if perche and "mappa)" in perche and "minimappa" not in perche and girato:
            return "vado verso la zona sicura (mappa)"
        if perche and "fuori dalla tempesta" in perche:
            return "esco dalla tempesta"
        if perche and "terra" in perche:
            return "torno a terra"
        return "scappo verso la zona sicura"

    def _uscita_lontana(self, t):
        """L'uscita dalla tempesta e' lontana (sulla minimappa, davanti a me, la tempesta continua per
        piu' di meta' della minimappa) o non la vedo proprio."""
        m = self.lavagna.mini
        if self.rotta is None or self.lavagna.guardo is None or abs(avvolgi(self.rotta - self.lavagna.guardo)) > 25:
            return False                 # prima mi giro dalla parte giusta
        if not m.ok:
            return True
        d = m.primo(self.rotta, (hud.TERRA, hud.ACQUA), di_fila=3)
        return d is None or d > 16

    def _lancio_impulso(self, t, perche):
        """LA GRANATA IMPULSO (slot 3 negli slot preferiti) ai miei piedi mentre corro: mi sbalza in
        avanti. Guardo per terra, la lancio, rialzo lo sguardo e salto; poi riprendo l'arma."""
        if not self.fort.get("usa_impulso", True) or t < self.prossimo_impulso or self.salto_da is not None:
            return False
        if self.lavagna.vita is not None and self.lavagna.vita < 25:
            return False                 # l'impulso non toglie i danni da caduta
        tasto = self._tasto_arma(int(self.fort.get("slot_impulso", 3) or 3))
        if not tasto or not self.mani.esiste("spara"):
            return False
        self.prossimo_impulso = t + float(self.fort.get("impulso_ogni_secondi", 25) or 25)
        self.log("%s: lancio la granata impulso ai miei piedi (slot 3) per volare avanti" % perche.capitalize())
        self.mani.premi(tasto, 0.08)
        self.esecutore.dormi(0.35)
        giu = self.passi_per_giro * 75.0 / 360.0
        self.mani.muovi(0, giu)                  # guardo per terra
        self.esecutore.dormi(0.08)
        self._cammina(avanti=True, corri=True)
        self.mani.imposta("spara", True)
        self.esecutore.dormi(0.08)
        self.mani.imposta("spara", False)
        self.esecutore.dormi(0.2)
        self.mani.muovi(0, -giu)                 # di nuovo dritto
        if self.mani.esiste("salta"):
            self.mani.premi("salta")
        self.esecutore.dormi(1.0)
        self._prendi_arma(self.lavagna.consiglio, t, subito=True)
        return True

    def _rotta_di_fuga(self, t):
        """-> (gradi, perche'): dove scappare. Prima la minimappa, poi la mappa vista dall'IA."""
        lv = self.lavagna
        m = lv.mini
        if m.ok:
            if m.qui == hud.TEMPESTA or (lv.in_tempesta and m.tempesta > 0.3):
                g = m.verso_fuori_tempesta()
                if g is not None:
                    return g, "fuori dalla tempesta (minimappa)"
            if lv.in_acqua:
                g = m.verso_terra(preferita=self._direzione_compagno(t))   # meglio la terra dov'e' il compagno
                if g is not None:
                    return g, "la terra piu' vicina (minimappa)"
            g = m.lontano_dalla_tempesta()
            if g is not None and lv.in_tempesta:
                return g, "lontano dalla tempesta (minimappa)"
        if lv.in_tempesta:
            # la minimappa e' tutta viola: vado dal compagno (lui sta nella zona sicura) o dove
            # ricordo che la tempesta finiva
            compagno = self._direzione_compagno(t)
            if compagno is not None:
                return compagno, "verso il compagno (fuori dalla tempesta)"
            if self.salvo_memo is not None and t - self.salvo_memo[1] < float(
                    self.fort.get("ricordo_zona_secondi", 180) or 180):
                return self.salvo_memo[0], "dove finiva la tempesta (ricordo della minimappa)"
        if self.rotta_ia is not None and t - self.rotta_ia_t < float(self.fort.get("mappa_valida_secondi", 90) or 90):
            return self.rotta_ia, "la zona sicura (mappa)"
        return None, None

    def _cerca_terra(self, t):
        """Senza bussola e senza IA: mi giro dove all'orizzonte c'e' meno mare e corro."""
        self.log("Sono in acqua: mi giro dove c'e' la terra")
        self._cammina()
        migliore, minimo = 0, None
        for i in range(8):
            foto = self.esecutore.foto_fresca()
            if foto is not None:
                q = acqua(foto, 0.38, 0.6)
                if minimo is None or q < minimo:
                    migliore, minimo = i, q
            self.esecutore.gira(45.0, durata=0.15)
            self.esecutore.dormi(0.25)
        if migliore:
            self.esecutore.gira(migliore * 45.0)
        self.fuga_fino = t + float(self.fort.get("corsa_fuori_acqua", 8) or 8)
        return "torno a terra"

    def _vai_verso(self, gradi, t):
        """Mi giro verso una direzione della bussola: se e' tanto di lato mi giro subito, se no
        piano piano mentre cammino. -> True se ho girato."""
        guardo = self.lavagna.guardo
        if gradi is None or guardo is None or t < self.deviazione_fino:
            return False
        errore = avvolgi(gradi - guardo)
        if abs(errore) > 45 and t >= self.prossima_svolta:
            self.prossima_svolta = t + 0.8
            self._gira(errore)
            self.lavagna.guardo = self.guardo_verso()
            return True
        self._tieni_rotta(t, gradi)
        return False

    def _tieni_rotta(self, t, gradi=None):
        gradi = self.rotta if gradi is None else gradi
        if gradi is None or self.lavagna.guardo is None or t < self.deviazione_fino:
            return
        errore = avvolgi(gradi - self.lavagna.guardo)
        gradi_al_secondo = max(-90.0, min(90.0, errore * 2.0))
        self.mani.mira_fluida(gradi_al_secondo * self.dt_medio * self.passi_per_giro / 360.0, 0, self.dt_medio)

    # ================================================================== 5. nemico
    def _ramo_nemico(self, vis, img, t):
        lv = self.lavagna
        nemici = lv.nemici
        c = lv.consiglio
        H = vis.altezza
        # IL SOSPETTO (come le guardie di Fortnite): vedo qualcosa -> si riempie (piu' in fretta se e'
        # grande, cioe' vicino); quando e' pieno attacco. Cosi' non inseguo le cose finte.
        dt = max(0.0, min(0.25, t - self.t_sospetto))
        self.t_sospetto = t
        if nemici:
            grande = max(b.h for b in nemici) / float(H)
            self.sospetto = min(1.0, self.sospetto + dt * (6.0 if grande >= 0.22 else 3.0 if grande >= 0.1 else 1.5))
            if grande >= float(self.fort.get("pompa_se_nemico_alto", 0.3) or 0.3):
                self.sospetto = 1.0                       # vicinissimo: niente dubbi
        else:
            self.sospetto = max(0.0, self.sospetto - dt * 0.7)
        if not nemici:
            self.mirando_da = None
            self.bersaglio = None
            self.arma_vicina = None
            if c is not None and lv.nuovo and c.nemico_xy is not None and self.comb.get("attivo", True):
                x, y, vicino = c.nemico_xy
                if vicino or not self._solo_vicini():
                    self.log("IA: c'e' un nemico%s -> mi giro e prendo l'arma" % (" vicino" if vicino else ""))
                    self._cammina()
                    allora = self.guardo_al_tempo(c.quando) if self.storia_guardo else None
                    if allora is not None and lv.guardo is not None:
                        self._gira(avvolgi(allora + self._gradi_schermo(x) - lv.guardo))
                    else:
                        self._gira(self._gradi_schermo(x))
                    self._prendi_arma(c, t, subito=True, vicino=bool(vicino))
                    return "mi giro verso il nemico (IA)"
            # il nemico e' sparito (dietro a un muro, o mi sono girato): lo cerco dove l'ho visto
            ng = self.nemico_gradi
            if ng is not None and lv.guardo is not None and \
                    t - ng[1] <= float(self.comb.get("cerca_nemico_secondi", 2.5) or 2.5):
                self._vai_verso(ng[0], t)
                if t >= self.prossima_schivata:
                    self.prossima_schivata = t + random.uniform(0.4, 0.9)
                    self.lato = "destra" if self.lato == "sinistra" else "sinistra"
                self._cammina(sinistra=self.lato == "sinistra", destra=self.lato == "destra")
                return "cerco il nemico"
            return None
        if self.bersaglio is None and self.sospetto < 1.0:
            return None                          # vedo qualcosa: aspetto di esserne sicuro
        if self._solo_vicini() and all(b.h < float(self.comb.get("nemico_vicino", 0.22)) * H for b in nemici):
            return None                          # obiettivo casse: i nemici lontani li lascio stare
        if not self.comb.get("attivo", True):
            return None
        mx, my = self._mirino(vis)
        b = min(nemici, key=lambda b: math.hypot(b.cx - mx, b.cy - my) / (1.0 + b.h / H))
        vicino = b.h >= float(self.fort.get("pompa_se_nemico_alto", 0.3) or 0.3) * H
        if self.bersaglio is None:
            self.mirando_da = t
            self.statistiche["combattimenti"] = self.statistiche.get("combattimenti", 0) + 1
            self._prendi_arma(c, t, subito=True, vicino=vicino)
        elif vicino != self.arma_vicina:
            self._prendi_arma(c, t, vicino=vicino)           # si e' avvicinato/allontanato: cambio arma
        ax = b.cx
        ay = b.y + float(self.mira.get("altezza_mira", 0.2)) * b.h
        self.bersaglio = (ax, ay)
        if lv.guardo is not None:
            self.nemico_gradi = ((lv.guardo + self._gradi_schermo(b.cx / float(vis.larghezza))) % 360.0, t)
        ex, ey = ax - mx, ay - my
        forza = float(self.mira.get("forza", 0.6) or 0.6) * self.stile.forza
        dy = ey / self.ppp * forza
        limite = self.passi_per_giro / 4.0
        dy = max(-limite - self.pitch, min(limite - self.pitch, dy))     # non oltre il cielo o i piedi
        self.mani.mira_fluida(ex / self.ppp * forza, dy, max(0.02, self.dt_medio))
        self.pitch += dy
        preciso = abs(ex) <= max(4.0, 0.35 * b.w) and abs(ey) <= max(4.0, 0.2 * b.h)
        quasi = abs(ex) <= 0.6 * b.w and abs(ey) <= 0.35 * b.h and t - self.mirando_da >= 0.5
        pronto = t - self.mirando_da >= self.stile.reazione
        sparavo = self.sparando
        self._spara((preciso or quasi) and pronto)
        if self.sparando and not sparavo:
            self.statistiche["nemici_colpiti"] = self.statistiche.get("nemici_colpiti", 0) + 1
        # mi muovo: a destra e sinistra (piu' difficile da colpire); se e' lontano mi avvicino
        if t >= self.prossima_schivata:
            self.prossima_schivata = t + random.uniform(0.4, 0.9)
            self.lato = "destra" if self.lato == "sinistra" else "sinistra"
        lontano = b.h < float(self.comb.get("distanza_insegui", 0.08)) * H
        self._cammina(avanti=lontano, sinistra=self.lato == "sinistra", destra=self.lato == "destra")
        return "combatto (%s)" % ("sparo" if self.sparando else "miro")

    def _solo_vicini(self):
        if self.stile.solo_vicini or self.obiettivo.tipo == "sopravvivere":
            return True
        return self.obiettivo.pensa_alle_casse(self.statistiche.get("casse_partita", 0))

    def _prendi_arma(self, c, t, subito=False, vicino=False):
        """L'arma in mano, come gli "slot preferiti": nemico vicino -> la pompa (slot 2), se no la
        mitra (slot 1). In Fortnite uno slot vuoto non si prende: non succede niente."""
        if not self.comb.get("prendi_arma", True) or (not subito and t < self.prossimo_cambio_arma):
            return
        k = int(self.fort.get("slot_pompa", 2) or 2) if vicino else int(self.fort.get("slot_in_mano", 1) or 1)
        tasto = self._tasto_arma(k)
        if tasto:
            self.prossimo_cambio_arma = t + 2.0
            self.arma_vicina = vicino
            self.mani.premi(tasto, 0.08)

    # ================================================================== 6. scritte sullo schermo
    def _ramo_scritta(self, vis, img, t):
        lv = self.lavagna
        if (lv.scritta and lv.barra and not lv.bus and self.salto_da is None and not lv.nemici
                and self.fort.get("apri_con_la_scritta", True) and t >= self.prossima_scritta
                and self.mani.esiste("interagisci")):
            return self._premi_e_sulla_scritta(t)
        c = self.lavagna.consiglio
        if (c is None or not self.lavagna.nuovo or c.fase != "playing" or c.prompt not in
                ("open", "pick_up", "zipline", "door") or not self.fort.get("usa_le_scritte", True)
                or t < self.prossima_scritta or not self.mani.esiste("interagisci")
                or t - c.quando > float(self.fort.get("scritta_valida_secondi", 5) or 5)):
            return None                  # la scritta c'e' solo finche' sono li': se la foto e' vecchia no
        self.prossima_scritta = t + 1.5
        self._cammina()
        tieni = c.prompt == "open"
        nome = {"open": "Apri", "pick_up": "Raccogli", "zipline": "zipline", "door": "porta"}[c.prompt]
        self.log("IA: sullo schermo c'e' '%s' -> %s E" % (nome, "tengo premuto" if tieni else "premo"))
        self.mani.giu("interagisci")
        try:
            self.esecutore.dormi(float(self.racc.get("tempo_apertura_cassa", 1.2)) if tieni else 0.12)
        finally:
            self.mani.su("interagisci")
        self.cammino_fino = 0.0
        self.apri_all_arrivo = False
        if c.prompt == "open":
            self._cassa_aperta(c, t)
            return "apro la cassa (IA)"
        if c.prompt == "pick_up":
            self.statistiche["armi"] = self.statistiche.get("armi", 0) + 1
            return "raccolgo (IA)"
        if c.prompt == "door":
            self._cammina(avanti=True)
            return "apro la porta"
        return "prendo la zipline"

    def _premi_e_sulla_scritta(self, t):
        """SENZA IA: a destra del mirino c'e' una scritta (davanti a una cassa c'e' "E Apri"; poi
        "Raccogli", "Rianima", "Assolda"...): tengo premuto E. Se la scritta sparisce ha funzionato:
        raccolgo quello che e' uscito (e, se e' una cassa, la spacco col piccone: si dice che cosi'
        si tira una seconda volta per il token, ma Epic non l'ha mai confermato)."""
        self.prossima_scritta = t + 2.0
        self._cammina()
        self.log("Vedo una scritta (Apri / Raccogli / ...): tengo premuto E")
        self.mani.giu("interagisci")
        try:
            self.esecutore.dormi(float(self.racc.get("tempo_apertura_cassa", 1.2)))
        finally:
            self.mani.su("interagisci")
        self.statistiche["scritte_e"] = self.statistiche.get("scritte_e", 0) + 1
        dopo = self.esecutore.foto_fresca()
        if dopo is not None and hud.scritta_interazione(dopo):
            self.prossima_scritta = t + 6.0                 # non e' servito: non insisto
            return "premo E sulla scritta"
        self.statistiche["casse"] = self.statistiche.get("casse", 0) + 1
        self.statistiche["casse_partita"] = self.statistiche.get("casse_partita", 0) + 1
        self.log("Fatto (cassa aperta o oggetto preso: %d in questa partita)" % self.statistiche["casse_partita"])
        self.cassa_da = None
        self.cassa_ultima = None
        self.cassa_conta = 0
        self.casse_sbagliate = []
        if self.fort.get("spacca_cassa_dopo_aperta", True) and self.mani.esiste("piccone"):
            self.mani.premi("piccone", 0.08)
            self.mani.imposta("spara", True)
            try:
                self.esecutore.dormi(float(self.fort.get("spacca_cassa_secondi", 1.2) or 1.2))
            finally:
                self.mani.imposta("spara", False)
        for _ in range(int(self.racc.get("raccogli_volte", 4) or 4)):
            self.mani.premi("interagisci", 0.08)
            self._cammina(avanti=True)
            self.esecutore.dormi(0.15)
            self._cammina()
        self._prendi_arma(self.lavagna.consiglio, t, subito=True)
        return "apro la cassa / raccolgo"

    def _cassa_aperta(self, c, t):
        self.statistiche["casse"] = self.statistiche.get("casse", 0) + 1
        self.statistiche["casse_partita"] = self.statistiche.get("casse_partita", 0) + 1
        self.log("Cassa aperta! (in questa partita: %d)" % self.statistiche["casse_partita"])
        # come in Fortnite: la cassa butta le cose per terra davanti; le raccolgo e riprendo l'arma
        for _ in range(int(self.racc.get("raccogli_volte", 4) or 4)):
            self.mani.premi("interagisci", 0.08)
            self._cammina(avanti=True)
            self.esecutore.dormi(0.15)
            self._cammina()
        self._prendi_arma(c, t, subito=True)

    # ================================================================== 7. arma e cure
    def _ramo_arma_e_cure(self, vis, img, t):
        lv = self.lavagna
        if lv.nemici:
            return None
        c = lv.consiglio
        if c is not None and lv.nuovo and c.fase == "playing":
            if c.poca_vita and t >= self.prossima_cura and self.fort.get("cura_con_ia", True):
                n = c.slot_cura - 1 if c.slot_cura and c.slot_cura != 1 else int(self.fort.get("slot_cure", 5) or 5)
                tasto = self._tasto_arma(n)
                if tasto:
                    self.prossima_cura = t + 10.0
                    secondi = float(self.fort.get("cura_secondi", 5) or 5)
                    self.log("IA: ho poca vita -> mi curo (slot %d)" % n)
                    self._cammina()
                    self.mani.premi(tasto, 0.08)
                    self.esecutore.dormi(0.3)
                    self.mani.imposta("spara", True)
                    try:
                        self.esecutore.dormi(secondi)
                    finally:
                        self.mani.imposta("spara", False)
                    self._prendi_arma(c, t, subito=True)
                    return "mi curo"
            # l'IA vede il piccone in mano: prendo lo slot 1; se resta il piccone, lo slot che dice lei
            if c.in_mano in ("pickaxe", "other") and c.ha_arma is not False and t >= self.prossimo_cambio_arma:
                self.tentativi_arma += 1
                if self.tentativi_arma >= 2 and c.slot_arma and c.slot_arma != 1:
                    n = c.slot_arma - 1
                else:
                    n = int(self.fort.get("slot_in_mano", 1) or 1)
                tasto = self._tasto_arma(n)
                if tasto:
                    self.prossimo_cambio_arma = t + 2.0
                    self.log("IA: in mano ho %s -> prendo l'arma (slot %d)" % (
                        "il piccone" if c.in_mano == "pickaxe" else "altro", n))
                    self.mani.premi(tasto, 0.08)
            elif c.in_mano == "weapon":
                self.tentativi_arma = 0
        # SENZA IA: leggo la vita e lo scudo dalle barre; se sono bassi e non ci sono nemici, mi curo
        if (lv.vita is not None and lv.barra and not lv.bus and self.salto_da is None
                and t - self.stato.get("ultimo_nemico", 0) >= 3.0 and t >= self.prossima_cura
                and self.fort.get("cura_da_sola", True)):
            poca_vita = lv.vita < float(self.fort.get("cura_sotto_vita", 70) or 70)
            # lo scudo solo se c'era e si e' consumato (0 = non ho mai avuto scudi: niente da bere)
            poco_scudo = lv.scudo is not None and 0 < lv.scudo < float(self.fort.get("cura_sotto_scudo", 50) or 0)
            if poca_vita or poco_scudo:
                return self._usa_le_cure(t, lv.vita, lv.scudo)
        # SEMPRE la mitra in mano (slot 1) mentre giro, anche senza IA (se lo slot e' vuoto non cambia niente)
        if lv.barra and not lv.bus and self.salto_da is None and t >= self.prossimo_slot \
                and self.fort.get("tieni_arma_in_mano", True):
            self.prossimo_slot = t + float(self.fort.get("riprendi_arma_ogni_secondi", 8) or 8)
            tasto = self._tasto_arma(int(self.fort.get("slot_in_mano", 1) or 1))
            if tasto:
                self.mani.premi(tasto, 0.06)
        return None                              # cambiare arma non ferma il resto

    def _usa_le_cure(self, t, vita, scudo):
        """Prendo lo slot delle cure (5, come negli slot preferiti), tengo premuto e poi controllo se
        vita o scudo sono saliti. Se due volte non succede niente, nello slot non ci sono cure: per
        un paio di minuti non ci riprovo."""
        n = int(self.fort.get("slot_cure", 5) or 5)
        tasto = self._tasto_arma(n)
        if not tasto:
            return None
        self.prossima_cura = t + 15.0
        secondi = float(self.fort.get("cura_secondi", 5) or 5)
        self.log("Ho %d di vita e %s di scudo: uso le cure (slot %d)" % (vita, scudo if scudo is not None else "?", n))
        self._cammina()
        self.mani.premi(tasto, 0.08)
        self.esecutore.dormi(0.3)
        self.mani.imposta("spara", True)
        try:
            self.esecutore.dormi(secondi)
        finally:
            self.mani.imposta("spara", False)
        v2, s2 = hud.leggi_vita(self.esecutore.foto_fresca())
        if v2 is not None and v2 <= vita and (s2 or 0) <= (scudo or 0):
            self.cure_fallite += 1
            if self.cure_fallite >= 2:
                self.cure_fallite = 0
                self.prossima_cura = t + 120.0
                self.log("Nello slot %d non ci sono cure (o sono finite): riprovo tra 2 minuti" % n)
        else:
            self.cure_fallite = 0
        self._prendi_arma(self.lavagna.consiglio, t, subito=True)
        return "mi curo"

    # ================================================================== 7b. rianimo il compagno
    def _ramo_rianima(self, vis, img, t):
        """Come i compagni assoldati (comando "Rianima"): un compagno a terra -> corro da lui e
        tengo premuto E finche' non si rialza."""
        lv = self.lavagna
        if not self.fort.get("rianima_compagni", True) or lv.nemici:
            return None
        if t < self.cammino_fino and self.cammino_cosa == "rianima":
            self._cammina(avanti=True, corri=True)
            self._controlla_blocco(img, t)
            return "vado dal compagno a terra"
        c = lv.consiglio
        a_terra = getattr(c, "compagno", "none") if c is not None else "none"
        if c is None or not lv.nuovo or c.fase != "playing" or a_terra in (None, "none"):
            return None
        if a_terra == "close":
            if not self.mani.esiste("interagisci"):
                return None
            self.log("IA: un compagno e' a terra qui vicino -> lo rianimo (tengo premuto E)")
            self._cammina()
            self.mani.giu("interagisci")
            try:
                self.esecutore.dormi(float(self.fort.get("rianima_secondi", 10) or 10))
            finally:
                self.mani.su("interagisci")
            self.statistiche["rianimati"] = self.statistiche.get("rianimati", 0) + 1
            return "rianimo un compagno"
        gradi = {"left": -35.0, "center": 0.0, "right": 35.0}.get(a_terra)
        if gradi is None:
            return None
        allora = self.guardo_al_tempo(c.quando) if self.storia_guardo else None
        if allora is not None and lv.guardo is not None:
            self._gira(avvolgi(allora + gradi - lv.guardo))
        else:
            self._gira(gradi)
        self.log("IA: un compagno e' a terra (%s) -> corro da lui" % a_terra)
        self.cammino_cosa = "rianima"
        self.cammino_fino = t + 2.0
        self._cammina(avanti=True, corri=True)
        return "vado dal compagno a terra"

    # ================================================================== 8. ogni tanto
    def _ramo_manutenzione(self, vis, img, t):
        """Misuro la sensibilita' con la bussola (appena atterrato) e ogni tanto l'IA guarda la mappa."""
        if self.lavagna.nemici:
            return None
        if self.calibra_da is not None and t >= self.calibra_da:
            self.calibra_da = None
            scritta = self._calibra_bussola(t)
            if scritta:
                return scritta
        ogni = float(self.fort.get("mappa_ogni_secondi", 60) or 0)
        if ogni > 0 and self.ia is not None and t >= self.prossima_mappa_periodica:
            self.prossima_mappa_periodica = t + ogni
            self._mappa_in_sottofondo(t, "Controllo")
        if self.apprendimento is not None and img is not None:
            self.apprendimento.forse_salva_foto(img, vis, t)
        return None

    # ================================================================== 9a. la cassa che vedo
    @staticmethod
    def _e_un_nome(img, b):
        """La macchia gialla e' il rombo di un NOME (es. "◆deandombo" sopra un compagno)? A destra
        c'e' una riga di lettere bianche."""
        if img is None:
            return False
        H, W = img.shape[:2]
        sx, sy = img.shape[1] / float(W), img.shape[0] / float(H)
        x0 = int(b.x + b.w + 1)
        x1 = int(min(W, b.x + b.w + 0.08 * W))
        y0 = int(max(0, b.cy - 0.012 * H))
        y1 = int(min(H, b.cy + 0.012 * H))
        pezzo = img[int(y0 * sy):int(y1 * sy), int(x0 * sx):int(x1 * sx)]
        return pezzo.size > 0 and int((pezzo.min(axis=2) > 200).sum()) >= 15

    def _casse_buone(self, vis, t, img=None):
        """Le casse viste dagli occhi (luce dorata), senza quelle finte: la punta del piccone in mano,
        le icone e le scritte dello schermo, la minimappa, le "casse" che ho gia' provato ad aprire."""
        W, H = float(vis.larghezza), float(vis.altezza)
        guardo = self.lavagna.guardo
        self.casse_ignorate = [(g, f) for g, f in self.casse_ignorate if f > t]
        buone = []
        for b in vis.casse:
            x, y, w = b.cx / W, b.cy / H, b.w / W
            if 0.51 <= x <= 0.60 and 0.52 <= y <= 0.72:
                continue                  # la punta del piccone che ho in mano
            if y < 0.30 or y > 0.86 or (x > 0.80 and y < 0.32) or (x < 0.25 and y > 0.55):
                continue                  # cielo e scritte in alto, minimappa, compagni, uccisioni
            if not 0.012 <= w <= 0.15:
                continue                  # troppo piccola (fiori gialli, scintille) o troppo grande
            if self._e_un_nome(img, b):
                continue                  # il rombo giallo davanti al nome di un compagno
            if guardo is not None:
                gradi = (guardo + self._gradi_schermo(x)) % 360.0
                if any(abs(avvolgi(gradi - g)) <= 12 for g, f in self.casse_ignorate):
                    continue
            buone.append(b)
        if len(buone) > 3:
            return []                     # tante macchie dorate insieme: fiori, tramonto, non casse
        return buone

    def _ramo_cassa_vista(self, vis, img, t):
        """APPENA VEDO UNA CASSA CI VADO INCONTRO: la metto al centro del mirino (anche guardando un
        po' in basso) e cammino. Quando sono davanti compare "E Apri" e il ramo delle scritte tiene E.
        Se in 7 secondi non succede niente non era una cassa: per un po' la ignoro."""
        lv = self.lavagna
        if (not self.racc.get("casse", True) or not self.fort.get("vai_alle_casse_viste", True) or lv.nemici
                or not (lv.barra or not self.fort.get("leggi_lo_schermo", True)) or lv.bus or self.salto_da is not None
                or t < self.casse_pausa_fino):
            self.cassa_conta = 0
            self.cassa_da = None
            return None
        buone = self._casse_buone(vis, t, img)
        W, H = float(vis.larghezza), float(vis.altezza)
        mx, my = self._mirino(vis)
        if self.cassa_da is None:
            self.cassa_conta = self.cassa_conta + 1 if buone else 0
            if self.cassa_conta < int(self.fort.get("cassa_conferma_volte", 2) or 2):
                return None
            self.cassa_da = t
            self.cassa_ultima = None
            self.log("Vedo una cassa: ci vado incontro e la apro")
        # la cassa da seguire: la piu' vicina a dove era (all'inizio la piu' grande, cioe' la piu' vicina)
        if buone:
            if self.cassa_ultima is not None and t - self.cassa_ultima[2] < 1.5:
                px, py = self.cassa_ultima[0] * W, self.cassa_ultima[1] * H
                b = min(buone, key=lambda q: math.hypot(q.cx - px, q.cy - py))
            else:
                b = max(buone, key=lambda q: q.w * q.h)
            self.cassa_ultima = (b.cx / W, b.cy / H, t)
        b_xy = self.cassa_ultima
        if b_xy is None or t - b_xy[2] > 1.5 or t - self.cassa_da > float(self.fort.get("cassa_secondi_massimi", 7) or 7):
            # persa o non si apre: provo E una volta (se sono gia' davanti) e poi la lascio stare
            if lv.guardo is not None and b_xy is not None:
                self.casse_ignorate.append(((lv.guardo + self._gradi_schermo(b_xy[0])) % 360.0, t + 60.0))
            self.casse_sbagliate = [x for x in self.casse_sbagliate if t - x < 40.0] + [t]
            if len(self.casse_sbagliate) >= 2:
                self.casse_pausa_fino = t + 20.0   # due "casse" finte di fila: per un po' non ci credo
                self.casse_sbagliate = []
            self.cassa_da = None
            self.cassa_ultima = None
            self.cassa_conta = 0
            self._cammina()
            if self.mani.esiste("interagisci"):
                self.mani.giu("interagisci")
                try:
                    self.esecutore.dormi(float(self.racc.get("tempo_apertura_cassa", 1.2)))
                finally:
                    self.mani.su("interagisci")
            return "provo ad aprire la cassa"
        if t - b_xy[2] < 0.3:                      # appena vista: la metto nel mirino
            ex, ey = b_xy[0] * W - mx, b_xy[1] * H - my
            forza = 0.5
            dy = ey / self.ppp * forza
            limite = self.passi_per_giro / 6.0          # al massimo un po' in basso (le casse sono per terra)
            dy = max(-limite - self.pitch, min(limite - self.pitch, dy))
            self.mani.mira_fluida(ex / self.ppp * forza, dy, max(0.02, self.dt_medio))
            self.pitch += dy
            dritto = abs(ex) < 0.15 * W
        else:
            dritto = True                          # non la vedo (e' sotto il mirino): vado avanti
        self._cammina(avanti=dritto)
        self._controlla_blocco(img, t)
        return "vado verso la cassa che vedo"

    # ================================================================== 9. bottino
    def _ramo_bottino(self, vis, img, t):
        lv = self.lavagna
        if t < self.cammino_fino and self.cammino_cosa in NOMI_COSE:
            if self.meta_bottino is not None:
                self._vai_verso(self.meta_bottino[0], t)
            self._cammina(avanti=True)
            self._controlla_blocco(img, t)
            return "vado verso %s (IA)" % NOMI_COSE[self.cammino_cosa]
        if self.apri_all_arrivo and self.mani.esiste("interagisci"):
            # arrivato dove l'IA vedeva la cassa: provo ad aprirla (se non c'e', E non fa niente)
            self.apri_all_arrivo = False
            self.cammino_cosa = ""
            self._cammina()
            self.log("Arrivato dove c'era la cassa: tengo premuto E")
            self.mani.giu("interagisci")
            try:
                self.esecutore.dormi(float(self.racc.get("tempo_apertura_cassa", 1.2)))
            finally:
                self.mani.su("interagisci")
            for _ in range(2):
                self.mani.premi("interagisci", 0.08)
                self.esecutore.dormi(0.1)
            self._prendi_arma(lv.consiglio, t, subito=True)
            return "provo ad aprire la cassa"
        if not self.racc.get("casse", True):
            return None
        c = lv.consiglio
        mb = self.meta_bottino
        valida = float(self.fort.get("bottino_valido_secondi", 20) or 20)
        if c is not None and lv.nuovo and c.fase == "playing" and c.obiettivo is not None:
            cosa, x, y = c.obiettivo
            gradi = self._gradi_schermo(x)
            self.bottino_usato = c.quando
        elif (mb is not None and t - mb[3] <= valida and mb[1] in ("chest", "weapon", "ammo_box")
              and lv.guardo is not None and self.bottino_usato != mb[3]):
            # l'IA ha risposto in ritardo ma la cassa l'ha vista: la direzione della bussola vale ancora
            cosa, y, gradi = mb[1], mb[2], None
            self.bottino_usato = mb[3]
        else:
            return None
        if cosa == "weapon" and not self.racc.get("armi", True):
            return None
        if mb is not None and lv.guardo is not None:
            self._vai_verso(mb[0], t)
        elif gradi is not None:
            self._gira(gradi)
        # piu' e' in alto sullo schermo, piu' e' lontana: cammino di piu'
        self.cammino_fino = t + 1.0 + 2.5 * max(0.0, min(1.0, (0.85 - y) / 0.5))
        if cosa != self.cammino_cosa:
            self.log("IA: vedo %s -> ci vado (poi torno dal compagno)" % NOMI_COSE[cosa])
        self.cammino_cosa = cosa
        self.apri_all_arrivo = cosa in ("chest", "ammo_box")
        self._cammina(avanti=True)
        return "vado verso %s (IA)" % NOMI_COSE[cosa]

    # ================================================================== 10. seguo il compagno
    def _direzione_compagno(self, t):
        """Dove e' il compagno (gradi della bussola): detto dall'IA o visto sulla bussola."""
        mc = self.meta_compagno
        if mc is not None and t - mc[2] <= float(self.fort.get("segui_memoria_secondi", 12) or 12):
            return mc[0]
        if self.compagno_hud is not None and t - self.compagno_hud_t <= 6.0:
            return self.compagno_hud
        return None

    def _ramo_compagno(self, vis, img, t):
        """IL GUINZAGLIO, come i compagni assoldati in Fortnite (nell'esempio di Epic: "stare tra 5 e
        10 metri"): oltre il raggio esterno corro da lui; dentro quello interno resto li' e mi guardo
        intorno (come le guardie). Due raggi diversi, cosi' non faccio avanti e indietro."""
        if not self.fort.get("segui_compagno", True):
            return None
        lv = self.lavagna
        if lv.guardo is not None:
            mc = self.meta_compagno
            ia_fresca = mc is not None and t - mc[2] <= float(self.fort.get("segui_memoria_secondi", 12) or 12)
            visto = t - self.compagno_hud_t
            if ia_fresca:
                gradi = mc[0]
            elif self.compagno_hud is not None and visto <= float(self.fort.get("aspetta_compagno_secondi", 12) or 12):
                gradi = self.compagno_hud
            else:
                gradi = None
            if gradi is not None:
                metri = mc[1] if mc is not None and t - mc[2] <= 6.0 else None
                dist = self.compagno_dist if t - self.compagno_dist_t <= 2.0 else None
                fermo = self.al_guinzaglio_fermo
                if metri is not None:
                    limite = self.fort.get("guinzaglio_metri_lontano", 10) if fermo else \
                        self.fort.get("guinzaglio_metri_vicino", 5)
                    vicino = metri <= float(limite or 5)
                elif dist is not None:
                    limite = self.fort.get("guinzaglio_lontano", 0.18) if fermo else self.fort.get("guinzaglio_vicino", 0.08)
                    vicino = dist <= float(limite or 0.08)
                else:
                    # non so quanto e' lontano: se da un po' non lo vedo piu' ne' ai bordi ne' sopra la
                    # bussola, e' davanti a me sullo schermo: cammino ancora un po' verso di lui (per
                    # raggiungerlo) e poi lo aspetto qui
                    vicino = not ia_fresca and visto > 1.5 + float(self.fort.get("raggiungi_compagno_secondi", 3) or 3)
                if vicino:
                    if not fermo:
                        self.log("Sono vicino al compagno: resto qui e mi guardo intorno")
                    self.al_guinzaglio_fermo = True
                    self.cammino_cosa = ""
                    self._cammina()
                    self._pattuglia(t, gradi)
                    return "sto vicino al compagno"
                self.al_guinzaglio_fermo = False
                if lv.mini.ok:
                    gradi = lv.mini.direzione_sicura(gradi, 10)      # non dietro di lui nel mare
                if self.cammino_cosa != "compagno":
                    self.log("Seguo il compagno di squadra (verso %.0f gradi%s)" % (
                        gradi, ", %.0f metri" % metri if metri is not None else
                        (", sulla minimappa a %.0f%% dal centro" % (100 * dist) if dist is not None else "")))
                self.cammino_cosa = "compagno"
                girato = self._vai_verso(gradi, t)
                corri = dist is None or dist > float(self.fort.get("guinzaglio_corri", 0.25) or 0.25)
                self._cammina(avanti=True, corri=corri)
                self._controlla_blocco(img, t)
                lontano = (dist is not None and dist >= 0.7) or (metri is not None and metri >= 80) or \
                    (self.compagno_fonte == "bussola" and visto <= 1.5)
                if lontano and not girato and lv.guardo is not None and abs(avvolgi(gradi - lv.guardo)) < 20 \
                        and not lv.in_acqua and self._lancio_impulso(t, "il compagno e' lontano"):
                    return "volo con l'impulso verso il compagno"
                return "seguo il compagno"
        if t < self.fermo_fino:
            self._cammina()
            return "sto vicino al compagno"
        # senza bussola: come prima, con quello che vede l'IA sullo schermo
        if t < self.cammino_fino and self.cammino_cosa == "compagno":
            self._cammina(avanti=True, corri=True)
            self._controlla_blocco(img, t)
            return "seguo il compagno"
        c = lv.consiglio
        if c is None or not lv.nuovo or c.fase != "playing" or c.compagno_xy is None:
            return None
        x, y, lato, metri = c.compagno_xy
        if lato == "on_screen":
            gradi = self._gradi_schermo(x)
        else:
            gradi = LATO_GRADI[lato]
        self._gira(gradi if abs(gradi) > 8 else 0)
        if lato == "on_screen" and metri is not None and metri <= float(self.fort.get("segui_vicino_metri", 8) or 8):
            self._cammina()
            self.fermo_fino = t + 2.0
            return "sto vicino al compagno"
        if self.cammino_cosa != "compagno":
            self.log("Seguo il compagno di squadra (%s)" % ("%.0f metri" % metri if metri is not None else lato))
        self.cammino_cosa = "compagno"
        self.cammino_fino = t + (2.5 if metri is None or metri > 30 else 1.2)
        self._cammina(avanti=True, corri=True)
        return "seguo il compagno"

    def _pattuglia(self, t, centro):
        """Vicino al compagno mi guardo intorno piano (come le guardie): cosi' vedo i nemici che
        arrivano e, se lui si sposta, lo ritrovo ai bordi dello schermo."""
        if self.lavagna.guardo is None:
            return
        ampiezza = float(self.fort.get("guarda_intorno_gradi", 60) or 60)
        periodo = float(self.fort.get("guarda_intorno_secondi", 8) or 8)
        self._tieni_rotta(t, centro + ampiezza * math.sin(2.0 * math.pi * t / periodo))

    # ================================================================== 11. viaggio
    def _ramo_viaggio(self, vis, img, t):
        lv = self.lavagna
        m = lv.mini
        stato = "esploro"
        lontano = m.lontano_dalla_tempesta() if m.ok else None
        if lontano is not None:
            self.rotta = lontano
            stato = "mi allontano dalla tempesta"
        elif self.rotta_ia is not None and t - self.rotta_ia_t < float(self.fort.get("mappa_valida_secondi", 90) or 90):
            self.rotta = self.rotta_ia
        if self.rotta is not None and lv.guardo is not None:
            voluta = m.direzione_sicura(self.rotta, 10) if m.ok else self.rotta
            errore = avvolgi(voluta - lv.guardo)
            if abs(errore) > 100 and t - self.ultimo_sblocco > 6.0 and t >= self.prossima_svolta:
                self.log("Riprendo la rotta (giro di %.0f gradi)" % errore)
            self._vai_verso(voluta, t)
            if stato == "esploro":
                stato = "vado verso il centro della zona sicura"
        elif lv.guardo is not None and m.ok and m.pericolo_davanti(lv.guardo, 10):
            nuova = m.direzione_sicura(lv.guardo, 10)
            if t >= self.prossima_svolta:
                self.log("Davanti c'e' il mare: giro verso %.0f gradi" % nuova)
            self._vai_verso(nuova, t)
            stato = "giro: davanti c'e' il mare"
        if self.espl.get("rimetti_visuale_dritta", True) and abs(self.pitch) > 3:
            self.mani.muovi(0, -self.pitch * 0.15)
            self.pitch *= 0.85
        self._cammina(avanti=True, corri=bool(self.espl.get("corri", True)))
        self._controlla_blocco(img, t)
        return stato

    # ================================================================== bloccato
    def _controlla_blocco(self, img, t):
        """Se cammino ma i LATI dello schermo non cambiano sono bloccato: salto; se ancora, mi giro
        di lato e faccio qualche passo (poi la bussola mi rimette sulla mia strada); a volte
        sfondo col piccone (F)."""
        if img is None or t - self.t_mini < 0.25:
            return False
        self.t_mini = t
        H, W = img.shape[:2]
        lati = np.hstack([img[int(0.3 * H):int(0.85 * H), int(0.04 * W):int(0.3 * W)],
                          img[int(0.3 * H):int(0.85 * H), int(0.7 * W):int(0.96 * W)]])
        mini = cv2.resize(cv2.cvtColor(lati, cv2.COLOR_BGR2GRAY), (48, 28), interpolation=cv2.INTER_AREA)
        if self.mini_prec is not None:
            if float(np.mean(cv2.absdiff(mini, self.mini_prec))) >= float(self.espl.get("sensibilita_blocco", 2.5)):
                self.ultimo_mosso = t
                self.fermo_conta = 0
            else:
                self.fermo_conta += 1
        self.mini_prec = mini
        self.stato["fermo_da"] = t - self.ultimo_mosso
        if self.fermo_conta < int(self.espl.get("controlli_blocco", 3) or 3):
            return False
        self.fermo_conta = 0
        di_nuovo = t - self.ultimo_sblocco < 4.0
        self.ultimo_sblocco = t
        self.statistiche["bloccato"] = self.statistiche.get("bloccato", 0) + 1
        self.mini_prec = None
        if not di_nuovo:
            self.log("Sono bloccato: salto")
            if self.mani.esiste("salta"):
                self.mani.premi("salta")
            return True
        if self.fort.get("piccona_i_muri", True) and self.mani.esiste("piccone") and random.random() < 0.35:
            self.log("Sono ancora bloccato: sfondo col piccone")
            self.mani.premi("piccone", 0.08)
            self.mani.imposta("spara", True)
            try:
                self.esecutore.dormi(float(self.fort.get("piccona_secondi", 1.5) or 1.5))
            finally:
                self.mani.imposta("spara", False)
            self._prendi_arma(self.lavagna.consiglio, t, subito=True)
            return True
        self.verso_sblocco = -self.verso_sblocco
        self.log("Sono ancora bloccato: mi giro di lato, faccio qualche passo e poi torno sulla mia strada")
        if self.mani.esiste("salta"):
            self.mani.premi("salta")
        self.esecutore.gira(self.verso_sblocco * random.uniform(60, 100))
        self.deviazione_fino = t + float(self.fort.get("aggira_secondi", 1.8) or 1.8)
        return True

    # ================================================================== mappa e bussola
    def _bussola_ferma(self):
        """Leggo la bussola da una foto nuova (senza IA); se non ci riesco la chiedo all'IA."""
        for _ in range(3):
            foto = self.esecutore.foto_fresca()
            g = hud.leggi_bussola(foto) if foto is not None else None
            if g is not None:
                return float(g)
            self.esecutore.dormi(0.1)
        return self._leggi_bussola_ia(self.esecutore.foto_fresca())

    def _leggi_bussola_ia(self, foto):
        from ia import DOMANDA_BUSSOLA
        if foto is None or self.ia is None or not hasattr(self.ia, "chiedi_voto"):
            return None
        h, w = foto.shape[:2]
        striscia = foto[0:max(1, int(0.075 * h)), int(0.3 * w):int(0.7 * w)]
        striscia = cv2.resize(striscia, (1024, max(1, int(striscia.shape[0] * 1024 / float(striscia.shape[1])))),
                              interpolation=cv2.INTER_CUBIC)
        gradi = []
        for r in self.ia.chiedi_voto(striscia, DOMANDA_BUSSOLA, 3, attesa=8.0):
            try:
                g = float(r.get("heading"))
            except (TypeError, ValueError):
                continue
            if 0 <= g <= 360:
                gradi.append(g % 360)
        if not gradi:
            return None
        gruppi = [[x for x in gradi if abs(avvolgi(x - g)) <= 15] for g in gradi]
        return angolo_medio(max(gruppi, key=len))

    def _calibra_bussola(self, t):
        """Misuro QUANTO MI GIRO DAVVERO: bussola, giro di 60 gradi secondo i miei conti, bussola."""
        if not self.fort.get("calibra_con_bussola", True):
            return None
        self.ferma_tutto()
        prima = self._bussola_ferma()
        if prima is None:
            self.calibra_da = t + 30.0
            return None
        voluti = float(self.fort.get("calibra_bussola_gradi", 60) or 60)
        self.esecutore.gira(voluti, durata=0.3)
        self.esecutore.dormi(0.4)
        dopo = self._bussola_ferma()
        if dopo is None:
            self.calibra_da = t + 30.0
            return "leggo la bussola"
        self.ultima_calibrazione = t
        girati = (dopo - prima) % 360.0
        self._leggi_bussola(dopo)
        if girati < 10 or girati > 350:
            self.log("Bussola: ho mosso il mouse ma la visuale non si e' girata")
            return "leggo la bussola"
        vecchi = self.passi_per_giro
        nuovi = vecchi * voluti / girati
        if abs(girati - voluti) <= 6:
            self.log("Bussola: giro giusto (%.0f gradi su %.0f): la sensibilita' va bene" % (girati, voluti))
            return "leggo la bussola"
        if not 0.25 <= nuovi / vecchi <= 4.0:
            self.log("Bussola: misura strana (%.0f gradi invece di %.0f): non cambio niente" % (girati, voluti))
            return "leggo la bussola"
        self.log("Bussola: volevo girarmi di %.0f gradi e mi sono girato di %.0f -> correggo la sensibilita' "
                 "(passi per un giro: %.0f -> %.0f)" % (voluti, girati, vecchi, nuovi))
        self._imposta_passi_per_giro(nuovi)
        return "correggo la sensibilita'"

    def _mappa_in_sottofondo(self, t, motivo):
        """Apro la mappa grande (M) un attimo, faccio la foto e la richiudo: le IA la guardano
        mentre IO CONTINUO A GIOCARE. Quando rispondono, la loro direzione diventa la rotta.
        -> True se le risposte sono gia' arrivate."""
        if (self.ia is None or not hasattr(self.ia, "chiedi_voto") or not self.mani.esiste("mappa")
                or not self.fort.get("guarda_mappa", True) or t < self.prossima_mappa
                or (self.filo_mappa is not None and self.filo_mappa.is_alive())):
            return False
        from ia import DOMANDA_MAPPA
        self.prossima_mappa = t + float(self.fort.get("mappa_non_prima_di_secondi", 20) or 20)
        self.log("%s: guardo la mappa (l'IA risponde mentre continuo a giocare)" % motivo)
        gioco = self.esecutore.foto_fresca()
        self.mani.premi("mappa", 0.1)
        self.esecutore.dormi(float(self.fort.get("mappa_attesa_secondi", 1.3) or 1.3))
        mappa = self.esecutore.foto_fresca()
        self.mani.premi("mappa", 0.1)
        self.esecutore.dormi(0.3)
        if mappa is None:
            return False
        foto = mappa_con_bussola(mappa, gioco)
        quante = int(self.fort.get("mappa_quante_ia", 3) or 3)
        attesa = float(self.fort.get("mappa_attesa_ia_secondi", 30) or 30)

        def chiedi():
            try:
                risposte = self.ia.chiedi_voto(foto, DOMANDA_MAPPA, quante, attesa=attesa)
            except Exception as e:
                self.log("Mappa: %s" % e)
                risposte = []
            self.risposte_mappa = (risposte, t)

        self.filo_mappa = threading.Thread(target=chiedi, daemon=True)
        self.filo_mappa.start()
        self.filo_mappa.join(0.2)                 # se rispondono subito le uso subito
        return self._applica_mappa(t)

    def _applica_mappa(self, t):
        """Le risposte delle IA sulla mappa (appena arrivate): vince la maggioranza."""
        if self.risposte_mappa is None:
            return False
        from ia import BUSSOLA, _si
        risposte, quando = self.risposte_mappa
        self.risposte_mappa = None
        dentro = [_si(r.get("inside")) for r in risposte if "inside" in r]
        bordo = [_si(r.get("near_edge")) for r in risposte if "near_edge" in r]
        sicura = [str(r.get("safe", "")).strip().upper() for r in risposte]
        sicura = [v for v in sicura if v in BUSSOLA or v == "HERE"]
        letti = []
        for r in risposte:
            try:
                g = float(r.get("heading"))
            except (TypeError, ValueError):
                continue
            if 0 <= g <= 360:
                letti.append(g % 360)
        if letti and t - self.ultima_bussola_hud > 10.0:
            self._leggi_bussola(angolo_medio(letti), quando)       # solo se io non la leggo da solo
            self.lavagna.guardo = self.guardo_verso()
        scelta = Counter(sicura).most_common(1)[0][0] if sicura else None
        if scelta == "HERE":
            self.log("Mappa: sono al centro della zona sicura")
            self.rotta_ia = None
            return True
        if scelta is None:
            self.log("Mappa: le IA non hanno risposto (%d risposte): continuo con la minimappa" % len(risposte))
            return False
        self.rotta_ia = float(BUSSOLA[scelta])
        self.rotta_ia_t = t
        sono_dentro = bool(dentro) and sum(dentro) * 2 > len(dentro)
        al_bordo = bool(bordo) and sum(bordo) * 2 > len(bordo)
        self.log("Mappa: la zona sicura e' a %s (voti: %s)%s" % (
            scelta, ", ".join(sicura), "; ci sono dentro" if sono_dentro and not al_bordo else ""))
        return True
