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


# ------------------------------------------------------------------ menu "Telecomando"
def svuota_tastiera_console():
    """I tasti premuti mentre il telecomando era acceso arrivano anche alla finestra nera:
    li butto via, cosi' il menu non li legge come se li avessi scritti li'."""
    try:
        import msvcrt
    except ImportError:
        return
    try:
        while msvcrt.kbhit():
            msvcrt.getwch()
    except Exception:
        pass


def centro_dello_schermo(area, mouse_modulo):
    """Mette la freccia del PC al centro dello schermo e restituisce dov'e' davvero."""
    centro = (area["left"] + area["width"] // 2, area["top"] + area["height"] // 2)
    try:
        freccia = mouse_modulo.Controller()
        freccia.position = centro
        centro = freccia.position
    except Exception:
        pass
    return centro


def usa(cfg, log=print, attesa=30):
    """Menu 12: tastiera e mouse del portatile vanno alla Play (attraverso la schedina)
    finche' non premi F9. Serve per esempio quando la Play chiede 'chi sta usando questa
    tastiera?' (premi INVIO), o per muoverti nei menu della Play dal portatile."""
    from pynput import keyboard, mouse

    from mani import ManiSchedina
    from occhi import Schermo

    mani = ManiSchedina(cfg.get("tasti"), log, (cfg.get("comandi", {}) or {}).get("porta", "auto"))
    esci = str((cfg.get("tasti_bot", {}) or {}).get("esci", "f9")).strip().lower()
    sch = cfg.get("schermo", {}) or {}
    print("\n" + "=" * 70)
    print("  TELECOMANDO: la tastiera e il mouse del portatile vanno alla Play")
    print("=" * 70)
    print("Esempio: la Play chiede 'chi sta usando questa tastiera?' -> premi INVIO.")
    print("Mentre e' acceso la freccia del PC resta ferma (il mouse lo usa la Play).")
    print("%s = basta, tutto torna normale." % esci.upper())
    print("\nClicca sulla finestra di PS Remote Play. Parto tra %d secondi..." % attesa)
    for n in range(int(attesa), 0, -1):
        print("  %d..." % n, flush=True)
        time.sleep(1)
    schermo = Schermo(int(sch.get("monitor", 1) or 1), sch.get("zona_cattura"))
    area = dict(schermo.area)
    schermo.chiudi()
    sens = float((cfg.get("telecomando", {}) or {}).get("sensibilita_mouse", 1.0) or 1.0)
    tele = Telecomando(mani, centro_dello_schermo(area, mouse), riservati=(esci,), sensibilita=sens)
    fine = threading.Event()

    def premuto(k):
        if nome_tasto(k) == esci:
            fine.set()
            return
        tele.tasto_giu(k)

    ascolta_t = keyboard.Listener(on_press=premuto, on_release=tele.tasto_su)
    ascolta_m = mouse.Listener(on_click=tele.click, on_move=tele.mosso, on_scroll=tele.rotella, suppress=True)
    for a in (ascolta_t, ascolta_m):
        a.daemon = True
        a.start()
    print("ACCESO: ora tastiera e mouse vanno alla Play.   %s = basta" % esci.upper(), flush=True)
    try:
        while not fine.wait(0.1):
            if tele.errore is not None:
                print("\nPROBLEMA con la schedina: %s" % tele.errore)
                break
    except KeyboardInterrupt:
        pass
    finally:
        for a in (ascolta_m, ascolta_t):        # prima il mouse: torna subito al PC
            try:
                a.stop()
            except Exception:
                pass
        tele.ferma()
        mani.chiudi()
        svuota_tastiera_console()
    print("Telecomando spento: tastiera e mouse sono di nuovo del PC.")
