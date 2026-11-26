"""
guida_completa.py - crea GUIDA_COMPLETA.pdf: la guida illustrata (con i disegni) per montare la
schedina Pico, collegare tutto alla Play e al PC, e avviare il bot.

    python guida_completa.py            -> scrive GUIDA_COMPLETA.pdf qui accanto

Serve matplotlib (pip install matplotlib). I disegni sono SCHEMI (non foto): mostrano dove va
ogni filo, con i nomi scritti sui piedini veri della Pico e dell'Arduino.
"""

import os
import sys
import textwrap

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Rectangle  # noqa: E402

QUI = os.path.dirname(os.path.abspath(__file__))
A4 = (8.27, 11.69)
BLU, ROSSO, VERDE, ARANCIO, VIOLA, GRIGIO = "#1f5fbf", "#d62728", "#2ca02c", "#ff7f0e", "#7b3fbf", "#555555"
FILO_RX, FILO_TX, FILO_GND, PONTICELLO = "#e6a100", "#1f9e3a", "#222222", "#d62728"


def pagina(pdf, titolo, sottotitolo=None):
    fig = plt.figure(figsize=A4)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 141.4)
    ax.axis("off")
    ax.add_patch(Rectangle((0, 131), 100, 10.4, color=BLU))
    ax.text(5, 136, titolo, color="white", fontsize=19, fontweight="bold", va="center")
    if sottotitolo:
        ax.text(5, 127.5, sottotitolo, color=GRIGIO, fontsize=10.5, va="center", style="italic")
    numero = len(pdf._pagine) + 1
    ax.text(95, 3, "Bot Sparatutto - guida completa - pagina %d" % numero, color=GRIGIO, fontsize=8, ha="right")
    pdf._pagine.append(fig)
    return fig, ax


def testo(ax, x, y, righe, larghezza=88, dimensione=10.5, interlinea=1.65, colore="black", grassetto=False):
    """Scrive un paragrafo (o una lista di paragrafi) andando a capo da solo. -> y dopo il testo."""
    if isinstance(righe, str):
        righe = [righe]
    for r in righe:
        rientro = "    " if r.startswith(("- ", "• ")) else ""
        pezzi = textwrap.wrap(r, larghezza, subsequent_indent=rientro) or [""]
        for p in pezzi:
            ax.text(x, y, p, fontsize=dimensione, color=colore, va="top",
                    fontweight="bold" if grassetto else "normal")
            y -= interlinea * dimensione / 10.5 * 2.05
        y -= 0.8
    return y


def riquadro(ax, x, y, w, h, colore, titolo=None, riempi=None, spessore=2):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.4,rounding_size=1.5",
                                linewidth=spessore, edgecolor=colore, facecolor=riempi or "white"))
    if titolo:
        ax.text(x + w / 2, y + h - 2.2, titolo, ha="center", va="top", fontsize=11, fontweight="bold", color=colore)


