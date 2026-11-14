"""
registra.py - GIOCA E REGISTRA (menu 17): per capire DAVVERO cosa sbaglia il bot.

Mentre gioca salva una foto ogni 2 secondi con scritto sopra cosa pensa il bot (cosa sta
facendo, dove crede di guardare, dove vuole andare, cosa gli ha detto l'IA, cosa vedono i suoi
occhi) e tutto quello che scrive nella finestra nera. Alla fine fa uno zip
(registrazione_....zip, accanto al programma) da mandare a chi sistema il bot.
Le foto restano sul tuo PC finche' non lo mandi tu.
"""

import os
import shutil
import threading
import time

import cv2
import numpy as np


class Registratore:
    def __init__(self, base, ogni=2.0, minuti=20, larghezza=960, log=print):
        self.cartella = os.path.join(base, "registrazione_" + time.strftime("%Y%m%d_%H%M%S"))
        os.makedirs(self.cartella, exist_ok=True)
        self.ogni = float(ogni)
        self.fine = time.monotonic() + float(minuti) * 60.0
        self.larghezza = int(larghezza)
        self.log = log
        self.n = 0
        self.prossima = 0.0
        self.inizio = time.monotonic()
        self._lock = threading.Lock()
        self._file_log = open(os.path.join(self.cartella, "log.txt"), "a", encoding="utf-8")
        self.attivo = True

    def scrivi_log(self, riga):
        with self._lock:
            if self._file_log is not None:
                self._file_log.write(riga + "\n")
                self._file_log.flush()

    def foto(self, img, righe, t=None):
        """Salva la foto (gia' disegnata con quello che vedono gli occhi) con sopra le righe di testo."""
        if not self.attivo or img is None:
            return False
        t = time.monotonic() if t is None else t
        if t < self.prossima:
            return False
        if t > self.fine:
            self.attivo = False
            self.log("Registrazione: 20 minuti finiti, smetto di registrare (il bot continua a giocare)")
            return False
        self.prossima = t + self.ogni
        H, W = img.shape[:2]
        if W > self.larghezza:
            img = cv2.resize(img, (self.larghezza, int(H * self.larghezza / float(W))), interpolation=cv2.INTER_AREA)
        alto = 18 * len(righe) + 8
        fascia = np.zeros((alto, img.shape[1], 3), np.uint8)
        for i, riga in enumerate(righe):
            cv2.putText(fascia, str(riga)[:150], (6, 18 * (i + 1)), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                        (255, 255, 255), 1, cv2.LINE_AA)
        out = np.vstack([fascia, img])
        self.n += 1
        ok, dati = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if ok:
            dati.tofile(os.path.join(self.cartella, "%05d_%06.1fs.jpg" % (self.n, t - self.inizio)))
        return True

    def chiudi(self):
        """Chiude e fa lo zip. -> il percorso dello zip (o della cartella se lo zip non riesce)."""
        self.attivo = False
        with self._lock:
            if self._file_log is not None:
                self._file_log.close()
                self._file_log = None
        try:
            zip_ = shutil.make_archive(self.cartella, "zip", os.path.dirname(self.cartella),
                                       os.path.basename(self.cartella))
            shutil.rmtree(self.cartella, ignore_errors=True)
            return zip_
        except Exception:
            return self.cartella


def righe_di_stato(cervello, vis, scritta, t):
    """Cosa pensa il bot adesso, in poche righe."""
    guardo = cervello.guardo_verso() if hasattr(cervello, "guardo_verso") else None
    righe = [
        "FA: %s" % scritta,
        "guardo: %s | rotta (zona sicura): %s | passi per un giro: %.0f | occhi: %d nemici, %d casse" % (
            "%.0f" % guardo if guardo is not None else "?",
            "%.0f" % cervello.rotta if getattr(cervello, "rotta", None) is not None else "nessuna",
            float(cervello.passi_per_giro), len(vis.nemici), len(vis.casse)),
    ]
    ia = getattr(cervello, "ia", None)
    c = ia.ultimo if ia is not None and hasattr(ia, "ultimo") else None
    if c is None:
        righe.append("IA: nessuna risposta ancora")
    else:
        righe.append("IA (%s, %.1fs fa): fase=%s schermo=%s osservo=%s tempesta=%s muro=%s sopra_isola=%s" % (
            c.fornitore, t - c.quando, c.fase, c.schermo, c.osservo, c.tempesta, c.muro, c.sopra_isola))
        righe.append("IA: mano=%s slot=%s migliore=%s cure=%s scritta=%s obiettivo=%s nemico=%s bussola=%s "
                     "esplora=%s" % (c.in_mano, c.slot, c.slot_arma, c.slot_cura, c.prompt, c.obiettivo,
                                     c.nemico_xy, c.bussola, c.esplora))
    return righe
