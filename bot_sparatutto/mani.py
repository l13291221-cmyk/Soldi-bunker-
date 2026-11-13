"""
mani.py - Le "mani" del bot: premono i tasti e muovono il mouse.

Tre modi (si sceglie in impostazioni.yaml -> comandi -> modo):
  schedina : manda i comandi alla Raspberry Pi Pico via USB, che li preme come
             una vera tastiera + mouse (funziona con tutti i giochi)
  software : preme i tasti direttamente da Windows (per provare senza schedina;
             alcuni giochi lo ignorano)
  prova    : non preme niente, scrive solo cosa farebbe (per i test)

I nomi dei tasti si possono scrivere in italiano o in inglese:
  lettere (w, a, x...), numeri (1, 2...), f1...f12, spazio, invio, esc, tab,
  ctrl, shift/maiusc, alt, frecce (su, giu, sinistra, destra)...
  mouse_sinistro, mouse_destro, mouse_centrale, rotella_su, rotella_giu
"""

import sys
import threading
import time

# ------------------------------------------------------------------ nomi dei tasti -> codici HID
# Codici "HID usage" della tastiera (gli stessi che usa una tastiera USB vera).
CODICI = {}
for _i, _c in enumerate("abcdefghijklmnopqrstuvwxyz"):
    CODICI[_c] = 0x04 + _i
for _i, _c in enumerate("123456789"):
    CODICI[_c] = 0x1E + _i
CODICI["0"] = 0x27
for _i in range(12):
    CODICI["f%d" % (_i + 1)] = 0x3A + _i

_ALIAS = {
    0x28: ["invio", "enter", "return"],
    0x29: ["esc", "escape"],
    0x2A: ["backspace", "cancella_indietro"],
    0x2B: ["tab"],
    0x2C: ["spazio", "space", "barra"],
    0x2D: ["meno", "-"],
    0x2E: ["uguale", "="],
    0x2F: ["["], 0x30: ["]"],
    0x31: ["\\"],
    0x33: [";", "ò"],
    0x34: ["'", "à"],
    0x35: ["`", "\\\\"],
    0x36: ["virgola", ","],
    0x37: ["punto", "."],
    0x38: ["/"],
    0x39: ["bloc_maiusc", "capslock", "caps_lock"],
    0x49: ["ins", "insert"],
    0x4A: ["home", "inizio"],
    0x4B: ["pagsu", "pageup", "pag_su"],
    0x4C: ["canc", "delete", "del"],
    0x4D: ["fine", "end"],
    0x4E: ["paggiu", "pagedown", "pag_giu"],
    0x4F: ["destra_freccia", "freccia_destra", "right"],
    0x50: ["sinistra_freccia", "freccia_sinistra", "left"],
    0x51: ["giu_freccia", "freccia_giu", "down"],
    0x52: ["su_freccia", "freccia_su", "up"],
    0xE0: ["ctrl", "control", "ctrl_sinistro", "lctrl"],
    0xE1: ["shift", "maiusc", "shift_sinistro", "lshift"],
    0xE2: ["alt", "alt_sinistro", "lalt"],
    0xE4: ["ctrl_destro", "rctrl"],
    0xE5: ["shift_destro", "rshift"],
    0xE6: ["alt_gr", "altgr", "alt_destro", "ralt"],
}
for _codice, _nomi in _ALIAS.items():
    for _n in _nomi:
        CODICI[_n] = _codice

PULSANTI_MOUSE = {
    "mouse_sinistro": 1, "clic": 1, "click": 1, "tasto_sinistro": 1, "mouse1": 1, "lmb": 1,
    "mouse_destro": 2, "clic_destro": 2, "click_destro": 2, "tasto_destro": 2, "mouse2": 2, "rmb": 2,
    "mouse_centrale": 4, "rotella": 4, "mouse3": 4, "mmb": 4,
    "mouse4": 8, "mouse_laterale_1": 8,
    "mouse5": 16, "mouse_laterale_2": 16,
}
ROTELLA = {"rotella_su": 1, "scroll_su": 1, "rotella_giu": -1, "scroll_giu": -1}

