"""
test_bot.py - Prove automatiche del bot (non servono il gioco ne' la schedina).

Avvio:  python test_bot.py
Simula un "gioco finto": un paesaggio a 360 gradi in cui la visuale gira quando
il bot muove il mouse, con nemici, casse e il personaggio del giocatore.
"""

import importlib.util
import os
import shutil
import sys
import tempfile
import threading
import time
import types
import unittest

import cv2
import numpy as np

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, QUI)

import impostazioni  # noqa: E402
from apprendimento import (Apprendimento, SalvaFoto, intervallo_da_pixel, misura_spostamento,  # noqa: E402
                           trova_colori_ricorrenti)
from cervello import Cervello  # noqa: E402
from istruzioni import (Esecutore, Istruzioni, leggi_azioni, leggi_condizione,  # noqa: E402
                        leggi_istruzioni, leggi_macro)
from mani import CODICI, ManiFinte, TastoSconosciuto, risolvi_grezzo  # noqa: E402
from occhi import (Box, Immagini, Occhi, SchermoFinto, Visione, box_da_maschera, decodifica_yolo,  # noqa: E402
                   decodifica_yolox, leggi_barra, maschera_colori)

ROSSO = (0, 0, 255)
ORO = (0, 200, 255)


def cfg_test(**sopra):
    cfg = impostazioni.unisci(impostazioni.PREDEFINITE, sopra)
    cfg["rilevatore_universale"]["attivo"] = False
    cfg["colori"]["nemico"] = [{"tinta": [170, 8], "saturazione": [170, 255], "luminosita": [150, 255]}]
    return cfg


class Mondo:
    """Gioco finto: paesaggio a 360 gradi (e un po' in su e in giu').
    La visuale segue il mouse di 'mani'. Le y degli oggetti sono quelle con la visuale dritta."""

    def __init__(self, mani, ppp=0.5, larghezza=640, altezza=360, giro_px=2400, seme=1):
        self.mani = mani
        self.ppp = ppp
        self.W, self.H = larghezza, altezza
        self.giro_px = giro_px
        rng = np.random.default_rng(seme)
        rumore = rng.integers(0, 255, (altezza // 2, giro_px // 4, 3), dtype=np.uint8)
        self.panorama = cv2.resize(cv2.GaussianBlur(rumore, (5, 5), 1.5), (giro_px, altezza * 2),
                                   interpolation=cv2.INTER_LINEAR)
        self.panorama = (self.panorama * 0.45).astype(np.uint8)      # scuro e poco colorato
        self.oggetti = []          # (x_panorama, y, w, h, colore)
        self.fissi = []            # (x_schermo, y, w, h, colore): attaccati alla visuale
        self.origine = (0, 0)
        self.foto_fatte = 0

    def x_visuale(self):
        return int(round(self.mani.mosso_x * self.ppp)) % self.giro_px

    def y_visuale(self):
        """Quanto ho guardato in giu' (pixel). Il gioco non lascia guardare oltre un certo punto."""
        return int(max(-self.H / 2, min(self.H / 2, round(self.mani.mosso_y * self.ppp))))

    def foto(self):
        self.foto_fatte += 1
        x0 = self.x_visuale()
        y0 = self.y_visuale()
        idx = (np.arange(self.W) + x0) % self.giro_px
        riga = self.H // 2 + y0
        img = self.panorama[riga:riga + self.H][:, idx].copy()
        for (px, y, w, h, col) in self.oggetti:
            sx = (px - x0) % self.giro_px
            if sx > self.giro_px / 2:
                sx -= self.giro_px
            if -w < sx < self.W:
                cv2.rectangle(img, (int(sx), y - y0), (int(sx + w), y - y0 + h), col, -1)
        for (sx, y, w, h, col) in self.fissi:
            cv2.rectangle(img, (sx, y), (sx + w, y + h), col, -1)
        return img

    def chiudi(self):
        pass


def crea(base, cfg, mondo_args=None, apprendimento=True):
    mani = ManiFinte(cfg["tasti"])
    mondo = Mondo(mani, **(mondo_args or {}))
    occhi = Occhi(cfg, base, print, universale=False)
    stat = {}
    macro, _ = leggi_macro(cfg["macro"], mani.esiste)
    esec = Esecutore(mani, occhi, mondo, cfg, None, print, stat, macro)
    app = Apprendimento(cfg, base, occhi, print) if apprendimento else None
    if app is not None:
        esec.passi_per_giro = app.passi_per_giro
    cerv = Cervello(cfg, mani, occhi, esec, Istruzioni([], occhi), print, app, mondo)
    return mani, mondo, occhi, esec, app, cerv


class ConCartella(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.base, "immagini"))

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)


