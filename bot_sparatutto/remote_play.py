"""
remote_play.py - Le cose da fare SUL PC (non sulla Play): la finestra di PS Remote Play.

La schedina preme i tasti sulla Play. Ma quando PS Remote Play si scollega ("Hai perso
la connessione alla PS5", "Seleziona l'ultima console...") i pulsanti da premere sono
nella finestra del PC: li clicca il mouse del PC (questo file). L'IA che guarda dice
quale pulsante premere (OK, il nome della console come PS5-649...).
Serve anche a riportare davanti la finestra di PS Remote Play se un'altra la copre.
Funziona solo su Windows; altrove non fa niente.
"""

import sys
import time

TITOLO = "PS Remote Play"


class PC:
    def __init__(self, log=print, titolo=TITOLO):
        self.log = log
        self.titolo = titolo
        self.attivo = sys.platform == "win32"

    def _user32(self):
        import ctypes
        return ctypes, ctypes.windll.user32

    def clicca(self, x, y):
        """Click sinistro del mouse del PC nel punto (x, y) dello schermo (pixel veri)."""
        if not self.attivo:
            return False
        try:
            _, u = self._user32()
            u.SetCursorPos(int(round(x)), int(round(y)))
            time.sleep(0.08)
            u.mouse_event(0x0002, 0, 0, 0, 0)          # giu'
            time.sleep(0.06)
            u.mouse_event(0x0004, 0, 0, 0, 0)          # su
            return True
        except Exception as e:
            self.log("Non riesco a cliccare sul PC: %s" % e)
            return False

    def trova_finestra(self):
        """La finestra di PS Remote Play (il suo numero per Windows), oppure None."""
        if not self.attivo:
            return None
        try:
            ctypes, u = self._user32()
            from ctypes import wintypes
            trovate = []
            cerca = self.titolo.lower()

            @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
            def guarda(hwnd, _):
                if u.IsWindowVisible(hwnd):
                    n = u.GetWindowTextLengthW(hwnd)
                    if n:
                        buf = ctypes.create_unicode_buffer(n + 1)
                        u.GetWindowTextW(hwnd, buf, n + 1)
                        if cerca in buf.value.lower():
                            trovate.append(hwnd)
                return True
            u.EnumWindows(guarda, 0)
            return trovate[0] if trovate else None
        except Exception:
            return None

    def porta_davanti(self):
        """Riporta davanti (e riapre se e' ridotta a icona) la finestra di PS Remote Play."""
        h = self.trova_finestra()
        if h is None:
            return False
        try:
            _, u = self._user32()
            if u.IsIconic(h):
                u.ShowWindow(h, 9)                       # SW_RESTORE
            u.keybd_event(0x12, 0, 0, 0)                 # ALT: Windows lascia cambiare finestra
            ok = bool(u.SetForegroundWindow(h))
            u.keybd_event(0x12, 0, 0x0002, 0)
            return ok
        except Exception:
            return False


class PCFinto:
    """Per le prove: si ricorda cosa avrebbe fatto."""

    def __init__(self, finestra=True):
        self.click = []
        self.davanti = 0
        self.finestra = finestra

    def clicca(self, x, y):
        self.click.append((x, y))
        return True

    def trova_finestra(self):
        return 1 if self.finestra else None

    def porta_davanti(self):
        self.davanti += 1
        return self.finestra