def freccia(ax, x1, y1, x2, y2, colore="black", testo_=None, doppia=False, spessore=2.2, curva=0.0):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="<|-|>" if doppia else "-|>",
                                 mutation_scale=16, linewidth=spessore, color=colore,
                                 connectionstyle="arc3,rad=%.2f" % curva))
    if testo_:
        ax.text((x1 + x2) / 2 + 1, (y1 + y2) / 2 + 1, testo_, fontsize=9, color=colore, ha="center",
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none"))


def resistenza(ax, x, y, verticale=False, etichetta="10 kΩ"):
    """Una resistenza disegnata come quelle vere (con le strisce colorate di 10 kΩ)."""
    if verticale:
        ax.add_patch(FancyBboxPatch((x - 1.3, y - 3.2), 2.6, 6.4, boxstyle="round,pad=0.1,rounding_size=1",
                                    fc="#e8d5a6", ec="#8a6d2f", lw=1.2))
        for i, c in enumerate(("#8b4513", "black", ARANCIO, "#c9a227")):
            ax.add_patch(Rectangle((x - 1.3, y + 2.0 - i * 1.4), 2.6, 0.55, color=c))
        ax.text(x + 2.2, y, etichetta, fontsize=8.5, va="center")
    else:
        ax.add_patch(FancyBboxPatch((x - 3.2, y - 1.3), 6.4, 2.6, boxstyle="round,pad=0.1,rounding_size=1",
                                    fc="#e8d5a6", ec="#8a6d2f", lw=1.2))
        for i, c in enumerate(("#8b4513", "black", ARANCIO, "#c9a227")):
            ax.add_patch(Rectangle((x - 2.0 + i * 1.4, y - 1.3), 0.55, 2.6, color=c))
        ax.text(x, y + 2.4, etichetta, fontsize=8.5, ha="center")


# ------------------------------------------------------------------ disegni dei pezzi
def disegna_pico(ax, x, y, scala=1.0, evidenzia=True):
    """La Raspberry Pi Pico vista da sopra, presa USB in alto. -> posizione dei piedini 1, 2, 3."""
    w, h = 21 * scala, 51 * scala
    ax.add_patch(Rectangle((x, y), w, h, fc="#2f8f4e", ec="#174d29", lw=2))
    ax.add_patch(Rectangle((x + w / 2 - 4 * scala, y + h - 1), 8 * scala, 4 * scala, fc="#cfcfcf", ec="#777"))
    ax.text(x + w / 2, y + h + 4 * scala, "presa USB", ha="center", fontsize=8.5)
    ax.add_patch(Rectangle((x + w / 2 - 2.8 * scala, y + h - 10 * scala), 5.6 * scala, 4 * scala, fc="white", ec="#999"))
    ax.text(x + w / 2, y + h - 8 * scala, "BOOTSEL", ha="center", va="center", fontsize=6.5 * scala, fontweight="bold")
    ax.add_patch(Circle((x + w / 2 + 6 * scala, y + h - 4 * scala), 1.0 * scala, color="#7CFC00"))
    ax.text(x + w / 2 + 8.2 * scala, y + h - 4.3 * scala, "lucina", fontsize=6.5, color="white")
    ax.add_patch(Rectangle((x + 4 * scala, y + 14 * scala), 13 * scala, 13 * scala, fc="#111", ec="#444"))
    ax.text(x + w / 2, y + 20.5 * scala, "RP2040", ha="center", va="center", fontsize=7, color="white")
    ax.text(x + w / 2, y + 6 * scala, "Raspberry\nPi Pico", ha="center", va="center", fontsize=7.5, color="white")
    piedini = {}
    nomi_sx = ["GP0", "GP1", "GND", "GP2", "GP3", "GP4", "GP5", "GND", "GP6", "GP7"]
    passo = (h - 6 * scala) / 20.0
    for i in range(20):
        py = y + h - 3 * scala - passo * (i + 0.5)
        for px in (x + 1.6 * scala, x + w - 1.6 * scala):
            ax.add_patch(Circle((px, py), 0.75 * scala, fc="#d4af37", ec="#8a6d2f"))
        if i < 3:
            piedini[i + 1] = (x + 1.6 * scala, py)
            if evidenzia:
                ax.add_patch(Circle((x + 1.6 * scala, py), 1.5 * scala, fc="none", ec=ROSSO, lw=2))
        if i < 3 and evidenzia:
            ax.text(x - 15, py, "%d  %s" % (i + 1, nomi_sx[i]), ha="right", va="center", fontsize=9,
                    fontweight="bold", color=ROSSO)
    return piedini


def disegna_arduino(ax, x, y, w=46, h=30):
    """L'Arduino UNO visto da sopra (presa USB a sinistra). -> posizioni di RX(0), TX(1), GND, RESET."""
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.2,rounding_size=2", fc="#1d6fb8", ec="#0d3f6b", lw=2))
    ax.add_patch(Rectangle((x - 3, y + h - 12), 8, 8, fc="#cfcfcf", ec="#777"))
    ax.text(x - 3.5, y + h - 8, "USB", ha="right", va="center", fontsize=8.5)
    ax.add_patch(Rectangle((x - 2, y + 2), 6, 6, fc="#222", ec="#555"))
    ax.text(x + w / 2, y + h / 2, "ARDUINO UNO", ha="center", va="center", fontsize=10, color="white", fontweight="bold")
    # fila in alto (digitali): ... 2, TX 1, RX 0 a destra
    nomi_alto = ["AREF", "GND", "13", "12", "11", "10", "9", "8", "", "7", "6", "5", "4", "3", "2", "TX 1", "RX 0"]
    passo = (w - 8) / len(nomi_alto)
    pos = {}
    for i, n in enumerate(nomi_alto):
        if not n:
            continue
        px = x + 6 + passo * i
        ax.add_patch(Rectangle((px - 0.8, y + h - 2.6), 1.6, 1.6, fc="#111"))
        if n in ("TX 1", "RX 0"):
            ax.text(px, y + h - 4.2, n, ha="center", va="top", fontsize=7.5, color="white", fontweight="bold", rotation=90)
            pos[n] = (px, y + h - 1.8)
    # fila in basso (alimentazione): IOREF RESET 3.3V 5V GND GND Vin
    nomi_basso = ["IOREF", "RESET", "3.3V", "5V", "GND", "GND", "Vin"]
    for i, n in enumerate(nomi_basso):
        px = x + 14 + 2.6 * i
        ax.add_patch(Rectangle((px - 0.8, y + 1.0), 1.6, 1.6, fc="#111"))
        ax.text(px, y + 3.6, n, ha="center", va="bottom", fontsize=6.5, color="white", rotation=90)
        if n in ("RESET", "GND") and n not in pos:
            pos[n] = (px, y + 1.8)
        if n == "GND":
            pos["GND2"] = (px, y + 1.8)
    ax.text(x + 20, y - 2.5, "fila POWER", ha="center", fontsize=8, color=GRIGIO)
    return pos


# ------------------------------------------------------------------ le pagine
def pagina_copertina(pdf, versione):
    fig, ax = pagina(pdf, "BOT SPARATUTTO - GUIDA COMPLETA", "Tutto quello che serve: montaggio, collegamenti, avvio")
    y = testo(ax, 6, 123, ["Versione del programma: %s" % versione], grassetto=True)
    y = testo(ax, 6, y - 1, [
        "COSA C'E' NEL FILE (BotSparatutto_TUTTO.zip). Estrai la cartella BotSparatutto in Documenti, "
        "cosi' diventa Documenti\\BotSparatutto. Dentro trovi:",
        "- AVVIA IL BOT.cmd: doppio click per avviare il bot.",
        "- BotSparatutto.exe: il programma (fa la stessa cosa).",
        "- GUIDA_COMPLETA.pdf: questa guida, con i disegni.",
        "- Schedina\\BotSparatutto_Schedina.uf2: il file da mettere sulla Pico (pagina 5).",
        "- Schedina\\file_della_schedina\\: gli stessi file sciolti (se la chiavetta CIRCUITPY resta vuota).",
        "- impostazioni.yaml, istruzioni.txt, fortnite.txt: le regolazioni (si aprono con Blocco note).",
        "- LEGGIMI_GUIDA.txt: la guida lunga, solo testo.",
    ])
    riquadro(ax, 5, y - 48, 90, 46, BLU, "IN 6 PASSI", riempi="#eef4ff")
    passi = [
        "1. Monta il PONTE: Arduino UNO + 3 fili + 3 resistenze + Pico (pagine 3 e 4).",
        "2. Metti il programma sulla PICO: BOOTSEL + trascina il file .uf2 (pagina 5).",
        "3. PICO nella presa USB della PS5; ARDUINO nella presa USB del PC (pagina 2).",
        "4. PS5: Riproduzione remota attiva; PC: app PS Remote Play a schermo intero (pagina 6).",
        "5. FORTNITE: tastiera e mouse, slot preferiti, raccolta automatica... (pagina 6).",
        "6. Doppio click su AVVIA IL BOT.cmd, scegli 1 (oppure 17 per registrare) e clicca su "
        "Remote Play (pagina 7).",
    ]
    testo(ax, 8, y - 9, passi, larghezza=82, dimensione=11)
    testo(ax, 6, 18, [
        "Durante il gioco: F8 = pausa / riprendi, F9 = chiudi. Per aggiornare: menu 13.",
        "Se qualcosa non va: pagina 8 (problemi e soluzioni), poi una partita col menu 17 e mandami lo zip.",
    ], dimensione=10, colore=GRIGIO)
    return fig


def pagina_schema(pdf):
    fig, ax = pagina(pdf, "1. COME E' COLLEGATO TUTTO", "Il bot GUARDA la Play sul PC e PREME i tasti con la Pico")
    riquadro(ax, 36, 110, 28, 8, GRIGIO, None, riempi="#f2f2f2")
    ax.text(50, 114, "ROUTER (casa)", ha="center", va="center", fontsize=9.5, fontweight="bold")
    riquadro(ax, 5, 80, 32, 24, VIOLA, "PS5", riempi="#f5eefc")
    ax.text(21, 89, "Fortnite\n(tastiera e mouse)", ha="center", fontsize=9.5)
    riquadro(ax, 63, 80, 32, 24, BLU, "PC / PORTATILE", riempi="#eef4ff")
    ax.text(79, 88, "app PS Remote Play\n(schermo intero)\n+ BotSparatutto", ha="center", fontsize=9.5)
    freccia(ax, 24, 104.5, 36, 112, GRIGIO, None, doppia=True)
    freccia(ax, 64, 112, 76, 104.5, GRIGIO, None, doppia=True)
    ax.text(50, 107, "rete di casa\n(meglio la PS5 col CAVO)", ha="center", fontsize=8.5, color=GRIGIO, va="top")
    riquadro(ax, 63, 44, 32, 22, BLU, "ARDUINO UNO", riempi="#e3f0fb")
    ax.text(79, 51, "fa da PONTE\n(ponticello RESET-GND)", ha="center", fontsize=9)
    riquadro(ax, 5, 44, 32, 22, VERDE, "PICO", riempi="#e9f7ec")
    ax.text(21, 51, "fa da TASTIERA\n+ MOUSE", ha="center", fontsize=9)
    freccia(ax, 79, 79.5, 79, 67, BLU, "cavo USB", spessore=3)
    freccia(ax, 21, 67, 21, 79.5, VERDE, "cavo USB (dati)", spessore=3)
    freccia(ax, 62.5, 55, 37.5, 55, ARANCIO, "3 fili", spessore=3)
    testo(ax, 6, 38, [
        "COSA SUCCEDE: la PS5 manda l'immagine del gioco al PC (PS Remote Play). Il programma "
        "BotSparatutto guarda quell'immagine e decide cosa fare. Manda i comandi all'Arduino col "
        "cavo USB; l'Arduino li passa alla Pico con 3 fili; la Pico e' attaccata alla PS5 e per la "
        "PS5 e' una tastiera e un mouse veri.",
        "PERCHE' L'ARDUINO: la Pico ha una sola presa USB. Se e' attaccata alla PS5, il PC non le "
        "puo' parlare da li': l'Arduino fa da ponte. Non serve caricare niente sull'Arduino.",
        "La Pico prende la corrente dalla PS5. Il 5V e il 3,3V NON si collegano tra Arduino e Pico.",
    ], dimensione=10.5)
    return fig


def pagina_fili(pdf):
    fig, ax = pagina(pdf, "2. I FILI TRA ARDUINO E PICO", "Il disegno piu' importante: segui i colori")
    piedini = disegna_pico(ax, 28, 56, scala=1.0)
    pos = disegna_arduino(ax, 54, 84, w=34, h=28)
    ax.text(5, 113, "piedini\ndella Pico", fontsize=8.5, color=ROSSO, fontweight="bold")
    # ponticello RESET - GND
    rx, ry = pos["RESET"]
    gx, gy = pos["GND"]
    ax.plot([rx, rx, gx, gx], [ry, ry - 4, ry - 4, gy], color=PONTICELLO, lw=3)
    ax.text((rx + gx) / 2 + 2, ry - 6.3, "PONTICELLO RESET-GND", ha="center", fontsize=8, color=PONTICELLO,
            fontweight="bold")
    p1x, p1y = piedini[1]
    p2x, p2y = piedini[2]
    p3x, p3y = piedini[3]
    # filo VERDE: Pico GP0 (piedino 1) -> Arduino TX 1 (diretto)
    tx, ty = pos["TX 1"]
    ax.plot([p1x, 15, 15, tx, tx], [p1y, p1y, 120, 120, ty], color=FILO_TX, lw=3, zorder=0.5)
    ax.text(40, 121.3, "VERDE: Pico GP0 (piedino 1) -> Arduino TX 1, diretto", fontsize=9, color=FILO_TX,
            fontweight="bold", ha="center")
    # filo NERO: Arduino GND -> Pico GND (piedino 3)
    g2x, g2y = pos["GND2"]
    ax.plot([g2x, g2x, 19, 19, p3x], [g2y, 66, 66, p3y, p3y], color=FILO_GND, lw=3, zorder=0.5)
    ax.text(51, 63.6, "NERO: Arduino GND -> Pico GND (piedino 3)", fontsize=9, color=FILO_GND, fontweight="bold")
    # filo GIALLO con le resistenze
    rx0, ry0 = pos["RX 0"]
    ax.plot([rx0, rx0, 93, 93], [ry0, 116, 116, 110.2], color=FILO_RX, lw=3, zorder=0.5)
    resistenza(ax, 93, 107, verticale=True, etichetta="R1")
    ax.plot([93, 93], [103.8, 73], color=FILO_RX, lw=3, zorder=0.5)
    ax.add_patch(Circle((93, 73), 1.0, color=FILO_RX))
    ax.plot([93, 23, 23, p2x], [73, 73, p2y, p2y], color=FILO_RX, lw=3, zorder=0.5)
    ax.text(51, 74.6, "GIALLO: Arduino RX 0 -> R1 -> Pico GP1 (piedino 2)", fontsize=9, color="#a07000",
            fontweight="bold")
    ax.plot([93, 93], [73, 66.2], color=FILO_RX, lw=2)
    resistenza(ax, 93, 63, verticale=True, etichetta="R2")
    ax.plot([93, 93], [59.8, 56.2], color=FILO_RX, lw=2)
    resistenza(ax, 93, 53, verticale=True, etichetta="R3")
    ax.plot([93, 93], [49.8, 47.5], color=FILO_GND, lw=3, zorder=0.5)
    ax.plot([88, 98], [47.5, 47.5], color=FILO_GND, lw=3, zorder=0.5)
    ax.plot([90, 96], [46.2, 46.2], color=FILO_GND, lw=2.5)
    ax.plot([91.5, 94.5], [44.9, 44.9], color=FILO_GND, lw=2)
    ax.text(86, 46, "a GND (alla fila\ndel filo nero)", fontsize=8, ha="right", va="center")
    ax.text(70, 55, "R1, R2, R3 = resistenze\nda 10 kΩ (strisce marrone-\nnero-arancione)", fontsize=8.5,
            ha="center", color="#8a6d2f")
    testo(ax, 6, 41, [
        "- PONTICELLO ROSSO: sull'Arduino, un cavetto tra RESET e GND (fila POWER): fa solo da passaggio.",
        "- VERDE: Pico GP0 (piedino 1) -> Arduino TX 1, diretto.   - NERO: Arduino GND -> Pico GND (piedino 3).",
        "- GIALLO: Arduino RX 0 -> R1 -> Pico GP1 (piedino 2); dal punto tra R1 e la Pico, R2 e R3 verso GND.",
        "PERCHE' LE RESISTENZE: l'Arduino manda 5 V, la Pico ne sopporta solo 3,3 (5 x 2/3 = 3,3). Senza, GP1 "
        "si puo' rompere. Vanno bene anche 1 kΩ al posto di R1 e 2 kΩ al posto di R2+R3.",
        "I piedini 1, 2, 3 sono i PRIMI TRE a sinistra, vicino alla presa USB (sotto la Pico c'e' scritto GP0, "
        "GP1, GND). RX 0 va a GP1 e TX 1 va a GP0: e' giusto cosi'.",
    ], dimensione=9.4, larghezza=98, interlinea=1.55)
    return fig


def pagina_breadboard(pdf):
    fig, ax = pagina(pdf, "3. MONTAGGIO SULLA BREADBOARD", "Una disposizione semplice (una delle tante possibili)")
    # breadboard
    bx, by, bw, bh = 8, 64, 84, 46
    ax.add_patch(FancyBboxPatch((bx, by), bw, bh, boxstyle="round,pad=0.3,rounding_size=1.5", fc="#f7f7f2", ec="#999"))
    for i in range(40):
        for j in range(10):
            px = bx + 3 + i * 2.0
            py = by + 6 + j * 3.6 + (5 if j >= 5 else 0)
            ax.add_patch(Rectangle((px - 0.35, py - 0.35), 0.7, 0.7, color="#bbb"))
    for k, (py, c) in enumerate(((by + 2.2, "#1f5fbf"), (by + bh - 2.2, ROSSO))):
        ax.plot([bx + 2, bx + bw - 2], [py, py], color=c, lw=1.2)
    ax.text(bx + bw / 2, by + 1.0, "fila lunga in basso = GND (la chiami \"fila GND\")", ha="center", fontsize=8,
            color=BLU)
    # pico sulla breadboard (a cavallo del solco), solo i primi 3 piedini interessano
    ax.add_patch(Rectangle((bx + 3, by + 18), 42, 18, fc="#2f8f4e", ec="#174d29", lw=2, alpha=0.9))
    ax.text(bx + 24, by + 27, "PICO (a cavallo del solco centrale)\npresa USB verso sinistra", ha="center",
            va="center", color="white", fontsize=9)
    for i, (nome, col) in enumerate((("GP0 (1)", FILO_TX), ("GP1 (2)", "#a07000"), ("GND (3)", FILO_GND))):
        px = bx + 5 + i * 2.0
        ax.add_patch(Circle((px, by + 18), 0.9, color=col if i != 1 else FILO_RX))
        ax.text(bx + 15, by + 13.5 - i * 3.0, "piedino " + nome, fontsize=8, color=col, fontweight="bold", ha="left")
    # resistenze
    resistenza(ax, bx + 56, by + 30, etichetta="R1 10kΩ")
    resistenza(ax, bx + 66, by + 22, verticale=True, etichetta="R2")
    resistenza(ax, bx + 66, by + 12, verticale=True, etichetta="R3")
    ax.plot([bx + 9, bx + 9, bx + 52.8], [by + 18, by + 30, by + 30], color=FILO_RX, lw=2.5)
    ax.plot([bx + 59.2, bx + 66, bx + 66], [by + 30, by + 30, by + 25.2], color=FILO_RX, lw=2.5)
    ax.plot([bx + 66, bx + 66], [by + 18.8, by + 15.2], color=FILO_RX, lw=2)
    ax.plot([bx + 66, bx + 66], [by + 8.8, by + 2.2], color=FILO_GND, lw=2.5)
    ax.plot([bx + 9, bx + 9], [by + 18, by + 2.2], color=FILO_GND, lw=0)
    ax.plot([bx + 11, bx + 11, bx + 11], [by + 18, by + 4, by + 2.2], color=FILO_GND, lw=2.5)
    ax.plot([bx + 59.2, bx + 59.2], [by + 30, by + bh + 5], color=FILO_RX, lw=2.5)
    ax.text(bx + 59.2, by + bh + 6.2, "all'Arduino\nRX 0", fontsize=8.5, color="#a07000", fontweight="bold",
            ha="center", va="bottom")
    ax.plot([bx + 7, bx + 7, bx + 30, bx + 30], [by + 18, by + 40, by + 40, by + bh + 5], color=FILO_TX, lw=2.5)
    ax.text(bx + 30, by + bh + 6.2, "all'Arduino\nTX 1", fontsize=8.5, color=FILO_TX, fontweight="bold",
            ha="center", va="bottom")
    ax.plot([bx + 78, bx + 78], [by + 2.2, by + bh + 5], color=FILO_GND, lw=2.5)
    ax.text(bx + 78, by + bh + 6.2, "all'Arduino\nGND", fontsize=8.5, color=FILO_GND, fontweight="bold",
            ha="center", va="bottom")
    testo(ax, 6, 60, [
        "PASSO PASSO:",
        "1. Salda i piedini alla Pico (almeno i primi 3 della fila vicino alla presa USB: GP0, GP1, GND).",
        "2. Metti la Pico sulla breadboard a cavallo del solco centrale.",
        "3. Filo VERDE dal piedino 1 (GP0) all'Arduino TX 1.",
        "4. R1 (10 kΩ) da una fila libera: un capo collegato al piedino 2 (GP1) col filo GIALLO, l'altro capo "
        "col filo giallo all'Arduino RX 0.",
        "5. Dalla fila del piedino 2: R2 e R3 una dopo l'altra fino alla fila GND (in basso).",
        "6. Piedino 3 (GND) della Pico alla fila GND; dalla fila GND un filo NERO all'Arduino GND.",
        "7. Sull'Arduino il PONTICELLO rosso tra RESET e GND.",
        "8. Controlla tutto due volte prima di attaccare i cavi USB.",
        "Il disegno della pagina prima conta di piu': i collegamenti devono essere QUELLI. La breadboard e' solo "
        "un modo comodo per farli senza saldare i fili.",
    ], dimensione=10)
    return fig


def pagina_pico_programma(pdf):
    fig, ax = pagina(pdf, "4. METTERE IL PROGRAMMA SULLA PICO", "Si fa UNA volta sola (e dopo un aggiornamento della schedina)")
    disegna_pico(ax, 10, 70, scala=0.85, evidenzia=False)
    ax.add_patch(FancyArrowPatch((30, 113), (22, 110.8), arrowstyle="-|>", mutation_scale=18, color=ROSSO, lw=2.5))
    ax.text(31, 114, "1. TIENI PREMUTO\n    BOOTSEL", fontsize=10, color=ROSSO, fontweight="bold")
    riquadro(ax, 50, 98, 44, 22, BLU, "2. Attacca la Pico al PC", riempi="#eef4ff")
    ax.text(72, 106, "con un cavo USB che passa i DATI\n(non uno solo per caricare)\npoi lascia BOOTSEL", ha="center",
            fontsize=9.5)
    riquadro(ax, 50, 70, 44, 24, VERDE, "3. Chiavetta RPI-RP2", riempi="#e9f7ec")
    ax.text(72, 78.5, "trascinaci dentro\nSchedina\\BotSparatutto_Schedina.uf2\ndopo pochi secondi diventa\nCIRCUITPY",
            ha="center", fontsize=9.5)
    testo(ax, 6, 62, [
        "COSA SUCCEDE: il file .uf2 contiene tutto (CircuitPython + il programma della schedina). La Pico si "
        "riavvia da sola e compare una chiavetta CIRCUITPY con dentro boot.py, code.py e \"AVVIA IL BOT\".",
        "SE CIRCUITPY E' VUOTA: copia dentro CIRCUITPY i file della cartella Schedina\\file_della_schedina "
        "(boot.py, code.py...). Poi stacca e riattacca la Pico.",
        "DOPO: stacca la Pico dal PC e attaccala alla PS5 (presa USB davanti o dietro). Per la PS5 e' una "
        "tastiera e un mouse. La prima volta la PS5 chiede \"Chi sta usando questo controller?\": premi INVIO "
        "dal menu 12 (Telecomando) del bot oppure col controller.",
        "La lucina verde della Pico: spenta = aspetta il programma sul PC; accesa = collegata al programma.",
        "Sicurezza: se chiudi il programma o stacchi un cavo, la Pico rilascia da sola tutti i tasti entro 1 secondo.",
    ], dimensione=10.3)
    return fig


def pagina_impostazioni(pdf):
    fig, ax = pagina(pdf, "5. PS5, PC E FORTNITE", "Le impostazioni da fare una volta")
    y = 124
    for titolo, colore, righe in (
        ("PS5", VIOLA, [
            "- Impostazioni -> Sistema -> Riproduzione remota -> ATTIVA.",
            "- Meglio la PS5 attaccata al router col CAVO di rete (meno ritardo).",
            "- Impostazioni -> Sistema -> Risparmio energetico: la PS5 non deve andare in riposo mentre gioca.",
        ]),
        ("PC / PORTATILE", BLU, [
            "- Installa l'app gratuita PS Remote Play (Sony) ed entra col tuo account PlayStation.",
            "- Collegati alla PS5 e metti la finestra a SCHERMO INTERO (il mirino deve stare al centro).",
            "- Non far andare il PC in sospensione: Impostazioni -> Sistema -> Alimentazione -> Schermo e "
            "sospensione -> MAI (anche quando e' attaccato alla corrente). Tienilo attaccato al caricabatterie.",
            "- Attacca l'Arduino a una presa USB del PC.",
        ]),
        ("FORTNITE (nel gioco, sulla PS5)", ARANCIO, [
            "- Comandi: TASTIERA E MOUSE (i tasti predefiniti: F piccone, 1-5 armi, E interagisci, M mappa).",
            "- SLOT PREFERITI (Impostazioni -> Gioco): 1 mitra, 2 pompa, 3 impulso/oggetti per muoversi, "
            "4 cecchino, 5 cure. Il bot tiene in mano l'1, prende il 2 da vicino, usa il 3 e il 5.",
            "- RACCOLTA AUTOMATICA DELLE ARMI: attiva.",
            "- Audio -> VISUALIZZA EFFETTI SONORI: attiva (le casse fanno un segno dorato).",
            "- Usa un PICCONE SENZA LUCE DORATA (quello dorato il bot lo scambia per una cassa).",
            "- Modalita': SQUADRE (o Coppie/Trio) con RIEMPI attivo: il bot segue un compagno e, a quanto si "
            "legge, se un compagno trova il gettone del negozio dei pirati vale per tutta la squadra.",
            "- Non cambiare la grandezza dell'interfaccia di continuo: se la cambi (Scala HUD) il bot la "
            "ritrova da solo in qualche minuto.",
        ]),
    ):
        ax.add_patch(Rectangle((5, y - 1.5), 1.5, 4, color=colore))
        ax.text(8, y + 0.5, titolo, fontsize=12.5, fontweight="bold", color=colore, va="center")
        y = testo(ax, 8, y - 3.5, righe, dimensione=10, larghezza=88) - 3
    return fig


def pagina_avvio(pdf):
    fig, ax = pagina(pdf, "6. AVVIARE IL BOT", "Dal PC, con la Pico nella PS5 e l'Arduino nel PC")
    riquadro(ax, 5, 92, 90, 32, BLU, "IL MODO PIU' SEMPLICE", riempi="#eef4ff")
    testo(ax, 8, 118, [
        "1. Estrai BotSparatutto_TUTTO.zip in Documenti (diventa Documenti\\BotSparatutto).",
        "2. Doppio click su AVVIA IL BOT.cmd (la prima volta crea anche il collegamento sul desktop).",
        "3. Se Windows dice \"Windows ha protetto il PC\": Ulteriori informazioni -> Esegui comunque.",
        "4. Nel menu scrivi 1 e premi INVIO (oppure 17 per giocare e REGISTRARE). Poi clicca sulla finestra "
        "di PS Remote Play: hai 30 secondi.",
    ], dimensione=10)
    testo(ax, 6, 88, [
        "SENZA IL FILE .cmd: tasto Windows + R, scrivi la riga qui sotto e premi INVIO:",
    ], dimensione=10)
    ax.text(8, 82.5, "%USERPROFILE%\\Documents\\BotSparatutto\\BotSparatutto.exe", fontsize=10.5, family="monospace",
            bbox=dict(boxstyle="round,pad=0.4", fc="#f2f2f2", ec="#999"))
    testo(ax, 6, 77, [
        "I NUMERI DEL MENU PIU' USATI:",
        "- 1 = Avvia il bot (sceglie la modalita': Normale, Pro, Tranquillo).",
        "- 17 = Gioca e REGISTRA: foto + cosa pensa il bot per 20 minuti, poi uno zip da mandare a chi lo sistema.",
        "- 13 = Aggiorna il programma (scarica l'ultima versione; le tue impostazioni restano).",
        "- 15 = Collega le IA GRATIS (Gemini di Google): aiutano a vedere casse e nemici.",
        "- 12 = Telecomando: tastiera e mouse del portatile sulla PS5 (es. INVIO per \"Chi sta usando...\").",
        "- 0 = Esci.",
        "DURANTE IL GIOCO: F8 = pausa / riprendi, F9 = chiudi il bot.",
        "COSA FA DA SOLO: aspetta sul bus e salta sopra l'isola, esce dalla tempesta e dall'acqua guardando la "
        "minimappa, segue un compagno \"al guinzaglio\", apre le casse quando compare \"E Apri\", tiene la "
        "mitra (slot 1), prende la pompa da vicino, si cura con lo slot 5, usa l'impulso (slot 3) se e' "
        "lontano; quando muore guarda i compagni fino alla fine e poi clicca \"Gioca di nuovo\".",
        "LE IA (facoltative): con Gemini collegato (menu 15) vede meglio casse e nemici. Le domande gratis "
        "finiscono ogni giorno: il bot gioca lo stesso, perche' le cose importanti le legge da solo.",
    ], dimensione=10)
    return fig


def pagina_problemi(pdf):
    fig, ax = pagina(pdf, "7. PROBLEMI E SOLUZIONI", "Prima di tutto: una foto della finestra nera aiuta sempre")
    righe = [
        ("Non trova la schedina / lucina spenta",
         "Controlla il PONTICELLO RESET-GND, i 3 fili (RX 0 -> R1 -> GP1, TX 1 <- GP0, GND), che la Pico sia nella "
         "PS5 e l'Arduino nel PC. In impostazioni.yaml puoi scrivere la porta (es. porta: COM4, la vedi in "
         "Gestione dispositivi -> Porte COM e LPT)."),
        ("La PS5 chiede \"Chi sta usando questo controller?\"",
         "Menu 12 (Telecomando): clicca su Remote Play e premi INVIO. Il bot da solo, se lo schermo resta fermo "
         "4 minuti, prova INVIO."),
        ("Il bot dice \"non sono in partita: aspetto\" mentre giochi",
         "La finestra di Remote Play non e' a schermo intero o e' coperta, oppure l'interfaccia di Fortnite e' "
         "cambiata: dopo 5 minuti la cerca da solo. Se continua, fai una registrazione (menu 17)."),
        ("Va sempre dalla parte sbagliata / gira male",
         "Lascia visibili bussola e minimappa (come sono di solito): il bot misura da solo la sensibilita' del mouse "
         "con la bussola. Nella finestra nera ogni 5 minuti scrive quanto riesce a leggere."),
        ("Scambia cose dorate per casse",
         "Cambia il piccone con uno senza luce dorata. Alberi gialli e fiori: dopo 7 secondi capisce e lascia stare."),
        ("Le IA non rispondono (errore 429)",
         "Sono finite le domande gratis del giorno (tornano verso le 9 del mattino). Il bot gioca lo stesso."),
        ("\"Windows ha protetto il PC\"",
         "Ulteriori informazioni -> Esegui comunque (succede ai programmi senza firma a pagamento)."),
        ("Il PC si spegne / va in sospensione",
         "Impostazioni -> Sistema -> Alimentazione -> sospensione MAI, e tienilo attaccato alla corrente."),
        ("Cambiare PC",
         "Copia tutta la cartella Documenti\\BotSparatutto sul PC nuovo (dentro ci sono anche le tue "
         "regolazioni: calibrazione.yaml e ia.yaml). Installa PS Remote Play, attacca l'Arduino e avvia."),
    ]
    y = 124
    for problema, soluzione in righe:
        ax.text(6, y, problema, fontsize=10, fontweight="bold", color=ROSSO, va="top")
        y = testo(ax, 8, y - 3.3, [soluzione], dimensione=9.2, larghezza=95, interlinea=1.55) - 0.8
    testo(ax, 6, y - 2, [
        "Per far sistemare il bot: menu 17 (Gioca e REGISTRA), poi manda lo zip registrazione_....zip che trovi "
        "nella cartella del bot. Dentro ci sono le foto dello schermo e cosa pensava il bot.",
    ], dimensione=10, colore=BLU)
    return fig


def crea(uscita=None, versione="?"):
    uscita = uscita or os.path.join(QUI, "GUIDA_COMPLETA.pdf")
    plt.rcParams["font.family"] = "DejaVu Sans"
    with PdfPages(uscita) as pdf:
        pdf._pagine = []
        for crea_pagina in (lambda p: pagina_copertina(p, versione), pagina_schema, pagina_fili, pagina_breadboard,
                            pagina_pico_programma, pagina_impostazioni, pagina_avvio, pagina_problemi):
            fig = crea_pagina(pdf)
            pdf.savefig(fig)
            plt.close(fig)
        info = pdf.infodict()
        info["Title"] = "Bot Sparatutto - guida completa"
    return uscita


if __name__ == "__main__":
    print(crea(versione=sys.argv[1] if len(sys.argv) > 1 else "?"))
