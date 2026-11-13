"""
bot.py - BOT SPARATUTTO: guarda lo schermo e gioca da solo, con la schedina
Raspberry Pi Pico che fa da tastiera + mouse.

OBIETTIVO: vincere la partita (restare vivo ed eliminare i nemici) e aprire piu'
casse possibili (casse delle armi e casse dei materiali). Si adatta da solo al
gioco: riconosce i personaggi in qualsiasi gioco e impara mentre gioca.

Avvio: doppio click su BotSparatutto.exe (oppure: python bot.py) e scegli dal menu.
Durante il gioco:  F8 = pausa / riprendi    F9 = chiudi il bot
(i tasti si cambiano in impostazioni.yaml -> tasti_bot)

Per usarlo da riga di comando:  python bot.py avvia | prova | test | impara | colori |
                                 immagine | vita | zone | mira | giro | obiettivo |
                                 telecomando | aggiorna | --autotest
"""

import os
import shutil
import sys
import time
import traceback

# cartella dove stanno impostazioni.yaml, istruzioni.txt, immagini/... (accanto all'exe)
if getattr(sys, "frozen", False):
    BASE = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE = os.path.dirname(os.path.abspath(__file__))
    if BASE not in sys.path:
        sys.path.insert(0, BASE)

import impostazioni  # noqa: E402
from istruzioni import (Esecutore, Interrotto, Istruzioni, finestra_in_primo_piano,  # noqa: E402
                        imposta_dpi, leggi_istruzioni, leggi_macro)


def log(testo):
    print(time.strftime("%H:%M:%S ") + str(testo), flush=True)


def aspetta_invio(messaggio="\nPremi INVIO per continuare..."):
    try:
        input(messaggio)
    except (EOFError, KeyboardInterrupt):
        pass


def disattiva_quick_edit():
    """Su Windows, cliccare nella finestra nera la 'congela': qui lo evitiamo."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        k = ctypes.windll.kernel32
        h = k.GetStdHandle(-10)
        modo = ctypes.c_uint32()
        if k.GetConsoleMode(h, ctypes.byref(modo)):
            k.SetConsoleMode(h, (modo.value & ~0x0040) | 0x0080)
    except Exception:
        pass


def conto_alla_rovescia(secondi, testo="Vai nel gioco"):
    print("%s: parto tra..." % testo)
    for s in range(int(secondi), 0, -1):
        print("  %d..." % s, flush=True)
        time.sleep(1)


# ------------------------------------------------------------------ pausa / uscita
class Controllo:
    def __init__(self, cfg):
        self.in_pausa = False
        self.uscita = False
        self.fuori_fuoco = False
        self.cfg = cfg
        self.titolo = str((cfg.get("schermo", {}) or {}).get("titolo_finestra_gioco") or "").strip().lower()
        self._prossimo_controllo = 0.0
        self.ascoltatore = None

    def deve_fermarsi(self):
        self.controlla_finestra()
        return self.in_pausa or self.uscita or self.fuori_fuoco

    def pausa(self):
        self.in_pausa = True

    def esci(self):
        self.uscita = True

    def alterna_pausa(self):
        self.in_pausa = not self.in_pausa
        log("PAUSA (premi di nuovo per riprendere)" if self.in_pausa else "RIPRENDO")

    def controlla_finestra(self):
        """Se e' impostato il titolo del gioco e la finestra in primo piano e' un'altra, si ferma."""
        if not self.titolo:
            return
        adesso = time.monotonic()
        if adesso < self._prossimo_controllo:
            return
        self._prossimo_controllo = adesso + 0.5
        titolo = finestra_in_primo_piano()
        if titolo is None:
            return
        fuori = self.titolo not in titolo.lower()
        if fuori != self.fuori_fuoco:
            self.fuori_fuoco = fuori
            log("Il gioco non e' in primo piano: mi fermo" if fuori else "Il gioco e' di nuovo in primo piano: riparto")

    def avvia_tasti(self):
        tb = self.cfg.get("tasti_bot", {}) or {}
        try:
            from pynput import keyboard
        except Exception as e:
            log("ATTENZIONE: non riesco a leggere F8/F9 (%s). Per fermare il bot chiudi la finestra nera." % e)
            return

        def tasto_pynput(nome):
            nome = str(nome).strip().lower()
            if hasattr(keyboard.Key, nome):
                return getattr(keyboard.Key, nome)
            if len(nome) == 1:
                return keyboard.KeyCode.from_char(nome)
            return None

        t_pausa = tasto_pynput(tb.get("pausa", "f8"))
        t_esci = tasto_pynput(tb.get("esci", "f9"))

        def premuto(k):
            if k == t_pausa or (hasattr(k, "char") and t_pausa is not None and getattr(t_pausa, "char", 0) == k.char):
                self.alterna_pausa()
            elif k == t_esci or (hasattr(k, "char") and t_esci is not None and getattr(t_esci, "char", 0) == k.char):
                log("Chiudo il bot...")
                self.uscita = True

        self.ascoltatore = keyboard.Listener(on_press=premuto)
        self.ascoltatore.daemon = True
        self.ascoltatore.start()

    def ferma_tasti(self):
        if self.ascoltatore is not None:
            try:
                self.ascoltatore.stop()
            except Exception:
                pass


