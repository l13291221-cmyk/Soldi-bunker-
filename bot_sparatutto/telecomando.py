"""
telecomando.py - Giochi TU sulla Play con la tastiera e il mouse del PORTATILE.

PS Remote Play fa solo VEDERE la Play sul portatile: la tastiera e il mouse attaccati al
portatile non arrivano alla Play (Remote Play il mouse non lo legge proprio).
Li porta questo programma: legge cosa premi e come muovi il mouse sul portatile e lo
manda alla schedina Pico attaccata alla Play (tramite il ponte Arduino). La schedina lo
preme davvero: per la Play e' come avere tastiera e mouse attaccati a lei.

Serve a "Impara guardando me" (menu 4) quando il gioco e' sulla Play: tu giochi dal
portatile e intanto il bot guarda lo schermo e impara.

Mentre e' acceso, il mouse del portatile "entra" nella Play: la freccia del PC resta
ferma e i click non arrivano al PC. F9 = ho finito (il mouse torna normale).
"""

import threading
import time

from mani import TastoSconosciuto

# nomi dei tasti speciali di pynput -> nomi usati dal bot (mani.py)
NOMI_TASTI = {
    "space": "spazio", "enter": "invio", "esc": "esc", "tab": "tab", "backspace": "backspace",
    "caps_lock": "bloc_maiusc", "shift": "shift", "shift_l": "shift", "shift_r": "shift_destro",
    "ctrl": "ctrl", "ctrl_l": "ctrl", "ctrl_r": "ctrl_destro", "alt": "alt", "alt_l": "alt",
    "alt_r": "alt_gr", "alt_gr": "alt_gr", "delete": "canc", "insert": "ins", "home": "home",
    "end": "fine", "page_up": "pagsu", "page_down": "paggiu",
    "up": "up", "down": "down", "left": "left", "right": "right",
}
PULSANTI = {"left": "mouse_sinistro", "right": "mouse_destro", "middle": "mouse_centrale",
            "x1": "mouse4", "x2": "mouse5"}


def nome_tasto(k):
    """Da un tasto di pynput al nome del bot ('w', '1', 'f8', 'spazio', 'shift'...)."""
    vk = getattr(k, "vk", None)
    if isinstance(vk, int):
        # su Windows il codice del tasto non cambia con Maiusc o Ctrl premuti
        if 0x41 <= vk <= 0x5A:
            return chr(vk).lower()
        if 0x30 <= vk <= 0x39:
            return chr(vk)
        if 0x70 <= vk <= 0x7B:
            return "f%d" % (vk - 0x6F)
    c = getattr(k, "char", None)
    if c and len(c) == 1 and c.isprintable():
        return c.lower()
    nome = getattr(k, "name", "") or ""
    return NOMI_TASTI.get(nome, nome)


class Telecomando:
    """Passa alla schedina (mani) i tasti e il mouse del portatile.

    centro = dove resta ferma la freccia del PC: ogni movimento del mouse arriva come
    'la freccia andrebbe in (x, y)' e la differenza dal centro e' lo spostamento.
    """

    def __init__(self, mani, centro, riservati=("f8", "f9"), sensibilita=1.0, ogni=0.004):
        self.mani = mani
        self.centro = (float(centro[0]), float(centro[1]))
        self.riservati = {str(r).lower() for r in riservati}
        self.sensibilita = float(sensibilita or 1.0)
        self.ogni = ogni
        self.errore = None             # se la schedina si stacca, qui c'e' il perche'
        self._dx = 0.0
        self._dy = 0.0
        self._lock = threading.Lock()
        self._vivo = True
        self._thread = threading.Thread(target=self._manda_movimenti, daemon=True)
        self._thread.start()

    # ---- tastiera ----
    def tasto_giu(self, k):
        nome = nome_tasto(k)
        if nome and nome not in self.riservati:
            self._premi(nome, True)

    def tasto_su(self, k):
        nome = nome_tasto(k)
        if nome and nome not in self.riservati:
            self._premi(nome, False)

    # ---- mouse ----
    def mosso(self, x, y):
        dx = x - self.centro[0]
        dy = y - self.centro[1]
        if dx or dy:
            with self._lock:
                self._dx += dx * self.sensibilita
                self._dy += dy * self.sensibilita

    def click(self, x, y, pulsante, giu):
        nome = PULSANTI.get(getattr(pulsante, "name", ""))
        if nome:
            self._premi(nome, giu)

    def rotella(self, x, y, dx, dy):
        if dy:
            self._premi("rotella_su" if dy > 0 else "rotella_giu", True)

    # ---- dentro ----
    def _premi(self, nome, giu):
        try:
            if giu:
                self.mani.giu(nome)        # tenere premuto un tasto non lo ripete: lo preme una volta
            else:
                self.mani.su(nome)
        except TastoSconosciuto:
            pass                           # un tasto che la schedina non sa premere: lo salto
        except Exception as e:
            self.errore = e

    def svuota(self):
        """Manda alla schedina il movimento del mouse accumulato (al massimo ogni 4 millesimi)."""
        with self._lock:
            dx, dy = self._dx, self._dy
            self._dx = self._dy = 0.0
        if dx or dy:
            try:
                self.mani.muovi(dx, dy)
            except Exception as e:
                self.errore = e

    def _manda_movimenti(self):
        while self._vivo:
            time.sleep(self.ogni)
            self.svuota()

    def ferma(self):
        self._vivo = False
        self._thread.join(timeout=1.0)
        self.svuota()
        try:
            self.mani.rilascia_tutto()
        except Exception:
            pass
