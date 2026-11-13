"""
obiettivo.py - L'obiettivo che scrivi tu (file obiettivo.txt), in parole semplici.

Frasi che il bot capisce (anche scritte in modo un po' diverso):
  "vincere e aprire piu' casse possibili"   -> quello predefinito: combatte e apre casse
  "aprire 50 casse a partita"               -> prima pensa alle casse (combatte solo se
                                               lo attaccano o un nemico e' vicino); arrivato
                                               a 50 casse in quella partita gioca per vincere
  "aprire piu' casse possibili"             -> sempre e solo casse (si difende se serve)
  "eliminare piu' nemici possibili"         -> cerca i nemici e li insegue
  "sopravvivere"                            -> evita i nemici lontani, si cura prima,
                                               costruisce quando lo colpiscono
"""

import os
import re
import unicodedata

PREDEFINITO = "vincere e aprire piu' casse possibili"

ESEMPI = [
    "vincere e aprire piu' casse possibili",
    "aprire 50 casse a partita",
    "aprire piu' casse possibili",
    "eliminare piu' nemici possibili",
    "sopravvivere",
]


class Obiettivo:
    def __init__(self, tipo="vincere", casse=0, testo=PREDEFINITO):
        self.tipo = tipo          # vincere | casse_n | casse | nemici | sopravvivere
        self.casse = int(casse)   # per casse_n: quante casse a partita
        self.testo = testo

    def descrizione(self):
        if self.tipo == "casse_n":
            return ("prima aprire %d casse a partita (combatte solo se lo attaccano o un nemico e' vicino), "
                    "poi giocare per vincere" % self.casse)
        return {
            "vincere": "vincere la partita e aprire piu' casse possibili",
            "casse": "aprire piu' casse possibili (combatte solo se lo attaccano o un nemico e' vicino)",
            "nemici": "eliminare piu' nemici possibili (li cerca e li insegue)",
            "sopravvivere": "sopravvivere (evita i nemici lontani, si cura prima, costruisce se lo colpiscono)",
        }[self.tipo]

    def pensa_alle_casse(self, casse_partita):
        """True = in questo momento le casse vengono prima dei nemici lontani."""
        if self.tipo == "casse":
            return True
        if self.tipo == "casse_n":
            return casse_partita < self.casse
        return False

    def __repr__(self):
        return "Obiettivo(%s, %d)" % (self.tipo, self.casse)


def _semplifica(testo):
    t = unicodedata.normalize("NFKD", str(testo).lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(t.replace("'", " ").split())


def capisci(testo):
    """Da una frase a un Obiettivo. Restituisce None se non la capisce."""
    t = _semplifica(testo)
    if not t:
        return Obiettivo()
    numero = re.search(r"\d+", t)
    parla_di_casse = re.search(r"\b(cass[ae]|forzier[ei]|loot|bottin[oi])", t) is not None
    if parla_di_casse and numero:
        n = int(numero.group())
        if n > 0:
            return Obiettivo("casse_n", n, testo)
    if re.search(r"\b(nemic|uccid|ammazz|elimin|kill|abbatt|sconfigg)", t):
        return Obiettivo("nemici", 0, testo)
    if re.search(r"\b(sopravviv|restare vivo|stare vivo|non morire|nasconder)", t):
        return Obiettivo("sopravvivere", 0, testo)
    if parla_di_casse and re.search(r"\b(vinc|vitt)", t):
        return Obiettivo("vincere", 0, testo)
    if parla_di_casse:
        return Obiettivo("casse", 0, testo)
    if re.search(r"\b(vinc|vitt|primo posto|win)", t):
        return Obiettivo("vincere", 0, testo)
    return None


def percorso(base):
    return os.path.join(base, "obiettivo.txt")


def leggi(base, log=print):
    """Legge obiettivo.txt (le righe con # non contano). Se manca o non la capisce: quello predefinito."""
    testo = ""
    try:
        with open(percorso(base), "r", encoding="utf-8-sig") as f:
            testo = " ".join(r.split("#", 1)[0].strip() for r in f if r.split("#", 1)[0].strip())
    except OSError:
        pass
    ob = capisci(testo)
    if ob is None:
        log("ATTENZIONE: non capisco l'obiettivo '%s'. Uso quello predefinito." % testo)
        log("   Esempi che capisco: " + " | ".join(ESEMPI))
        return Obiettivo()
    return ob


def scrivi(base, testo):
    with open(percorso(base), "w", encoding="utf-8") as f:
        f.write("# L'OBIETTIVO DEL BOT: scrivilo qui sotto con parole tue, su una riga.\n")
        f.write("# Esempi: " + " | ".join(ESEMPI) + "\n")
        f.write(testo.strip() + "\n")


SCELTE = [
    ("1", "vincere e aprire piu' casse possibili"),
    ("2", "aprire un tot di casse a partita (es. 50), poi giocare per vincere"),
    ("3", "aprire piu' casse possibili"),
    ("4", "eliminare piu' nemici possibili"),
    ("5", "sopravvivere"),
]


def chiedi(base, log=print):
    """Chiede l'obiettivo nella finestra nera (con i numeri o con parole tue) e lo salva.
    Restituisce l'Obiettivo. INVIO = lascia quello di prima."""
    attuale = leggi(base, lambda *_: None)
    print("\nOBIETTIVO attuale: %s" % attuale.testo)
    for numero, testo in SCELTE:
        print("  %s) %s" % (numero, testo))
    print("  (oppure scrivilo con parole tue)")
    while True:
        try:
            testo = input("Scrivi il numero e premi INVIO (solo INVIO = lascia quello attuale): ").strip()
        except (EOFError, KeyboardInterrupt):
            return attuale
        if not testo:
            return attuale
        if testo == "2":
            try:
                quante = input("Quante casse a partita? (es. 50): ").strip()
            except (EOFError, KeyboardInterrupt):
                return attuale
            if not quante.isdigit() or int(quante) <= 0:
                print("Scrivi solo un numero, es. 50.")
                continue
            testo = "aprire %d casse a partita" % int(quante)
        elif testo in ("1", "3", "4", "5"):
            testo = {"1": ESEMPI[0], "3": ESEMPI[2], "4": ESEMPI[3], "5": ESEMPI[4]}[testo]
        ob = capisci(testo)
        if ob is None:
            print("Non l'ho capito. Prova a scriverlo come uno degli esempi.")
            continue
        scrivi(base, testo)
        print("Ok! Ho capito: %s" % ob.descrizione())
        return ob