# ------------------------------------------------------------------ preparazione
def prepara(cfg, mani, occhi, schermo, controllo, statistiche):
    macro, errori = leggi_macro(cfg.get("macro"), mani.esiste)
    for e in errori:
        log("ERRORE nelle macro di impostazioni.yaml: " + e)
    percorso = os.path.join(BASE, "istruzioni.txt")
    testo = ""
    if os.path.isfile(percorso):
        with open(percorso, "r", encoding="utf-8-sig") as f:
            testo = f.read()
    attesa = float((cfg.get("regole", {}) or {}).get("attesa_tra_ripetizioni", 3.0))
    regole, errori = leggi_istruzioni(testo, mani.esiste, macro, occhi.immagini.esiste, attesa)
    for e in errori:
        log("ERRORE in istruzioni.txt, " + e + "  (questa riga la salto)")
    mancanti = set()
    for r in regole:
        for c in r.condizioni:
            if c.tipo == "vedi" and not occhi.immagini.esiste(c.valore):
                mancanti.add(c.valore)
        for a in r.azioni:
            if a.tipo in ("clicca_immagine", "aspetta_immagine") and not occhi.immagini.esiste(a.valori[0]):
                mancanti.add(a.valori[0])
    for nome in sorted(mancanti):
        log("ATTENZIONE: manca l'immagine immagini/%s.png (salvala con il menu 'Salva un'immagine')" % nome)
    log("Istruzioni lette: %d" % len(regole))
    esecutore = Esecutore(mani, occhi, schermo, cfg, controllo, log, statistiche, macro)
    return esecutore, Istruzioni(regole, occhi, log)


def scrivi_statistiche(statistiche, inizio):
    minuti = (time.monotonic() - inizio) / 60.0
    riga = "%s  durata %.0f min  casse armi %d  casse materiali %d  armi %d  combattimenti %d  partite %d" % (
        time.strftime("%Y-%m-%d %H:%M"), minuti, statistiche.get("casse", 0), statistiche.get("materiali", 0),
        statistiche.get("armi", 0), statistiche.get("combattimenti", 0), statistiche.get("partite", 0))
    log("STATISTICHE: " + riga)
    try:
        with open(os.path.join(BASE, "statistiche.txt"), "a", encoding="utf-8") as f:
            f.write(riga + "\n")
    except OSError:
        pass


