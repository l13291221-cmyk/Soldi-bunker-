# code.py - Programma per la schedina Raspberry Pi Pico (CircuitPython 10).
#
# La schedina si presenta alla PlayStation come TASTIERA + MOUSE.
# Cosa fa si sceglie nel file impostazioni.txt (modalita):
#   gioca      = gioca a caso (cammina, gira, spara, salta...) e in sottofondo
#                i due dadi decidono quando e dove cliccare sul punto
#   solo_click = clicca solo sul punto, sempre con i due dadi
#   avanti_e_spazio = tiene SEMPRE premuto W, preme SPAZIO ogni 0-20 secondi
#                (deciso dal dado) e in sottofondo clicca sul punto con i due dadi
#   prova      = porta il cursore sul punto ogni 5 secondi SENZA cliccare
#   righello   = muove il cursore a scatti di 100 passi per trovare i numeri del punto
#
# Ogni decisione casuale e' un tiro di un dado da 1.000.000 di facce che usa il
# generatore casuale hardware della schedina: ogni faccia ha la stessa
# probabilita', ogni tiro e' indipendente, nessuna faccia viene mai tolta.
#
# Sicurezza: se la schedina e' attaccata al PC e premi BLOC MAIUSC (Caps Lock),
# si ferma e non fa niente (lucina accesa fissa): cosi' puoi modificare i file.

import os
import time

import usb_hid

try:
    import board
    import digitalio
except ImportError:
    board = None

try:
    import supervisor
except ImportError:
    supervisor = None


FACCE = 1000000

PREDEFINITE = {
    "modalita": "righello",
    "punto_destra": 800,
    "punto_giu": 450,
    "spostamento_x": 80,
    "spostamento_y": 15,
    "attesa_max": 40.0,
    "pausa_percentuale": 10,
    "pausa_min": 120,
    "pausa_max": 240,
    "cammina": 35,
    "gira": 15,
    "spara": 15,
    "spara_in_aria": 10,
    "salta": 10,
    "accovacciati": 5,
    "ricarica": 5,
    "fermo": 5,
    "tasto_avanti": "w",
    "tasto_indietro": "s",
    "tasto_sinistra": "a",
    "tasto_destra": "d",
    "tasto_salto": "spazio",
    "tasto_accovacciati": "ctrl",
    "tasto_ricarica": "r",
    "sensibilita": 1.0,
    "attesa_iniziale": 15,
    "controllo_pc": 1,
    "tasto_tenuto": "w",
    "tasto_ogni_tanto": "spazio",
    "ogni_tanto_min": 0.0,
    "ogni_tanto_max": 20.0,
    "clicca_anche": 1,
}


# ------------------------------------------------------------------ impostazioni
def leggi_impostazioni(percorso="impostazioni.txt"):
    """Legge impostazioni.txt. Le righe sbagliate o mancanti usano il valore predefinito."""
    imp = dict(PREDEFINITE)
    try:
        with open(percorso, "r") as f:
            righe = f.read().split("\n")
    except OSError:
        return imp
    for riga in righe:
        riga = riga.split("#")[0].strip()
        if "=" not in riga:
            continue
        chiave, valore = riga.split("=", 1)
        chiave = chiave.strip().lower()
        valore = valore.strip().lower()
        if chiave not in PREDEFINITE or not valore:
            continue
        predefinito = PREDEFINITE[chiave]
        if isinstance(predefinito, str):
            imp[chiave] = valore.replace(" ", "_")
            continue
        try:
            numero = float(valore.replace(",", "."))
        except ValueError:
            continue
        if isinstance(predefinito, float):
            imp[chiave] = abs(numero)
        else:
            imp[chiave] = abs(int(round(numero)))
    if imp["pausa_min"] > imp["pausa_max"]:
        imp["pausa_min"], imp["pausa_max"] = imp["pausa_max"], imp["pausa_min"]
    if imp["ogni_tanto_min"] > imp["ogni_tanto_max"]:
        imp["ogni_tanto_min"], imp["ogni_tanto_max"] = imp["ogni_tanto_max"], imp["ogni_tanto_min"]
    return imp


