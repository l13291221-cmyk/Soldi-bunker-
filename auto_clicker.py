"""
auto_clicker.py - Auto-clicker per Windows con posizione e tempi casuali.

Avvio:   doppio click su AutoClicker.exe  (oppure: python auto_clicker.py)
Stop:    CTRL+C nella finestra nera
         (oppure porta il mouse in un angolo dello schermo: failsafe di pyautogui)
"""

import random
import sys
import time


def pausa_prima_di_chiudere():
    """Tiene aperta la finestra, cosi' si riesce a leggere il messaggio prima che sparisca."""
    try:
        input("\nPremi INVIO per chiudere...")
    except (EOFError, KeyboardInterrupt):
        pass


try:
    import pyautogui
except ImportError:
    print("Manca la libreria pyautogui. Installala con:  pip install pyautogui")
    pausa_prima_di_chiudere()
    sys.exit(1)


# ---------------------------------------------------------------- impostazioni
SECONDI_COUNTDOWN = 5

OFFSET_X = 80             # offset orizzontale casuale: da -80 a +80 pixel
OFFSET_Y = 15             # offset verticale casuale:   da -15 a +15 pixel

FACCE_DADO = 1000000      # dado da 1 a 1.000.000
ATTESA_MAX = 40           # attesa sempre dentro i 40 secondi

FACCE_DADO_PAUSA = 10     # se esce 1 su un dado da 10 -> pausa lunga (10%)
PAUSA_MIN = 120           # pausa lunga minima: 2 minuti
PAUSA_MAX = 240           # pausa lunga massima: 4 minuti

# Failsafe: se porti il mouse in un angolo dello schermo, il programma si ferma
# al click successivo. E' una sicurezza in piu' oltre a CTRL+C.
pyautogui.FAILSAFE = True


# ---------------------------------------------------------------- funzioni
def disattiva_quick_edit():
    """
    Solo Windows: se per sbaglio si clicca dentro la finestra nera, Windows
    "congela" il programma finche' non si preme un tasto (modalita' Modifica rapida).
    Qui la spegniamo, cosi' il clicker non si blocca mai.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-10)               # input della console
        modo = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(modo)):
            # toglie ENABLE_QUICK_EDIT_MODE (0x40), tiene ENABLE_EXTENDED_FLAGS (0x80)
            kernel32.SetConsoleMode(handle, (modo.value & ~0x0040) | 0x0080)
    except Exception:
        pass


def aspetta(secondi):
    """Aspetta a piccoli passi, cosi' CTRL+C risponde subito anche durante le attese lunghe."""
    fine = time.monotonic() + secondi
    while True:
        rimasto = fine - time.monotonic()
        if rimasto <= 0:
            return
        time.sleep(min(rimasto, 0.1))


def countdown_e_salva_posizione():
    """Countdown di 5 secondi, poi salva dove si trova il mouse."""
    print("Metti il mouse dove vuoi cliccare e non muoverlo")
    for secondi in range(SECONDI_COUNTDOWN, 0, -1):
        print(f"  {secondi}...")
        aspetta(1)
    x, y = pyautogui.position()
    return x, y


class GeneratorePosizioni:
    """
    Sceglie ogni volta un pixel casuale intorno al punto salvato
    (X da -80 a +80, Y da -15 a +15) e non ripete mai un pixel gia' cliccato.
    """

    def __init__(self, base_x, base_y):
        self.base_x = base_x
        self.base_y = base_y
        self.larghezza, self.altezza = pyautogui.size()
        self.usate = set()
        self.ultima = None
        # Quanti pixel diversi si possono usare intorno al punto (solo quelli dentro lo schermo).
        self.totale = sum(
            1
            for dx in range(-OFFSET_X, OFFSET_X + 1)
            for dy in range(-OFFSET_Y, OFFSET_Y + 1)
            if self._dentro_lo_schermo(base_x + dx, base_y + dy)
        )

    def _dentro_lo_schermo(self, x, y):
        # 1 pixel di margine dai bordi: negli angoli esatti scatterebbe il failsafe.
        return 1 <= x <= self.larghezza - 2 and 1 <= y <= self.altezza - 2

    def prossima(self):
        # Se sono stati usati tutti i pixel possibili, si ricomincia da capo
        # (tenendo fuori l'ultimo cliccato, cosi' non si ripete mai due volte di fila).
        if len(self.usate) >= self.totale:
            print("  (Usati tutti i pixel possibili intorno al punto: ricomincio da capo)")
            self.usate = {self.ultima}

        while True:
            x = self.base_x + random.randint(-OFFSET_X, OFFSET_X)
            y = self.base_y + random.randint(-OFFSET_Y, OFFSET_Y)
            if self._dentro_lo_schermo(x, y) and (x, y) not in self.usate:
                self.usate.add((x, y))
                self.ultima = (x, y)
                return x, y


def main():
    disattiva_quick_edit()
    print("=" * 60)
    print("  AUTO-CLICKER   -   premi CTRL+C per fermarlo")
    print("=" * 60)

    base_x, base_y = countdown_e_salva_posizione()
    print(f"\nPosizione salvata: X={base_x}, Y={base_y}")

    generatore = GeneratorePosizioni(base_x, base_y)
    if generatore.totale < 2:
        print("Il mouse deve stare sullo schermo principale. Riavvia e riprova.")
        return

    print(f"Pixel diversi disponibili intorno al punto: {generatore.totale}")
    print("Parto! (CTRL+C per fermare)\n")

    numero_click = 0
    while True:
        # 1) Tiro il dado da 1 a 1.000.000 e calcolo l'attesa (sempre dentro i 40 secondi)
        dado = random.randint(1, FACCE_DADO)
        attesa = (dado / FACCE_DADO) * ATTESA_MAX
        print(f"[Click {numero_click + 1}] Dado: {dado}  ->  attesa: {attesa:.2f} secondi")

        # 2) Aspetto
        aspetta(attesa)

        # 3) Scelgo una nuova posizione casuale intorno a dove ho lasciato il mouse
        x, y = generatore.prossima()

        # 4) Clicco
        pyautogui.click(x, y)
        numero_click += 1
        print(f"           Cliccato in: X={x}, Y={y}")

        # 5) Ogni tanto pausa lunga: 1 su 10
        if random.randint(1, FACCE_DADO_PAUSA) == 1:
            pausa = random.randint(PAUSA_MIN, PAUSA_MAX)
            print(f"PAUSA LUNGA - torno tra {pausa} secondi")
            aspetta(pausa)

        print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nFermato con CTRL+C. Ciao!")
        sys.exit(0)
    except pyautogui.FailSafeException:
        print("\nFermato: il mouse e' stato portato in un angolo dello schermo (failsafe).")
    except Exception:
        import traceback
        traceback.print_exc()
        print("\nC'e' stato un errore imprevisto.")
    # Si arriva qui solo se il programma si e' fermato per un motivo diverso da CTRL+C:
    # la finestra resta aperta per far leggere il messaggio.
    pausa_prima_di_chiudere()
