"""
apprendimento.py - Il bot impara il gioco da solo, cosi' si adatta a ogni gioco.

Mentre GIOCA impara:
  1. la SENSIBILITA' del mouse: muove un po' la visuale e misura di quanto si sposta lo schermo
  2. il GIRO COMPLETO: quanti passi del mouse servono per girarsi di 360 gradi
  3. la FORZA della mira: se supera il bersaglio la abbassa, se e' lenta la alza
  4. cosa IGNORARE: se un "nemico" resta fermo sullo schermo anche quando gira la visuale,
     e' il TUO personaggio (o un'icona): da quel momento lo ignora per sempre
  5. (se vuoi) salva foto gia' etichettate per addestrare un'IA solo per quel gioco

Quando GUARDA TE (menu "Impara guardando me") impara:
  6. i COLORI delle casse / casse dei materiali / armi: guarda cosa c'e' davanti a te
     ogni volta che premi il tasto per aprire/raccogliere
  7. DOVE MIRI sui nemici (testa, petto...): guarda dove sta il mirino quando spari

Tutto quello che impara lo scrive in calibrazione.yaml: la volta dopo lo sa gia'.
"""

import math
import os
import queue
import time

import cv2
import numpy as np

import impostazioni

CLASSI_DATASET = ["nemico", "cassa", "materiali", "arma"]