# ====================================================================== mani
class TestMani(unittest.TestCase):
    def test_nomi_tasti(self):
        self.assertEqual(risolvi_grezzo("w"), ("tasto", 0x1A))
        self.assertEqual(risolvi_grezzo("Spazio"), ("tasto", 0x2C))
        self.assertEqual(risolvi_grezzo("f1"), ("tasto", 0x3A))
        self.assertEqual(risolvi_grezzo("ctrl"), ("tasto", 0xE0))
        self.assertEqual(risolvi_grezzo("mouse_sinistro"), ("mouse", 1))
        self.assertEqual(risolvi_grezzo("rotella_giu"), ("rotella", -1))
        with self.assertRaises(TastoSconosciuto):
            risolvi_grezzo("tastoinventato")

    def test_tasti_stile_fortnite(self):
        cfg = impostazioni.carica(QUI)
        m = ManiFinte(cfg["tasti"])
        self.assertEqual(m.risolvi("costruisci"), ("tasto", CODICI["f1"]))   # costruisci -> muro -> F1
        self.assertEqual(m.risolvi("pavimento"), ("tasto", CODICI["f2"]))
        self.assertEqual(m.risolvi("interagisci"), ("tasto", CODICI["e"]))
        self.assertEqual(m.risolvi("arma_1"), ("tasto", CODICI["2"]))
        self.assertEqual(m.risolvi("cura"), ("tasto", CODICI["6"]))           # cura -> arma_5 -> 6
        self.assertEqual(m.risolvi("spara"), ("mouse", 1))

    def test_mouse_con_virgola(self):
        m = ManiFinte({})
        for _ in range(10):
            m.muovi(0.35, -0.5)
        self.assertEqual((m.mosso_x, m.mosso_y), (3, -5))

    def test_tieni_e_rilascia(self):
        m = ManiFinte({"avanti": "w"})
        m.giu("avanti")
        m.giu("avanti")
        self.assertTrue(m.e_premuto("avanti"))
        self.assertEqual(sum(1 for s in m.storia if s.startswith("giu")), 1)
        m.rilascia_tutto()
        self.assertFalse(m.e_premuto("avanti"))


# ====================================================================== istruzioni
class TestIstruzioni(unittest.TestCase):
    def setUp(self):
        self.m = ManiFinte(impostazioni.carica(QUI)["tasti"])
        self.macro, err = leggi_macro(impostazioni.carica(QUI)["macro"], self.m.esiste)
        self.assertEqual(err, [])

    def test_file_istruzioni_vero(self):
        with open(os.path.join(QUI, "istruzioni.txt"), encoding="utf-8") as f:
            regole, errori = leggi_istruzioni(f.read(), self.m.esiste, self.macro)
        self.assertEqual(errori, [])
        self.assertGreaterEqual(len(regole), 2)
        squadra = regole[0]
        self.assertEqual(squadra.condizioni[0].tipo, "vedi")
        self.assertEqual(squadra.condizioni[0].valore, "squadra_eliminata")
        self.assertEqual([a.tipo for a in squadra.azioni], ["aspetta", "clicca_immagine", "aspetta", "conta"])

    def test_tutte_le_righe_commentate_sono_valide(self):
        """Anche gli esempi spenti con # devono funzionare se l'utente li accende."""
        with open(os.path.join(QUI, "istruzioni.txt"), encoding="utf-8") as f:
            righe = [r[2:] for r in f if r.startswith("# QUANDO")]
        regole, errori = leggi_istruzioni("\n".join(righe), self.m.esiste, self.macro)
        self.assertEqual(errori, [])
        self.assertEqual(len(regole), len(righe))

    def test_frasi(self):
        a = leggi_azioni("premi e poi clicca", self.m.esiste, self.macro)
        self.assertEqual((a[0].tipo, a[0].valori[0]), ("premi", "e"))
        self.assertEqual(a[1].tipo, "clicca")
        a = leggi_azioni("premi x e poi tieni e 2 secondi, premi esc 2 volte", self.m.esiste, self.macro)
        self.assertEqual([(x.tipo, x.valori) for x in a],
                         [("premi", ("x", 1)), ("tieni", ("e", 2.0)), ("premi", ("esc", 2))])
        a = leggi_azioni("muro, scatola, costruisci, girati, gira -45", self.m.esiste, self.macro)
        self.assertEqual([x.tipo for x in a], ["macro", "macro", "premi", "gira", "gira"])
        self.assertEqual(a[4].valori[0], -45.0)
        self.assertEqual(leggi_condizione("ogni 2 minuti").valore, 120.0)
        self.assertEqual(leggi_condizione("vedi una cassa dei materiali").valore, "materiali")
        self.assertEqual(leggi_condizione("non vedi gioca").negata, True)

    def test_errori_chiari(self):
        regole, errori = leggi_istruzioni("QUANDO vedi x FAI premi tastoinventato\nciao\n", self.m.esiste, self.macro)
        self.assertEqual(regole, [])
        self.assertEqual(len(errori), 2)
        self.assertIn("riga 1", errori[0])

    def test_controllo_regole(self):
        class OcchiFinti:
            visibili = set()

            def vedi(self, nome, soglia=None):
                return (1, 1, 1) if nome in self.visibili else None
        occhi = OcchiFinti()
        testo = "QUANDO inizio FAI premi m\nQUANDO vedi fine FAI premi esc\nogni 10 secondi fai premi m"
        regole, err = leggi_istruzioni(testo, self.m.esiste, self.macro)
        ist = Istruzioni(regole, occhi)
        vis = Visione(100, 100)
        t = ist.inizio
        self.assertEqual(ist.controlla(vis, {}, t).riga, 1)
        self.assertIsNone(ist.controlla(vis, {}, t + 0.1))           # inizio solo una volta
        occhi.visibili.add("fine")
        self.assertEqual(ist.controlla(vis, {}, t + 0.2).riga, 2)
        self.assertIsNone(ist.controlla(vis, {}, t + 1.0))           # attesa tra ripetizioni
        occhi.visibili.clear()
        self.assertEqual(ist.controlla(vis, {}, t + 10.5).riga, 3)


