"""
auto_clicker.py - Auto-clicker per Windows con posizione e tempi casuali.

Avvio:   doppio click su AutoClicker.exe  (oppure: python auto_clicker.py)
Stop:    chiudi la finestra nera con la X, oppure CTRL+C dentro la finestra nera
         (oppure porta il mouse in un angolo dello schermo: failsafe di pyautogui)

Ogni decisione casuale (tempo, posizione, pausa) e' un tiro di un dado da
1.000.000 di facce:
  - ogni faccia ha la stessa probabilita' (1 su 1.000.000);
  - ogni tiro e' indipendente dai precedenti e nessuna faccia viene mai tolta;
  - il dado usa la casualita' del sistema operativo (la stessa usata per creare
    password e chiavi di sicurezza), quindi non si puo' prevedere.
"""

import secrets
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

FACCE_DADO = 1000000      # il dado va da 1 a 1.000.000

ATTESA_MAX = 40           # attesa = (dado / 1.000.000) * 40  -> sempre dentro i 40 secondi

OFFSET_X = 80             # spostamento destra/sinistra: da -80 a +80 pixel
OFFSET_Y = 15             # spostamento su/giu':         da -15 a +15 pixel

SOGLIA_PAUSA = 100000     # pausa lunga se il dado fa 100.000 o meno -> esattamente il 10%
PAUSA_MIN = 120           # pausa lunga minima: 2 minuti
PAUSA_MAX = 240           # pausa lunga massima: 4 minuti

# Failsafe: se porti il mouse in un angolo dello schermo, il programma si ferma
# al click successivo. E' una sicurezza in piu' oltre a CTRL+C.
pyautogui.FAILSAFE = True


# ---------------------------------------------------------------- il dado
def tira_dado():
    """
    Tira un dado da 1 a 1.000.000, come un dado vero:
    ogni faccia ha la stessa probabilita', ogni tiro e' indipendente,
    nessuna faccia viene tolta. secrets usa la casualita' del sistema operativo,
    quindi il risultato e' imprevedibile.
    """
    return secrets.randbelow(FACCE_DADO) + 1


def dado_in_spostamento(dado, massimo):
    """
    Trasforma un tiro da 1 a 1.000.000 in uno spostamento da -massimo a +massimo pixel.
    Il milione di facce e' diviso in parti uguali tra tutti gli spostamenti possibili:
    per X sono 161 spostamenti (circa 6.211 facce ciascuno),
    per Y sono 31 spostamenti (circa 32.258 facce ciascuno).
    """
    possibili = 2 * massimo + 1
    return (dado - 1) * possibili // FACCE_DADO - massimo


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


def scegli_posizione(base_x, base_y, ultima, larghezza, altezza):
    """
    Tira due dadi da 1.000.000: uno decide destra/sinistra, l'altro su/giu'.
    Insieme danno qualsiasi direzione: sopra, sotto, di lato, in diagonale.
    Si ritira solo se il punto uscirebbe dallo schermo, oppure se e' identico
    al click appena fatto (cosi' non clicca mai due volte di fila nello stesso pixel).
    """
    while True:
        dado_x = tira_dado()
        dado_y = tira_dado()
        dx = dado_in_spostamento(dado_x, OFFSET_X)
        dy = dado_in_spostamento(dado_y, OFFSET_Y)
        x, y = base_x + dx, base_y + dy
        # 1 pixel di margine dai bordi: negli angoli esatti scatterebbe il failsafe
        dentro_lo_schermo = 1 <= x <= larghezza - 2 and 1 <= y <= altezza - 2
        if dentro_lo_schermo and (x, y) != ultima:
            return x, y, dado_x, dado_y, dx, dy


def main():
    disattiva_quick_edit()
    print("=" * 70)
    print("  AUTO-CLICKER   -   per fermarlo chiudi questa finestra o premi CTRL+C")
    print("=" * 70)

    base_x, base_y = countdown_e_salva_posizione()
    print(f"\nPosizione salvata: X={base_x}, Y={base_y}")

    if not pyautogui.onScreen(base_x, base_y):
        print("Il mouse deve stare sullo schermo principale. Riavvia e riprova.")
        return

    larghezza, altezza = pyautogui.size()
    print("Parto!\n")

    ultima = None
    numero_click = 0
    while True:
        numero_click += 1

        # 1) Dado del TEMPO: quanto aspettare prima del click (sempre dentro i 40 secondi)
        dado_tempo = tira_dado()
        attesa = (dado_tempo / FACCE_DADO) * ATTESA_MAX
        print(f"[Click {numero_click}] Dado tempo: {dado_tempo:>7}  ->  attesa {attesa:.2f} secondi")
        aspetta(attesa)

        # 2) Dadi della POSIZIONE: dove cliccare intorno a dove hai lasciato il mouse
        x, y, dado_x, dado_y, dx, dy = scegli_posizione(base_x, base_y, ultima, larghezza, altezza)
        pyautogui.click(x, y)
        ultima = (x, y)
        print(f"           Dado X: {dado_x:>7}   Dado Y: {dado_y:>7}  ->  "
              f"cliccato in X={x}, Y={y}  (spostamento {dx:+d}, {dy:+d})")

        # 3) Dado della PAUSA: con 100.000 o meno (10%) fa la pausa lunga
        dado_pausa = tira_dado()
        if dado_pausa <= SOGLIA_PAUSA:
            dado_durata = tira_dado()
            pausa = PAUSA_MIN + (dado_durata / FACCE_DADO) * (PAUSA_MAX - PAUSA_MIN)
            print(f"           Dado pausa: {dado_pausa:>7}  ->  "
                  f"PAUSA LUNGA - torno tra {pausa:.0f} secondi  (dado durata: {dado_durata})")
            aspetta(pausa)
        else:
            print(f"           Dado pausa: {dado_pausa:>7}  ->  niente pausa (serve {SOGLIA_PAUSA} o meno)")

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