# ------------------------------------------------------------------ il bot
def avvia(modo=None):
    import obiettivo as modulo_obiettivo
    import stile as modulo_stile
    from allenamento import Allenamento
    from apprendimento import Apprendimento
    from cervello import Cervello
    import ia as modulo_ia
    from ia import IA
    from mani import crea_mani
    from occhi import Occhi, Schermo, disegna

    cfg = impostazioni.carica(BASE)
    if modo == "prova":
        cfg["comandi"]["scrivi_comandi_in_prova"] = True
    # come deve giocare: Normale / Pro player / Tranquillo (in prova usa l'ultima scelta)
    stile = modulo_stile.leggi(BASE) if modo == "prova" else modulo_stile.chiedi(BASE)
    if modo != "prova" and modulo_ia.serve_chiedere_gemini(cfg):
        # Gemini non c'e' ancora: si collega adesso con il tuo account Google (una volta sola)
        if modulo_ia.collega_gemini(BASE, cfg, log):
            cfg = impostazioni.carica(BASE)
    sch = cfg.get("schermo", {}) or {}
    mani = crea_mani(cfg, log, modo)
    log("Comandi: %s" % mani.nome_modo)
    schermo = Schermo(int(sch.get("monitor", 1) or 1), sch.get("zona_cattura"))
    occhi = Occhi(cfg, BASE, log)
    controllo = Controllo(cfg)
    statistiche = {}
    esecutore, istruzioni = prepara(cfg, mani, occhi, schermo, controllo, statistiche)
    apprendimento = Apprendimento(cfg, BASE, occhi, log)
    if modo == "prova":
        # in prova non preme niente: la visuale non si muove, quindi non deve imparare niente
        apprendimento.calibra_da_solo = False
        apprendimento.mira_adattiva = False
        apprendimento.impara_attaccati = False
    esecutore.passi_per_giro = apprendimento.passi_per_giro
    # l'obiettivo: si sceglie ogni volta (INVIO = quello di prima); in prova usa quello salvato
    obiettivo = modulo_obiettivo.leggi(BASE, log) if modo == "prova" else modulo_obiettivo.chiedi(BASE)
    allenamento = Allenamento(cfg, BASE, statistiche, log)
    if modo == "prova":
        allenamento.attivo = False                 # scrive il riepilogo ma non cambia le regolazioni
    esecutore.su_fine_partita = allenamento.fine_partita
    ia = IA(cfg, log, conoscenza=modulo_ia.leggi_conoscenza(BASE))
    cervello = Cervello(cfg, mani, occhi, esecutore, istruzioni, log, apprendimento, schermo, obiettivo, stile,
                        ia if ia.attiva else None)
    import remote_play
    cervello.pc = remote_play.PC(log)
    if not controllo.titolo and cervello.pc.trova_finestra() is not None:
        # giochi sulla Play con PS Remote Play: se un'altra finestra la copre il bot si ferma
        # (prima "giocava" sul desktop scambiando le icone gialle per casse)
        controllo.titolo = remote_play.TITOLO.lower()
        log("Gioco dentro PS Remote Play: se un'altra finestra la copre mi fermo e aspetto")
    if occhi.universale is None and occhi.ia is None and not (cfg.get("colori", {}) or {}).get("nemico"):
        log("ATTENZIONE: non ho niente per riconoscere i nemici (occhio universale spento e nessun colore).")
    mostra = bool(sch.get("mostra_finestra", False)) or modo == "prova"
    fps = float(sch.get("fps_massimi", 60) or 60)
    controllo.avvia_tasti()
    tb = cfg.get("tasti_bot", {}) or {}

    print()
    print("=" * 70)
    print("  OBIETTIVO: " + obiettivo.descrizione())
    print("  (si cambia dal menu 11 o nel file obiettivo.txt)")
    print("  MODALITA': %s - %s" % (stile.nome, stile.descrizione))
    if ia.attiva:
        print("  IA CHE GUARDA: accesa (%s)" % ", ".join(f["nome"] for f in ia.fornitori))
    else:
        print("  IA CHE GUARDA: spenta (menu 14 per collegarla)")
    if allenamento.attivo:
        print("  ALLENAMENTO: dopo ogni partita scrive il riepilogo in allenamento.txt e migliora")
    print("  BOT ATTIVO  -  %s = pausa/riprendi   %s = chiudi" % (str(tb.get("pausa", "f8")).upper(),
                                                                  str(tb.get("esci", "f9")).upper()))
    if apprendimento.calibra_da_solo and not (apprendimento.ppp_noto and apprendimento.giro_noto):
        print("  Primo avvio in questo gioco: all'inizio della partita muovera' la visuale")
        print("  da solo per qualche secondo per imparare come si muove. E' normale!")
    if controllo.titolo:
        print("  Gioca solo quando e' in primo piano una finestra con '%s' nel titolo" % controllo.titolo)
    print("=" * 70)
    attesa = int(float(sch.get("secondi_prima_di_partire", 30) or 30))
    conto_alla_rovescia(attesa, "Clicca sulla finestra del gioco (o di PS Remote Play)")
    inizio = time.monotonic()
    prossime_stat = inizio + 60
    fermo_prima = False
    scritta_prec = ""
    t_fotogramma = time.monotonic()
    if ia.attiva:
        ia.avvia()
    try:
        while not controllo.uscita:
            t0 = time.monotonic()
            if controllo.deve_fermarsi():
                if not fermo_prima:
                    cervello.ferma_tutto()
                    fermo_prima = True
                time.sleep(0.1)
                continue
            if fermo_prima:
                fermo_prima = False
                cervello.t_prec = time.monotonic()
            img = schermo.foto()
            vis = occhi.analizza(img)
            try:
                scritta = cervello.passo(vis, img)
            except Interrotto:
                cervello.ferma_tutto()
                continue
            if scritta != scritta_prec and scritta and not scritta.startswith(("combatto", "vado verso", "esploro")):
                log(scritta)
            scritta_prec = scritta
            adesso = time.monotonic()
            allenamento.conta_tempo(scritta, adesso - t_fotogramma)
            t_fotogramma = adesso
            if mostra:
                try:
                    import cv2
                    from occhi import rimpicciolisci
                    W = img.shape[1]
                    out = disegna(img, vis, scritta, cervello.bersaglio, cervello._mirino(vis))
                    out = rimpicciolisci(out, min(1.0, 960.0 / W))
                    cv2.imshow("Bot - cosa vedo (F9 per chiudere)", out)
                    cv2.waitKey(1)
                except Exception:
                    mostra = False
            if time.monotonic() >= prossime_stat:
                prossime_stat += 60
                log("casse armi %d | casse materiali %d | armi %d | combattimenti %d | partite %d" % (
                    statistiche.get("casse", 0), statistiche.get("materiali", 0), statistiche.get("armi", 0),
                    statistiche.get("combattimenti", 0), statistiche.get("partite", 0)))
                apprendimento.salva()
            resto = 1.0 / fps - (time.monotonic() - t0)
            if resto > 0:
                time.sleep(resto)
    except KeyboardInterrupt:
        log("Fermato con CTRL+C")
    finally:
        ia.ferma()
        try:
            mani.chiudi()
        except Exception:
            pass
        try:
            apprendimento.salva(forzato=True)
        except Exception:
            pass
        try:
            allenamento.fine_partita("interrotta")
        except Exception:
            pass
        controllo.ferma_tasti()
        schermo.chiudi()
        scrivi_statistiche(statistiche, inizio)
        try:
            import cv2
            cv2.destroyAllWindows()
        except Exception:
            pass


