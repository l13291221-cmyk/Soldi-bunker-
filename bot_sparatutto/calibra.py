"""
calibra.py - Strumenti per insegnare al bot com'e' fatto il TUO gioco.

  colori   : clicchi su nemici / casse / armi e il bot impara i loro colori
  immagine : selezioni un pezzo di schermo (pulsante, scritta) e lo salva
  vita     : selezioni la barra della vita e clicchi sul suo colore
  zone     : selezioni le zone da ignorare (minimappa, icone, il tuo personaggio)
  mira     : misura da solo quanto si muove la visuale per ogni passo del mouse
  giro     : misura quanti passi del mouse servono per fare un giro completo

(Il bot impara gia' da solo sensibilita', giro e forza della mira mentre gioca:
 questi strumenti servono se vuoi farlo a mano o se da solo non ci riesce.)

Tutto quello che impara lo scrive in calibrazione.yaml.
"""

import os
import time

import cv2
import numpy as np

import impostazioni
from apprendimento import intervallo_da_pixel, misura_spostamento

LARGHEZZA_FINESTRA = 1280
CATEGORIE = {"1": "cassa", "2": "materiali", "3": "arma", "4": "nemico", "5": "alleato", "6": "testa"}


def _schermo(cfg):
    from occhi import Schermo
    sch = cfg.get("schermo", {}) or {}
    return Schermo(int(sch.get("monitor", 1) or 1), sch.get("zona_cattura"))


def _scatta(cfg, secondi=5, testo="Vai nel gioco, nel punto giusto"):
    print("\n%s: faccio la foto dello schermo tra..." % testo)
    for s in range(secondi, 0, -1):
        print("  %d..." % s, flush=True)
        time.sleep(1)
    schermo = _schermo(cfg)
    img = schermo.foto()
    schermo.chiudi()
    print("Foto fatta! Torna qui sulla finestra che si apre.")
    return img


def _adatta(img):
    scala = min(1.0, LARGHEZZA_FINESTRA / float(img.shape[1]))
    return cv2.resize(img, None, fx=scala, fy=scala, interpolation=cv2.INTER_AREA), scala


def _scritta(img, righe):
    for i, r in enumerate(righe):
        y = 28 + 26 * i
        cv2.putText(img, r, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 4)
        cv2.putText(img, r, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)


def _in_primo_piano(nome):
    try:
        cv2.setWindowProperty(nome, cv2.WND_PROP_TOPMOST, 1)
    except Exception:
        pass


# ------------------------------------------------------------------ colori
def _scegli_colori(img, titolo, spiegazione):
    """Finestra dove clicchi sul colore. Restituisce l'intervallo, oppure None se annulli."""
    from occhi import maschera_colori
    piccola, scala = _adatta(img)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    punti = []
    stato = {"cambiato": True}

    def click(evento, x, y, flags, param):
        if evento == cv2.EVENT_LBUTTONDOWN:
            punti.append((int(x / scala), int(y / scala)))
            stato["cambiato"] = True

    nome = "Calibra: " + titolo
    cv2.namedWindow(nome)
    cv2.setMouseCallback(nome, click)
    _in_primo_piano(nome)
    intervallo = None
    while True:
        if stato["cambiato"]:
            stato["cambiato"] = False
            vista = piccola.copy()
            if punti:
                pixel = []
                for (x, y) in punti:
                    pezzo = hsv[max(0, y - 3):y + 4, max(0, x - 3):x + 4].reshape(-1, 3)
                    pixel.append(pezzo)
                intervallo = intervallo_da_pixel(np.concatenate(pixel))
                m = maschera_colori(cv2.cvtColor(piccola, cv2.COLOR_BGR2HSV), [intervallo])
                vista[m > 0] = (0, 255, 0)
                for (x, y) in punti:
                    cv2.circle(vista, (int(x * scala), int(y * scala)), 4, (255, 0, 255), -1)
            _scritta(vista, [spiegazione,
                             "Click = aggiungi un punto   Z = togli l'ultimo   R = ricomincia",
                             "INVIO = salva   ESC = annulla      (in VERDE quello che il bot vedra')"])
            cv2.imshow(nome, vista)
        k = cv2.waitKey(30) & 0xFF
        if k in (13, 10):
            break
        if k == 27:
            intervallo = None
            break
        if k in (ord("z"), ord("Z")) and punti:
            punti.pop()
            stato["cambiato"] = True
            if not punti:
                intervallo = None
        if k in (ord("r"), ord("R")):
            punti.clear()
            intervallo = None
            stato["cambiato"] = True
        try:
            if cv2.getWindowProperty(nome, cv2.WND_PROP_VISIBLE) < 1:
                intervallo = None
                break
        except Exception:
            break
    cv2.destroyWindow(nome)
    return intervallo if punti else None