# Tasti a cui servono maiuscole per scrivere un testo
_SHIFT_PER = {}
for _c in "abcdefghijklmnopqrstuvwxyz":
    _SHIFT_PER[_c.upper()] = _c


def _intero(v):
    """La parte intera, ma 199.99999 (errore dei numeri con la virgola) conta come 200."""
    r = round(v)
    return int(r) if abs(v - r) < 1e-6 else int(v)


def normalizza(nome):
    return str(nome).strip().lower().replace(" ", "_")


class TastoSconosciuto(ValueError):
    pass


def risolvi_grezzo(nome):
    """Da nome del tasto a ('tasto', codice) / ('mouse', bit) / ('rotella', +-1)."""
    n = normalizza(nome)
    if n in PULSANTI_MOUSE:
        return ("mouse", PULSANTI_MOUSE[n])
    if n in ROTELLA:
        return ("rotella", ROTELLA[n])
    if n in CODICI:
        return ("tasto", CODICI[n])
    if n.startswith("0x"):
        try:
            return ("tasto", int(n, 16))
        except ValueError:
            pass
    raise TastoSconosciuto("tasto sconosciuto: '%s'" % nome)


# ------------------------------------------------------------------ base comune
class Mani:
    """Parte comune: tiene il conto di cosa e' premuto e risolve i nomi dei tasti."""

    nome_modo = "base"

    def __init__(self, tasti_gioco=None, log=print):
        # tasti_gioco: dizionario azione -> tasto (es. {"costruisci": "x"})
        self.tasti_gioco = {normalizza(k): str(v) for k, v in (tasti_gioco or {}).items()}
        self.log = log
        self.tenuti = set()          # tasti tenuti premuti (codici HID)
        self.pulsanti = 0            # pulsanti del mouse premuti (bit)
        self._resto_x = 0.0
        self._resto_y = 0.0
        self.passi_totali_y = 0      # quanto ha alzato/abbassato la visuale (per rimetterla dritta)
        self.lock = threading.RLock()
        # movimento fluido: invece di un salto, tanti passettini (circa 200 al secondo)
        self.usa_fluido = True
        self.passo_fluido = 0.005
        self._fluido = None          # [dx che manca, dy che manca, quando deve aver finito]
        self._lock_fluido = threading.Lock()
        self._thread_fluido = None

    # ---- risoluzione nomi ----
    def risolvi(self, nome):
        """Accetta sia un'azione del gioco (es. 'costruisci' -> x) sia un tasto (es. 'x')."""
        n = normalizza(nome)
        visti = set()
        while n in self.tasti_gioco and n not in visti:
            visti.add(n)
            n = normalizza(self.tasti_gioco[n])
        return risolvi_grezzo(n)

    def esiste(self, nome):
        try:
            self.risolvi(nome)
            return True
        except TastoSconosciuto:
            return False

    # ---- da implementare nei modi ----
    def _tasto(self, codice, premuto):
        raise NotImplementedError

    def _mouse_pulsante(self, bit, premuto):
        raise NotImplementedError

    def _mouse_muovi(self, dx, dy):
        raise NotImplementedError

    def _rotella(self, n):
        raise NotImplementedError

    def _rilascia_tutto(self):
        raise NotImplementedError

    def chiudi(self):
        self.rilascia_tutto()

    # ---- comandi ----
    def giu(self, nome):
        tipo, valore = self.risolvi(nome)
        with self.lock:
            if tipo == "tasto":
                if valore not in self.tenuti:
                    self.tenuti.add(valore)
                    self._tasto(valore, True)
            elif tipo == "mouse":
                if not self.pulsanti & valore:
                    self.pulsanti |= valore
                    self._mouse_pulsante(valore, True)
            elif tipo == "rotella":
                self._rotella(valore)

    def su(self, nome):
        tipo, valore = self.risolvi(nome)
        with self.lock:
            if tipo == "tasto":
                if valore in self.tenuti:
                    self.tenuti.discard(valore)
                    self._tasto(valore, False)
            elif tipo == "mouse":
                if self.pulsanti & valore:
                    self.pulsanti &= ~valore
                    self._mouse_pulsante(valore, False)

    def e_premuto(self, nome):
        tipo, valore = self.risolvi(nome)
        if tipo == "tasto":
            return valore in self.tenuti
        if tipo == "mouse":
            return bool(self.pulsanti & valore)
        return False

    def premi(self, nome, durata=0.06):
        """Preme e rilascia (un 'tap')."""
        tipo, _ = self.risolvi(nome)
        if tipo == "rotella":
            self.giu(nome)
            return
        self.giu(nome)
        time.sleep(durata)
        self.su(nome)

    def imposta(self, nome, premuto):
        if premuto:
            self.giu(nome)
        else:
            self.su(nome)

    def muovi(self, dx, dy):
        """Muove il mouse di (dx, dy) 'passi'. Accetta anche numeri con la virgola:
        i pezzetti avanzati vengono sommati alla volta dopo."""
        with self.lock:
            self._resto_x += dx
            self._resto_y += dy
            ix = _intero(self._resto_x)
            iy = _intero(self._resto_y)
            self._resto_x -= ix
            self._resto_y -= iy
            if ix or iy:
                self.passi_totali_y += iy
                self._mouse_muovi(ix, iy)

    def rilascia_tutto(self):
        self.ferma_fluido()
        with self.lock:
            self.tenuti.clear()
            self.pulsanti = 0
            self._rilascia_tutto()

    # ---- movimento fluido (la visuale non va a scatti) ----
    def mira_fluida(self, dx, dy, durata):
        """Muove il mouse di (dx, dy) in 'durata' secondi a passettini, AL POSTO di quello
        che restava da fare (ogni fotogramma il cervello ricalcola dove andare)."""
        if not self.usa_fluido:
            self.muovi(dx, dy)
            return
        with self._lock_fluido:
            self._fluido = [float(dx), float(dy), time.monotonic() + max(self.passo_fluido, float(durata))]
            if self._thread_fluido is None or not self._thread_fluido.is_alive():
                self._thread_fluido = threading.Thread(target=self._ciclo_fluido, daemon=True)
                self._thread_fluido.start()

    def ferma_fluido(self):
        with self._lock_fluido:
            self._fluido = None

    def _passo_fluido(self, adesso):
        """Quanto muovere adesso (velocita' costante fino alla fine). None = niente da fare."""
        with self._lock_fluido:
            f = self._fluido
            if f is None:
                return None
            resto = f[2] - adesso
            if resto <= self.passo_fluido:
                dx, dy = f[0], f[1]
                self._fluido = None
            else:
                frazione = self.passo_fluido / resto
                dx, dy = f[0] * frazione, f[1] * frazione
                f[0] -= dx
                f[1] -= dy
            return dx, dy

    def _ciclo_fluido(self):
        fermo_da = time.monotonic()
        while True:
            time.sleep(self.passo_fluido)
            adesso = time.monotonic()
            passo = self._passo_fluido(adesso)
            if passo is None:
                if adesso - fermo_da > 1.0:
                    with self._lock_fluido:          # niente da fare da un po': il thread si ferma
                        if self._fluido is None:
                            self._thread_fluido = None
                            return
                continue
            fermo_da = adesso
            try:
                self.muovi(*passo)
            except Exception:
                self.ferma_fluido()                  # schedina staccata: se ne accorge il bot

    def scrivi(self, testo):
        """Scrive un testo (lettere, numeri, spazi)."""
        for c in str(testo):
            if c == " ":
                self.premi("spazio", 0.03)
            elif c in _SHIFT_PER:
                self.giu("shift")
                self.premi(_SHIFT_PER[c], 0.03)
                self.su("shift")
            else:
                try:
                    self.premi(c, 0.03)
                except TastoSconosciuto:
                    continue
            time.sleep(0.03)


