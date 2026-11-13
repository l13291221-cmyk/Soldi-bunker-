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

    def __init__(self, cartella, massimo=0, larghezza_massima=1280):
        self.cartella = cartella
        self.massimo = int(massimo or 0)                  # 0 = senza limite
        self.larghezza_massima = int(larghezza_massima or 0)
        self.immagini = os.path.join(cartella, "images")
        self.etichette = os.path.join(cartella, "labels")
        os.makedirs(self.immagini, exist_ok=True)
        os.makedirs(self.etichette, exist_ok=True)
        dataset = os.path.join(cartella, "dataset.yaml")
        if not os.path.isfile(dataset):
            with open(dataset, "w", encoding="utf-8") as f:
                f.write("# Dataset per addestrare l'IA del tuo gioco (vedi LEGGIMI_GUIDA.txt, parte F)\n")
                f.write("train: images\nval: images\nnames:\n")
                for i, n in enumerate(CLASSI_DATASET):
                    f.write("  %d: %s\n" % (i, n))
        self.n = 0
        self.gia_salvate = sum(1 for f in os.listdir(self.immagini) if f.lower().endswith(".jpg"))

    @property
    def pieno(self):
        return self.massimo > 0 and self.gia_salvate >= self.massimo

    def salva(self, img, vis, anche_vuote=False):
        if self.pieno:
            return False
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
        self.gia_salvate += 1
        if self.larghezza_massima and W > self.larghezza_massima:     # piu' piccola: basta per addestrare
            scala = self.larghezza_massima / float(W)
            img = cv2.resize(img, (self.larghezza_massima, int(round(H * scala))), interpolation=cv2.INTER_AREA)
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
        # con PS Remote Play l'immagine arriva in ritardo: aspetto di piu' prima di misurare
        self.attesa_misura = float(ap.get("attesa_misura", 0.45) or 0.45)
        self.tentativi_massimi = int(ap.get("tentativi_sensibilita", 6) or 6)
        self.fallimenti_giro = 0
        self._att = None                  # bersaglio che sto controllando (attaccato alla visuale?)
        self.salva_foto_ogni = float(ap.get("salva_foto_ogni", 0) or 0)
        self.foto = (SalvaFoto(os.path.join(base, "foto_per_ia"), ap.get("foto_massime", 3000))
                     if self.salva_foto_ogni > 0 else None)
        self._avvisato_pieno = False
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
                self.prossimo_tentativo = time.monotonic() + 6.0
                if self.fallimenti >= self.tentativi_massimi:
                    # non riesco a misurarla: tengo la stima e NON riprovo piu' (prima riprovava
                    # all'infinito e intanto il bot stava fermo a muovere la visuale)
                    self.ppp_noto = True
                    self.giro_noto = True
                    self.log("Non riesco a misurare la sensibilita': uso la stima (%.3f) e gioco" % self.ppp)
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
            esecutore.dormi(self.attesa_misura)
            dopo = schermo.foto()
            mani.muovi(-passi, 0)
            esecutore.dormi(self.attesa_misura)
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
        if self.foto.pieno:
            if not self._avvisato_pieno:
                self._avvisato_pieno = True
                self.log("Foto per l'IA: ne ho %d, bastano! Ora puoi addestrare l'IA (guida, parte F)."
                         % self.foto.gia_salvate)
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


# ------------------------------------------------------------------ pulsanti dei menu
def somiglianza(a, b):
    """Quanto si somigliano due pezzetti di schermo (da -1 a 1)."""
    if a is None or b is None:
        return -1.0
    if a.shape != b.shape:
        b = cv2.resize(b, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_AREA)
    ga = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY).astype(np.float32)
    gb = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY).astype(np.float32)
    if ga.std() < 2 or gb.std() < 2:          # pezzi tutti di un colore: confronto i colori medi
        return 1.0 - min(1.0, float(np.abs(a.astype(np.float32).mean((0, 1)) - b.astype(np.float32).mean((0, 1))).max()) / 40.0)
    return float(cv2.matchTemplate(ga, gb, cv2.TM_CCOEFF_NORMED)[0][0])


def somiglianza_spostata(a, b, margine=0.3):
    """Come somiglianza, ma accetta che uno dei due pezzi sia un po' spostato
    (hai cliccato lo stesso pulsante in un punto un po' diverso)."""
    if a is None or b is None:
        return -1.0
    if a.shape != b.shape:
        b = cv2.resize(b, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_AREA)
    h, w = a.shape[:2]
    mh, mw = int(h * margine), int(w * margine)
    ga = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY).astype(np.float32)
    gb = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY).astype(np.float32)
    ca, cb = ga[mh:h - mh, mw:w - mw], gb[mh:h - mh, mw:w - mw]
    if mh < 1 or mw < 1 or ca.std() < 2 or cb.std() < 2:
        return somiglianza(a, b)
    return float(max(cv2.matchTemplate(ga, cb, cv2.TM_CCOEFF_NORMED).max(),
                     cv2.matchTemplate(gb, ca, cv2.TM_CCOEFF_NORMED).max()))


