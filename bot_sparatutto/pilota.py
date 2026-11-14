"""
pilota.py - IL CERVELLO NUOVO (rifatto da zero, novembre 2026).

Fatto come i bot dei giochi fatti con Unreal Engine (Fortnite compreso): una LAVAGNA con quello
che il bot sa adesso (dai suoi occhi veloci e dall'IA che guarda) e un ALBERO DI COMPORTAMENTI:
un elenco di "rami" in ordine di importanza. A ogni fotogramma si prende il PRIMO ramo che serve
e si fa SOLO quello. Niente pezzi che litigano tra loro.

L'ORDINE (dal piu' importante):
  1. le tue istruzioni (istruzioni.txt) e il pulsante giallo "Gioca di nuovo"
  2. schermi strani: PS5 "Chi sta usando...?", PS Remote Play scollegato, desktop
  3. fasi: menu / eliminato (guarda il compagno e poi torna alla lobby) / bus / caduta
  4. PERICOLO: tempesta o acqua -> verso il centro della zona sicura (mappa + bussola), nient'altro
  5. NEMICO: arma in mano, mira, spara
  6. SCRITTA sullo schermo: Apri / Raccogli / porta / zipline -> E
  7. ARMA in mano e CURE (gli slot giusti li dice l'IA)
  8. SEGUO IL COMPAGNO (come i bot che si assoldano in Fortnite)
  9. BOTTINO: la cassa (o la casa, o l'arma) che vede l'IA
 10. VIAGGIO: verso il centro della zona sicura (la rotta), guardando la mappa ogni tanto

Dove guardo lo so dalla BUSSOLA (il numero in alto, letto dall'IA) piu' quanto ho girato col
mouse da allora. Appena atterrato misuro con la bussola quanto mi giro davvero (sensibilita').

Il cervello vecchio (cervello.py) resta: in impostazioni.yaml -> fortnite -> cervello: vecchio
"""

import math
import random
import time
from collections import Counter

import cv2
import numpy as np

import impostazioni
from cervello import acqua, angolo_medio, mappa_con_bussola, trova_pulsante_giallo, viola
from obiettivo import Obiettivo
from stile import STILI

