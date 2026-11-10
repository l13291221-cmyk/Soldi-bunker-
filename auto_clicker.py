"""
auto_clicker.py - Preme il tasto P a tempi casuali (Windows).

Avvio:   doppio click su AutoClicker.exe  (oppure: python auto_clicker.py)
Stop:    chiudi la finestra nera con la X, oppure CTRL+C dentro la finestra nera
         (oppure porta il mouse in un angolo dello schermo: failsafe di pyautogui)

Ogni decisione casuale (tempo e pausa lunga) e' un tiro di un dado da
1.000.000 di facce:
  - ogni faccia ha la stessa probabilita' (1 su 1.000.000);
  - ogni tiro e' indipendente dai precedenti e nessuna faccia viene mai tolta;
  - il dado usa la casualita' del sistema operativo (la stessa usata per creare
    password e chiavi di sicurezza), quindi non si puo' prevedere.

Il tasto arriva alla finestra in primo piano: quella su cui hai cliccato per ultima.
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

TASTO = "p"               # il tasto da premere (minuscolo: P senza maiuscole)
NOME_TASTO = "P"          # come viene scritto nella finestra nera

FACCE_DADO = 1000000      # il dado va da 1 a 1.000.000

ATTESA_MAX = 40           # attesa = (dado / 1.000.000) * 40  -> sempre dentro i 40 secondi

SOGLIA_PAUSA = 100000     # pausa lunga se il dado fa 100.000 o meno -> esattamente il 10%
PAUSA_MIN = 120           # pausa lunga minima: 2 minuti
PAUSA_MAX = 240           # pausa lunga massima: 4 minuti

# Failsafe: se porti il mouse in un angolo dello schermo, il programma si ferma
# alla pressione successiva. E' una sicurezza in piu' oltre a CTRL+C.
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


# ---------------------------------------------------------------- funzioni
def disattiva_quick_edit():
    """
    Solo Windows: se per sbaglio si clicca dentro la finestra nera, Windows
    "congela" il programma finche' non si preme un tasto (modalita' Modifica rapida).
    Qui la spegniamo, cosi' il programma non si blocca mai.
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


def countdown():
    """Lascia 5 secondi per cliccare sulla finestra che deve ricevere il tasto."""
    print(f"Clicca sulla finestra dove vuoi che prema {NOME_TASTO} e lasciala in primo piano")
    for secondi in range(SECONDI_COUNTDOWN, 0, -1):
        print(f"  {secondi}...")
        aspetta(1)


def main():
    disattiva_quick_edit()
    print("=" * 70)
    print(f"  PREME {NOME_TASTO} DA SOLO   -   per fermarlo chiudi questa finestra o CTRL+C")
    print("=" * 70)

    countdown()
    print("\nParto!\n")

    numero = 0
    while True:
        numero += 1

        # 1) Dado del TEMPO: quanto aspettare prima di premere il tasto (sempre dentro i 40 secondi)
        dado_tempo = tira_dado()
        attesa = (dado_tempo / FACCE_DADO) * ATTESA_MAX
        print(f"[{NOME_TASTO} n.{numero}] Dado tempo: {dado_tempo:>7}  ->  attesa {attesa:.2f} secondi")
        aspetta(attesa)

        # 2) Premo il tasto
        pyautogui.press(TASTO)
        print(f"           Premuto {NOME_TASTO}")

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