# ------------------------------------------------------------------ modo PROVA
class ManiFinte(Mani):
    """Non preme niente: scrive solo cosa farebbe (se parla=True)."""

    nome_modo = "prova"

    def __init__(self, tasti_gioco=None, log=print, parla=False):
        super().__init__(tasti_gioco, log)
        self.usa_fluido = False       # nelle prove i movimenti si vedono subito
        self.parla = parla
        self.storia = []              # per i test: tutti i comandi mandati
        self.mosso_x = 0
        self.mosso_y = 0

    def _scrivi(self, testo):
        self.storia.append(testo)
        if len(self.storia) > 5000:
            del self.storia[:1000]
        if self.parla:
            self.log("   [prova] " + testo)

    def _tasto(self, codice, premuto):
        self._scrivi("%s tasto 0x%02X" % ("giu" if premuto else "su", codice))

    def _mouse_pulsante(self, bit, premuto):
        self._scrivi("%s mouse %d" % ("giu" if premuto else "su", bit))

    def _mouse_muovi(self, dx, dy):
        self.mosso_x += dx
        self.mosso_y += dy
        self._scrivi("muovi %d %d" % (dx, dy))

    def _rotella(self, n):
        self._scrivi("rotella %d" % n)

    def _rilascia_tutto(self):
        self._scrivi("rilascia tutto")