NOMI_COSE = {"chest": "una cassa", "weapon": "un'arma per terra", "ammo_box": "una cassa di munizioni",
             "building": "una casa (dentro ci sono le casse)"}


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
        # navigazione
        self.rotta = None                 # gradi della bussola verso il centro della zona sicura
        self.bussola_rif = None           # (gradi letti, passi del mouse in quel momento)
        self.storia_passi = []
        self.prossima_mappa = 0.0
        self.prossima_mappa_periodica = adesso + 30.0
        self.fuga_fino = 0.0              # scappo da tempesta/acqua: corro sulla rotta senza fermarmi
        self.acqua_da = None
        self.calibra_da = None
        self.ultima_calibrazione = -1e9
        self.bussola_sbagliata = 0
        # movimento
        self.cammino_fino = 0.0           # cammino avanti fino a (verso la cassa / il compagno)
        self.cammino_cosa = ""
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
        self.tentativi_arma = 0
        self.prossima_cura = 0.0
        self.prossima_scritta = 0.0

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
        """Slot dell'inventario (1 = piccone, 2-6 = armi) -> nome del tasto (F, 1-5)."""
        if not n:
            return None
        nome = "piccone" if n == 1 else "arma_%d" % (n - 1)
        return nome if self.mani.esiste(nome) else None

    # ---- bussola e rotta
    def _passi_x(self):
        return getattr(self.mani, "passi_totali_x", 0)

    def guardo_verso(self):
        if self.bussola_rif is None:
            return None
        gradi, passi = self.bussola_rif
        return (gradi + (self._passi_x() - passi) * 360.0 / max(1.0, self.passi_per_giro)) % 360.0

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
        for ramo in (self._ramo_istruzioni, self._ramo_pulsante_giallo, self._ramo_schermi, self._ramo_fasi,
                     self._ramo_pericolo, self._ramo_nemico, self._ramo_scritta, self._ramo_arma_e_cure,
                     self._ramo_compagno, self._ramo_bottino, self._ramo_viaggio):
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
        lv.consiglio, lv.nuovo = None, False
        if self.ia is not None:
            if img is not None:
                self.ia.guarda(img)
            c = self.ia.consiglio(t, getattr(self.ia, "validita_fase", 45))
            if c is not None and c.fase != "playing" and t - c.quando > 6.0 and not self._schermo_uguale(c, img):
                c = None                                  # parlava di uno schermo che e' cambiato
            if c is not None and c.fase == "playing" and t - c.quando > float(
                    (self.cfg.get("ia", {}) or {}).get("validita_secondi", 8) or 8):
                c = None
            lv.consiglio = c
            if c is not None and c.numero != self.ultimo_numero:
                self.ultimo_numero = c.numero
                lv.nuovo = True
                if c.bussola is not None:
                    previsto = self.guardo_verso()
                    if previsto is not None and abs(avvolgi(c.bussola - previsto)) > 60:
                        self.bussola_sbagliata += 1
                        if self.bussola_sbagliata >= 3 and self.calibra_da is None:
                            self.log("I miei conti non tornano con la bussola: rimisuro quanto mi giro")
                            self.calibra_da = t
                            self.bussola_sbagliata = 0
                    else:
                        self.bussola_sbagliata = 0
                    self._leggi_bussola(c.bussola, c.quando)
        lv.guardo = self.guardo_verso()
        # pericoli: tempesta (l'IA, o il TERRENO viola) e acqua (la parte bassa blu)
        c = lv.consiglio
        lv.in_tempesta = bool(img is not None and self.fort.get("tempesta_dal_colore", True)
                              and viola(img) >= float(self.fort.get("tempesta_soglia_viola", 0.35) or 0.35))
        if c is not None and c.fase == "playing" and c.tempesta:
            lv.in_tempesta = True
        bagnato = img is not None and self.fort.get("evita_acqua", True) and \
            acqua(img) >= float(self.fort.get("acqua_soglia", 0.5) or 0.5)
        if bagnato:
            self.acqua_da = self.acqua_da if self.acqua_da is not None else t
        else:
            self.acqua_da = None
        lv.in_acqua = self.acqua_da is not None and t - self.acqua_da >= 1.5

    def _schermo_uguale(self, c, img):
        prima = getattr(c, "miniatura", None)
        if prima is None or img is None:
            return False
        from ia import miniatura
        return float(np.mean(np.abs(miniatura(img) - prima))) < 10.0

    # ================================================================== 1. istruzioni e "Gioca di nuovo"
    def _ramo_istruzioni(self, vis, img, t):
        if self.istruzioni is None or t < self.prossimo_controllo_regole:
            return None
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
    def _ramo_fasi(self, vis, img, t):
        c = self.lavagna.consiglio
        if c is None:
            return None
        if c.fase != "bus":
            self.bus_da = None
        if c.fase != "dead":
            self.morto_da = None
        if c.fase == "playing" and self.ultima_fase in ("bus", "falling"):
            self.log("Atterrato: prendo l'arma e misuro la bussola")
            tasto = self._tasto_slot(c.slot_arma if c.slot_arma and c.slot_arma != 1 else 2)
            if tasto:
                self.mani.premi(tasto, 0.08)
            self.prossima_mappa_periodica = t + 12.0
            if t - self.ultima_calibrazione > float(self.fort.get("ricalibra_bussola_secondi", 1200) or 1200):
                self.calibra_da = t + 2.0
        self.ultima_fase = c.fase
        if c.fase in ("bus", "falling", "playing"):
            self.in_partita = True
        if c.fase == "bus":
            return self._sul_bus(c, t)
        if c.fase == "falling":
            return self._in_caduta(c, t)
        if c.fase in ("menu", "dead"):
            return self._menu_o_morto(c, vis, img, t)
        return None

    def _sul_bus(self, c, t):
        self.ferma_tutto()
        if self.bus_da is None:
            self.bus_da = t
            self.rotta = None
        if self.rotta is None:
            self._guarda_mappa(t, "Sul bus")              # la rotta: il centro dell'isola
        # all'inizio il bus vola sul MARE: aspetto di essere sopra l'isola
        if c.sopra_isola is False and t - self.bus_da < float(self.fort.get("bus_attesa_massima", 45) or 45):
            return "sul bus: aspetto di essere sopra l'isola"
        if t >= self.prossimo_salto and self.mani.esiste("salta"):
            self.prossimo_salto = t + 3.0
            self.log("Salto dal bus%s" % (" (sotto c'e' l'isola)" if c.sopra_isola else ""))
            self.mani.premi("salta")
        return "sul bus"

    def _in_caduta(self, c, t):
        self._spara(False)
        if self.lavagna.nuovo and t >= self.prossima_correzione:
            gradi = None
            if c.compagno_xy is not None and c.compagno_xy[2] == "on_screen" and self.fort.get("segui_compagno", True):
                gradi, motivo = self._gradi_schermo(c.compagno_xy[0]), "verso il compagno"
            elif c.sopra_isola is not True and self.rotta is not None and self.lavagna.guardo is not None:
                gradi, motivo = avvolgi(self.rotta - self.lavagna.guardo), "verso il centro dell'isola"
            elif c.obiettivo is not None and c.obiettivo[0] in ("building", "chest"):
                gradi, motivo = self._gradi_schermo(c.obiettivo[1]), "verso le case"
            elif self.rotta is None and c.sopra_isola is False:
                self._guarda_mappa(t, "In caduta sopra il mare")
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
        lv = self.lavagna
        if t < self.fuga_fino:
            # scappo: corro sulla rotta, senza fermarmi per casse, case o compagni
            self._tieni_rotta(t)
            self._cammina(avanti=True, corri=True)
            self._controlla_blocco(img, t)
            if lv.nemici:
                return None                      # se mi sparano mi difendo (ramo nemico)
            return "scappo verso la zona sicura"
        if not (lv.in_tempesta or lv.in_acqua):
            return None
        motivo = "Sono nella tempesta" if lv.in_tempesta else "Sono in acqua"
        scritta = self._guarda_mappa(t, motivo)
        if scritta == "vado verso la zona sicura (mappa)":
            self._cammina(avanti=True, corri=True)
            return scritta                       # girato verso la zona sicura: adesso corro
        if scritta == "sono nella zona sicura" and lv.in_tempesta and not lv.in_acqua:
            return None                          # la tempesta era solo vicina
        if self.rotta is not None and self.guardo_verso() is not None:
            self._gira(avvolgi(self.rotta - self.guardo_verso()))
            self.fuga_fino = t + float(self.fort.get("corsa_fuori_tempesta", 10) or 10)
            self._cammina(avanti=True, corri=True)
            return "scappo verso la zona sicura"
        if scritta is None and lv.in_acqua and self.ia is None:
            return self._cerca_terra(t)
        return scritta

    def _cerca_terra(self, t):
        """Senza IA: mi giro dove all'orizzonte c'e' meno mare e corro."""
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

    def _tieni_rotta(self, t):
        if self.rotta is None or self.lavagna.guardo is None:
            return
        errore = avvolgi(self.rotta - self.lavagna.guardo)
        gradi_al_secondo = max(-60.0, min(60.0, errore * 1.5))
        self.mani.mira_fluida(gradi_al_secondo * self.dt_medio * self.passi_per_giro / 360.0, 0, self.dt_medio)

    # ================================================================== 5. nemico
    def _ramo_nemico(self, vis, img, t):
        lv = self.lavagna
        nemici = lv.nemici
        c = lv.consiglio
        if not nemici:
            self.mirando_da = None
            self.bersaglio = None
            if c is not None and lv.nuovo and c.nemico_xy is not None and self.comb.get("attivo", True):
                x, y, vicino = c.nemico_xy
                if vicino or not self._solo_vicini():
                    self.log("IA: c'e' un nemico%s -> mi giro e prendo l'arma" % (" vicino" if vicino else ""))
                    self._cammina()
                    self._gira(self._gradi_schermo(x))
                    self._prendi_arma(c, t, subito=True)
                    return "mi giro verso il nemico (IA)"
            return None
        H = vis.altezza
        if self._solo_vicini() and all(b.h < float(self.comb.get("nemico_vicino", 0.22)) * H for b in nemici):
            return None                          # obiettivo casse: i nemici lontani li lascio stare
        if not self.comb.get("attivo", True):
            return None
        mx, my = self._mirino(vis)
        b = min(nemici, key=lambda b: math.hypot(b.cx - mx, b.cy - my) / (1.0 + b.h / H))
        if self.bersaglio is None:
            self.mirando_da = t
            self.statistiche["combattimenti"] = self.statistiche.get("combattimenti", 0) + 1
            self._prendi_arma(c, t, subito=True)
        ax = b.cx
        ay = b.y + float(self.mira.get("altezza_mira", 0.2)) * b.h
        self.bersaglio = (ax, ay)
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

    def _prendi_arma(self, c, t, subito=False):
        """Prende in mano l'arma: lo slot migliore detto dall'IA, altrimenti lo slot 2 (tasto 1)."""
        if not self.comb.get("prendi_arma", True) or (not subito and t < self.prossimo_cambio_arma):
            return
        if c is not None and c.slot is not None and c.slot == c.slot_arma and c.in_mano == "weapon":
            return
        n = c.slot_arma if c is not None and c.slot_arma and c.slot_arma != 1 else 2
        tasto = self._tasto_slot(n)
        if tasto:
            self.prossimo_cambio_arma = t + 2.0
            self.mani.premi(tasto, 0.08)

    # ================================================================== 6. scritte sullo schermo
    def _ramo_scritta(self, vis, img, t):
        c = self.lavagna.consiglio
        if (c is None or not self.lavagna.nuovo or c.fase != "playing" or c.prompt not in
                ("open", "pick_up", "zipline", "door") or not self.fort.get("usa_le_scritte", True)
                or t < self.prossima_scritta or not self.mani.esiste("interagisci")):
            return None
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
        if c.prompt == "open":
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
            return "apro la cassa (IA)"
        if c.prompt == "pick_up":
            self.statistiche["armi"] = self.statistiche.get("armi", 0) + 1
            return "raccolgo (IA)"
        if c.prompt == "door":
            self._cammina(avanti=True)
            return "apro la porta"
        return "prendo la zipline"

    # ================================================================== 7. arma e cure
    def _ramo_arma_e_cure(self, vis, img, t):
        c = self.lavagna.consiglio
        if c is None or not self.lavagna.nuovo or c.fase != "playing":
            return None
        if self.lavagna.nemici:
            return None
        if c.poca_vita and c.slot_cura and c.slot_cura != 1 and t >= self.prossima_cura \
                and self.fort.get("cura_con_ia", True):
            tasto = self._tasto_slot(c.slot_cura)
            if tasto:
                self.prossima_cura = t + 10.0
                secondi = float(self.fort.get("cura_secondi", 5) or 5)
                self.log("IA: ho poca vita -> mi curo (slot %d)" % c.slot_cura)
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
        # in mano il piccone (o altro) e nell'inventario c'e' un'arma: prendo quella giusta
        sbagliato = c.in_mano in ("pickaxe", "other") or (c.slot and c.slot_arma and c.slot != c.slot_arma
                                                          and c.slot_arma != 1)
        if sbagliato and c.ha_arma is not False and t >= self.prossimo_cambio_arma:
            n = c.slot_arma if c.slot_arma and c.slot_arma != 1 else [2, 3, 4, 5, 6][self.tentativi_arma % 5]
            self.tentativi_arma += 1
            tasto = self._tasto_slot(n)
            if tasto:
                self.prossimo_cambio_arma = t + 2.0
                self.log("IA: in mano ho %s -> prendo l'arma (slot %d)" % (
                    "il piccone" if c.in_mano == "pickaxe" else "lo slot %s" % c.slot, n))
                self.mani.premi(tasto, 0.08)
        elif c.in_mano == "weapon":
            self.tentativi_arma = 0
        return None                              # cambiare arma non ferma il resto

    # ================================================================== 8. seguo il compagno
    def _ramo_compagno(self, vis, img, t):
        if not self.fort.get("segui_compagno", True):
            return None
        if t < self.fermo_fino:
            self._cammina()
            return "sto vicino al compagno"
        if t < self.cammino_fino and self.cammino_cosa == "compagno":
            self._cammina(avanti=True, corri=True)
            self._controlla_blocco(img, t)
            return "seguo il compagno"
        c = self.lavagna.consiglio
        if c is None or not self.lavagna.nuovo or c.fase != "playing" or c.compagno_xy is None:
            return None
        x, y, lato, metri = c.compagno_xy
        vicino_casse = lato == "on_screen" and metri is not None and \
            metri <= float(self.fort.get("segui_casse_entro_metri", 25) or 25)
        if vicino_casse and c.obiettivo is not None:
            return None                          # col compagno vicino apro prima le casse li' intorno
        if lato == "on_screen":
            gradi = self._gradi_schermo(x)
        else:
            gradi = {"left": -75.0, "right": 75.0, "behind": 180.0}[lato]
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

    # ================================================================== 9. bottino
    def _ramo_bottino(self, vis, img, t):
        if t < self.cammino_fino and self.cammino_cosa in NOMI_COSE:
            self._cammina(avanti=True)
            self._controlla_blocco(img, t)
            return "vado verso %s (IA)" % NOMI_COSE[self.cammino_cosa]
        c = self.lavagna.consiglio
        if (c is None or not self.lavagna.nuovo or c.fase != "playing" or c.obiettivo is None
                or not self.racc.get("casse", True)):
            return None
        cosa, x, y = c.obiettivo
        if cosa == "weapon" and not self.racc.get("armi", True):
            return None
        self._gira(self._gradi_schermo(x))
        # piu' e' in alto sullo schermo, piu' e' lontana: cammino di piu' prima della prossima risposta
        self.cammino_fino = t + 1.0 + 1.5 * max(0.0, min(1.0, (0.85 - y) / 0.5))
        if cosa != self.cammino_cosa:
            self.log("IA: vedo %s -> ci vado" % NOMI_COSE[cosa])
        self.cammino_cosa = cosa
        self._cammina(avanti=True)
        return "vado verso %s (IA)" % NOMI_COSE[cosa]

    # ================================================================== 10. viaggio
    def _ramo_viaggio(self, vis, img, t):
        if self.calibra_da is not None and t >= self.calibra_da:
            self.calibra_da = None
            scritta = self._calibra_bussola(t)
            if scritta:
                return scritta
        ogni = float(self.fort.get("mappa_ogni_secondi", 60) or 0)
        if ogni > 0 and self.ia is not None and t >= self.prossima_mappa_periodica:
            self.prossima_mappa_periodica = t + ogni
            scritta = self._guarda_mappa(t, "Controllo")
            if scritta and scritta != "sono nella zona sicura":
                return scritta
        if self.apprendimento is not None and img is not None:
            self.apprendimento.forse_salva_foto(img, vis, t)
        # verso il centro della zona sicura (se lo so), altrimenti dritto
        if self.rotta is not None and self.lavagna.guardo is not None:
            errore = avvolgi(self.rotta - self.lavagna.guardo)
            if abs(errore) > 100 and t - self.ultimo_sblocco > 6.0:
                self.log("Riprendo la rotta verso il centro della zona sicura (giro di %.0f gradi)" % errore)
                self._gira(errore)
            else:
                self._tieni_rotta(t)
            stato = "vado verso il centro della zona sicura"
        else:
            stato = "esploro"
        if self.espl.get("rimetti_visuale_dritta", True) and abs(self.pitch) > 3:
            self.mani.muovi(0, -self.pitch * 0.15)
            self.pitch *= 0.85
        self._cammina(avanti=True, corri=bool(self.espl.get("corri", True)))
        self._controlla_blocco(img, t)
        return stato

    # ================================================================== bloccato
    def _controlla_blocco(self, img, t):
        """Se cammino ma i LATI dello schermo non cambiano sono bloccato: salto; se ancora, giro;
        la terza volta sfondo col piccone (F)."""
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
        if self.fort.get("piccona_i_muri", True) and self.mani.esiste("piccone") and random.random() < 0.5:
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
        self.log("Sono ancora bloccato: salto e giro")
        if self.mani.esiste("salta"):
            self.mani.premi("salta")
        self.esecutore.gira(self.verso_sblocco * random.uniform(60, 110))
        return True

    # ================================================================== mappa e bussola
    def _leggi_bussola_ia(self, foto):
        from ia import DOMANDA_BUSSOLA
        if foto is None or self.ia is None or not hasattr(self.ia, "chiedi_voto"):
            return None
        h, w = foto.shape[:2]
        striscia = foto[0:max(1, int(0.075 * h)), int(0.3 * w):int(0.7 * w)]
        striscia = cv2.resize(striscia, (1024, max(1, int(striscia.shape[0] * 1024 / float(striscia.shape[1])))),
                              interpolation=cv2.INTER_CUBIC)
        gradi = []
        for r in self.ia.chiedi_voto(striscia, DOMANDA_BUSSOLA, 3, attesa=12.0):
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
        if self.ia is None or not hasattr(self.ia, "chiedi_voto") or not self.fort.get("calibra_con_bussola", True):
            return None
        self.ferma_tutto()
        prima = self._leggi_bussola_ia(self.esecutore.foto_fresca())
        if prima is None:
            self.calibra_da = t + 30.0
            return "leggo la bussola"
        voluti = float(self.fort.get("calibra_bussola_gradi", 60) or 60)
        self.esecutore.gira(voluti, durata=0.3)
        self.esecutore.dormi(0.5)
        dopo = self._leggi_bussola_ia(self.esecutore.foto_fresca())
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
        if abs(girati - voluti) <= 8:
            self.log("Bussola: giro giusto (%.0f gradi su %.0f): la sensibilita' va bene" % (girati, voluti))
            return "leggo la bussola"
        if not 0.25 <= nuovi / vecchi <= 4.0:
            self.log("Bussola: misura strana (%.0f gradi invece di %.0f): non cambio niente" % (girati, voluti))
            return "leggo la bussola"
        self.log("Bussola: volevo girarmi di %.0f gradi e mi sono girato di %.0f -> correggo la sensibilita' "
                 "(passi per un giro: %.0f -> %.0f)" % (voluti, girati, vecchi, nuovi))
        if self.apprendimento is not None:
            self.apprendimento.passi_per_giro = nuovi
            impostazioni.salva_calibrazione(self.apprendimento.base, ["mira", "passi_per_giro"], round(nuovi))
        else:
            self.mira["passi_per_giro"] = nuovi
        self.esecutore.passi_per_giro = nuovi
        return "correggo la sensibilita'"

    def _guarda_mappa(self, t, motivo):
        """Leggo la bussola (fuori dalla mappa), apro la mappa (M), foto, la chiudo. A piu' IA chiedo
        il numero della bussola e da che parte e' il centro della zona sicura SULLA MAPPA (nord in
        alto): vince la maggioranza. La rotta e il giro li calcolo io."""
        if (self.ia is None or not hasattr(self.ia, "chiedi_voto") or not self.mani.esiste("mappa")
                or not self.fort.get("guarda_mappa", True) or t < self.prossima_mappa):
            return None
        from ia import BUSSOLA, DOMANDA_MAPPA, _si
        self.prossima_mappa = t + float(self.fort.get("mappa_non_prima_di_secondi", 15) or 15)
        self.log("%s: guardo la mappa per capire dov'e' la zona sicura" % motivo)
        self.ferma_tutto()
        gioco = self.esecutore.foto_fresca()
        self.mani.premi("mappa", 0.1)
        self.esecutore.dormi(float(self.fort.get("mappa_attesa_secondi", 1.3) or 1.3))
        mappa = self.esecutore.foto_fresca()
        self.mani.premi("mappa", 0.1)
        self.esecutore.dormi(0.4)
        if mappa is None:
            return None
        risposte = self.ia.chiedi_voto(mappa_con_bussola(mappa, gioco), DOMANDA_MAPPA,
                                       int(self.fort.get("mappa_quante_ia", 3) or 3))
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
        if letti:
            self._leggi_bussola(angolo_medio(letti))
            self.lavagna.guardo = self.guardo_verso()
        scelta = Counter(sicura).most_common(1)[0][0] if sicura else None
        if scelta == "HERE":
            self.log("Mappa: sono al centro della zona sicura")
            self.rotta = None
            return "sono nella zona sicura"
        if scelta is None or not letti:
            self.log("Mappa: le IA non capiscono da che parte andare (%d risposte)" % len(risposte))
            return "guardo la mappa"
        self.rotta = float(BUSSOLA[scelta])
        sono_dentro = bool(dentro) and sum(dentro) * 2 > len(dentro)
        al_bordo = bool(bordo) and sum(bordo) * 2 > len(bordo)
        if sono_dentro and not al_bordo:
            self.log("Mappa: sono dentro la zona sicura; vado piano verso il centro (%s)" % scelta)
            return "sono nella zona sicura"
        giro = avvolgi(self.rotta - self.guardo_verso())
        self.log("Mappa: la zona sicura e' a %s (voti: %s), guardo a %.0f gradi -> giro di %.0f e corro" % (
            scelta, ", ".join(sicura), angolo_medio(letti), giro))
        self._gira(giro)
        self.fuga_fino = t + float(self.fort.get("corsa_fuori_tempesta", 10) or 10)
        self.cammino_fino = 0.0
        self.mini_prec = None
        return "vado verso la zona sicura (mappa)"
