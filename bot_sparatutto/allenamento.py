"""
allenamento.py - Ogni partita e' un allenamento.

Alla fine di ogni partita (quando passa alla successiva) il bot:
  1. scrive un RIEPILOGO in allenamento.txt: casse aperte, casse che non si aprivano,
     armi, combattimenti, quante volte e' rimasto bloccato, quanto tempo ha esplorato...
  2. AGGIUSTA da solo le sue regolazioni per la partita dopo, per esempio:
     - tante casse non si aprivano      -> si avvicina di piu' e tiene premuto piu' a lungo
     - tutte le casse si aprivano       -> prova ad aprirle da un po' piu' lontano (piu' veloce)
     - tante casse irraggiungibili      -> perde meno tempo prima di lasciar perdere
     - spesso bloccato contro i muri    -> se ne accorge prima
     - tanto tempo a girare senza casse -> si guarda intorno piu' spesso
     - tante casse e poca esplorazione  -> si guarda intorno un po' meno (piu' tempo per aprire)
Gli aggiustamenti hanno sempre dei limiti (non esagera mai) e si salvano in
calibrazione.yaml: la volta dopo riparte da li'. Cancella calibrazione.yaml per ricominciare.
"""

import os
import time

import impostazioni

# chiavi delle statistiche contate per partita
CONTATORI = ("casse", "materiali", "armi", "casse_tentate", "casse_fallite", "combattimenti",
             "bloccato", "lasciate_perdere")

DURATA_MINIMA = 30.0           # secondi: sotto, non e' una partita (es. due pulsanti di fila nei menu)
DURATA_PER_AGGIUSTARE = 60.0   # secondi: sotto, non cambia le regolazioni


def _categoria(scritta):
    s = str(scritta or "")
    if s.startswith(("esploro", "mi guardo intorno")):
        return "esplora"
    if s.startswith(("combatto", "cerco il nemico", "costruisco")):
        return "combatte"
    if s.startswith(("vado verso", "apro", "lascio perdere")):
        return "casse"
    return "altro"