def colori(base, log=print):
    cfg = impostazioni.carica(base)
    print("\nDi cosa vuoi insegnare il colore?")
    print("  1) casse delle armi     (es. la luce dorata)")
    print("  2) casse dei materiali  (es. le casse delle munizioni/materiali)")
    print("  3) armi per terra       (es. la luce delle armi)")
    print("  4) nemici               (facoltativo: i personaggi li riconosce gia' da solo)")
    print("  5) compagni di squadra  (es. il nome blu sopra di loro: cosi' non gli spara)")
    print("  6) teste                (facoltativo)")
    scelta = input("Numero: ").strip()
    cat = CATEGORIE.get(scelta)
    if not cat:
        return
    vecchi = (cfg.get("colori", {}) or {}).get(cat) or []
    aggiungi = False
    if vecchi:
        r = input("Ci sono gia' dei colori per '%s'. Scrivi A per AGGIUNGERNE uno, INVIO per sostituirli: " % cat)
        aggiungi = r.strip().lower().startswith("a")
    img = _scatta(cfg, 5, "Vai nel gioco dove si vede bene un/una %s" % cat)
    intervallo = _scegli_colori(img, cat, "Clicca piu' volte sul colore di: %s" % cat.upper())
    if intervallo is None:
        print("Annullato, non ho cambiato niente.")
        return
    nuovi = (list(vecchi) + [intervallo]) if aggiungi else [intervallo]
    p = impostazioni.salva_calibrazione(base, ["colori", cat], nuovi)
    print("Salvato in %s: %s = %s" % (p, cat, nuovi))
    print("Consiglio: prova il bot con il menu 2 (prova) per vedere se riconosce bene.")


# ------------------------------------------------------------------ immagini
def _seleziona(img, titolo, piu_di_una=False):
    piccola, scala = _adatta(img)
    vista = piccola.copy()
    _scritta(vista, ["Trascina con il mouse per fare un rettangolo, poi INVIO (o SPAZIO).",
                     ("Puoi farne piu' di uno. Quando hai finito premi ESC." if piu_di_una else "C = annulla")])
    nome = "Calibra: " + titolo
    cv2.namedWindow(nome)
    _in_primo_piano(nome)
    if piu_di_una:
        rett = cv2.selectROIs(nome, vista, showCrosshair=False)
    else:
        r = cv2.selectROI(nome, vista, showCrosshair=False)
        rett = [r] if r is not None and r[2] > 0 and r[3] > 0 else []
    cv2.destroyWindow(nome)
    risultato = []
    for (x, y, w, h) in (rett if rett is not None else []):
        if w > 0 and h > 0:
            risultato.append((int(x / scala), int(y / scala), int(w / scala), int(h / scala)))
    return risultato


def immagine(base, log=print):
    cfg = impostazioni.carica(base)
    print("\nSalva un pezzo di schermo da riconoscere (un pulsante, una scritta...).")
    print("Esempi di nomi: squadra_eliminata, gioca_ancora, pronto, premi_e")
    nome = input("Come la chiamo? (senza spazi): ").strip().lower().replace(" ", "_")
    if not nome:
        return
    img = _scatta(cfg, 5, "Vai nel gioco dove si vede '%s'" % nome)
    rett = _seleziona(img, nome)
    if not rett:
        print("Annullato.")
        return
    x, y, w, h = rett[0]
    pezzo = img[y:y + h, x:x + w]
    cartella = os.path.join(base, "immagini")
    os.makedirs(cartella, exist_ok=True)
    p = os.path.join(cartella, nome + ".png")
    ok, dati = cv2.imencode(".png", pezzo)
    if ok:
        dati.tofile(p)
        print("Salvata: %s" % p)
        print("Ora puoi scrivere in istruzioni.txt ad esempio:  QUANDO vedi %s FAI ..." % nome)
        print("Consiglio: scegli un pezzo che c'e' SOLO in quella schermata (una scritta, un pulsante).")