# ====================================================================== occhi
class TestOcchi(ConCartella):
    def test_colori_e_rosso_che_fa_il_giro(self):
        img = np.full((200, 300, 3), 40, np.uint8)
        cv2.rectangle(img, (10, 10), (40, 60), (0, 0, 255), -1)      # rosso (tinta 0)
        cv2.rectangle(img, (100, 10), (130, 60), (60, 0, 230), -1)   # rosso-viola (tinta ~170)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        m = maschera_colori(hsv, [{"tinta": [165, 8], "saturazione": [150, 255], "luminosita": [100, 255]}])
        self.assertEqual(len(box_da_maschera(m, 20)), 2)

    def test_intervallo_imparato_dai_pixel(self):
        img = np.zeros((10, 10, 3), np.uint8)
        img[:5] = (0, 0, 250)
        img[5:] = (40, 0, 220)
        r = intervallo_da_pixel(cv2.cvtColor(img, cv2.COLOR_BGR2HSV))
        self.assertGreater(r["tinta"][0], r["tinta"][1])       # il rosso "fa il giro"

    def test_barra_vita(self):
        img = np.zeros((100, 400, 3), np.uint8)
        img[40:50, 100:200] = (0, 255, 0)           # meta' barra piena (verde)
        v = leggi_barra(img, [0.25, 0.4, 0.5, 0.1], [{"tinta": [50, 70], "saturazione": [100, 255],
                                                      "luminosita": [100, 255]}])
        self.assertAlmostEqual(v, 50, delta=2)

    def test_immagini(self):
        rng = np.random.default_rng(3)
        schermo = (rng.random((400, 600, 3)) * 255).astype(np.uint8)
        pezzo = schermo[100:140, 300:380].copy()
        ok, dati = cv2.imencode(".png", pezzo)
        dati.tofile(os.path.join(self.base, "immagini", "pulsante.png"))
        im = Immagini(os.path.join(self.base, "immagini"), 0.5, 0.8)
        trovato = im.trova(cv2.resize(schermo, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA), "pulsante")
        self.assertIsNotNone(trovato)
        self.assertAlmostEqual(trovato[0], 340, delta=3)
        self.assertAlmostEqual(trovato[1], 120, delta=3)
        self.assertIsNone(im.trova(np.zeros((200, 300, 3), np.uint8), "pulsante"))

    def test_decodifica_yolo_v8_e_v5(self):
        v8 = np.zeros((1, 4 + 3, 10), np.float32)
        v8[0, :4, 2] = [320, 320, 64, 128]
        v8[0, 4 + 1, 2] = 0.9                       # classe 1 = cassa
        b = decodifica_yolo(v8, 0.4, 0.5, 0, 0, lambda i: ["nemico", "cassa", "arma"][i])
        self.assertEqual(len(b), 1)
        self.assertEqual(b[0].categoria, "cassa")
        self.assertAlmostEqual(b[0].x, (320 - 32) / 0.5)
        v5 = np.zeros((1, 10, 5 + 3), np.float32)
        v5[0, 3] = [100, 100, 20, 40, 0.9, 0.95, 0, 0]
        b = decodifica_yolo(v5, 0.4, 1.0, 0, 0, lambda i: ["nemico", "cassa", "arma"][i])
        self.assertEqual(b[0].categoria, "nemico")

    def test_decodifica_yolox(self):
        uscita = np.zeros((1, 3549, 85), np.float32)
        i = 20 * 52 + 10                             # cella (10, 20) della griglia da 8 pixel
        uscita[0, i, :4] = [0.5, 0.5, np.log(4), np.log(4)]
        uscita[0, i, 4] = 0.9
        uscita[0, i, 5] = 0.9                        # classe 0 = persona
        b = decodifica_yolox(uscita, 416, 0.5, 0.5)
        self.assertEqual(len(b), 1)
        x, y, w, h, p = b[0]
        self.assertAlmostEqual(x, (84 - 16) / 0.5)
        self.assertAlmostEqual(w, 64.0)
        self.assertAlmostEqual(p, 0.81, places=3)

    def test_occhio_universale_se_presente(self):
        p = os.path.join(QUI, "modelli", "yolox_nano.onnx")
        if not os.path.isfile(p):
            self.skipTest("modello non scaricato")
        from occhi import RilevatoreUniversale
        r = RilevatoreUniversale(p)
        self.assertEqual(r.rileva(np.full((360, 640, 3), 90, np.uint8)), [])

    def test_compagni_e_zone(self):
        cfg = cfg_test()
        cfg["colori"]["alleato"] = [{"tinta": [100, 130], "saturazione": [150, 255], "luminosita": [150, 255]}]
        occhi = Occhi(cfg, self.base, print, universale=False)
        img = np.full((360, 640, 3), 40, np.uint8)
        cv2.rectangle(img, (100, 150), (130, 220), ROSSO, -1)     # nemico
        cv2.rectangle(img, (400, 150), (430, 220), ROSSO, -1)     # compagno...
        cv2.rectangle(img, (395, 125), (435, 135), (255, 0, 0), -1)   # ...col nome blu sopra
        cv2.rectangle(img, (300, 280), (330, 350), ROSSO, -1)     # nella zona imparata
        occhi.zone_apprese.append([0.45, 0.75, 0.1, 0.25])
        vis = occhi.analizza(img)
        self.assertEqual(len(vis.nemici), 1)
        self.assertAlmostEqual(vis.nemici[0].cx, 115, delta=3)