class ImparaPulsanti:
    """Ogni click su un pulsante dei menu: salva il pulsante. Poi il bot lo clicca da solo quando lo vede."""

    def __init__(self, cartella_immagini, larghezza=0.12, altezza=0.06):
        self.cartella = cartella_immagini
        self.larghezza = larghezza
        self.altezza = altezza
        self.visti = []           # [{"nome", "img", "volte"}]

    def ritaglia(self, img, x, y):
        if img is None:
            return None
        H, W = img.shape[:2]
        w, h = max(16, int(W * self.larghezza)), max(12, int(H * self.altezza))
        x1 = int(min(max(0, x - w / 2), W - w))
        y1 = int(min(max(0, y - h / 2), H - h))
        return img[y1:y1 + h, x1:x1 + w].copy()

    def _nome_libero(self):
        usati = {v["nome"] for v in self.visti}
        for n in range(1, 1000):
            nome = "pulsante_%d" % n
            if nome not in usati and not os.path.isfile(os.path.join(self.cartella, nome + ".png")):
                return nome
        raise RuntimeError("troppi pulsanti")

    def click(self, img_prima, img_ora, x, y):
        """img_ora = schermo subito prima del click; img_prima = mezzo secondo/un secondo prima
        (di solito senza il cursore sopra il pulsante: e' come lo vedra' il bot)."""
        ora = self.ritaglia(img_ora, x, y)
        prima = self.ritaglia(img_prima, x, y)
        pezzo = prima if prima is not None and somiglianza(prima, ora) >= 0.5 else ora
        if pezzo is None:
            return None
        for v in self.visti:
            if somiglianza_spostata(v["img"], pezzo) >= 0.85:
                v["volte"] += 1
                return v
        v = {"nome": self._nome_libero(), "img": pezzo, "volte": 1}
        self.visti.append(v)
        return v

    def salva(self, scelti):
        os.makedirs(self.cartella, exist_ok=True)
        nomi = []
        for v in scelti:
            ok, dati = cv2.imencode(".png", v["img"])
            if ok:
                dati.tofile(os.path.join(self.cartella, v["nome"] + ".png"))
                nomi.append(v["nome"])
        return nomi


def aggiungi_regole_pulsanti(base, nomi):
    """Scrive in istruzioni.txt: QUANDO vedi pulsante_N FAI aspetta 1, clicca pulsante_N."""
    if not nomi:
        return
    p = os.path.join(base, "istruzioni.txt")
    vecchio = ""
    if os.path.isfile(p):
        with open(p, "r", encoding="utf-8-sig") as f:
            vecchio = f.read()
    righe = ["", "# Imparato guardandoti (%s): quando vede questi pulsanti li clicca da solo" % time.strftime("%d/%m/%Y")]
    for nome in nomi:
        regola = "QUANDO vedi %s FAI aspetta 1, clicca %s" % (nome, nome)
        if regola not in vecchio:
            righe.append(regola)
    if len(righe) > 2:
        with open(p, "a", encoding="utf-8") as f:
            if vecchio and not vecchio.endswith("\n"):
                f.write("\n")
            f.write("\n".join(righe) + "\n")