# ------------------------------------------------------------------ il dado
try:
    os.urandom(4)
    _HARDWARE = True
except (NotImplementedError, AttributeError):
    import random
    _HARDWARE = False

_LIMITE = (4294967296 // FACCE) * FACCE   # per non favorire nessuna faccia


def tira_dado():
    """Tira un dado da 1 a 1.000.000, come un dado vero."""
    while True:
        if _HARDWARE:
            n = int.from_bytes(os.urandom(4), "big")
        else:
            n = random.getrandbits(32)
        if n < _LIMITE:
            return n % FACCE + 1


def tra(minimo, massimo):
    """Numero intero da minimo a massimo (compresi), deciso da un tiro di dado."""
    return minimo + (tira_dado() - 1) * (massimo - minimo + 1) // FACCE


def dado_in_spostamento(dado, massimo):
    """Trasforma un tiro da 1 a 1.000.000 in uno spostamento da -massimo a +massimo."""
    return (dado - 1) * (2 * massimo + 1) // FACCE - massimo


def ora():
    """Millisecondi dall'accensione (intero: resta preciso anche dopo giorni)."""
    return time.monotonic_ns() // 1000000


# ------------------------------------------------------------------ tasti
def codice_tasto(nome):
    """Da nome del tasto (es. 'w', 'spazio', 'ctrl') a (codice, modificatore)."""
    nome = nome.strip().lower()
    modificatori = {"ctrl": 0x01, "control": 0x01, "shift": 0x02, "maiusc": 0x02, "alt": 0x04}
    if nome in modificatori:
        return (0, modificatori[nome])
    speciali = {
        "spazio": 0x2C, "space": 0x2C, "invio": 0x28, "enter": 0x28, "tab": 0x2B,
        "esc": 0x29, "backspace": 0x2A,
        "freccia_su": 0x52, "freccia_giu": 0x51, "freccia_sinistra": 0x50, "freccia_destra": 0x4F,
    }
    if nome in speciali:
        return (speciali[nome], 0)
    if len(nome) == 1 and "a" <= nome <= "z":
        return (0x04 + ord(nome) - ord("a"), 0)
    if len(nome) == 1 and "1" <= nome <= "9":
        return (0x1E + ord(nome) - ord("1"), 0)
    if nome == "0":
        return (0x27, 0)
    if len(nome) > 1 and nome[0] == "f" and nome[1:].isdigit() and 1 <= int(nome[1:]) <= 12:
        return (0x3A + int(nome[1:]) - 1, 0)
    return None   # nome non riconosciuto: quel tasto non viene premuto


# ------------------------------------------------------------------ tastiera e mouse
def trova_dispositivo(usage):
    for d in usb_hid.devices:
        if d.usage_page == 0x01 and d.usage == usage:
            return d
    return None


def invia(dispositivo, rapporto):
    while True:
        try:
            dispositivo.send_report(rapporto)
            return
        except OSError:
            time.sleep(0.5)   # la console non e' ancora pronta: riprovo


class Controlli:
    """Tiene premuti/rilascia tasti e pulsanti, e muove il mouse."""

    def __init__(self, tastiera, mouse):
        self.tastiera = tastiera
        self.mouse = mouse
        self.tasti = []
        self.modificatori = 0
        self.pulsanti = 0
        self.rt = bytearray(8)
        self.rm = bytearray(4)

    def _invia_tastiera(self):
        self.rt[0] = self.modificatori
        self.rt[1] = 0
        for i in range(6):
            self.rt[2 + i] = self.tasti[i] if i < len(self.tasti) else 0
        invia(self.tastiera, self.rt)

    def premi(self, tasto):
        if tasto is None:
            return
        codice, mod = tasto
        if mod:
            self.modificatori |= mod
        elif codice not in self.tasti and len(self.tasti) < 6:
            self.tasti.append(codice)
        self._invia_tastiera()

    def rilascia(self, tasto):
        if tasto is None:
            return
        codice, mod = tasto
        if mod:
            self.modificatori &= ~mod
        elif codice in self.tasti:
            self.tasti.remove(codice)
        self._invia_tastiera()

    def _invia_mouse(self, dx, dy):
        self.rm[0] = self.pulsanti
        self.rm[1] = dx & 0xFF
        self.rm[2] = dy & 0xFF
        self.rm[3] = 0
        invia(self.mouse, self.rm)

    def muovi(self, dx, dy):
        dx = int(dx)
        dy = int(dy)
        while dx or dy:
            px = max(-127, min(127, dx))
            py = max(-127, min(127, dy))
            self._invia_mouse(px, py)
            dx -= px
            dy -= py

    def pulsante_sinistro(self, premuto):
        self.pulsanti = 1 if premuto else 0
        self._invia_mouse(0, 0)

    def rilascia_tutto(self):
        self.tasti = []
        self.modificatori = 0
        self._invia_tastiera()
        self.pulsante_sinistro(False)


# ------------------------------------------------------------------ lucina
led = None
if board is not None and hasattr(board, "LED"):
    led = digitalio.DigitalInOut(board.LED)
    led.direction = digitalio.Direction.OUTPUT


def luce(accesa):
    if led is not None:
        led.value = accesa


# ------------------------------------------------------------------ il programma
class OraDiCliccare(Exception):
    pass


imp = None
c = None
TASTIERA = None
prossimo_click = None      # in millisecondi; None = nessun click in arrivo
ultimo_spostamento = None
sens = 1.0


def attaccata_al_pc():
    """True se il PC ha mandato la lucina di BLOC MAIUSC o BLOC NUM accesa."""
    if not imp["controllo_pc"]:
        return False
    try:
        r = TASTIERA.get_last_received_report()
    except Exception:
        return False
    return r is not None and len(r) > 0 and r[0] != 0


def modalita_pc():
    """Ferma tutto e resta ferma (lucina fissa) finche' non la stacchi."""
    c.rilascia_tutto()
    luce(True)
    while True:
        time.sleep(1)


def attendi(ms, vx=0.0, vy=0.0):
    """Aspetta ms millisecondi; intanto gira la visuale di (vx, vy) passi ogni 10 ms.
    Se e' ora di cliccare, interrompe l'azione in corso."""
    fine = ora() + int(ms)
    resto_x = 0.0
    resto_y = 0.0
    while True:
        if attaccata_al_pc():
            modalita_pc()
        adesso = ora()
        if prossimo_click is not None and adesso >= prossimo_click:
            raise OraDiCliccare()
        if adesso >= fine:
            return
        if vx or vy:
            resto_x += vx
            resto_y += vy
            mx = int(resto_x)
            my = int(resto_y)
            resto_x -= mx
            resto_y -= my
            if mx or my:
                c.muovi(mx, my)
        time.sleep(0.01)


def tocca(tasto):
    """Preme e rilascia un tasto."""
    c.premi(tasto)
    try:
        attendi(tra(60, 120))
    finally:
        c.rilascia(tasto)


# ---- spostamento sul punto ----
def vai_angolo():
    """Spinge il cursore nell'angolo in alto a sinistra: e' sempre lo stesso punto di partenza."""
    for _ in range(50):
        c.muovi(-127, -127)
        time.sleep(0.005)
    time.sleep(0.05)


def muovi_piano(x, y):
    """Muove di (x, y) a piccoli passi, sempre allo stesso ritmo: arriva sempre nello stesso punto."""
    passi = max(abs(x), abs(y)) // 10 + 1
    fatto_x = 0
    fatto_y = 0
    for i in range(1, passi + 1):
        nx = x * i // passi
        ny = y * i // passi
        c.muovi(nx - fatto_x, ny - fatto_y)
        fatto_x = nx
        fatto_y = ny
        time.sleep(0.008)


def vai_al_punto(dx, dy, tieni=None):
    c.rilascia_tutto()
    if tieni is not None:
        c.premi(tieni)          # questo tasto resta premuto anche mentre va sul punto
    vai_angolo()
    muovi_piano(max(0, imp["punto_destra"] + dx), max(0, imp["punto_giu"] + dy))


def clicca_sul_punto(tieni=None):
    """Due dadi decidono lo spostamento intorno al punto, poi clicca.
    Si ritira solo se uscirebbe identico al click precedente."""
    global ultimo_spostamento
    sx = imp["spostamento_x"]
    sy = imp["spostamento_y"]
    while True:
        dx = dado_in_spostamento(tira_dado(), sx)
        dy = dado_in_spostamento(tira_dado(), sy)
        if (dx, dy) != ultimo_spostamento or (sx == 0 and sy == 0):
            break
    ultimo_spostamento = (dx, dy)
    luce(True)
    vai_al_punto(dx, dy, tieni)
    time.sleep(0.1)
    c.pulsante_sinistro(True)
    time.sleep(0.08)
    c.pulsante_sinistro(False)
    luce(False)
    return dx, dy


# ---- azioni di gioco (tutte decise dal dado) ----
def azione_cammina():
    av = codice_tasto(imp["tasto_avanti"])
    ind = codice_tasto(imp["tasto_indietro"])
    sx = codice_tasto(imp["tasto_sinistra"])
    dx = codice_tasto(imp["tasto_destra"])
    direzioni = [(av,), (ind,), (sx,), (dx,), (av, sx), (av, dx), (ind, sx), (ind, dx)]
    scelta = direzioni[tra(0, len(direzioni) - 1)]
    for t in scelta:
        c.premi(t)
    try:
        attendi(tra(500, 3000), tra(-6, 6) * sens, 0)
    finally:
        for t in scelta:
            c.rilascia(t)


def azione_gira():
    totale = tra(150, 900) * (1 if tra(0, 1) else -1) * sens
    durata = tra(200, 800)
    attendi(durata, totale / (durata / 10), 0)


def azione_spara():
    c.pulsante_sinistro(True)
    try:
        attendi(tra(200, 2000), tra(-3, 3) * sens, 0)
    finally:
        c.pulsante_sinistro(False)


def azione_spara_in_aria():
    su = tra(250, 500) * sens
    attendi(300, 0, -su / 30)        # alza la visuale
    c.pulsante_sinistro(True)
    try:
        attendi(tra(500, 2000))
    finally:
        c.pulsante_sinistro(False)
    attendi(300, 0, su / 30)         # la riabbassa


def azione_salta():
    tocca(codice_tasto(imp["tasto_salto"]))
    attendi(tra(300, 800))


def azione_accovacciati():
    t = codice_tasto(imp["tasto_accovacciati"])
    c.premi(t)
    try:
        attendi(tra(500, 2000))
    finally:
        c.rilascia(t)


def azione_ricarica():
    tocca(codice_tasto(imp["tasto_ricarica"]))
    attendi(tra(500, 1500))


def azione_fermo():
    attendi(tra(500, 3000))


AZIONI = [
    ("cammina", azione_cammina),
    ("gira", azione_gira),
    ("spara", azione_spara),
    ("spara_in_aria", azione_spara_in_aria),
    ("salta", azione_salta),
    ("accovacciati", azione_accovacciati),
    ("ricarica", azione_ricarica),
    ("fermo", azione_fermo),
]


def scegli_azione(pesi, totale):
    r = (tira_dado() - 1) * totale // FACCE
    for peso, funzione in pesi:
        if r < peso:
            return funzione
        r -= peso
    return pesi[-1][1]


def nuova_attesa():
    """Dado del tempo: attesa = (dado / 1.000.000) * attesa_max secondi."""
    return int(tira_dado() * imp["attesa_max"] * 1000 // FACCE)


# ---- modalita ----
def gioca(con_azioni):
    global prossimo_click
    pesi = [(imp[nome], funzione) for nome, funzione in AZIONI if imp[nome] > 0]
    totale = 0
    for peso, _ in pesi:
        totale += peso
    soglia_pausa = int(imp["pausa_percentuale"] * FACCE // 100)
    prossimo_click = ora() + nuova_attesa()
    while True:
        try:
            if con_azioni and totale > 0:
                scegli_azione(pesi, totale)()
            else:
                attendi(1000)
        except OraDiCliccare:
            prossimo_click = None
            c.rilascia_tutto()
            clicca_sul_punto()
            if tira_dado() <= soglia_pausa:
                # pausa lunga: si ferma del tutto, come una persona che fa una pausa
                durata = imp["pausa_min"] * 1000 + tira_dado() * (imp["pausa_max"] - imp["pausa_min"]) * 1000 // FACCE
                attendi(durata)
            prossimo_click = ora() + nuova_attesa()


def attesa_ogni_tanto():
    """Dado del tasto ogni tanto: da ogni_tanto_min a ogni_tanto_max secondi (in millisecondi)."""
    minimo = int(imp["ogni_tanto_min"] * 1000)
    massimo = int(imp["ogni_tanto_max"] * 1000)
    return minimo + (tira_dado() - 1) * (massimo - minimo + 1) // FACCE


def avanti_e_spazio():
    """Tiene SEMPRE premuto W (anche mentre clicca); ogni 0-20 secondi (dado) preme
    SPAZIO; in sottofondo clicca sul punto con i due dadi (se clicca_anche = 1).
    La pausa lunga (1 volta su 10) ferma solo i click: W e SPAZIO continuano."""
    global prossimo_click
    tenuto = codice_tasto(imp["tasto_tenuto"])
    ogni_tanto = codice_tasto(imp["tasto_ogni_tanto"])
    soglia_pausa = int(imp["pausa_percentuale"] * FACCE // 100)
    prossimo_click = ora() + nuova_attesa() if imp["clicca_anche"] else None
    prossimo_tasto = ora() + attesa_ogni_tanto()
    c.premi(tenuto)
    while True:
        try:
            attendi(max(0, prossimo_tasto - ora()))
            tocca(ogni_tanto)
            prossimo_tasto = ora() + attesa_ogni_tanto()
        except OraDiCliccare:
            prossimo_click = None
            clicca_sul_punto(tenuto)
            prossimo_click = ora() + nuova_attesa()
            if tira_dado() <= soglia_pausa:
                # pausa lunga: per 2-4 minuti non clicca (W e SPAZIO continuano)
                durata = imp["pausa_min"] * 1000 + tira_dado() * (imp["pausa_max"] - imp["pausa_min"]) * 1000 // FACCE
                prossimo_click += durata
            c.premi(tenuto)


def prova():
    while True:
        vai_al_punto(0, 0)
        luce(True)
        attendi(5000)
        luce(False)


def righello():
    while True:
        c.rilascia_tutto()
        vai_angolo()
        for _ in range(25):
            muovi_piano(100, 0)
            luce(True)
            attendi(300)
            luce(False)
            attendi(1200)
        vai_angolo()
        for _ in range(15):
            muovi_piano(0, 100)
            luce(True)
            attendi(300)
            luce(False)
            attendi(1200)
        attendi(3000)


def lampeggia_errore():
    while True:
        luce(True)
        time.sleep(0.1)
        luce(False)
        time.sleep(0.1)


def main():
    global imp, c, TASTIERA, sens
    if supervisor is not None:
        try:
            # le modifiche ai file valgono dalla prossima volta che la attacchi
            supervisor.runtime.autoreload = False
        except Exception:
            pass
    imp = leggi_impostazioni()
    sens = imp["sensibilita"]
    TASTIERA = trova_dispositivo(0x06)
    mouse = trova_dispositivo(0x02)
    if TASTIERA is None or mouse is None:
        lampeggia_errore()
    c = Controlli(TASTIERA, mouse)

    # attesa iniziale: lucina che lampeggia piano = sta per partire
    fine = ora() + imp["attesa_iniziale"] * 1000
    accesa = False
    while ora() < fine:
        if attaccata_al_pc():
            modalita_pc()
        accesa = not accesa
        luce(accesa)
        time.sleep(0.5)
    luce(False)

    modalita = imp["modalita"]
    print("Modalita:", modalita)
    if modalita == "righello":
        righello()
    elif modalita == "prova":
        prova()
    elif modalita == "solo_click":
        gioca(False)
    elif modalita == "gioca":
        gioca(True)
    elif modalita == "avanti_e_spazio":
        avanti_e_spazio()
    else:
        print("Modalita sconosciuta:", modalita)
        lampeggia_errore()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("Errore:", e)
        try:
            c.rilascia_tutto()
        except Exception:
            pass
        lampeggia_errore()