# ====================================================================== apprendimento
class TestApprendimento(ConCartella):
    def test_misura_spostamento(self):
        mani = ManiFinte({})
        mondo = Mondo(mani, ppp=1.0)
        a = mondo.foto()
        mani.muovi(40, 0)
        b = mondo.foto()
        dx, dy, risposta, _ = misura_spostamento(a, b)
        self.assertAlmostEqual(dx, -40, delta=1)       # la visuale va a destra, lo schermo a sinistra
        self.assertGreater(risposta, 0.3)

    def test_impara_sensibilita_e_giro_da_solo(self):
        cfg = cfg_test()
        mani, mondo, occhi, esec, app, cerv = crea(self.base, cfg, {"ppp": 0.37, "giro_px": 2400})
        self.assertTrue(app.serve_calibrare(time.monotonic()))
        for _ in range(4):
            if not app.serve_calibrare(time.monotonic()):
                break
            app.prossimo_tentativo = 0
            app.calibra(mani, mondo, esec)
        self.assertTrue(app.ppp_noto)
        self.assertTrue(app.giro_noto)
        self.assertAlmostEqual(app.ppp, 0.37, delta=0.02)
        self.assertAlmostEqual(app.passi_per_giro, 2400 / 0.37, delta=2400 / 0.37 * 0.01)
        salvato = impostazioni.leggi_calibrazione(self.base)["mira"]
        self.assertAlmostEqual(salvato["pixel_per_passo"], 0.37, delta=0.02)
        # la volta dopo lo sa gia'
        self.assertFalse(Apprendimento(impostazioni.unisci(cfg, impostazioni.leggi_calibrazione(self.base)),
                                       self.base, occhi).serve_calibrare(time.monotonic()))

    def test_capisce_che_il_suo_personaggio_non_e_un_nemico(self):
        cfg = cfg_test(mira={"pixel_per_passo": 0.5, "passi_per_giro": 4800})
        impostazioni.salva_calibrazione(self.base, ["mira", "pixel_per_passo"], 0.5)
        impostazioni.salva_calibrazione(self.base, ["mira", "passi_per_giro"], 4800)
        mani, mondo, occhi, esec, app, cerv = crea(self.base, cfg, {"ppp": 0.5})
        mondo.fissi.append((250, 220, 50, 120, ROSSO))      # il mio personaggio: sempre li', sotto il mirino
        t = time.monotonic()
        for i in range(30):
            img = mondo.foto()
            cerv.passo(occhi.analizza(img), img, t + i * 0.03)
            if occhi.zone_apprese:
                break
        self.assertEqual(len(occhi.zone_apprese), 1)
        self.assertIn("zone_apprese", impostazioni.leggi_calibrazione(self.base)["schermo"])
        img = mondo.foto()
        self.assertEqual(occhi.analizza(img).nemici, [])     # ora lo ignora

    def test_colori_ricorrenti(self):
        rng = np.random.default_rng(0)
        campioni = []
        for _ in range(10):
            oro = np.stack([rng.integers(24, 29, 300), rng.integers(180, 250, 300), rng.integers(200, 255, 300)], 1)
            caso = np.stack([rng.integers(0, 180, 300), rng.integers(120, 255, 300), rng.integers(150, 255, 300)], 1)
            campioni.append(np.concatenate([oro, caso]).astype(np.uint8))
        trovati = trova_colori_ricorrenti(campioni, 3)
        self.assertTrue(trovati)
        tinta, volte, intervallo = trovati[0]
        self.assertTrue(22 <= tinta <= 30)
        self.assertEqual(volte, 10)
        self.assertLessEqual(intervallo["tinta"][0], 24)
        self.assertGreaterEqual(intervallo["tinta"][1], 28)

    def test_salva_foto_etichettate(self):
        sf = SalvaFoto(os.path.join(self.base, "foto"))
        vis = Visione(640, 360)
        vis.oggetti["cassa"].append(Box(100, 100, 64, 36, 1.0, "cassa"))
        self.assertTrue(sf.salva(np.zeros((360, 640, 3), np.uint8), vis))
        etichette = os.listdir(os.path.join(self.base, "foto", "labels"))
        with open(os.path.join(self.base, "foto", "labels", etichette[0])) as f:
            riga = f.read().split()
        self.assertEqual(riga[0], "1")
        self.assertAlmostEqual(float(riga[1]), 132 / 640, places=4)
        self.assertTrue(os.path.isfile(os.path.join(self.base, "foto", "dataset.yaml")))