# ------------------------------------------------------------------ prova della schedina
def prova_schedina():
    from mani import ManiSchedina
    cfg = impostazioni.carica(BASE)
    mani = ManiSchedina(cfg.get("tasti"), log, (cfg.get("comandi", {}) or {}).get("porta", "auto"))
    try:
        print("\nOra il mouse fa un quadrato per 3 volte (non clicca e non preme tasti).")
        time.sleep(1)
        for _ in range(3):
            for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
                for _ in range(20):
                    mani.muovi(dx * 10, dy * 10)
                    time.sleep(0.01)
        print("Se il mouse si e' mosso a quadrato, la schedina funziona!")
        r = input("\nVuoi provare anche la tastiera? Apri il Blocco note e scrivi 's' qui: ").strip().lower()
        if r.startswith("s"):
            conto_alla_rovescia(5, "Clicca dentro il Blocco note")
            mani.scrivi("ciao sono il bot 123")
            print("Nel Blocco note dovrebbe esserci scritto: ciao sono il bot 123")
    finally:
        mani.chiudi()


# ------------------------------------------------------------------ aggiorna il programma
URL_AGGIORNAMENTO = "https://github.com/l13291221-cmyk/Soldi-bunker-/releases/download/bot-sparatutto/BotSparatutto.zip"
TUE_IMPOSTAZIONI = ("impostazioni.yaml", "istruzioni.txt", "obiettivo.txt")


def leggi_versione(cartella):
    try:
        with open(os.path.join(cartella, "versione.txt"), "r", encoding="utf-8-sig") as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return 0


def script_aggiornamento(sorgente, destinazione, exe, temporanea):
    """Il .cmd che, a bot chiuso, copia la versione nuova (senza toccare le TUE impostazioni)
    e lo riapre. robocopy riprova finche' l'exe non e' libero."""
    righe = [
        "@echo off",
        "title Aggiorno il Bot Sparatutto",
        "echo  Aggiorno il bot... (qualche secondo)",
        "timeout /t 3 /nobreak >nul",
        'robocopy "%s" "%s" /E /R:30 /W:1 /XF %s >nul' % (sorgente, destinazione, " ".join(TUE_IMPOSTAZIONI)),
        "if errorlevel 8 (",
        "  echo  Aggiornamento NON riuscito: chiudi tutte le finestre del bot e riprova dal menu.",
        "  pause",
        "  exit /b 1",
        ")",
        'rmdir /s /q "%s" >nul 2>&1' % temporanea,
        "echo  Fatto! Riapro il bot.",
        'start "" /D "%s" "%s"' % (destinazione, exe),
    ]
    return "\r\n".join(righe) + "\r\n"