# ------------------------------------------------------------------ modo SCHEDINA (Pico)
class SchedinaNonTrovata(RuntimeError):
    pass


class ManiSchedina(Mani):
    """
    Parla con code.py sulla Pico. Due strade, le cerca tutte e due:
      - la seconda porta seriale USB della Pico (quella "dati", attivata da
        boot.py): la schedina e' attaccata a QUESTO PC;
      - un "ponte" (Arduino UNO tenuto in reset, o adattatore USB-seriale)
        collegato coi fili a GP0/GP1: la schedina e' attaccata alla PLAY.
    Protocollo a righe di testo (uguale per le due strade):
        P            -> la schedina risponde "OK BOT"
        H            -> "ci sono ancora" (se non arriva niente per 1 secondo,
                        la schedina rilascia tutti i tasti da sola)
        KD n / KU n  -> tasto giu / su (n = codice HID)
        BD n / BU n  -> pulsante del mouse giu / su
        M dx dy      -> muovi il mouse
        W n          -> rotella
        R            -> rilascia tutto
    """

    nome_modo = "schedina"
    VID_SCHEDINA = (0x239A, 0x2E8A)     # Adafruit/CircuitPython, Raspberry Pi: schedina sul PC
    # Ponti verso la schedina attaccata alla Play: Arduino (e cloni), CH340, CP210x, FTDI
    VID_PONTE = (0x2341, 0x2A03, 0x1A86, 0x10C4, 0x0403)

    def __init__(self, tasti_gioco=None, log=print, porta="auto"):
        super().__init__(tasti_gioco, log)
        try:
            import serial  # noqa: F401
        except ImportError:
            raise SchedinaNonTrovata("manca la libreria pyserial (pip install pyserial)")
        self.seriale = self._apri(porta)
        self._vivo = True
        self._ultimo_invio = time.monotonic()
        self._battito = threading.Thread(target=self._batti_cuore, daemon=True)
        self._battito.start()

    # ---- connessione ----
    def _prova_porta(self, nome):
        import serial
        try:
            s = serial.Serial(nome, 115200, timeout=0.3, write_timeout=1)
        except Exception:
            return None
        try:
            s.reset_input_buffer()
            for _ in range(3):
                s.write(b"\nP\n")
                s.flush()
                fine = time.monotonic() + 0.6
                ricevuto = b""
                while time.monotonic() < fine:
                    ricevuto += s.read(64)
                    if b"OK BOT" in ricevuto:
                        s.timeout = 0
                        return s
        except Exception:
            pass
        try:
            s.close()
        except Exception:
            pass
        return None

    def _apri(self, porta):
        porta = str(porta or "auto").strip()
        if porta.lower() != "auto":
            s = self._prova_porta(porta)
            if s is None:
                raise SchedinaNonTrovata("la schedina non risponde sulla porta %s" % porta)
            self.log("Schedina trovata sulla porta %s" % porta)
            return s
        from serial.tools import list_ports
        porte = list(list_ports.comports())
        schedina = [p for p in porte if p.vid in self.VID_SCHEDINA]
        # prima le porte "dati" (di solito hanno il numero di interfaccia piu' alto)
        schedina.sort(key=lambda p: (str(p.location or ""), p.device), reverse=True)
        ponti = sorted((p for p in porte if p.vid in self.VID_PONTE), key=lambda p: p.device)
        for p in schedina + ponti:
            s = self._prova_porta(p.device)
            if s is not None:
                self.log("Schedina trovata sulla porta %s" % p.device)
                return s
        elenco = ", ".join("%s (%s)" % (p.device, p.description) for p in porte) or "nessuna"
        raise SchedinaNonTrovata(
            "schedina non trovata. Porte viste: %s.\n"
            "Schedina sul PC: controlla che su CIRCUITPY ci siano boot.py e code.py del bot, "
            "poi stacca e riattacca la schedina (boot.py vale solo dopo averla staccata).\n"
            "Schedina sulla Play (guida, parte G): controlla i 3 fili e, se il ponte e' "
            "l'Arduino, il filo tra RESET e GND." % elenco)

    def _manda(self, testo):
        with self.lock:
            try:
                self.seriale.write((testo + "\n").encode("ascii"))
                self._ultimo_invio = time.monotonic()
            except Exception as e:
                self._vivo = False
                raise SchedinaNonTrovata("persa la connessione con la schedina: %s" % e)

    def _batti_cuore(self):
        while self._vivo:
            time.sleep(0.3)
            if time.monotonic() - self._ultimo_invio > 0.3:
                try:
                    self._manda("H")
                except Exception:
                    return

    # ---- comandi ----
    def _tasto(self, codice, premuto):
        self._manda("%s %d" % ("KD" if premuto else "KU", codice))

    def _mouse_pulsante(self, bit, premuto):
        self._manda("%s %d" % ("BD" if premuto else "BU", bit))

    def _mouse_muovi(self, dx, dy):
        self._manda("M %d %d" % (dx, dy))

    def _rotella(self, n):
        self._manda("W %d" % n)

    def _rilascia_tutto(self):
        self._manda("R")

    def chiudi(self):
        try:
            self.rilascia_tutto()
        except Exception:
            pass
        self._vivo = False
        try:
            self.seriale.close()
        except Exception:
            pass