# ====================================================================== cervello
class TestCervello(ConCartella):
    def setUp(self):
        super().setUp()
        impostazioni.salva_calibrazione(self.base, ["mira", "pixel_per_passo"], 0.5)
        impostazioni.salva_calibrazione(self.base, ["mira", "passi_per_giro"], 4800)
        self.cfg = cfg_test(mira={"pixel_per_passo": 0.5, "passi_per_giro": 4800})

    def test_mira_e_spara(self):
        mani, mondo, occhi, esec, app, cerv = crea(self.base, self.cfg, {"ppp": 0.5})
        mondo.oggetti.append((500, 120, 24, 60, ROSSO))      # nemico a destra del mirino (320, 180)
        t = time.monotonic()
        sparato = False
        for i in range(40):
            img = mondo.foto()
            cerv.passo(occhi.analizza(img), img, t + i * 0.03)
            sparato = sparato or mani.e_premuto("spara")
        img = mondo.foto()
        b = occhi.analizza(img).nemici[0]
        punto = b.y + 0.2 * b.h
        self.assertAlmostEqual(b.cx, 320, delta=6)             # mirino sul nemico
        self.assertAlmostEqual(punto, 180, delta=6)
        self.assertTrue(sparato)
        self.assertTrue(mani.e_premuto("spara"))

    def test_mira_adattiva_si_corregge(self):
        """Il bot crede che la sensibilita' sia la meta' di quella vera: impara a non esagerare."""
        mani, mondo, occhi, esec, app, cerv = crea(self.base, self.cfg, {"ppp": 1.0})
        app.forza = 0.9
        mondo.oggetti.append((560, 120, 24, 60, ROSSO))
        t = time.monotonic()
        for i in range(60):
            img = mondo.foto()
            cerv.passo(occhi.analizza(img), img, t + i * 0.03)
        self.assertLess(app.forza, 0.75)
        b = occhi.analizza(mondo.foto()).nemici[0]
        self.assertAlmostEqual(b.cx, 320, delta=8)

    def test_apre_le_casse(self):
        mani, mondo, occhi, esec, app, cerv = crea(self.base, self.cfg, {"ppp": 0.5})
        cassa = (300, 300, 60, 50, ORO)                       # cassa vicina, in basso al centro
        mondo.oggetti.append(cassa)
        vecchio_foto = mondo.foto

        def foto_che_apre():
            # quando il bot tiene premuto E la cassa si apre (sparisce la luce dorata)
            if any(s == "giu tasto 0x08" for s in mani.storia) and cassa in mondo.oggetti:
                mondo.oggetti.remove(cassa)
            return vecchio_foto()
        mondo.foto = foto_che_apre
        esec.schermo = mondo
        t = time.monotonic()
        for i in range(10):
            img = mondo.foto()
            cerv.passo(occhi.analizza(img), img, t + i * 0.05)
            if cerv.statistiche["casse"]:
                break
        self.assertEqual(cerv.statistiche["casse"], 1)
        self.assertEqual(cerv.statistiche["casse_tentate"], 1)

    def test_casse_prima_delle_armi_e_poi_materiali(self):
        cfg = cfg_test(mira={"pixel_per_passo": 0.5, "passi_per_giro": 4800})
        cfg["colori"]["materiali"] = [{"tinta": [55, 65], "saturazione": [150, 255], "luminosita": [150, 255]}]
        cfg["colori"]["arma"] = [{"tinta": [115, 125], "saturazione": [150, 255], "luminosita": [150, 255]}]
        mani, mondo, occhi, esec, app, cerv = crea(self.base, cfg, {"ppp": 0.5})
        mondo.oggetti += [(150, 200, 40, 30, (255, 0, 0)), (330, 200, 40, 30, (0, 255, 0)),
                          (500, 200, 40, 30, ORO)]
        img = mondo.foto()
        cerv.passo(occhi.analizza(img), img)
        self.assertGreater(mani.mosso_x, 0)                 # va verso la cassa d'oro (a destra), non l'arma

    def test_istruzione_squadra_eliminata(self):
        rng = np.random.default_rng(5)
        schermata = (rng.random((360, 640, 3)) * 255).astype(np.uint8)
        for nome, (y, x) in (("squadra_eliminata", (50, 200)), ("gioca_ancora", (280, 260))):
            ok, d = cv2.imencode(".png", schermata[y:y + 40, x:x + 120])
            d.tofile(os.path.join(self.base, "immagini", nome + ".png"))
        mani, mondo, occhi, esec, app, cerv = crea(self.base, self.cfg)
        schermo = SchermoFinto([schermata])
        esec.schermo = schermo
        regole, err = leggi_istruzioni("QUANDO vedi squadra_eliminata FAI aspetta 0.1, clicca gioca_ancora, conta partita",
                                       mani.esiste, esec.macro, occhi.immagini.esiste)
        cerv.istruzioni = Istruzioni(regole, occhi)
        scritta = cerv.passo(occhi.analizza(schermata), schermata)
        self.assertEqual(scritta, "istruzione riga 1")
        self.assertIn("giu mouse 1", mani.storia)
        self.assertEqual(cerv.statistiche["partite"], 1)

    def test_se_bloccato_salta_e_gira(self):
        mani, mondo, occhi, esec, app, cerv = crea(self.base, self.cfg, {"ppp": 0.5})
        mondo.foto = lambda: np.full((360, 640, 3), 50, np.uint8)   # lo schermo non cambia mai
        t = time.monotonic()
        cerv.prossimo_guardarsi = t + 999
        for i in range(12):
            img = mondo.foto()
            cerv.passo(occhi.analizza(img), img, t + i * 0.45)
        self.assertIn("giu tasto 0x%02X" % CODICI["spazio"], mani.storia)