def aggiorna():
    """Menu 13: scarica l'ultima versione da GitHub e la mette al posto di questa."""
    import subprocess
    import tempfile
    import urllib.request
    import zipfile
    if not getattr(sys, "frozen", False) or sys.platform != "win32":
        print("L'aggiornamento automatico funziona solo con BotSparatutto.exe su Windows.")
        return
    temporanea = os.path.join(tempfile.gettempdir(), "BotSparatutto_aggiornamento")
    shutil.rmtree(temporanea, ignore_errors=True)
    os.makedirs(temporanea, exist_ok=True)
    file_zip = os.path.join(temporanea, "BotSparatutto.zip")
    print("\nScarico l'ultima versione (circa 100 MB, puo' metterci qualche minuto)...", flush=True)
    urllib.request.urlretrieve(URL_AGGIORNAMENTO, file_zip)
    print("Estraggo...", flush=True)
    with zipfile.ZipFile(file_zip) as z:
        z.extractall(temporanea)
    sorgente = os.path.join(temporanea, "BotSparatutto")
    nuova, attuale = leggi_versione(sorgente), leggi_versione(BASE)
    if nuova <= attuale:
        print("Hai gia' l'ultima versione (%d)." % attuale)
        shutil.rmtree(temporanea, ignore_errors=True)
        return
    print("C'e' la versione %d (tu hai la %d)." % (nuova, attuale))
    print("Ora il bot si chiude, si aggiorna e si riapre da solo. Le tue impostazioni restano.")
    script = os.path.join(tempfile.gettempdir(), "aggiorna_bot_sparatutto.cmd")
    with open(script, "w", encoding="ascii", errors="replace", newline="") as f:
        f.write(script_aggiornamento(sorgente, BASE, os.path.basename(sys.executable), temporanea))
    time.sleep(2)
    subprocess.Popen(["cmd", "/c", script], creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    sys.exit(0)


# ------------------------------------------------------------------ autotest (per GitHub)
def autotest():
    """Controlla che tutto si carichi e che il cervello reagisca a un nemico finto."""
    import cv2
    import numpy as np

    from cervello import Cervello
    from mani import ManiFinte
    from occhi import Occhi, SchermoFinto

    from occhi import crea_rilevatore_universale

    cfg = impostazioni.carica(BASE)
    cfg["rilevatore_universale"]["scarica_se_manca"] = False
    img = np.full((720, 1280, 3), 60, np.uint8)
    cv2.rectangle(img, (800, 250), (840, 340), (0, 0, 255), -1)        # nemico rosso a destra
    cv2.rectangle(img, (300, 520), (360, 560), (0, 200, 255), -1)       # cassa dorata
    mani = ManiFinte(cfg.get("tasti"), log)
    schermo = SchermoFinto([img])
    occhi = Occhi(cfg, BASE, log, universale=False)
    cfg["colori"]["nemico"] = [{"tinta": [170, 8], "saturazione": [170, 255], "luminosita": [150, 255]}]
    occhi.colori["nemico"] = cfg["colori"]["nemico"]
    controllo = Controllo({"schermo": {}})
    statistiche = {}
    esecutore, istruzioni = prepara(cfg, mani, occhi, schermo, controllo, statistiche)
    cervello = Cervello(cfg, mani, occhi, esecutore, istruzioni, log)
    vis = occhi.analizza(schermo.foto())
    ok = True
    if not vis.nemici:
        log("AUTOTEST: nemico non trovato")
        ok = False
    if not vis.casse:
        log("AUTOTEST: cassa non trovata")
        ok = False
    istruzioni.regole = [r for r in istruzioni.regole if not any(c.tipo == "inizio" for c in r.condizioni)]
    for r in istruzioni.regole:
        r.prossimo_ogni = time.monotonic() + 3600
    cervello.passo(vis, img)
    if mani.mosso_x <= 0:
        log("AUTOTEST: non ha mirato verso il nemico (mosso_x=%s)" % mani.mosso_x)
        ok = False
    # l'occhio universale (se i modelli ci sono) deve caricarsi e funzionare
    if os.path.isdir(os.path.join(BASE, "modelli")) and any(
            f.endswith(".onnx") for f in os.listdir(os.path.join(BASE, "modelli"))):
        ru = crea_rilevatore_universale(cfg["rilevatore_universale"], BASE, log)
        if ru is None:
            log("AUTOTEST: occhio universale non si carica")
            ok = False
        else:
            ru.rileva(img)
    log("AUTOTEST " + ("OK" if ok else "FALLITO"))
    return 0 if ok else 1


# ------------------------------------------------------------------ menu
MENU = [
    ("1", "Avvia il bot (scegli la modalita': Normale, Pro player o Tranquillo)", "avvia"),
    ("2", "Prova senza premere niente (vedi cosa farebbe, con finestra di controllo)", "prova"),
    ("3", "Prova la schedina (il mouse fa un quadrato)", "test"),
    ("4", "Impara guardando me (giochi tu, anche sulla Play: il bot impara casse e mira)", "impara"),
    ("5", "Calibra i colori a mano (casse, casse materiali, armi, compagni)", "colori"),
    ("6", "Salva un'immagine (pulsanti e scritte per le istruzioni)", "immagine"),
    ("7", "Calibra la barra della vita", "vita"),
    ("8", "Zone da ignorare (minimappa, icone...)", "zone"),
    ("9", "Calibra la mira a mano (di solito la impara da solo)", "mira"),
    ("10", "Calibra il giro completo a mano (di solito lo impara da solo)", "giro"),
    ("11", "Scrivi l'obiettivo (es. aprire 50 casse a partita)", "obiettivo"),
    ("12", "Telecomando: tastiera e mouse del portatile sulla Play (es. INVIO per l'account)", "telecomando"),
    ("13", "Aggiorna il programma (scarica l'ultima versione)", "aggiorna"),
    ("14", "Collega le IA (il cervello che guarda: bus, casse vere, muri, tempesta)", "ia"),
    ("15", "Collega Gemini con il tuo account Google (la piu' brava a capire il gioco)", "gemini"),
    ("16", "L'IA studia le foto: trova nemici e casse nelle foto di foto_per_ia", "studia"),
    ("0", "Esci", "esci"),
]


def esegui_comando(cmd):
    import calibra
    if cmd == "avvia":
        avvia()
    elif cmd == "prova":
        avvia("prova")
    elif cmd == "test":
        prova_schedina()
    elif cmd == "obiettivo":
        import obiettivo
        obiettivo.chiedi(BASE)
    elif cmd == "telecomando":
        import telecomando
        cfg = impostazioni.carica(BASE)
        attesa = int(float((cfg.get("schermo", {}) or {}).get("secondi_prima_di_partire", 30) or 30))
        telecomando.usa(cfg, log, attesa)
    elif cmd == "aggiorna":
        aggiorna()
    elif cmd == "ia":
        import ia
        ia.collega(BASE, impostazioni.carica(BASE), log)
    elif cmd == "gemini":
        import ia
        ia.collega_gemini(BASE, impostazioni.carica(BASE), log)
    elif cmd == "studia":
        import studia_foto
        studia_foto.studia(BASE, impostazioni.carica(BASE), log)
    elif cmd in ("colori", "immagine", "vita", "zone", "mira", "giro", "impara"):
        getattr(calibra, cmd)(BASE, log)
    else:
        print("Comando sconosciuto:", cmd)


def menu():
    while True:
        print()
        print("=" * 70)
        print("  BOT SPARATUTTO")
        print("=" * 70)
        for numero, testo, _ in MENU:
            print("  %2s) %s" % (numero, testo))
        try:
            scelta = input("\nScrivi il numero e premi INVIO: ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        cmd = next((c for n, _, c in MENU if n == scelta), None)
        if cmd is None:
            continue
        if cmd == "esci":
            return
        try:
            esegui_comando(cmd)
        except KeyboardInterrupt:
            print("\nFermato.")
        except Exception as e:
            from mani import SchedinaNonTrovata
            if isinstance(e, (SchedinaNonTrovata, impostazioni.ErroreImpostazioni)):
                print("\nPROBLEMA: %s" % e)
            else:
                traceback.print_exc()
                print("\nC'e' stato un errore imprevisto (copia il testo qui sopra e mandamelo).")
            aspetta_invio()


def main():
    imposta_dpi()
    disattiva_quick_edit()
    os.chdir(BASE)
    args = [a.lower() for a in sys.argv[1:]]
    if "--autotest" in args:
        sys.exit(autotest())
    if args:
        esegui_comando(args[0])
        return
    menu()


if __name__ == "__main__":
    main()