# ------------------------------------------------------------------ modo SOFTWARE (solo Windows)
# Da codice HID a "scan code" (quello che usano i giochi con DirectInput)
_HID_A_SCAN = {}
for _i, _sc in enumerate([0x1E, 0x30, 0x2E, 0x20, 0x12, 0x21, 0x22, 0x23, 0x17, 0x24, 0x25, 0x26, 0x32,
                          0x31, 0x18, 0x19, 0x10, 0x13, 0x1F, 0x14, 0x16, 0x2F, 0x11, 0x2D, 0x15, 0x2C]):
    _HID_A_SCAN[0x04 + _i] = _sc                                   # a-z
for _i in range(9):
    _HID_A_SCAN[0x1E + _i] = 0x02 + _i                             # 1-9
_HID_A_SCAN[0x27] = 0x0B                                           # 0
for _i, _sc in enumerate([0x3B, 0x3C, 0x3D, 0x3E, 0x3F, 0x40, 0x41, 0x42, 0x43, 0x44, 0x57, 0x58]):
    _HID_A_SCAN[0x3A + _i] = _sc                                   # f1-f12
_HID_A_SCAN.update({
    0x28: 0x1C, 0x29: 0x01, 0x2A: 0x0E, 0x2B: 0x0F, 0x2C: 0x39, 0x2D: 0x0C, 0x2E: 0x0D,
    0x2F: 0x1A, 0x30: 0x1B, 0x31: 0x2B, 0x33: 0x27, 0x34: 0x28, 0x35: 0x29, 0x36: 0x33,
    0x37: 0x34, 0x38: 0x35, 0x39: 0x3A,
    0xE0: 0x1D, 0xE1: 0x2A, 0xE2: 0x38, 0xE5: 0x36,
})
# tasti "estesi" (serve un flag in piu')
_HID_ESTESI = {0x49: 0x52, 0x4A: 0x47, 0x4B: 0x49, 0x4C: 0x53, 0x4D: 0x4F, 0x4E: 0x51,
               0x4F: 0x4D, 0x50: 0x4B, 0x51: 0x50, 0x52: 0x48, 0xE4: 0x1D, 0xE6: 0x38}