# ------------------------------------------------------------------ misure sullo schermo
def fascia_grigia(img):
    """La fascia in alto al centro dello schermo (lontana dal tuo personaggio e dalle icone)."""
    H, W = img.shape[:2]
    x1, x2 = int(W * 0.2), int(W * 0.8)
    y1, y2 = int(H * 0.12), int(H * 0.45)
    return cv2.cvtColor(img[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY).astype(np.float32)


def misura_spostamento(prima, dopo):
    """Di quanti pixel si e' spostata l'immagine: (dx, dy, affidabilita' 0-1, larghezza fascia)."""
    a = fascia_grigia(prima)
    b = fascia_grigia(dopo)
    finestra = cv2.createHanningWindow((a.shape[1], a.shape[0]), cv2.CV_32F)
    (dx, dy), risposta = cv2.phaseCorrelate(a, b, finestra)
    return float(dx), float(dy), float(risposta), a.shape[1]


def intervallo_da_pixel(hsv_pixel):
    """Da tanti pixel HSV a un intervallo {tinta, saturazione, luminosita} (gestisce il rosso)."""
    hsv_pixel = np.asarray(hsv_pixel).reshape(-1, 3)
    h = hsv_pixel[:, 0].astype(np.int32)
    s = hsv_pixel[:, 1].astype(np.int32)
    v = hsv_pixel[:, 2].astype(np.int32)
    rosso = np.mean((h < 15) | (h > 165)) > 0.5
    if rosso:
        h = (h + 90) % 180       # sposto il rosso in mezzo per non spezzarlo
    h1, h2 = int(np.percentile(h, 3)) - 5, int(np.percentile(h, 97)) + 5
    if rosso:
        h1, h2 = (h1 - 90) % 180, (h2 - 90) % 180
    else:
        h1, h2 = max(0, h1), min(179, h2)
    s1 = max(0, int(np.percentile(s, 3)) - 40)
    s2 = min(255, int(np.percentile(s, 97)) + 40)
    v1 = max(0, int(np.percentile(v, 3)) - 40)
    v2 = min(255, int(np.percentile(v, 97)) + 40)
    return {"tinta": [int(h1), int(h2)], "saturazione": [s1, s2], "luminosita": [v1, v2]}


def nome_colore(tinta):
    t = int(tinta) % 180
    for limite, nome in ((8, "rosso"), (20, "arancione"), (34, "giallo/oro"), (85, "verde"), (100, "azzurro"),
                         (130, "blu"), (160, "viola"), (180, "rosa/rosso")):
        if t <= limite:
            return nome
    return "?"


def _iou(a, b):
    x1, y1 = max(a.x, b.x), max(a.y, b.y)
    x2, y2 = min(a.x + a.w, b.x + b.w), min(a.y + a.h, b.y + b.h)
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    unione = a.w * a.h + b.w * b.h - inter
    return inter / unione if unione > 0 else 0.0


# ------------------------------------------------------------------ foto etichettate per l'IA
class SalvaFoto:
    """Salva foto + etichette in formato YOLO (cartella foto_per_ia), pronte per l'addestramento."""

    def __init__(self, cartella):
        self.cartella = cartella
        self.immagini = os.path.join(cartella, "images")
        self.etichette = os.path.join(cartella, "labels")
        os.makedirs(self.immagini, exist_ok=True)
        os.makedirs(self.etichette, exist_ok=True)
        dataset = os.path.join(cartella, "dataset.yaml")
        if not os.path.isfile(dataset):
            with open(dataset, "w", encoding="utf-8") as f:
                f.write("# Dataset per addestrare l'IA del tuo gioco (vedi GUIDA.txt, parte IA)\n")
                f.write("train: images\nval: images\nnames:\n")
                for i, n in enumerate(CLASSI_DATASET):
                    f.write("  %d: %s\n" % (i, n))
        self.n = 0

    def salva(self, img, vis, anche_vuote=False):
        H, W = img.shape[:2]
        righe = []
        for i, cat in enumerate(CLASSI_DATASET):
            for b in vis.oggetti.get(cat, []):
                x1, y1 = max(0.0, b.x), max(0.0, b.y)
                x2, y2 = min(float(W), b.x + b.w), min(float(H), b.y + b.h)
                if x2 - x1 < 2 or y2 - y1 < 2:
                    continue
                righe.append("%d %.6f %.6f %.6f %.6f" % (i, (x1 + x2) / 2 / W, (y1 + y2) / 2 / H,
                                                         (x2 - x1) / W, (y2 - y1) / H))
        if not righe and not anche_vuote:
            return False
        nome = time.strftime("foto_%Y%m%d_%H%M%S_") + "%05d" % self.n
        self.n += 1
        ok, dati = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if not ok:
            return False
        dati.tofile(os.path.join(self.immagini, nome + ".jpg"))
        with open(os.path.join(self.etichette, nome + ".txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(righe) + ("\n" if righe else ""))
        return True


# ------------------------------------------------------------------ apprendimento mentre gioca
class Apprendimento:
    def __init__(self, cfg, base, occhi, log=print):
        self.cfg = cfg
        self.base = base
        self.occhi = occhi
        self.log = log
        ap = cfg.get("apprendimento", {}) or {}
        mira = cfg.get("mira", {}) or {}
        cal_mira = (impostazioni.leggi_calibrazione(base).get("mira", {}) or {})
        self.attivo = bool(ap.get("attivo", True))
        self.calibra_da_solo = self.attivo and bool(ap.get("calibra_da_solo", True))
        self.mira_adattiva = self.attivo and bool(ap.get("mira_adattiva", True))
        self.impara_attaccati = self.attivo and bool(ap.get("impara_cose_attaccate", True))
        self.ppp_noto = "pixel_per_passo" in cal_mira or not self.calibra_da_solo
        self.giro_noto = "passi_per_giro" in cal_mira or not self.calibra_da_solo
        self.ppp = max(0.01, float(mira.get("pixel_per_passo", 1.0) or 1.0))
        self.passi_per_giro = float(mira.get("passi_per_giro", 3600) or 3600)
        self.forza = float(mira.get("forza", 0.6) or 0.6)
        self._forza_salvata = self.forza
        self.prossimo_tentativo = 0.0
        self.fallimenti = 0
        self.fallimenti_giro = 0
        self._att = None                  # bersaglio che sto controllando (attaccato alla visuale?)
        self.salva_foto_ogni = float(ap.get("salva_foto_ogni", 0) or 0)
        self.foto = SalvaFoto(os.path.join(base, "foto_per_ia")) if self.salva_foto_ogni > 0 else None
        self.prossima_foto = 0.0
        self.prossimo_salvataggio = time.monotonic() + 300

    # ---- 1 e 2: sensibilita' e giro completo ----
    def serve_calibrare(self, t):
        return self.calibra_da_solo and (not self.ppp_noto or not self.giro_noto) and t >= self.prossimo_tentativo

    def calibra(self, mani, schermo, esecutore):
        """Fa una misura (dura 1-3 secondi). Restituisce una scritta su cosa sta imparando."""
        mani.rilascia_tutto()
        if not self.ppp_noto:
            if self._misura_sensibilita(mani, schermo, esecutore):
                self.fallimenti = 0
            else:
                self.fallimenti += 1
                self.prossimo_tentativo = time.monotonic() + (4.0 if self.fallimenti < 5 else 20.0)
            return "imparo la sensibilita' del mouse"
        if self._misura_giro(mani, schermo, esecutore):
            esecutore.passi_per_giro = self.passi_per_giro
        else:
            self.fallimenti_giro += 1
            self.prossimo_tentativo = time.monotonic() + 30.0
            if self.fallimenti_giro >= 3:
                self.giro_noto = True       # tengo la stima, non riprovo piu'
                self.log("Giro completo: uso la stima %.0f passi" % self.passi_per_giro)
        esecutore.passi_per_giro = self.passi_per_giro
        return "imparo il giro completo"

    def _misura_sensibilita(self, mani, schermo, esecutore):
        esecutore.dormi(0.25)
        passi = 60.0
        misure = []
        for _ in range(8):
            prima = schermo.foto()
            mani.muovi(passi, 0)
            esecutore.dormi(0.22)
            dopo = schermo.foto()
            mani.muovi(-passi, 0)
            esecutore.dormi(0.22)
            dx, dy, risposta, larghezza = misura_spostamento(prima, dopo)
            if abs(dx) < 3:
                passi *= 3
                if passi > 3000:
                    return False              # la visuale non si muove: forse e' un menu
                continue
            if abs(dx) > 0.25 * larghezza:
                passi = max(3.0, passi / 3)
                continue
            if risposta < 0.05:
                continue
            misure.append(abs(dx) / passi)
            if self.impara_attaccati and abs(dx) > 15:
                self._cerca_attaccati(prima, dopo)
            if len(misure) >= 3:
                break
        if len(misure) < 2:
            return False
        mediana = float(np.median(misure))
        if max(abs(m - mediana) for m in misure) > 0.3 * mediana:
            return False
        self.ppp = mediana
        self.ppp_noto = True
        impostazioni.salva_calibrazione(self.base, ["mira", "pixel_per_passo"], round(mediana, 4))
        if not self.giro_noto:
            # stima (visuale di circa 90 gradi): la affino dopo
            self.passi_per_giro = math.pi * prima.shape[1] / self.ppp
        self.log("Ho imparato la sensibilita': %.3f pixel per passo del mouse" % mediana)
        return True

    def _gira(self, mani, esecutore, passi, durata=0.5):
        pezzi = 50
        for _ in range(pezzi):
            mani.muovi(passi / pezzi, 0)
            esecutore.dormi(durata / pezzi)

    def _prova_giro(self, mani, schermo, esecutore, stima):
        """Fa un giro di 'stima' passi: di quanto e' fuori dal giro completo? (dx, affidabile?)"""
        prima = schermo.foto()
        self._gira(mani, esecutore, stima)
        esecutore.dormi(0.35)
        dopo = schermo.foto()
        dx, dy, risposta, larghezza = misura_spostamento(prima, dopo)
        return dx, (risposta >= 0.15 and abs(dx) <= 0.2 * larghezza and abs(dy) <= 0.2 * larghezza)

    def _misura_giro(self, mani, schermo, esecutore):
        stima_base = self.passi_per_giro
        for moltiplica in (1.0, 1.1, 0.9, 1.2, 0.83, 1.32, 0.75, 1.45, 0.68):
            stima = stima_base * moltiplica
            dx, ok = self._prova_giro(mani, schermo, esecutore, stima)
            if not ok:
                continue
            for _ in range(5):
                if abs(dx) <= 3:
                    break
                stima += dx / self.ppp       # se ho girato troppo lo schermo e' andato a sinistra (dx < 0)
                dx, ok = self._prova_giro(mani, schermo, esecutore, stima)
                if not ok:
                    break
            if not ok or abs(dx) > 4:
                continue                     # non era un giro vero: provo il prossimo
            self.passi_per_giro = stima
            self.giro_noto = True
            impostazioni.salva_calibrazione(self.base, ["mira", "passi_per_giro"], round(stima))
            self.log("Ho imparato il giro completo: %.0f passi del mouse = 360 gradi" % stima)
            return True
        return False

    # ---- 3: forza della mira ----
    def osserva_mira(self, errore_prima, errore_dopo):
        """Due fotogrammi di fila sullo stesso bersaglio: la mira e' andata oltre o e' troppo lenta?"""
        if not self.mira_adattiva:
            return
        ex0, ey0 = errore_prima
        ex1, ey1 = errore_dopo
        n2 = ex0 * ex0 + ey0 * ey0
        if n2 < 144:
            return
        r = (ex1 * ex0 + ey1 * ey0) / n2
        if r < -0.15:
            self.forza *= 0.94            # e' andata oltre: piu' delicata
        elif r > 0.65:
            self.forza *= 1.04            # troppo lenta: piu' decisa
        self.forza = min(1.2, max(0.15, self.forza))

    # ---- 4: cose attaccate alla visuale (il tuo personaggio, icone) ----
    def _cerca_attaccati(self, prima, dopo):
        """Ho girato la visuale: un 'nemico' rimasto nello stesso punto e' attaccato allo schermo."""
        try:
            vis_a = self.occhi.analizza(prima)
            vis_b = self.occhi.analizza(dopo)
        except Exception:
            return
        H = prima.shape[0]
        for a in vis_a.nemici:
            if a.h < 0.06 * H:
                continue
            for b in vis_b.nemici:
                if _iou(a, b) > 0.6:
                    self.aggiungi_zona(a, prima.shape[1], H, None)
                    break

    def controlla_bersaglio(self, box, errore, mosso_px, nuovo, larghezza, altezza, mirino):
        """Ogni fotogramma di combattimento. True = quel bersaglio e' attaccato alla visuale: ignoralo."""
        if not (self.impara_attaccati and self.ppp_noto):
            return False
        e = math.hypot(errore[0], errore[1])
        if nuovo or self._att is None:
            self._att = {"e0": e, "mosso": 0.0, "n": 0, "forza0": self.forza}
            return False
        a = self._att
        a["mosso"] += mosso_px
        a["n"] += 1
        if e < 0.5 * a["e0"]:
            # si avvicina al mirino: e' un bersaglio vero
            self._att = {"e0": e, "mosso": 0.0, "n": 0, "forza0": self.forza}
            return False
        if a["n"] >= 6 and a["e0"] > 25 and a["mosso"] >= 3 * a["e0"] and e >= 0.8 * a["e0"]:
            self._att = None
            self.forza = a["forza0"]      # quello che ho "imparato" mirando a lui non vale
            self.aggiungi_zona(box, larghezza, altezza, mirino)
            return True
        return False

    def aggiungi_zona(self, box, larghezza, altezza, mirino):
        # solo il centro del rettangolo: cosi' i nemici veri che ci passano vicino si vedono ancora
        z = [round((box.x + 0.2 * box.w) / larghezza, 4), round((box.y + 0.2 * box.h) / altezza, 4),
             round(0.6 * box.w / larghezza, 4), round(0.6 * box.h / altezza, 4)]
        if mirino is not None and box.contiene(mirino[0], mirino[1]):
            self.occhi.zone_temporanee.append((z, time.monotonic() + 15.0))
            self.log("Quella cosa sul mirino non si muove mai: la ignoro per 15 secondi")
            return
        for v in self.occhi.zone_apprese:
            if abs(v[0] - z[0]) < 0.03 and abs(v[1] - z[1]) < 0.03:
                return
        self.occhi.zone_apprese.append(z)
        impostazioni.salva_calibrazione(self.base, ["schermo", "zone_apprese"], list(self.occhi.zone_apprese))
        self.log("Ho capito che quello e' il TUO personaggio (o un'icona): d'ora in poi lo ignoro")

    # ---- 5: foto per l'IA ----
    def forse_salva_foto(self, img, vis, t):
        if self.foto is None or t < self.prossima_foto:
            return
        if self.foto.salva(img, vis):
            self.prossima_foto = t + self.salva_foto_ogni

    # ---- salvataggio ----
    def salva(self, forzato=False):
        adesso = time.monotonic()
        if not forzato and adesso < self.prossimo_salvataggio:
            return
        self.prossimo_salvataggio = adesso + 300
        if self.mira_adattiva and abs(self.forza - self._forza_salvata) > 0.03:
            impostazioni.salva_calibrazione(self.base, ["mira", "forza"], round(self.forza, 3))
            self._forza_salvata = self.forza
            self.log("Ho imparato la forza della mira: %.2f" % self.forza)


# ------------------------------------------------------------------ IMPARA GUARDANDO TE
def _nome_tasto_pynput(k):
    """Da un tasto di pynput al nome usato nelle impostazioni (es. 'e', 'f1', 'spazio')."""
    c = getattr(k, "char", None)
    if c:
        return c.lower()
    nome = getattr(k, "name", "") or ""
    return {"space": "spazio", "shift": "shift", "shift_l": "shift", "ctrl_l": "ctrl", "ctrl": "ctrl",
            "alt_l": "alt", "enter": "invio", "esc": "esc", "tab": "tab"}.get(nome, nome)


def _risolvi_nome(tasti, nome):
    n = str(nome).strip().lower()
    visti = set()
    while n in tasti and n not in visti:
        visti.add(n)
        n = str(tasti[n]).strip().lower()
    return n


def impara(base, log=print):
    """Giochi tu: il bot guarda e impara i colori di casse/armi e dove miri."""
    from occhi import Occhi, Schermo
    try:
        from pynput import keyboard, mouse
    except Exception as e:
        print("Non riesco a leggere tastiera e mouse (%s)." % e)
        return
    cfg = impostazioni.carica(base)
    tasti = {str(k).lower(): str(v).lower() for k, v in (cfg.get("tasti") or {}).items()}
    tasto_apri = _risolvi_nome(tasti, "interagisci")
    sch = cfg.get("schermo", {}) or {}
    mirino_f = sch.get("mirino") or [0.5, 0.5]
    ogni = float((cfg.get("apprendimento", {}) or {}).get("foto_in_impara_ogni", 2.0) or 0)

    print("\n" + "=" * 70)
    print("  IMPARA GUARDANDO TE")
    print("=" * 70)
    print("Gioca normalmente. Il bot guarda e impara:")
    print("  - ogni volta che premi '%s' (apri/raccogli) guarda i colori davanti a te" % tasto_apri.upper())
    print("  - quando spari a un nemico guarda dove stai mirando")
    print("  - salva foto con le etichette per addestrare l'IA del tuo gioco")
    print("Apri piu' casse che puoi (almeno 8-10)!   F8 = pausa   F9 = ho finito")
    print("Sto caricando l'occhio universale...")
    occhi = Occhi(cfg, base, log)
    schermo = Schermo(int(sch.get("monitor", 1) or 1), sch.get("zona_cattura"))
    salva_foto = SalvaFoto(os.path.join(base, "foto_per_ia")) if ogni > 0 else None
    eventi = queue.Queue()
    stato = {"pausa": False, "fine": False, "sparo": False}
    conteggio = {}

    def premuto(k):
        if k == keyboard.Key.f8:
            stato["pausa"] = not stato["pausa"]
            print("PAUSA" if stato["pausa"] else "RIPRENDO", flush=True)
            return
        if k == keyboard.Key.f9:
            stato["fine"] = True
            return
        nome = _nome_tasto_pynput(k)
        conteggio[nome] = conteggio.get(nome, 0) + 1
        if nome == tasto_apri:
            eventi.put("apri")

    def click(x, y, pulsante, giu):
        if pulsante == mouse.Button.left:
            stato["sparo"] = bool(giu)

    ascolta_t = keyboard.Listener(on_press=premuto)
    ascolta_m = mouse.Listener(on_click=click)
    for a in (ascolta_t, ascolta_m):
        a.daemon = True
        a.start()
    print("VIA! Torna nel gioco.\n")

    campioni = []          # per ogni pressione: pixel colorati davanti a te
    altezze = []           # dove miri sul nemico (0 = testa, 1 = piedi)
    prossima_foto = 0.0
    prossima_analisi = 0.0
    try:
        while not stato["fine"]:
            time.sleep(0.05)
            if stato["pausa"]:
                continue
            img = schermo.foto()
            H, W = img.shape[:2]
            mx, my = mirino_f[0] * W, mirino_f[1] * H
            while not eventi.empty():
                eventi.get()
                x1, x2 = int(max(0, mx - 0.12 * W)), int(min(W, mx + 0.12 * W))
                y1, y2 = int(max(0, my - 0.05 * H)), int(min(H, my + 0.25 * H))
                hsv = cv2.cvtColor(img[y1:y2, x1:x2], cv2.COLOR_BGR2HSV).reshape(-1, 3)
                colorati = hsv[(hsv[:, 1] > 110) & (hsv[:, 2] > 140)]
                if len(colorati) > 3000:
                    colorati = colorati[np.random.default_rng(len(campioni)).choice(len(colorati), 3000, replace=False)]
                campioni.append(colorati)
                print("  visto! (%d aperture)" % len(campioni), flush=True)
            adesso = time.monotonic()
            if stato["sparo"] and adesso >= prossima_analisi:
                prossima_analisi = adesso + 0.2
                vis = occhi.analizza(img)
                for b in vis.nemici:
                    if b.contiene(mx, my) and b.fonte == "universale":
                        altezze.append((my - b.y) / max(1.0, b.h))
                        break
            if salva_foto is not None and adesso >= prossima_foto:
                prossima_foto = adesso + ogni
                salva_foto.salva(img, occhi.analizza(img))
    except KeyboardInterrupt:
        pass
    finally:
        schermo.chiudi()
        for a in (ascolta_t, ascolta_m):
            try:
                a.stop()
            except Exception:
                pass

    print("\n" + "=" * 70)
    print("  COSA HO IMPARATO")
    print("=" * 70)
    if salva_foto is not None:
        print("Foto etichettate salvate: %d (in foto_per_ia)" % salva_foto.n)
    if conteggio:
        piu_usati = sorted(conteggio.items(), key=lambda kv: -kv[1])[:10]
        print("Tasti che usi di piu': " + ", ".join("%s (%d)" % kv for kv in piu_usati))
    if len(altezze) >= 8:
        a = float(np.median(altezze))
        impostazioni.salva_calibrazione(base, ["mira", "altezza_mira_universale"], round(min(0.9, max(0.0, a)), 3))
        print("Dove miri sui nemici: %.0f%% dall'alto (0%% = testa). Salvato: il bot mirera' come te." % (a * 100))
    else:
        print("Dove miri: troppi pochi spari su nemici per impararlo (%d)." % len(altezze))
    _impara_colori(base, campioni)


def trova_colori_ricorrenti(campioni, minimo_volte=3):
    """Dai pixel visti a ogni apertura, i colori che tornano piu' spesso. -> [(tinta, volte, intervallo)]"""
    if not campioni:
        return []
    istogramma = np.zeros(180)
    for c in campioni:
        if len(c) == 0:
            continue
        h = np.bincount(c[:, 0].astype(np.int64), minlength=180)[:180].astype(float)
        istogramma += h / max(1.0, h.sum())          # ogni apertura conta uguale
    liscio = np.array([istogramma.take(range(i - 3, i + 4), mode="wrap").sum() for i in range(180)])
    risultati = []
    usati = np.zeros(180, bool)
    for _ in range(4):
        candidati = np.where(~usati, liscio, -1)
        picco = int(np.argmax(candidati))
        if candidati[picco] <= 0:
            break
        for d in range(-12, 13):
            usati[(picco + d) % 180] = True
        pixel, volte = [], 0
        for c in campioni:
            if len(c) == 0:
                continue
            dist = np.abs(((c[:, 0].astype(int) - picco + 90) % 180) - 90)
            vicini = c[dist <= 6]
            if len(vicini) >= 30:
                volte += 1
                pixel.append(vicini)
        if volte >= minimo_volte and pixel:
            risultati.append((picco, volte, intervallo_da_pixel(np.concatenate(pixel))))
    return risultati


def _impara_colori(base, campioni):
    if len(campioni) < 3:
        print("Colori: hai aperto troppe poche cose (%d). Riprova aprendo almeno 8 casse." % len(campioni))
        return
    trovati = trova_colori_ricorrenti(campioni, max(3, len(campioni) // 4))
    if not trovati:
        print("Colori: non ho trovato un colore che torna sempre. Usa il menu 'Calibra i colori'.")
        return
    cfg = impostazioni.carica(base)
    print("\nColori che c'erano spesso davanti a te quando aprivi/raccoglievi:")
    scelte = {"c": "cassa", "m": "materiali", "a": "arma"}
    for tinta, volte, intervallo in trovati:
        print("\n  Colore %s (tinta %d): visto in %d aperture su %d" % (nome_colore(tinta), tinta, volte, len(campioni)))
        try:
            r = input("  Cos'e'?  c = casse armi   m = casse materiali   a = armi   INVIO = niente: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return
        cat = scelte.get(r[:1]) if r else None
        if not cat:
            continue
        vecchi = list((cfg.get("colori", {}) or {}).get(cat) or [])
        vecchi.append(intervallo)
        impostazioni.salva_calibrazione(base, ["colori", cat], vecchi)
        cfg.setdefault("colori", {})[cat] = vecchi
        print("  Salvato come colore di: %s" % cat)
    print("\nFatto! Prova il bot con il menu 2 (prova) per vedere se riconosce bene.")
