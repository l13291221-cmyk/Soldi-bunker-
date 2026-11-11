# code.py - Raspberry Pi Pico (CircuitPython 10) - BOT SPARATUTTO
#
# La schedina fa da TASTIERA + MOUSE per il PC. Non decide niente da sola:
# il programma BotSparatutto sul PC guarda lo schermo, decide cosa fare e
# manda qui i comandi; la schedina li preme come una tastiera vera.
#
# Serve anche boot.py (accende la porta USB "dati").
#
# Sicurezza: se il PC non manda niente per 1 secondo (programma chiuso, cavo
# staccato, PC bloccato) la schedina rilascia da sola tutti i tasti.
#
# LA LUCINA VERDE:
#   spenta            = aspetta il programma sul PC
#   accesa fissa      = il programma sul PC e' collegato
#   lampeggia veloce  = manca boot.py, oppure non hai staccato e riattaccato
#                       la schedina dopo averlo copiato
#
# Comandi (una riga ciascuno):
#   P          -> risponde "OK BOT"          H         -> "ci sono ancora"
#   KD n/KU n  -> tasto giu/su (codice HID)   M dx dy   -> muovi il mouse
#   BD n/BU n  -> pulsante mouse giu/su       W n       -> rotella
#   R          -> rilascia tutto

import time

import usb_cdc
import usb_hid

try:
    import board
    import digitalio
except ImportError:
    board = None

try:
    import supervisor
    supervisor.runtime.autoreload = False   # salvare i file non riavvia il bot a meta' partita
except Exception:
    pass

ATTESA_SICUREZZA = 1.0   # secondi senza comandi prima di rilasciare tutto


# ------------------------------------------------------------------ lucina
led = None
if board is not None and hasattr(board, "LED"):
    led = digitalio.DigitalInOut(board.LED)
    led.direction = digitalio.Direction.OUTPUT


def luce(accesa):
    if led is not None:
        led.value = accesa


def lampeggia_errore(messaggio):
    print(messaggio)
    while True:
        luce(True)
        time.sleep(0.1)
        luce(False)
        time.sleep(0.1)


# ------------------------------------------------------------------ tastiera e mouse
def trova_dispositivo(usage):
    for d in usb_hid.devices:
        if d.usage_page == 0x01 and d.usage == usage:
            return d
    return None


tastiera = trova_dispositivo(0x06)
mouse = trova_dispositivo(0x02)
seriale = usb_cdc.data

if tastiera is None or mouse is None:
    lampeggia_errore("Tastiera o mouse USB non disponibili")
if seriale is None:
    lampeggia_errore("Manca la porta dati: copia boot.py, poi stacca e riattacca la schedina")

seriale.timeout = 0

tasti = []          # tasti normali premuti (massimo 6, come una tastiera vera)
modificatori = 0    # ctrl, shift, alt...
pulsanti = 0        # pulsanti del mouse
rt = bytearray(8)
rm = bytearray(4)


def invia(dispositivo, rapporto):
    for _ in range(20):
        try:
            dispositivo.send_report(rapporto)
            return
        except OSError:
            time.sleep(0.01)


def invia_tastiera():
    rt[0] = modificatori
    rt[1] = 0
    for i in range(6):
        rt[2 + i] = tasti[i] if i < len(tasti) else 0
    invia(tastiera, rt)


def invia_mouse(dx, dy, rotella=0):
    rm[0] = pulsanti
    rm[1] = dx & 0xFF
    rm[2] = dy & 0xFF
    rm[3] = rotella & 0xFF
    invia(mouse, rm)


def tasto(codice, premuto):
    global modificatori
    if 0xE0 <= codice <= 0xE7:
        bit = 1 << (codice - 0xE0)
        if premuto:
            modificatori |= bit
        else:
            modificatori &= ~bit
    elif premuto:
        if codice not in tasti and len(tasti) < 6:
            tasti.append(codice)
    elif codice in tasti:
        tasti.remove(codice)
    invia_tastiera()


def muovi(dx, dy):
    while dx or dy:
        px = max(-127, min(127, dx))
        py = max(-127, min(127, dy))
        invia_mouse(px, py)
        dx -= px
        dy -= py


def pulsante(bit, premuto):
    global pulsanti
    if premuto:
        pulsanti |= bit
    else:
        pulsanti &= ~bit
    invia_mouse(0, 0)


def rilascia_tutto():
    global modificatori, pulsanti
    del tasti[:]
    modificatori = 0
    pulsanti = 0
    invia_tastiera()
    invia_mouse(0, 0)


def qualcosa_premuto():
    return bool(tasti) or modificatori != 0 or pulsanti != 0


# ------------------------------------------------------------------ comandi dal PC
def esegui(riga):
    parti = riga.split()
    if not parti:
        return
    cmd = parti[0]
    try:
        numeri = [int(p) for p in parti[1:]]
    except ValueError:
        return
    if cmd == "P":
        seriale.write(b"OK BOT 1\n")
    elif cmd == "H":
        pass
    elif cmd == "M" and len(numeri) == 2:
        muovi(numeri[0], numeri[1])
    elif cmd == "KD" and numeri:
        tasto(numeri[0], True)
    elif cmd == "KU" and numeri:
        tasto(numeri[0], False)
    elif cmd == "BD" and numeri:
        pulsante(numeri[0], True)
    elif cmd == "BU" and numeri:
        pulsante(numeri[0], False)
    elif cmd == "W" and numeri:
        n = numeri[0]
        while n:
            p = max(-127, min(127, n))
            invia_mouse(0, 0, p)
            n -= p
    elif cmd == "R":
        rilascia_tutto()


def main():
    buffer = b""
    ultimo = -100.0
    collegato = False
    luce(False)
    print("Bot sparatutto: aspetto il programma sul PC...")
    while True:
        n = seriale.in_waiting
        if n:
            buffer += seriale.read(n)
            while True:
                fine = buffer.find(b"\n")
                if fine < 0:
                    break
                riga = buffer[:fine]
                buffer = buffer[fine + 1:]
                try:
                    esegui(riga.decode().strip())
                except Exception as e:
                    print("Comando sbagliato:", riga, e)
            if len(buffer) > 256:      # riga troppo lunga: spazzatura
                buffer = b""
            ultimo = time.monotonic()
            if not collegato:
                collegato = True
                luce(True)
        else:
            if collegato and time.monotonic() - ultimo > ATTESA_SICUREZZA:
                # il PC non parla piu': per sicurezza rilascio tutto
                collegato = False
                if qualcosa_premuto():
                    rilascia_tutto()
                luce(False)
            time.sleep(0.0005)


try:
    main()
except Exception as e:
    try:
        rilascia_tutto()
    except Exception:
        pass
    lampeggia_errore("Errore: %s" % e)