class ManiSoftware(Mani):
    """Preme i tasti con SendInput di Windows (senza schedina)."""

    nome_modo = "software"

    def __init__(self, tasti_gioco=None, log=print):
        super().__init__(tasti_gioco, log)
        if sys.platform != "win32":
            raise RuntimeError("il modo 'software' funziona solo su Windows")
        import ctypes
        from ctypes import wintypes
        self.ctypes = ctypes

        ULONG_PTR = ctypes.c_size_t

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

        class HARDWAREINPUT(ctypes.Structure):
            _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]

        class _U(ctypes.Union):
            _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", wintypes.DWORD), ("u", _U)]

        self.INPUT = INPUT
        self.SendInput = ctypes.windll.user32.SendInput

    def _invia(self, inp):
        self.SendInput(1, self.ctypes.byref(inp), self.ctypes.sizeof(inp))

    def _tasto(self, codice, premuto):
        esteso = codice in _HID_ESTESI
        scan = _HID_ESTESI.get(codice) or _HID_A_SCAN.get(codice)
        if not scan:
            return
        inp = self.INPUT(type=1)
        inp.u.ki.wScan = scan
        inp.u.ki.dwFlags = 0x0008 | (0x0001 if esteso else 0) | (0 if premuto else 0x0002)
        self._invia(inp)

    def _mouse_pulsante(self, bit, premuto):
        flag = {1: (0x0002, 0x0004), 2: (0x0008, 0x0010), 4: (0x0020, 0x0040),
                8: (0x0080, 0x0100), 16: (0x0080, 0x0100)}.get(bit)
        if not flag:
            return
        inp = self.INPUT(type=0)
        inp.u.mi.dwFlags = flag[0] if premuto else flag[1]
        if bit in (8, 16):
            inp.u.mi.mouseData = 1 if bit == 8 else 2
        self._invia(inp)

    def _mouse_muovi(self, dx, dy):
        inp = self.INPUT(type=0)
        inp.u.mi.dx = int(dx)
        inp.u.mi.dy = int(dy)
        inp.u.mi.dwFlags = 0x0001
        self._invia(inp)

    def _rotella(self, n):
        inp = self.INPUT(type=0)
        inp.u.mi.mouseData = self.ctypes.c_uint32(120 * n).value
        inp.u.mi.dwFlags = 0x0800
        self._invia(inp)

    def _rilascia_tutto(self):
        # Windows non ha un "rilascia tutto": rilascio uno per uno quelli tenuti
        for codice in self._da_rilasciare:
            self._tasto(codice, False)
        for bit in (1, 2, 4):
            if self._pulsanti_da_rilasciare & bit:
                self._mouse_pulsante(bit, False)

    def rilascia_tutto(self):
        with self.lock:
            self._da_rilasciare = set(self.tenuti)
            self._pulsanti_da_rilasciare = self.pulsanti
            self.tenuti.clear()
            self.pulsanti = 0
            self._rilascia_tutto()


def crea_mani(cfg, log=print, modo=None):
    """Crea le mani giuste in base alle impostazioni."""
    comandi = cfg.get("comandi", {}) or {}
    modo = normalizza(modo or comandi.get("modo", "schedina"))
    tasti = cfg.get("tasti", {}) or {}
    if modo == "schedina":
        return ManiSchedina(tasti, log, comandi.get("porta", "auto"))
    if modo == "software":
        return ManiSoftware(tasti, log)
    if modo == "prova":
        return ManiFinte(tasti, log, parla=bool(comandi.get("scrivi_comandi_in_prova", False)))
    raise ValueError("modo comandi sconosciuto: '%s' (usa schedina, software o prova)" % modo)