# ------------------------------------------------------------------ barra della vita
def vita(base, log=print):
    from occhi import leggi_barra
    cfg = impostazioni.carica(base)
    print("\nInsegno al bot dov'e' la barra della vita.")
    print("Fallo quando la vita NON e' piena del tutto (va bene anche piena, ma e' meglio a meta').")
    img = _scatta(cfg, 5, "Vai nel gioco, con la barra della vita visibile")
    rett = _seleziona(img, "barra della vita (stretta, solo la barra)")
    if not rett:
        print("Annullato.")
        return
    x, y, w, h = rett[0]
    H, W = img.shape[:2]
    zona = [round(x / W, 4), round(y / H, 4), round(w / W, 4), round(h / H, 4)]
    zoom = cv2.resize(img[y:y + h, x:x + w], None, fx=max(1, 600 // max(1, w)), fy=max(1, 600 // max(1, w)),
                      interpolation=cv2.INTER_NEAREST)
    intervallo = _scegli_colori(zoom, "colore della vita", "Clicca sulla parte PIENA della barra")
    if intervallo is None:
        print("Annullato.")
        return
    impostazioni.salva_calibrazione(base, ["vita", "zona"], zona)
    impostazioni.salva_calibrazione(base, ["vita", "colore"], [intervallo])
    print("Salvato! Adesso leggo: vita = %.0f%%" % leggi_barra(img, zona, [intervallo]))


def zone(base, log=print):
    cfg = impostazioni.carica(base)
    print("\nSeleziona le zone dello schermo che il bot deve IGNORARE:")
    print("minimappa, icone, la tua arma, il TUO personaggio (se il gioco e' in terza persona)...")
    img = _scatta(cfg, 5, "Vai nel gioco, durante una partita")
    rett = _seleziona(img, "zone da ignorare", piu_di_una=True)
    H, W = img.shape[:2]
    lista = [[round(x / W, 4), round(y / H, 4), round(w / W, 4), round(h / H, 4)] for (x, y, w, h) in rett]
    impostazioni.salva_calibrazione(base, ["schermo", "zone_ignorate"], lista)
    print("Salvate %d zone da ignorare." % len(lista))


# ------------------------------------------------------------------ mira e giro
def _mani(cfg):
    from mani import crea_mani
    return crea_mani(cfg, print)


def mira(base, log=print):
    cfg = impostazioni.carica(base)
    print("\nMisuro la sensibilita': il bot girera' la visuale un po' a destra e a sinistra.")
    print("Nel gioco: stai FERMO in un posto aperto, con la visuale libera (non in un menu).")
    mani = _mani(cfg)
    schermo = _schermo(cfg)
    try:
        for s in range(5, 0, -1):
            print("  clicca sul gioco: parto tra %d..." % s, flush=True)
            time.sleep(1)
        passi = 100
        misure = []
        for tentativo in range(8):
            prima = schermo.foto()
            mani.muovi(passi, 0)
            time.sleep(0.3)
            dopo = schermo.foto()
            mani.muovi(-passi, 0)
            time.sleep(0.3)
            dx, dy, risposta, larghezza = misura_spostamento(prima, dopo)
            print("  %d passi -> %.1f pixel (sicurezza %.2f)" % (passi, abs(dx), risposta))
            if abs(dx) < 3:
                passi *= 3
                continue
            if abs(dx) > 0.3 * larghezza:
                passi = max(5, passi // 3)
                continue
            if risposta > 0.05:
                misure.append(abs(dx) / passi)
            if len(misure) >= 3:
                break
        if not misure:
            print("Non sono riuscito a misurare. Prova in un posto con piu' dettagli (non il cielo).")
            return
        ppp = float(np.median(misure))
        impostazioni.salva_calibrazione(base, ["mira", "pixel_per_passo"], round(ppp, 4))
        print("Fatto! pixel_per_passo = %.4f (salvato)" % ppp)
    finally:
        mani.chiudi()
        schermo.chiudi()


def giro(base, log=print):
    cfg = impostazioni.carica(base)
    mira_cfg = cfg.get("mira", {}) or {}
    passi = float(mira_cfg.get("passi_per_giro", 3600) or 3600)
    ppp = float(mira_cfg.get("pixel_per_passo", 1.0) or 1.0)
    print("\nMisuro quanti passi del mouse servono per un giro completo (360 gradi).")
    print("Nel gioco: stai FERMO in un posto aperto. Il bot fara' qualche giro su se stesso.")
    print("Valore attuale: %.0f passi" % passi)
    mani = _mani(cfg)
    schermo = _schermo(cfg)
    try:
        for s in range(5, 0, -1):
            print("  clicca sul gioco: parto tra %d..." % s, flush=True)
            time.sleep(1)
        for tentativo in range(6):
            prima = schermo.foto()
            pezzi = 100
            for _ in range(pezzi):
                mani.muovi(passi / pezzi, 0)
                time.sleep(0.015)
            time.sleep(0.4)
            dopo = schermo.foto()
            dx, dy, risposta, larghezza = misura_spostamento(prima, dopo)
            print("  giro di %.0f passi: differenza %.1f pixel (sicurezza %.2f)" % (passi, dx, risposta))
            if risposta < 0.05 or abs(dx) > 0.3 * larghezza:
                print("  Non riesco a misurarlo da solo (il giro e' troppo diverso da 360 gradi).")
                break
            if abs(dx) <= 2:
                impostazioni.salva_calibrazione(base, ["mira", "passi_per_giro"], round(passi))
                print("Fatto! passi_per_giro = %.0f (salvato)" % passi)
                return
            passi += dx / ppp
        # a mano
        print("\nFacciamolo a mano. Guarda il gioco mentre gira.")
        while True:
            r = input("Scrivi: 'poco' (non arriva al giro), 'troppo' (lo supera), un numero, oppure 'ok': ").strip().lower()
            if r == "ok":
                break
            if r == "poco":
                passi *= 1.1
            elif r == "troppo":
                passi /= 1.1
            else:
                try:
                    passi = float(r.replace(",", "."))
                except ValueError:
                    continue
            print("Provo con %.0f passi. Clicca sul gioco..." % passi)
            time.sleep(3)
            for _ in range(100):
                mani.muovi(passi / 100, 0)
                time.sleep(0.02)
        impostazioni.salva_calibrazione(base, ["mira", "passi_per_giro"], round(passi))
        print("Salvato: passi_per_giro = %.0f" % passi)
    finally:
        mani.chiudi()
        schermo.chiudi()


# ------------------------------------------------------------------ impara guardando te
def impara(base, log=print):
    from apprendimento import impara as _impara
    _impara(base, log)