# ====================================================================== obiettivo e pulsanti imparati
class TestObiettivo(ConCartella):
    def test_capisce_le_frasi(self):
        import obiettivo
        casi = {
            "aprire 50 casse a partita": ("casse_n", 50),
            "Apri 30 casse per partita!": ("casse_n", 30),
            "aprire più casse possibili": ("casse", 0),
            "vincere e aprire piu' casse possibili": ("vincere", 0),
            "eliminare più nemici possibili": ("nemici", 0),
            "uccidere tutti": ("nemici", 0),
            "sopravvivere": ("sopravvivere", 0),
            "vincere": ("vincere", 0),
            "": ("vincere", 0),
        }
        for frase, (tipo, n) in casi.items():
            ob = obiettivo.capisci(frase)
            self.assertIsNotNone(ob, frase)
            self.assertEqual((ob.tipo, ob.casse), (tipo, n), frase)
        self.assertIsNone(obiettivo.capisci("fai la spesa"))

    def test_file_obiettivo(self):
        import obiettivo
        self.assertEqual(obiettivo.leggi(self.base, lambda *_: None).tipo, "vincere")      # manca: predefinito
        obiettivo.scrivi(self.base, "aprire 7 casse a partita")
        ob = obiettivo.leggi(self.base)
        self.assertEqual((ob.tipo, ob.casse), ("casse_n", 7))
        with open(os.path.join(QUI, "obiettivo.txt"), encoding="utf-8") as f:
            self.assertIsNotNone(obiettivo.capisci(" ".join(r for r in f if not r.startswith("#"))))

    def _cervello(self, frase, oggetti):
        import obiettivo
        impostazioni.salva_calibrazione(self.base, ["mira", "pixel_per_passo"], 0.5)
        impostazioni.salva_calibrazione(self.base, ["mira", "passi_per_giro"], 4800)
        cfg = cfg_test(mira={"pixel_per_passo": 0.5, "passi_per_giro": 4800})
        mani, mondo, occhi, esec, app, cerv = crea(self.base, cfg, {"ppp": 0.5})
        cerv.obiettivo = obiettivo.capisci(frase)
        mondo.oggetti += oggetti
        return mani, mondo, occhi, cerv

    def test_con_le_casse_ignora_i_nemici_lontani(self):
        lontano = (100, 160, 10, 25, ROSSO)          # nemico piccolo (lontano) a sinistra
        cassa = (500, 260, 50, 40, ORO)              # cassa a destra
        mani, mondo, occhi, cerv = self._cervello("aprire 50 casse a partita", [lontano, cassa])
        img = mondo.foto()
        scritta = cerv.passo(occhi.analizza(img), img)
        self.assertTrue(scritta.startswith("vado verso cassa"), scritta)
        self.assertGreater(mani.mosso_x, 0)                     # gira verso la cassa, non verso il nemico
        # arrivato a 50 casse in questa partita: ora combatte
        cerv.statistiche["casse_partita"] = 50
        img = mondo.foto()
        self.assertTrue(cerv.passo(occhi.analizza(img), img).startswith("combatto"))

    def test_nemico_vicino_si_combatte_anche_con_le_casse(self):
        vicino = (300, 100, 60, 200, ROSSO)
        mani, mondo, occhi, cerv = self._cervello("aprire piu' casse possibili", [vicino, (500, 260, 50, 40, ORO)])
        img = mondo.foto()
        self.assertTrue(cerv.passo(occhi.analizza(img), img).startswith("combatto"))

    def test_obiettivo_nemici_insegue(self):
        medio = (330, 120, 20, 60, ROSSO)            # nemico a media distanza (alto 1/6 dello schermo)
        mani, mondo, occhi, cerv = self._cervello("eliminare piu' nemici possibili", [medio])
        img = mondo.foto()
        cerv.passo(occhi.analizza(img), img)
        self.assertTrue(mani.e_premuto("avanti"))
        mani2, mondo2, occhi2, cerv2 = self._cervello("vincere", [medio])
        img = mondo2.foto()
        cerv2.passo(occhi2.analizza(img), img)
        self.assertFalse(mani2.e_premuto("avanti"))

    def test_le_casse_si_contano_per_partita(self):
        mani, mondo, occhi, cerv = self._cervello("aprire 50 casse a partita", [])
        cerv.statistiche["casse_partita"] = 12
        cerv.esecutore.esegui(leggi_azioni("conta partita", mani.esiste, {}))
        self.assertEqual(cerv.statistiche["casse_partita"], 0)
        self.assertEqual(cerv.statistiche["partite"], 1)