class Allenamento:
    def __init__(self, cfg, base, statistiche, log=print):
        self.cfg = cfg
        self.base = base
        self.statistiche = statistiche
        self.log = log
        self.attivo = bool((cfg.get("apprendimento", {}) or {}).get("allenamento", True))
        self.numero = 0
        self._ricomincia(time.monotonic())

    def _ricomincia(self, adesso):
        self.inizio = adesso
        self.partenza = {k: self.statistiche.get(k, 0) for k in CONTATORI}
        self.tempi = {"esplora": 0.0, "combatte": 0.0, "casse": 0.0, "altro": 0.0}

    def conta_tempo(self, scritta, secondi):
        """Ogni fotogramma: quanto tempo ha passato a fare cosa."""
        if 0 < secondi < 5:
            self.tempi[_categoria(scritta)] += secondi

    # ------------------------------------------------------------------ fine partita
    def fine_partita(self, motivo="partita successiva", adesso=None):
        """Chiamata quando passa alla partita successiva (o quando chiudi il bot)."""
        adesso = time.monotonic() if adesso is None else adesso
        durata = adesso - self.inizio
        if durata < DURATA_MINIMA:
            self._ricomincia(adesso)
            return None
        d = {k: self.statistiche.get(k, 0) - self.partenza.get(k, 0) for k in CONTATORI}
        totale_tempi = sum(self.tempi.values()) or 1.0
        esplora = self.tempi["esplora"] / totale_tempi
        self.numero += 1
        aggiustamenti = []
        if self.attivo and durata >= DURATA_PER_AGGIUSTARE:
            aggiustamenti = self._aggiusta(d, esplora)
        riga = ("%s  partita %d%s  durata %d:%02d  casse armi %d  casse materiali %d  non aperte %d  armi %d  "
                "combattimenti %d  bloccato %d  lasciate perdere %d  esplorazione %d%%" % (
                    time.strftime("%Y-%m-%d %H:%M"), self.numero, "" if motivo == "partita successiva" else
                    " (%s)" % motivo, int(durata) // 60, int(durata) % 60, d["casse"], d["materiali"],
                    d["casse_fallite"], d["armi"], d["combattimenti"], d["bloccato"], d["lasciate_perdere"],
                    round(esplora * 100)))
        if aggiustamenti:
            riga += "  -> " + "; ".join(aggiustamenti)
        self.log("ALLENAMENTO: " + riga)
        try:
            with open(os.path.join(self.base, "allenamento.txt"), "a", encoding="utf-8") as f:
                f.write(riga + "\n")
        except OSError:
            pass
        self._ricomincia(adesso)
        return riga

    # ------------------------------------------------------------------ aggiustamenti
    def _cambia(self, sezione, chiave, nuovo, minimo, massimo, cifre=3):
        """Cambia un'impostazione (dentro i limiti) e la salva. True se e' cambiata davvero."""
        sez = self.cfg.setdefault(sezione, {})
        vecchio = float(sez.get(chiave, impostazioni.PREDEFINITE.get(sezione, {}).get(chiave, 0)) or 0)
        nuovo = round(min(massimo, max(minimo, nuovo)), cifre)
        if abs(nuovo - vecchio) < 1e-9:
            return False
        sez[chiave] = nuovo
        try:
            impostazioni.salva_calibrazione(self.base, [sezione, chiave], nuovo)
        except OSError:
            pass
        return True

    def _valore(self, sezione, chiave):
        return float((self.cfg.get(sezione, {}) or {}).get(
            chiave, impostazioni.PREDEFINITE.get(sezione, {}).get(chiave, 0)) or 0)

    def _aggiusta(self, d, esplora):
        fatti = []
        tentate, fallite = d["casse_tentate"], d["casse_fallite"]
        casse_aperte = d["casse"] + d["materiali"]
        # 1. casse che non si aprono: piu' vicino e piu' a lungo
        if tentate >= 3 and fallite / float(tentate) >= 0.3:
            a = self._cambia("raccolta", "vicino_altezza", self._valore("raccolta", "vicino_altezza") * 1.15, 0.06, 0.35)
            b = self._cambia("raccolta", "vicino_fondo", self._valore("raccolta", "vicino_fondo") + 0.02, 0.7, 0.95)
            c = self._cambia("raccolta", "tempo_apertura_cassa",
                             self._valore("raccolta", "tempo_apertura_cassa") + 0.2, 0.3, 3.0, 2)
            if a or b or c:
                fatti.append("si avvicina di piu' alle casse e tiene premuto piu' a lungo")
        # 2. si aprono tutte: prova da un po' piu' lontano (ci mette meno)
        elif tentate >= 5 and fallite == 0:
            if self._cambia("raccolta", "vicino_altezza", self._valore("raccolta", "vicino_altezza") * 0.95, 0.06, 0.35):
                fatti.append("prova ad aprire le casse da un po' piu' lontano")
        # 3. casse irraggiungibili: lascia perdere prima
        if d["lasciate_perdere"] >= 3:
            if self._cambia("raccolta", "tempo_massimo_avvicinamento",
                            self._valore("raccolta", "tempo_massimo_avvicinamento") - 1.5, 5.0, 15.0, 1):
                fatti.append("perde meno tempo con le casse irraggiungibili")
        # 4. spesso bloccato: se ne accorge prima
        if d["bloccato"] >= 4:
            if self._cambia("esplorazione", "sensibilita_blocco",
                            self._valore("esplorazione", "sensibilita_blocco") + 0.5, 1.0, 5.0, 2):
                fatti.append("si accorge prima quando e' bloccato")
        # 5. tanto tempo a girare senza trovare casse: si guarda intorno piu' spesso
        guarda = self._valore("esplorazione", "guarda_intorno_ogni")
        if guarda > 0:
            if esplora > 0.6 and casse_aperte < 3:
                if self._cambia("esplorazione", "guarda_intorno_ogni", guarda - 2, 5.0, 20.0, 1):
                    fatti.append("si guarda intorno piu' spesso per trovare casse")
            elif esplora < 0.25 and casse_aperte >= 8:
                if self._cambia("esplorazione", "guarda_intorno_ogni", guarda + 1, 5.0, 20.0, 1):
                    fatti.append("si guarda intorno un po' meno (piu' tempo per aprire casse)")
        return fatti
