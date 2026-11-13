"""
stile.py - COME gioca il bot: si sceglie ogni volta che lo avvii (menu 1).

  1. Normale     : mira un po' piu' lenta, ci mette un attimo a reagire e ogni tanto
                   sbaglia il colpo (come una persona normale)
  2. Pro player  : velocissimo e preciso, reagisce subito
  3. Tranquillo  : evita gli scontri: non insegue, ignora i nemici lontani, si difende
                   solo se lo attaccano o se un nemico e' vicino, e intanto apre casse

L'OBIETTIVO (quello che scrivi tu, menu 11) resta lo stesso: lo stile dice solo COME gioca.
L'ultima scelta si ricorda nel file modalita.txt.
"""

import os


class Stile:
    def __init__(self, chiave, nome, descrizione, forza=1.0, errore=0.0, reazione=0.0,
                 solo_vicini=False, insegui=True):
        self.chiave = chiave
        self.nome = nome
        self.descrizione = descrizione
        self.forza = forza                # la mira imparata x questo numero (meno = piu' lenta)
        self.errore = errore              # quanto sbaglia la mira (parte della grandezza del nemico)
        self.reazione = reazione          # secondi prima di sparare a un nemico appena visto
        self.solo_vicini = solo_vicini    # True = ignora i nemici lontani (si difende solo se serve)
        self.insegui = insegui            # False = non va mai verso i nemici

    @property
    def mira_perfetta(self):
        """Solo con la mira 'vera' (senza errori voluti) il bot impara la forza giusta della mira."""
        return self.errore == 0 and self.forza == 1.0

    def __repr__(self):
        return "Stile(%s)" % self.chiave


STILI = {
    "normale": Stile("normale", "Normale", "mira un po' piu' lenta e ogni tanto sbaglia",
                     forza=0.7, errore=0.35, reazione=0.25),
    "pro": Stile("pro", "Pro player", "velocissimo e preciso, reagisce subito"),
    "tranquillo": Stile("tranquillo", "Tranquillo",
                        "evita gli scontri: non insegue, si difende solo se serve e apre piu' casse possibili",
                        forza=0.85, errore=0.15, reazione=0.15, solo_vicini=True, insegui=False),
}
ORDINE = ["normale", "pro", "tranquillo"]
PREDEFINITO = "normale"


def capisci(testo):
    """'1' / 'normale' / 'pro' / 'tranquillo'... -> Stile, oppure None."""
    t = str(testo or "").strip().lower()
    if t in ("1", "2", "3"):
        return STILI[ORDINE[int(t) - 1]]
    for chiave in ORDINE:
        if t and (t == chiave or chiave.startswith(t) or t in STILI[chiave].nome.lower()):
            return STILI[chiave]
    return None


def percorso(base):
    return os.path.join(base, "modalita.txt")


def leggi(base):
    """L'ultima modalita' scelta (oppure Normale)."""
    try:
        with open(percorso(base), "r", encoding="utf-8-sig") as f:
            for riga in f:
                riga = riga.split("#", 1)[0].strip()
                if riga:
                    return capisci(riga) or STILI[PREDEFINITO]
    except OSError:
        pass
    return STILI[PREDEFINITO]


def scrivi(base, stile):
    try:
        with open(percorso(base), "w", encoding="utf-8") as f:
            f.write("# Ultima modalita' scelta (normale / pro / tranquillo). Si sceglie quando avvii il bot.\n")
            f.write(stile.chiave + "\n")
    except OSError:
        pass


def chiedi(base):
    """Chiede la modalita' nella finestra nera (INVIO = l'ultima usata) e la ricorda."""
    ultima = leggi(base)
    print("\nCOME DEVE GIOCARE?")
    for i, chiave in enumerate(ORDINE, 1):
        s = STILI[chiave]
        print("  %d) %-11s - %s%s" % (i, s.nome, s.descrizione, "   <- l'ultima" if s is ultima else ""))
    while True:
        try:
            testo = input("Scrivi 1, 2 o 3 e premi INVIO (solo INVIO = %s): " % ultima.nome).strip()
        except (EOFError, KeyboardInterrupt):
            return ultima
        if not testo:
            return ultima
        stile = capisci(testo)
        if stile is not None:
            scrivi(base, stile)
            return stile
        print("Non ho capito: scrivi 1, 2 oppure 3.")