def _chiedi_pulsanti(pulsanti):
    """Mostra ogni pulsante visto e chiede se cliccarlo da solo. -> lista dei pulsanti scelti."""
    scelti = []
    for v in sorted(pulsanti.visti, key=lambda v: -v["volte"]):
        grande = cv2.resize(v["img"], None, fx=3, fy=3, interpolation=cv2.INTER_NEAREST)
        tela = np.full((grande.shape[0] + 70, max(grande.shape[1], 640), 3), 30, np.uint8)
        tela[70:70 + grande.shape[0], :grande.shape[1]] = grande
        cv2.putText(tela, "Lo clicco da solo quando lo vedo?  S = si   N = no", (10, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(tela, "(l'hai cliccato %d volte)" % v["volte"], (10, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (200, 200, 200), 1)
        nome = "Pulsante visto"
        cv2.imshow(nome, tela)
        try:
            cv2.setWindowProperty(nome, cv2.WND_PROP_TOPMOST, 1)
        except Exception:
            pass
        while True:
            k = cv2.waitKey(100) & 0xFF
            if k in (ord("s"), ord("S")):
                scelti.append(v)
                break
            if k in (ord("n"), ord("N"), 27):
                break
        cv2.destroyWindow(nome)
    return scelti


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


def _chiedi_dove_giochi():
    print("\nDOVE GIOCHI?")
    print("  1) sul computer (il gioco e' aperto qui)")
    print("  2) sulla Play: la guardi con PS Remote Play e giochi con tastiera e mouse del portatile")
    while True:
        try:
            r = input("Scrivi 1 o 2 e premi INVIO: ").strip()
        except (EOFError, KeyboardInterrupt):
            return False
        if r in ("1", "2"):
            return r == "2"


def impara(base, log=print, sulla_play=None):
    """Giochi tu: il bot guarda e impara i colori di casse/armi e dove miri.
    sulla_play=True: il gioco e' sulla Play e tu giochi con tastiera e mouse del portatile
    (il telecomando li passa alla schedina attaccata alla Play)."""
    from occhi import Occhi, Schermo
    try:
        from pynput import keyboard, mouse
    except Exception as e:
        print("Non riesco a leggere tastiera e mouse (%s)." % e)
        return
    if sulla_play is None:
        sulla_play = _chiedi_dove_giochi()
    cfg = impostazioni.carica(base)
    mani_play = None
    if sulla_play:
        # prima di tutto la schedina sulla Play (tramite il ponte): se non c'e' lo dico subito
        from mani import ManiSchedina
        mani_play = ManiSchedina(cfg.get("tasti"), log, (cfg.get("comandi", {}) or {}).get("porta", "auto"))
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
    if not sulla_play:
        print("  - quando clicchi un pulsante nei menu (es. 'Gioca ancora') se lo ricorda")
    print("  - salva foto con le etichette per addestrare l'IA del tuo gioco")
    if sulla_play:
        print("SULLA PLAY: giochi con la tastiera e il mouse del PORTATILE guardando Remote Play.")
        print("Il programma li passa alla Play attraverso la schedina. Mentre giochi la freccia")
        print("del PC resta ferma: il mouse lo usa la Play. Con F9 torna tutto normale.")
        print("(Sulla Play non so dove clicchi nei menu: i pulsanti salvali col menu 6.)")
        print("Gioca una partita intera e apri piu' casse che puoi (almeno 8-10).")
        print("F8 = pausa (continui a giocare, ma non impara)   F9 = ho finito")
    else:
        print("Gioca una partita intera, apri piu' casse che puoi (almeno 8-10) e poi")
        print("passa alla partita successiva cliccando i pulsanti.   F8 = pausa   F9 = ho finito")
    print("Sto caricando l'occhio universale...")
    occhi = Occhi(cfg, base, log)
    schermo = Schermo(int(sch.get("monitor", 1) or 1), sch.get("zona_cattura"))
    salva_foto = SalvaFoto(os.path.join(base, "foto_per_ia")) if ogni > 0 else None
    from collections import deque

    from istruzioni import cursore_visibile
    eventi = queue.Queue()
    stato = {"pausa": False, "fine": False, "sparo": False, "giu": None}
    conteggio = {}
    pulsanti = ImparaPulsanti(os.path.join(base, "immagini"))
    foto_recenti = deque()        # (tempo, foto): gli ultimi 2 secondi, una ogni 0.2 s
    origine = schermo.origine
    tele = None
    if sulla_play:
        from telecomando import Telecomando
        attesa = int(float(sch.get("secondi_prima_di_partire", 30) or 30))
        print("\nClicca sulla finestra di PS Remote Play (a schermo intero): tra %d secondi" % attesa)
        print("il mouse e la tastiera del portatile passano alla Play.")
        for n in range(attesa, 0, -1):
            print("  %d..." % n, flush=True)
            time.sleep(1)
        # la freccia del PC resta ferma al centro: ogni movimento del mouse va alla Play
        area = schermo.area
        centro = (area["left"] + area["width"] // 2, area["top"] + area["height"] // 2)
        try:
            freccia = mouse.Controller()
            freccia.position = centro
            centro = freccia.position
        except Exception:
            pass
        sens = float((cfg.get("telecomando", {}) or {}).get("sensibilita_mouse", 1.0) or 1.0)
        tele = Telecomando(mani_play, centro, sensibilita=sens)

    def premuto(k):
        if k == keyboard.Key.f8:
            stato["pausa"] = not stato["pausa"]
            print("PAUSA" if stato["pausa"] else "RIPRENDO", flush=True)
            return
        if k == keyboard.Key.f9:
            stato["fine"] = True
            return
        if tele is not None:
            tele.tasto_giu(k)
        nome = _nome_tasto_pynput(k)
        conteggio[nome] = conteggio.get(nome, 0) + 1
        if nome == tasto_apri:
            eventi.put("apri")

    def rilasciato(k):
        if tele is not None:
            tele.tasto_su(k)

    def click(x, y, pulsante, giu):
        if tele is not None:
            tele.click(x, y, pulsante, giu)
        if pulsante != mouse.Button.left:
            return
        stato["sparo"] = bool(giu)
        if tele is not None:
            return                 # sulla Play non so dove clicchi nei menu: niente pulsanti
        adesso = time.monotonic()
        if giu:
            stato["giu"] = (adesso, x, y, cursore_visibile())
        elif stato["giu"] is not None:
            t0, x0, y0, visibile = stato["giu"]
            stato["giu"] = None
            if adesso - t0 < 0.6:                      # un click breve, non una raffica
                eventi.put(("click", t0, x0 - origine[0], y0 - origine[1], visibile))

    ascolta_t = keyboard.Listener(on_press=premuto, on_release=rilasciato)
    if tele is not None:
        # suppress: il mouse non muove la freccia del PC e i click non vanno al PC, ma alla Play
        ascolta_m = mouse.Listener(on_click=click, on_move=tele.mosso, on_scroll=tele.rotella, suppress=True)
    else:
        ascolta_m = mouse.Listener(on_click=click)
    for a in (ascolta_t, ascolta_m):
        a.daemon = True
        a.start()
    print("VIA! Gioca pure.\n" if tele is not None else "VIA! Torna nel gioco.\n")

    campioni = []          # per ogni pressione: pixel colorati davanti a te
    altezze = []           # dove miri sul nemico (0 = testa, 1 = piedi)
    prossima_foto = 0.0
    prossima_analisi = 0.0
    try:
        while not stato["fine"]:
            time.sleep(0.05)
            if tele is not None and tele.errore is not None:
                print("\nPROBLEMA con la schedina: %s" % tele.errore)
                break
            if stato["pausa"]:
                continue
            img = schermo.foto()
            H, W = img.shape[:2]
            mx, my = mirino_f[0] * W, mirino_f[1] * H
            adesso = time.monotonic()
            if not foto_recenti or adesso - foto_recenti[-1][0] >= 0.2:
                foto_recenti.append((adesso, img))
                while foto_recenti and adesso - foto_recenti[0][0] > 2.0:
                    foto_recenti.popleft()
            while not eventi.empty():
                evento = eventi.get()
                if evento != "apri":
                    _, t0, cx, cy, visibile = evento
                    lontano_dal_mirino = abs(cx - mx) > 0.08 * W or abs(cy - my) > 0.08 * H
                    nei_menu = visibile if visibile is not None else lontano_dal_mirino
                    if nei_menu and 0 <= cx < W and 0 <= cy < H:
                        ora_ = [f for tf, f in foto_recenti if tf <= t0] or [img]
                        prima_ = [f for tf, f in foto_recenti if tf <= t0 - 0.8]
                        v = pulsanti.click(prima_[-1] if prima_ else None, ora_[-1], cx, cy)
                        if v is not None and v["volte"] == 1:
                            print("  pulsante visto! (%d finora)" % len(pulsanti.visti), flush=True)
                    continue
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
        for a in (ascolta_m, ascolta_t):        # prima il mouse: torna subito al PC
            try:
                a.stop()
            except Exception:
                pass
        if tele is not None:
            tele.ferma()
        if mani_play is not None:
            mani_play.chiudi()
            from telecomando import svuota_tastiera_console
            svuota_tastiera_console()
        schermo.chiudi()

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
        a = min(0.45, max(0.08, a))       # sempre tra testa e petto, anche se tu miri piu' in basso
        impostazioni.salva_calibrazione(base, ["mira", "altezza_mira_universale"], round(a, 3))
        print("Dove mirare sui nemici: %.0f%% dall'alto (0%% = testa). Salvato." % (a * 100))
    else:
        print("Dove miri: troppi pochi spari su nemici per impararlo (%d)." % len(altezze))
    _impara_colori(base, campioni)
    if pulsanti.visti:
        print("\nHo visto %d pulsanti che hai cliccato: guarda la finestra e rispondi S o N." % len(pulsanti.visti))
        nomi = pulsanti.salva(_chiedi_pulsanti(pulsanti))
        aggiungi_regole_pulsanti(base, nomi)
        if nomi:
            print("Fatto: quando vedra' %s li clicchera' da solo (scritto in istruzioni.txt)." % ", ".join(nomi))
    else:
        print("\nPulsanti: non ne ho visti. Per passare da solo alla partita successiva clicca i pulsanti")
        print("mentre sei in 'Impara guardando me', oppure salvali col menu 6.")
    import obiettivo
    obiettivo.chiedi(base)


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