class TestImparaPulsanti(ConCartella):
    def test_impara_i_pulsanti_che_clicchi(self):
        from apprendimento import ImparaPulsanti, aggiungi_regole_pulsanti
        rng = np.random.default_rng(9)
        menu = (rng.random((360, 640, 3)) * 60).astype(np.uint8)
        cv2.rectangle(menu, (260, 280), (380, 310), (40, 160, 40), -1)
        cv2.putText(menu, "GIOCA", (285, 303), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        con_cursore = menu.copy()
        cv2.circle(con_cursore, (322, 296), 4, (255, 255, 255), -1)       # il cursore sopra al pulsante
        p = ImparaPulsanti(os.path.join(self.base, "immagini"))
        v = p.click(menu, con_cursore, 320, 295)
        self.assertEqual(v["nome"], "pulsante_1")
        self.assertIs(p.click(menu, con_cursore, 321, 294), v)               # stesso pulsante: non lo duplica
        self.assertIs(p.click(menu, con_cursore, 334, 297), v)               # anche cliccato un po' piu' in la'
        self.assertEqual(v["volte"], 3)
        cv2.rectangle(menu, (40, 40), (160, 70), (40, 40, 160), -1)
        cv2.putText(menu, "ESCI", (70, 63), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        altro = p.click(menu, menu, 100, 55)
        self.assertEqual(altro["nome"], "pulsante_2")                        # un pulsante diverso: nuovo
        p.visti.remove(altro)
        nomi = p.salva([v])
        aggiungi_regole_pulsanti(self.base, nomi)
        aggiungi_regole_pulsanti(self.base, nomi)                            # la seconda volta non la riscrive
        with open(os.path.join(self.base, "istruzioni.txt"), encoding="utf-8") as f:
            testo = f.read()
        self.assertEqual(testo.count("QUANDO vedi pulsante_1 FAI aspetta 1, clicca pulsante_1"), 1)
        # e il bot lo trova davvero sullo schermo, e lo clicca
        cfg = cfg_test()
        mani, mondo, occhi, esec, app, cerv = crea(self.base, cfg)
        esec.schermo = SchermoFinto([menu])
        regole, err = leggi_istruzioni(testo, mani.esiste, esec.macro, occhi.immagini.esiste)
        self.assertEqual(err, [])
        cerv.istruzioni = Istruzioni(regole, occhi)
        cerv.statistiche["casse_partita"] = 9
        self.assertEqual(cerv.passo(occhi.analizza(menu), menu), "istruzione riga %d" % regole[0].riga)
        self.assertIn("giu mouse 1", mani.storia)
        self.assertEqual(cerv.statistiche["casse_partita"], 0)               # menu = nuova partita


# ====================================================================== schedina (Pico)
class FintoSeriale:
    def __init__(self, dati):
        self.dati = bytearray(dati)
        self.scritto = b""
        self.timeout = None

    @property
    def in_waiting(self):
        return len(self.dati)

    def read(self, n):
        pezzo = bytes(self.dati[:n])
        del self.dati[:n]
        return pezzo

    def write(self, b):
        self.scritto += bytes(b)


class FineProva(BaseException):
    pass


class TestSchedinaPico(unittest.TestCase):
    """Fa girare il vero code.py della schedina con tastiera, mouse e USB finti."""

    def esegui_code_py(self, comandi, secondi_dopo=0.0):
        rapporti = []

        class Dispositivo:
            def __init__(self, usage):
                self.usage_page, self.usage = 0x01, usage

            def send_report(self, r):
                rapporti.append((self.usage, bytes(r)))

        seriale = FintoSeriale(comandi)
        orologio = {"t": 100.0, "fine": None}
        finto_time = types.ModuleType("time")
        finto_time.monotonic = lambda: orologio["t"]

        def dormi(s):
            orologio["t"] += max(s, 0.01)
            if not seriale.dati:
                if orologio["fine"] is None:
                    orologio["fine"] = orologio["t"] + secondi_dopo
                if orologio["t"] >= orologio["fine"]:
                    raise FineProva()
        finto_time.sleep = dormi
        moduli = {
            "time": finto_time,
            "usb_hid": types.SimpleNamespace(devices=[Dispositivo(0x06), Dispositivo(0x02)]),
            "usb_cdc": types.SimpleNamespace(data=seriale),
        }
        vecchi = {k: sys.modules.get(k) for k in moduli}
        sys.modules.update(moduli)
        try:
            spec = importlib.util.spec_from_file_location("code_pico", os.path.join(QUI, "pico", "code.py"))
            with self.assertRaises(FineProva):
                spec.loader.exec_module(importlib.util.module_from_spec(spec))
        finally:
            for k, v in vecchi.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v
        return rapporti, seriale.scritto

    def test_comandi(self):
        rapporti, risposta = self.esegui_code_py(b"P\nKD 4\nKD 225\nM 300 -10\nBD 1\nKU 4\nR\n")
        self.assertIn(b"OK BOT", risposta)
        tastiera = [r for u, r in rapporti if u == 0x06]
        mouse = [r for u, r in rapporti if u == 0x02]
        self.assertEqual(tastiera[0], bytes([0, 0, 4, 0, 0, 0, 0, 0]))          # A giu
        self.assertEqual(tastiera[1], bytes([2, 0, 4, 0, 0, 0, 0, 0]))          # + shift
        self.assertEqual(mouse[:3], [bytes([0, 127, 246, 0]), bytes([0, 127, 0, 0]), bytes([0, 46, 0, 0])])
        self.assertEqual(mouse[3], bytes([1, 0, 0, 0]))                         # click giu
        self.assertEqual(tastiera[2], bytes([2, 0, 0, 0, 0, 0, 0, 0]))          # A su
        self.assertEqual(tastiera[-1], bytes(8))                                 # R: tutto rilasciato
        self.assertEqual(mouse[-1], bytes(4))

    def test_sicurezza_rilascia_se_il_pc_tace(self):
        rapporti, _ = self.esegui_code_py(b"KD 26\nBD 1\n", secondi_dopo=1.5)
        self.assertEqual([r for u, r in rapporti if u == 0x06][-1], bytes(8))   # W rilasciato da solo
        self.assertEqual([r for u, r in rapporti if u == 0x02][-1], bytes(4))


class TestSchedinaSeriale(unittest.TestCase):
    """Il programma sul PC trova la schedina e le manda i comandi (porta seriale finta)."""

    def test_collegamento(self):
        if sys.platform == "win32":
            self.skipTest("serve una porta finta (pty), solo Linux/Mac")
        import pty
        from mani import ManiSchedina
        padrone, schiavo = pty.openpty()
        nome = os.ttyname(schiavo)
        import termios
        import tty
        tty.setraw(schiavo)
        attr = termios.tcgetattr(schiavo)
        attr[3] &= ~termios.ECHO
        termios.tcsetattr(schiavo, termios.TCSANOW, attr)
        ricevuto = []
        fine = threading.Event()

        def finta_pico():
            buf = b""
            while not fine.is_set():
                try:
                    buf += os.read(padrone, 1024)
                except OSError:
                    return
                while b"\n" in buf:
                    riga, buf = buf.split(b"\n", 1)
                    if riga == b"P":
                        os.write(padrone, b"OK BOT 1\n")
                    elif riga:
                        ricevuto.append(riga.decode())
        th = threading.Thread(target=finta_pico, daemon=True)
        th.start()
        m = ManiSchedina({"costruisci": "f1"}, print, nome)
        m.premi("costruisci", 0.01)
        m.muovi(10, -3)
        time.sleep(1.0)
        m.chiudi()
        time.sleep(0.3)
        fine.set()
        os.close(padrone)
        comandi = [r for r in ricevuto if r != "H"]
        self.assertIn("H", ricevuto)                 # il "ci sono ancora" arriva da solo
        self.assertEqual(comandi, ["KD 58", "KU 58", "M 10 -3", "R"])


# ====================================================================== file unico per la schedina
def leggi_fat12(img):
    """Lettore FAT12 indipendente (per controllare la chiavetta creata): -> {nome lungo: contenuto}."""
    import struct
    bps, spc, ris, nfat, nroot, tot, _, fatsz = struct.unpack_from("<HBHBHHBH", img, 11)
    assert img[510:512] == b"\x55\xAA" and bps == 512 and spc == 1
    fat = img[ris * bps:(ris + fatsz) * bps]
    root_inizio = (ris + nfat * fatsz) * bps
    dati_inizio = root_inizio + nroot * 32

    def prossimo(c):
        o = c + c // 2
        v = fat[o] | (fat[o + 1] << 8)
        return (v >> 4) if c % 2 else (v & 0xFFF)
    file, lfn = {}, []
    for i in range(nroot):
        e = img[root_inizio + i * 32:root_inizio + (i + 1) * 32]
        if e[0] == 0:
            break
        if e[11] == 0x0F:
            pezzo = e[1:11] + e[14:26] + e[28:32]
            lfn.insert(0, pezzo.decode("utf-16-le").split("\x00")[0].replace("￿", ""))
            continue
        if e[11] & 0x08:
            lfn = []
            continue
        base, est = e[0:8].decode().rstrip(), e[8:11].decode().rstrip()
        if e[12] & 0x08:
            base = base.lower()
        if e[12] & 0x10:
            est = est.lower()
        nome = "".join(lfn) or (base + ("." + est if est else ""))
        lfn = []
        primo, dim = struct.unpack_from("<HI", e, 26)
        dati, c = b"", primo
        while dim and 2 <= c < 0xFF8:
            dati += img[dati_inizio + (c - 2) * bps:dati_inizio + (c - 1) * bps]
            c = prossimo(c)
        file[nome] = dati[:dim]
    return file


class TestFileUnicoSchedina(unittest.TestCase):
    def test_chiavetta_e_uf2(self):
        sys.path.insert(0, os.path.join(QUI, "pico"))
        import crea_uf2
        file = crea_uf2.file_del_bot(42, "https://esempio/BotSparatutto.zip")
        nomi = [n for n, _ in file]
        self.assertEqual(nomi, ["AVVIA IL BOT.cmd", "LEGGIMI.txt", "boot.py", "code.py", "installa.ps1"])
        img = crea_uf2.crea_fat12(file + [("un nome lungo esattamente13.x", b"y" * 1500)])
        self.assertEqual(len(img), 2048 * 512)
        letti = leggi_fat12(img)
        for nome, contenuto in file:
            self.assertEqual(letti[nome], contenuto)
        self.assertEqual(letti["un nome lungo esattamente13.x"], b"y" * 1500)
        with open(os.path.join(QUI, "pico", "code.py"), "rb") as f:
            self.assertEqual(letti["code.py"], f.read())
        self.assertIn(b"$Versione = 42", letti["installa.ps1"])
        self.assertIn(b"https://esempio/BotSparatutto.zip", letti["installa.ps1"])
        self.assertIn(b"\r\n", letti["AVVIA IL BOT.cmd"])

        # UF2: CircuitPython finto (2 blocchi) + chiavetta a 0x10100000
        finto = crea_uf2.scrivi_uf2([(0x10000000, b"\x01" * 256), (0x10000100, b"\x02" * 256)])
        uf2 = crea_uf2.uf2_con_chiavetta(finto, img)
        blocchi = crea_uf2.leggi_uf2(uf2)
        self.assertEqual(len(blocchi), 2 + 4096)
        self.assertEqual(len(uf2), 512 * len(blocchi))
        self.assertEqual(blocchi[2][0], 0x10100000)
        self.assertEqual(blocchi[-1][0], 0x10100000 + 1024 * 1024 - 256)
        ricostruita = b"".join(c for a, c in blocchi[2:])
        self.assertEqual(ricostruita, img)
        import struct
        numeri = [struct.unpack_from("<II", uf2, i * 512 + 20) for i in range(len(blocchi))]
        self.assertEqual(numeri[0], (0, len(blocchi)))
        self.assertEqual(numeri[-1], (len(blocchi) - 1, len(blocchi)))
        with self.assertRaises(ValueError):          # un firmware che invade la chiavetta viene rifiutato
            crea_uf2.uf2_con_chiavetta(crea_uf2.scrivi_uf2([(0x10100000, b"\x00" * 256)]), img)

    def test_schedina_della_play(self):
        """La vecchia schedina (gioca a caso + click col dado) in un solo file: file copiati tali e quali."""
        sys.path.insert(0, os.path.join(QUI, "pico"))
        import crea_uf2
        radice = os.path.dirname(QUI)
        voci = ["code.py=%s" % os.path.join(radice, "schedina_pico", "code.py"),
                "impostazioni.txt=%s" % os.path.join(radice, "schedina_pico", "impostazioni.txt")]
        letti = leggi_fat12(crea_uf2.crea_fat12(crea_uf2.file_da_argomenti(voci)))
        for nome in ("code.py", "impostazioni.txt"):
            with open(os.path.join(radice, "schedina_pico", nome), "rb") as f:
                self.assertEqual(letti[nome], f.read())
        with self.assertRaises(ValueError):
            crea_uf2.file_da_argomenti(["senza_uguale"])


# ====================================================================== autotest dell'exe
class TestAutotest(unittest.TestCase):
    def test_autotest(self):
        import bot
        self.assertEqual(bot.autotest(), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
