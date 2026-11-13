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
    # le prove vecchie guardano un fotogramma alla volta e usano tutto lo schermo
    if "raccolta" not in sopra or "conferma_fotogrammi" not in sopra["raccolta"]:
        cfg["raccolta"]["conferma_fotogrammi"] = 1
    if "schermo" not in sopra or "zone_interfaccia_fortnite" not in sopra["schermo"]:
        cfg["schermo"]["zone_interfaccia_fortnite"] = False
    if "apprendimento" not in sopra or "attesa_misura" not in sopra["apprendimento"]:
        cfg["apprendimento"]["attesa_misura"] = 0.05        # il mondo finto risponde subito
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

    def test_foto_senza_il_tuo_personaggio_e_le_icone(self):
        """Nelle foto vere il bot salvava il TUO personaggio come nemico e le icone in alto come casse."""
        sf = SalvaFoto(os.path.join(self.base, "foto"))
        vis = Visione(1280, 720)
        vis.oggetti["nemico"].append(Box(560, 380, 110, 330, 0.9, "nemico"))   # tu: piedi in fondo, al centro
        vis.oggetti["cassa"].append(Box(480, 45, 20, 18, 1.0, "cassa"))        # icona gialla nella bussola
        self.assertFalse(sf.salva(np.zeros((720, 1280, 3), np.uint8), vis))   # niente di buono: non la salva
        vis.oggetti["nemico"].append(Box(900, 250, 40, 110, 0.9, "nemico"))    # un nemico vero, lontano
        vis.oggetti["cassa"].append(Box(300, 420, 60, 45, 1.0, "cassa"))       # una cassa vera
        self.assertTrue(sf.salva(np.zeros((720, 1280, 3), np.uint8), vis))
        cartella = os.path.join(self.base, "foto", "labels")
        with open(os.path.join(cartella, os.listdir(cartella)[0])) as f:
            righe = [r.split() for r in f.read().splitlines()]
        self.assertEqual(sorted(r[0] for r in righe), ["0", "1"])
        self.assertAlmostEqual(float(righe[0][1]), 920 / 1280, places=4)


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

    def test_si_accorge_presto_e_la_seconda_volta_gira_dall_altra_parte(self):
        mani, mondo, occhi, esec, app, cerv = crea(self.base, self.cfg, {"ppp": 0.5})
        mondo.foto = lambda: np.full((360, 640, 3), 50, np.uint8)   # contro un muro: non cambia niente
        t = time.monotonic()
        cerv.prossimo_guardarsi = t + 999
        cerv.deriva = 0.0
        cerv.prossima_deriva = t + 999
        giri = []
        salto = "giu tasto 0x%02X" % CODICI["spazio"]
        primo = None
        for i in range(80):
            prima_x, salti = mani.mosso_x, mani.storia.count(salto)
            img = mondo.foto()
            cerv.passo(occhi.analizza(img), img, t + i * 0.1)
            if mani.storia.count(salto) > salti:
                giri.append(mani.mosso_x - prima_x)
                if primo is None:
                    primo = i * 0.1
        self.assertIsNotNone(primo)
        self.assertLess(primo, 1.5)                                  # prima ci metteva 2 secondi
        self.assertIn("giu tasto 0x%02X" % CODICI["1"], mani.storia)   # la prima volta: piccone
        self.assertIn("giu mouse 1", mani.storia)                        # ...e sfonda
        giri = [g for g in giri if g]
        self.assertGreaterEqual(len(giri), 2)
        self.assertLess(giri[0] * giri[1], 0)                       # poi gira, e la volta dopo dall'altra parte


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


class TestCasseVere(ConCartella):
    """Niente casse inventate: piu' fotogrammi, forma giusta, fuori dall'interfaccia."""

    def test_conferma_in_piu_fotogrammi(self):
        from cervello import Conferma
        c = Conferma(volte=3)
        b = Box(300, 200, 30, 20, categoria="cassa")
        self.assertEqual(c.filtra([b], 1.0, (0, 0), 640), [])          # vista una volta: no
        self.assertEqual(c.filtra([b], 1.05, (0, 0), 640), [])         # due volte: no
        self.assertEqual(len(c.filtra([b], 1.10, (0, 0), 640)), 1)     # tre volte: si'
        # un riflesso che compare un attimo in un altro posto non conta
        self.assertEqual(c.filtra([Box(50, 50, 30, 20)], 1.15, (0, 0), 640), [])
        # se giro la visuale a destra di 40 pixel la cassa sullo schermo va a sinistra: e' la stessa
        c2 = Conferma(volte=3)
        for i in range(3):
            visti = c2.filtra([Box(300 - 40 * i, 200, 30, 20)], 2.0 + i * 0.05, (40 if i else 0, 0), 640)
        self.assertEqual(len(visti), 1)
        # dopo un po' che non la vedo si ricomincia a contare
        self.assertEqual(c.filtra([b], 5.0, (0, 0), 640), [])

    def test_occhio_del_gioco_si_carica_da_solo(self):
        import occhi as modulo
        vecchio = modulo.RilevatoreIA
        caricati = []
        modulo.RilevatoreIA = lambda percorso, *a, **k: caricati.append(percorso) or "ia"
        try:
            os.makedirs(os.path.join(self.base, "modelli"), exist_ok=True)
            Occhi(cfg_test(), self.base, print, universale=False)
            self.assertEqual(caricati, [])                                   # non c'e': niente
            open(os.path.join(self.base, "modelli", "gioco.onnx"), "wb").close()
            o = Occhi(cfg_test(), self.base, print, universale=False)
            self.assertEqual(o.ia, "ia")
            self.assertTrue(caricati[0].endswith(os.path.join("modelli", "gioco.onnx")))
        finally:
            modulo.RilevatoreIA = vecchio

    def test_forma_e_interfaccia(self):
        cfg = cfg_test(schermo={"zone_interfaccia_fortnite": True})
        occhi = Occhi(cfg, self.base, print, universale=False)
        img = np.full((360, 640, 3), 40, np.uint8)
        cv2.rectangle(img, (300, 200), (340, 230), ORO, -1)              # cassa vera
        cv2.rectangle(img, (0, 290), (640, 300), ORO, -1)                # striscia lunghissima (sabbia)
        cv2.rectangle(img, (560, 40), (590, 60), ORO, -1)                # nella minimappa
        cv2.rectangle(img, (100, 60), (330, 180), ORO, -1)               # enorme (cielo dorato)
        casse = occhi.analizza(img).casse
        self.assertEqual(len(casse), 1)
        self.assertAlmostEqual(casse[0].cx, 320, delta=4)

    def test_il_cervello_aspetta_la_conferma(self):
        cfg = cfg_test(raccolta={"conferma_fotogrammi": 3}, mira={"pixel_per_passo": 0.5, "passi_per_giro": 4800})
        mani, mondo, occhi, esec, app, cerv = crea(self.base, cfg, {"ppp": 0.5}, apprendimento=False)
        mondo.oggetti.append((500, 260, 50, 40, ORO))
        t = time.monotonic()
        scritte = []
        for i in range(3):
            img = mondo.foto()
            scritte.append(cerv.passo(occhi.analizza(img), img, t + i * 0.05))
        self.assertFalse(scritte[0].startswith("vado verso cassa"), scritte)
        self.assertTrue(scritte[2].startswith("vado verso cassa"), scritte)

    def test_dopo_la_cassa_raccoglie_e_prende_l_arma(self):
        cfg = cfg_test(raccolta={"tempo_apertura_cassa": 0.06}, mira={"pixel_per_passo": 0.5, "passi_per_giro": 4800})
        mani, mondo, occhi, esec, app, cerv = crea(self.base, cfg, {"ppp": 0.5}, apprendimento=False)
        mondo.oggetti.append((300, 250, 60, 60, ORO))
        mondo_foto = mondo.foto

        def foto_senza_cassa():          # dopo aver premuto E la cassa e' aperta (sparita)
            if mani.storia.count("giu tasto 0x%02X" % CODICI["e"]):
                mondo.oggetti.clear()
            return mondo_foto()
        mondo.foto = foto_senza_cassa
        esec.foto_fresca = foto_senza_cassa
        img = mondo_foto()
        self.assertEqual(cerv.passo(occhi.analizza(img), img), "apro cassa")
        self.assertEqual(cerv.statistiche["casse"], 1)
        self.assertGreaterEqual(mani.storia.count("giu tasto 0x%02X" % CODICI["e"]), 4)   # raccoglie il bottino
        self.assertIn("giu tasto 0x%02X" % CODICI["2"], mani.storia)                      # prende l'arma

    def test_cassa_che_non_si_apre_la_lascia_stare(self):
        cfg = cfg_test(raccolta={"tempo_apertura_cassa": 0.06, "tentativi_per_cassa": 2},
                       mira={"pixel_per_passo": 0.5, "passi_per_giro": 4800})
        mani, mondo, occhi, esec, app, cerv = crea(self.base, cfg, {"ppp": 0.5}, apprendimento=False)
        mondo.oggetti.append((300, 250, 60, 60, ORO))     # davanti e vicina, ma non si apre mai
        scritte = []
        for i in range(2):
            img = mondo.foto()
            scritte.append(cerv.passo(occhi.analizza(img), img))
        self.assertEqual(scritte[0], "apro cassa")
        self.assertEqual(scritte[1], "lascio stare cassa")
        self.assertEqual(cerv.statistiche["casse"], 0)
        self.assertEqual(len(occhi.zone_temporanee), 1)              # per un po' quel punto si ignora


class TestIA(ConCartella):
    """L'IA che guarda: risposte, richieste, cambio di IA se una non va, menu 'Collega le IA'."""

    def test_capisce_le_risposte(self):
        import ia
        c = ia.leggi_risposta('{"phase": "bus", "chest": "left", "wall_ahead": true, "storm_near": false,'
                              ' "safe_direction": "unknown", "enemy": false}')
        self.assertEqual((c.fase, c.cassa, c.muro, c.tempesta), ("bus", "left", True, False))
        c = ia.leggi_risposta('Ecco:\n```json\n{"phase": "playing", "chest": "none", "storm_near": "true",'
                              ' "safe_direction": "right"}\n```')
        self.assertEqual((c.fase, c.cassa, c.tempesta, c.direzione), ("playing", "none", True, "right"))
        c = ia.leggi_risposta("{'phase': 'falling', 'chest': 'center'}")             # apici singoli
        self.assertEqual((c.fase, c.cassa), ("falling", "center"))
        c = ia.leggi_risposta("phase: menu, chest: none, wall_ahead: false")         # IA piccole
        self.assertEqual(c.fase, "menu")
        c = ia.leggi_risposta('{"phase": "boh", "chest": "sopra"}')                   # valori strani
        self.assertEqual((c.fase, c.cassa), ("unknown", "none"))
        self.assertIsNone(ia.leggi_risposta("non so cosa dire"))
        self.assertIsNone(ia.leggi_risposta(""))

    def test_richieste(self):
        import json as js

        import ia
        f = dict(ia.FORNITORI["ollama"], nome="ollama")
        url, intest, corpo = ia.richiesta(f, "QUJD")
        d = js.loads(corpo)
        self.assertEqual(url, "http://localhost:11434/api/chat")
        self.assertEqual(d["messages"][0]["images"], ["QUJD"])
        self.assertNotIn("Authorization", intest)
        f = dict(ia.FORNITORI["gemini"], nome="gemini", chiave="segreta")
        url, intest, corpo = ia.richiesta(f, "QUJD")
        d = js.loads(corpo)
        self.assertEqual(intest["Authorization"], "Bearer segreta")
        self.assertEqual(d["messages"][0]["content"][1]["image_url"]["url"], "data:image/jpeg;base64,QUJD")
        self.assertEqual(ia.testo_della_risposta(f, {"choices": [{"message": {"content": "ciao"}}]}), "ciao")
        self.assertEqual(ia.testo_della_risposta(f, {"choices": [{"message": {"content": [{"text": "a"}]}}]}), "a")
        self.assertEqual(ia.testo_della_risposta(dict(ia.FORNITORI["ollama"]), {"message": {"content": "x"}}), "x")
        self.assertTrue(ia.jpeg_base64(np.zeros((720, 1280, 3), np.uint8)))

    def test_quali_ia_sono_pronte(self):
        import ia
        pronte = ia.fornitori_da_cfg({"fornitori": ["ollama", "gemini", "groq", "personale"],
                                      "chiavi": {"groq": "k"}, "modelli": {"ollama": "llava"},
                                      "personale": {"url": "http://x/v1/chat/completions", "modello": "m"}})
        self.assertEqual([f["nome"] for f in pronte], ["ollama", "groq", "personale"])   # gemini senza chiave: no
        self.assertEqual(pronte[0]["modello"], "llava")
        self.assertEqual(pronte[1]["chiave"], "k")

    def test_se_una_ia_non_va_passa_alla_prossima(self):
        import ia
        chiamate = []

        def invia(url, intest, corpo, attesa):
            chiamate.append(url)
            if "localhost" in url:
                raise RuntimeError("troppe richieste (429)")
            return {"choices": [{"message": {"content": '{"phase": "playing", "chest": "right"}'}}]}
        cfg = {"ia": {"attiva": True, "fornitori": ["ollama", "personale"],
                      "personale": {"url": "https://esempio/v1/chat/completions", "modello": "m"}}}
        cervello_lento = ia.IA(cfg, lambda *_: None, invia)
        img = np.zeros((360, 640, 3), np.uint8)
        c = cervello_lento.chiedi(img, adesso=100.0)
        self.assertEqual((c.fornitore, c.cassa, c.numero), ("personale", "right", 1))
        c = cervello_lento.chiedi(img, adesso=110.0)        # ollama riposa (429): non la richiama
        self.assertEqual(sum("localhost" in u for u in chiamate), 1)
        self.assertEqual(c.numero, 2)
        self.assertIsNotNone(cervello_lento.consiglio(adesso=110.0))
        self.assertIsNone(cervello_lento.consiglio(adesso=110.0 + 60))               # troppo vecchio

    def test_openrouter_sceglie_un_modello_gratis_che_vede(self):
        import ia
        dati = {"data": [
            {"id": "a/testo:free", "architecture": {"input_modalities": ["text"]}},
            {"id": "b/vede-a-pagamento", "architecture": {"input_modalities": ["text", "image"]},
             "pricing": {"prompt": "0.001", "completion": "0.002"}},
            {"id": "c/vede:free", "architecture": {"input_modalities": ["text", "image"]}}]}
        self.assertEqual(ia.scegli_modello_openrouter("k", lambda: dati), "c/vede:free")

    def test_menu_collega_e_ia_yaml(self):
        import builtins

        import ia
        vecchio_input, vecchio_invia, vecchio_pronto = builtins.input, ia.invia_http, ia.ollama_pronto
        risposte = {"GEMINI": "chiave-gemini"}

        def finto_input(domanda=""):
            for nome, valore in risposte.items():
                if domanda.startswith(nome):
                    return valore
            return ""

        def finto_invia(url, intest, corpo, attesa):
            if "localhost" in url:
                return {"message": {"content": '{"phase": "menu", "chest": "none"}'}}
            if "groq" in url:
                raise RuntimeError("chiave sbagliata (401)")
            return {"choices": [{"message": {"content": '{"phase": "playing", "chest": "none"}'}}]}
        risposte["GROQ"] = "chiave-sbagliata"
        try:
            builtins.input = finto_input
            ia.invia_http = finto_invia
            ia.ollama_pronto = lambda: "qwen2.5vl:3b"          # Ollama c'e' gia' sul computer
            funzionano = ia.collega(self.base, impostazioni.carica(self.base), print,
                                    np.zeros((360, 640, 3), np.uint8))
        finally:
            builtins.input, ia.invia_http, ia.ollama_pronto = vecchio_input, vecchio_invia, vecchio_pronto
        self.assertEqual(funzionano, ["ollama", "gemini"])                 # groq no: chiave sbagliata
        cfg = impostazioni.carica(self.base)                       # ia.yaml entra nelle impostazioni
        self.assertTrue(cfg["ia"]["attiva"])
        self.assertEqual(cfg["ia"]["fornitori"], ["ollama", "gemini"])
        self.assertEqual(cfg["ia"]["chiavi"]["gemini"], "chiave-gemini")
        self.assertEqual(cfg["ia"]["modelli"]["ollama"], "qwen2.5vl:3b")
        cfg["ia"]["auto_ollama"] = False
        self.assertTrue(ia.IA(cfg).attiva)

    def test_collega_ollama_da_sola(self):
        import ia
        vecchio = ia.ollama_pronto
        try:
            ia.ollama_pronto = lambda: "qwen2.5vl:3b"
            cervello_lento = ia.IA({"ia": {"attiva": False}}, lambda *_: None)
            self.assertTrue(cervello_lento.attiva)
            self.assertEqual(cervello_lento.fornitori[0]["modello"], "qwen2.5vl:3b")
            ia.ollama_pronto = lambda: None                    # non c'e': resta spenta
            self.assertFalse(ia.IA({"ia": {"attiva": False}}, lambda *_: None).attiva)
        finally:
            ia.ollama_pronto = vecchio

    def test_ollama_sceglie_un_modello_che_vede(self):
        import ia
        vecchio = ia.ollama_modelli
        try:
            ia.ollama_modelli = lambda attesa=1.5: ["llama3:8b", "gemma3:4b", "qwen2.5vl:3b"]
            self.assertEqual(ia.ollama_pronto(), "qwen2.5vl:3b")             # il preferito
            ia.ollama_modelli = lambda attesa=1.5: ["llama3:8b"]
            self.assertIsNone(ia.ollama_pronto())                            # nessuno che vede
            ia.ollama_modelli = lambda attesa=1.5: None
            self.assertIsNone(ia.ollama_pronto())                            # Ollama spenta
        finally:
            ia.ollama_modelli = vecchio


class TestGeminiEConoscenza(ConCartella):
    """Gemini con l'account Google, fortnite.txt alle IA, l'IA che studia le foto."""

    def test_fortnite_txt_e_alle_ia_online(self):
        import json as js

        import ia
        self.assertEqual(ia.leggi_conoscenza(self.base), "")                  # senza file: niente
        conoscenza = ia.leggi_conoscenza(QUI)                                  # il file vero del bot
        for parola in ("CTRL", "ACCOVACCIATI", "FURGONE DEL RIAVVIO", "TEMPESTA", "CASSA"):
            self.assertIn(parola, conoscenza)
        f = dict(ia.FORNITORI["gemini"], nome="gemini", chiave="k")
        d = js.loads(ia.richiesta(f, "QUJD", conoscenza="sa tutto")[2])
        self.assertEqual(d["messages"][0]["role"], "system")
        self.assertIn("sa tutto", d["messages"][0]["content"])
        self.assertEqual(d["messages"][1]["content"][1]["image_url"]["url"], "data:image/jpeg;base64,QUJD")
        d = js.loads(ia.richiesta(dict(ia.FORNITORI["ollama"], nome="ollama"), "QUJD", conoscenza="x")[2])
        self.assertEqual(len(d["messages"]), 1)                                # Ollama sul PC: no (lenta)
        mandati = []

        def invia(url, intest, corpo, attesa):
            mandati.append(js.loads(corpo))
            return {"choices": [{"message": {"content": '{"phase": "playing", "chest": "left"}'}}]}
        cfg = {"ia": {"attiva": True, "fornitori": ["gemini"], "chiavi": {"gemini": "k"}}}
        ia.IA(cfg, lambda *_: None, invia, conoscenza=conoscenza).chiedi(np.zeros((360, 640, 3), np.uint8))
        self.assertIn("FURGONE DEL RIAVVIO", mandati[0]["messages"][0]["content"])

    def test_collega_gemini_con_l_account_google(self):
        import ia
        aperte = []
        foto = np.zeros((360, 640, 3), np.uint8)

        def invia(url, intest, corpo, attesa):
            self.assertEqual(intest["Authorization"], "Bearer AIza-chiave")
            return {"choices": [{"message": {"content": '{"phase": "menu", "chest": "none"}'}}]}
        cfg = impostazioni.carica(self.base)
        self.assertTrue(ia.serve_chiedere_gemini(cfg))
        # email o password al posto della chiave: non le salva
        self.assertFalse(ia.collega_gemini(self.base, cfg, print, foto, aperte.append,
                                           lambda _="": "io@gmail.com", invia))
        self.assertFalse(os.path.isfile(os.path.join(self.base, "ia.yaml")))
        # INVIO: non adesso (lo richiede la prossima volta)
        self.assertFalse(ia.collega_gemini(self.base, cfg, print, foto, aperte.append, lambda _="": "", invia))
        self.assertTrue(ia.serve_chiedere_gemini(impostazioni.carica(self.base)))
        # la chiave giusta: la prova, la salva e accende l'IA con Gemini per prima
        self.assertTrue(ia.collega_gemini(self.base, cfg, print, foto, aperte.append,
                                          lambda _="": "  AIza-chiave ", invia))
        self.assertEqual(aperte[0], ia.PAGINA_CHIAVE_GEMINI)                   # ha aperto la pagina di Google
        cfg = impostazioni.carica(self.base)
        self.assertEqual(cfg["ia"]["chiavi"]["gemini"], "AIza-chiave")
        self.assertEqual(cfg["ia"]["fornitori"][0], "gemini")
        self.assertTrue(cfg["ia"]["attiva"])
        self.assertFalse(ia.serve_chiedere_gemini(cfg))
        # "mai": non lo chiede piu'
        altra = tempfile.mkdtemp()
        try:
            self.assertFalse(ia.collega_gemini(altra, cfg, print, foto, aperte.append, lambda _="": "mai", invia))
            self.assertFalse(ia.serve_chiedere_gemini(impostazioni.carica(altra)))
        finally:
            shutil.rmtree(altra, ignore_errors=True)

    def test_capisce_i_rettangoli_dell_ia(self):
        import studia_foto
        o = studia_foto.leggi_oggetti('```json\n{"objects": [{"label": "enemy", "box_2d": [100, 500, 400, 560]},'
                                      ' {"label": "chest", "box_2d": [600, 200, 680, 280]},'
                                      ' {"label": "cloud", "box_2d": [0, 0, 100, 100]},'
                                      ' {"label": "weapon", "box_2d": [10, 10]}]}\n```')
        self.assertEqual([x[0] for x in o], ["nemico", "cassa"])                  # nuvola e box rotto: via
        self.assertEqual(o[0][1:], (0.5, 0.1, 0.56, 0.4))
        righe = studia_foto.righe_yolo(o)
        self.assertEqual(righe[0], "0 0.530000 0.250000 0.060000 0.300000")
        self.assertTrue(righe[1].startswith("1 0.240000 0.640000"))
        self.assertEqual(studia_foto.leggi_oggetti('{"objects": []}'), [])        # niente: etichetta vuota
        self.assertEqual(studia_foto.leggi_oggetti('[{"label": "ammo_box", "box_2d": [0.1, 0.1, 0.2, 0.2]}]')[0][0],
                         "materiali")                                             # lista e coordinate 0-1
        self.assertIsNone(studia_foto.leggi_oggetti("non lo so"))                 # da riprovare

    def test_l_ia_studia_le_foto(self):
        import json as js

        import studia_foto
        cartella = os.path.join(self.base, "foto_per_ia")
        os.makedirs(os.path.join(cartella, "images"))
        for n in ("a.jpg", "b.jpg", "c.jpg"):
            cv2.imwrite(os.path.join(cartella, "images", n), np.zeros((720, 1280, 3), np.uint8))
        with open(os.path.join(cartella, "studiate.txt"), "w") as f:
            f.write("# gia' fatte\nc.jpg\n")                                   # c: gia' controllata
        shutil.copy(os.path.join(QUI, "fortnite.txt"), self.base)
        risposte = ['{"objects": [{"label": "enemy", "box_2d": [200, 700, 450, 740]}]}', "boh", "boh", "boh"]
        mandati = []

        def invia(url, intest, corpo, attesa):
            mandati.append(js.loads(corpo))
            return {"choices": [{"message": {"content": risposte.pop(0)}}]}
        cfg = impostazioni.carica(self.base)
        self.assertEqual(studia_foto.studia(self.base, cfg, print, invia), 0)    # nessuna IA collegata
        cfg["ia"]["chiavi"] = {"gemini": "k"}
        fatte = studia_foto.studia(self.base, cfg, print, invia, pausa=0, dormi=lambda s: None)
        self.assertEqual(fatte, 1)                                               # a si', b non capita
        with open(os.path.join(cartella, "labels", "a.txt")) as f:
            self.assertTrue(f.read().startswith("0 0.720000 0.325000"))
        self.assertFalse(os.path.isfile(os.path.join(cartella, "labels", "b.txt")))
        self.assertEqual(studia_foto.leggi_studiate(cartella), {"a.jpg", "c.jpg"})
        self.assertIn("FURGONE DEL RIAVVIO", mandati[0]["messages"][0]["content"])  # sa come funziona il gioco
        self.assertIn("box_2d", mandati[0]["messages"][1]["content"][0]["text"])


class FintaIA:
    def __init__(self, consiglio):
        self.c = consiglio
        self.validita_fase = 45
        self.fidati_casse = True
        self.foto = 0

    def guarda(self, img):
        self.foto += 1

    def consiglio(self, adesso=None, validita=None):
        return self.c


class TestLogicaFortnite(ConCartella):
    """Con l'IA che guarda: bus, caduta, menu, casse finte, muri, tempesta."""

    def _cervello(self, **consiglio):
        import ia
        cfg = cfg_test(mira={"pixel_per_passo": 0.5, "passi_per_giro": 4800})
        mani, mondo, occhi, esec, app, cerv = crea(self.base, cfg, {"ppp": 0.5}, apprendimento=False)
        c = ia.Consiglio(**consiglio)
        c.numero = 1
        c.quando = time.monotonic()
        cerv.ia = FintaIA(c)
        cerv.prossimo_guardarsi = time.monotonic() + 999
        return mani, mondo, occhi, cerv

    def _passo(self, mondo, occhi, cerv, t=None):
        img = mondo.foto()
        return cerv.passo(occhi.analizza(img), img, t)

    def test_bus_caduta_menu(self):
        mani, mondo, occhi, cerv = self._cervello(fase="bus")
        self.assertEqual(self._passo(mondo, occhi, cerv), "sul bus")
        self.assertIn("giu tasto 0x%02X" % CODICI["spazio"], mani.storia)      # salta giu' dal bus
        self.assertEqual(cerv.ia.foto, 1)                                        # le passa la foto
        mani, mondo, occhi, cerv = self._cervello(fase="falling")
        self.assertEqual(self._passo(mondo, occhi, cerv), "cado verso terra")
        self.assertTrue(mani.e_premuto("avanti"))
        mani, mondo, occhi, cerv = self._cervello(fase="menu")
        mondo.oggetti.append((330, 120, 20, 60, ROSSO))
        self.assertEqual(self._passo(mondo, occhi, cerv), "aspetto (menu)")
        self.assertFalse(mani.e_premuto("spara"))

    def test_capisce_ps5_e_remote_play(self):
        import ia
        c = ia.leggi_risposta('{"phase": "unknown", "chest": "none", "screen": "remote_play", '
                              '"pc_button": {"x": 0.5, "y": 0.64}}')
        self.assertEqual((c.schermo, c.pulsante_pc), ("remote_play", (0.5, 0.64)))
        c = ia.leggi_risposta('{"phase": "menu", "screen": "ps5_who_is_using"}')
        self.assertEqual(c.schermo, "ps5_who_is_using")
        c = ia.leggi_risposta('{"phase": "playing", "chest": "none"}')               # IA vecchie: gioco
        self.assertEqual((c.schermo, c.pulsante_pc), ("game", None))
        self.assertIn("PS Remote Play", ia.DOMANDA)

    def test_chi_sta_usando_il_controller(self):
        """Il riquadro della PS5 che bloccava il bot a fine partita: preme INVIO."""
        mani, mondo, occhi, cerv = self._cervello(fase="menu", schermo="ps5_who_is_using")
        self.assertEqual(self._passo(mondo, occhi, cerv), "la PS5 chiede chi sta giocando")
        self.assertIn("giu tasto 0x%02X" % CODICI["invio"], mani.storia)
        n = len(mani.storia)
        self._passo(mondo, occhi, cerv)                                   # stesso consiglio: non ripreme
        self.assertEqual(len(mani.storia), n)

    def test_remote_play_scollegato_si_ricollega(self):
        from remote_play import PCFinto
        mani, mondo, occhi, cerv = self._cervello(fase="unknown", schermo="remote_play", pulsante_pc=(0.5, 0.64))
        cerv.pc = PCFinto()
        mondo.oggetti.append((330, 220, 40, 30, ORO))                     # un'icona gialla: NON e' una cassa
        self.assertEqual(self._passo(mondo, occhi, cerv), "PS Remote Play scollegato")
        self.assertEqual(len(cerv.pc.click), 1)
        x, y = cerv.pc.click[0]
        self.assertAlmostEqual(x, 0.5 * mondo.W)
        self.assertAlmostEqual(y, 0.64 * mondo.H)
        self.assertFalse(mani.e_premuto("avanti"))
        self.assertFalse(mani.e_premuto("spara"))

    def test_desktop_si_ferma_e_riporta_davanti_remote_play(self):
        from remote_play import PCFinto
        mani, mondo, occhi, cerv = self._cervello(fase="playing", schermo="desktop")
        cerv.pc = PCFinto()
        mondo.oggetti.append((330, 220, 40, 30, ORO))                     # cartella gialla del desktop
        self.assertEqual(self._passo(mondo, occhi, cerv), "non vedo il gioco")
        self.assertEqual(cerv.pc.davanti, 1)
        self.assertFalse(mani.e_premuto("avanti"))

    def test_in_caduta_per_troppo_tempo_non_ci_crede(self):
        mani, mondo, occhi, cerv = self._cervello(fase="falling")
        t = time.monotonic()
        self.assertEqual(self._passo(mondo, occhi, cerv, t), "cado verso terra")
        cerv.ia.c.quando = t + 130
        self.assertNotEqual(self._passo(mondo, occhi, cerv, t + 130), "cado verso terra")

    def test_casse_finte_e_vere(self):
        cassa = (500, 260, 50, 40, ORO)
        mani, mondo, occhi, cerv = self._cervello(fase="playing", cassa="none")
        mondo.oggetti.append(cassa)
        self.assertFalse(self._passo(mondo, occhi, cerv).startswith("vado verso cassa"))   # l'IA: e' finta
        mani, mondo, occhi, cerv = self._cervello(fase="playing", cassa="right")
        mondo.oggetti.append(cassa)
        self.assertTrue(self._passo(mondo, occhi, cerv).startswith("vado verso cassa"))

    def test_tempesta_e_muro(self):
        mani, mondo, occhi, cerv = self._cervello(fase="playing", tempesta=True, direzione="right")
        self.assertEqual(self._passo(mondo, occhi, cerv), "scappo dalla tempesta")
        self.assertGreater(mani.mosso_x, 0)                                       # gira a destra
        self.assertNotEqual(self._passo(mondo, occhi, cerv), "scappo dalla tempesta")   # una volta sola
        mani, mondo, occhi, cerv = self._cervello(fase="playing", muro=True)
        self.assertEqual(self._passo(mondo, occhi, cerv), "evito il muro")

    def test_partite_in_loop(self):
        mani, mondo, occhi, cerv = self._cervello(fase="playing")
        c = cerv.ia.c
        self._passo(mondo, occhi, cerv)
        # eliminato: la schermata dice "premi SPAZIO"
        c.fase, c.numero, c.tasto = "dead", 2, "space"
        self.assertEqual(self._passo(mondo, occhi, cerv), "premo spazio per continuare")
        self.assertEqual(cerv.statistiche["partite"], 1)                      # partita contata
        self.assertIn("giu tasto 0x%02X" % CODICI["spazio"], mani.storia)
        self.assertEqual(self._passo(mondo, occhi, cerv), "aspetto (eliminato)")   # stessa risposta: aspetta
        # nella lobby: il cursore e' lontano dal pulsante "Gioca" -> lo sposta
        c.fase, c.numero, c.tasto, c.pulsante, c.cursore = "menu", 3, "none", (0.5, 0.9), (0.2, 0.2)
        self.assertEqual(self._passo(mondo, occhi, cerv), "porto il cursore sul pulsante")
        self.assertGreater(mani.mosso_x, 0)
        self.assertGreater(mani.mosso_y, 0)
        # ora ci e' sopra -> clicca
        c.numero, c.cursore = 4, (0.5, 0.89)
        self.assertEqual(self._passo(mondo, occhi, cerv), "clicco per la partita dopo")
        self.assertIn("giu mouse 1", mani.storia)
        self.assertEqual(cerv.statistiche["partite"], 1)                      # non la conta due volte
        # comincia la partita nuova e poi finisce di nuovo: la conta
        c.fase, c.numero, c.pulsante, c.cursore = "bus", 5, None, None
        self.assertEqual(self._passo(mondo, occhi, cerv), "sul bus")
        c.fase, c.numero = "dead", 6
        self._passo(mondo, occhi, cerv)
        self.assertEqual(cerv.statistiche["partite"], 2)

    def test_impara_quanto_si_muove_il_cursore(self):
        mani, mondo, occhi, cerv = self._cervello(fase="menu", pulsante=(0.8, 0.5), cursore=(0.2, 0.5))
        cerv.esecutore.passi_per_pixel_menu = 1.0
        self._passo(mondo, occhi, cerv)                       # chiede di spostarsi di 384 pixel
        c = cerv.ia.c
        c.numero, c.cursore = 2, (0.5, 0.5)                   # ma il cursore si e' mosso solo di 192
        self._passo(mondo, occhi, cerv)
        self.assertAlmostEqual(cerv.esecutore.passi_per_pixel_menu, 1.5, places=2)

    def test_da_eliminato_guarda_un_altro_e_poi_esce(self):
        """Morto in squadra la telecamera segue un ALTRO personaggio: non lo comanda, aspetta il
        furgone del riavvio e poi clicca 'Ritorna alla lobby' per la partita dopo."""
        import ia
        c = ia.leggi_risposta('{"phase": "dead", "spectating": true, "button": {"x": 0.5, "y": 0.9}}')
        self.assertTrue(c.osservo)
        self.assertIn("Stai osservando", ia.DOMANDA)
        mani, mondo, occhi, cerv = self._cervello(fase="dead", osservo=True, pulsante=(0.5, 0.9))
        cerv.in_partita = True
        mondo.oggetti.append((330, 120, 20, 60, ROSSO))                    # l'altro personaggio / un nemico
        t = time.monotonic()
        self.assertEqual(self._passo(mondo, occhi, cerv, t), "eliminato: guardo un compagno, aspetto il furgone "
                         "del riavvio")
        self.assertNotIn("giu mouse 1", mani.storia)                         # non spara, non clicca
        self.assertFalse(mani.e_premuto("avanti"))
        self.assertEqual(cerv.statistiche["partite"], 1)
        cerv.ia.c.quando = t + 95
        self.assertEqual(self._passo(mondo, occhi, cerv, t + 95), "clicco per la partita dopo")
        self.assertIn("giu mouse 1", mani.storia)
        # se lo riportano in partita (furgone del riavvio) torna a giocare
        cerv.ia.c.fase, cerv.ia.c.osservo, cerv.ia.c.numero = "falling", False, 2
        self.assertEqual(self._passo(mondo, occhi, cerv, t + 100), "cado verso terra")
        self.assertIsNone(cerv.morto_da)

    def test_clicca_anche_senza_vedere_il_cursore(self):
        mani, mondo, occhi, cerv = self._cervello(fase="menu", pulsante=(0.5, 0.5))
        self.assertEqual(self._passo(mondo, occhi, cerv), "clicco per la partita dopo")
        self.assertIn("giu mouse 1", mani.storia)

    def test_macchina(self):
        mani, mondo, occhi, cerv = self._cervello(fase="playing", in_veicolo=True)
        t = time.monotonic()
        self.assertEqual(self._passo(mondo, occhi, cerv, t), "guido")
        self.assertTrue(mani.e_premuto("avanti"))
        self.assertEqual(self._passo(mondo, occhi, cerv, t + 30), "scendo dalla macchina")
        self.assertIn("giu tasto 0x%02X" % CODICI["e"], mani.storia)
        c = cerv.ia.c
        c.in_veicolo, c.veicolo, c.numero = False, "close", 2
        self.assertNotEqual(self._passo(mondo, occhi, cerv, t + 31), "salgo in macchina")   # appena sceso: no
        c.numero = 3
        self.assertEqual(self._passo(mondo, occhi, cerv, t + 100), "salgo in macchina")

    def test_si_cura_se_l_ia_vede_poca_vita(self):
        mani, mondo, occhi, cerv = self._cervello(fase="playing", poca_vita=True)
        self.assertEqual(self._passo(mondo, occhi, cerv), "mi curo")
        self.assertIn("giu tasto 0x%02X" % CODICI["6"], mani.storia)          # cura = arma_5 = tasto 6

    def test_non_resta_fermo_se_l_ia_e_lenta(self):
        """L'IA lenta aveva detto 'menu' un minuto fa, ma ora si gioca: il bot non deve restare fermo."""
        import ia
        mani, mondo, occhi, cerv = self._cervello(fase="menu")
        c = cerv.ia.c
        c.quando = time.monotonic() - 60
        c.miniatura = ia.miniatura(np.full((360, 640, 3), 255, np.uint8))     # la foto era tutta diversa
        self.assertFalse(self._passo(mondo, occhi, cerv).startswith("aspetto"))
        # ...ma se lo schermo e' ancora quello del menu (fermo), il consiglio vale anche se vecchio
        c.miniatura = ia.miniatura(mondo.foto())
        self.assertTrue(self._passo(mondo, occhi, cerv).startswith(("aspetto", "clicco", "porto")))

    def test_rianima_il_compagno(self):
        mani, mondo, occhi, cerv = self._cervello(fase="playing", compagno="close")
        cerv.fort["rianima_secondi"] = 0.1
        self.assertEqual(self._passo(mondo, occhi, cerv), "rianimo un compagno")
        self.assertIn("giu tasto 0x%02X" % CODICI["e"], mani.storia)
        self.assertFalse(mani.e_premuto("interagisci"))                 # poi lo lascia
        mani, mondo, occhi, cerv = self._cervello(fase="playing", compagno="left")
        self.assertEqual(self._passo(mondo, occhi, cerv), "vado dal compagno a terra")
        self.assertLess(mani.mosso_x, 0)

    def test_i_nemici_vengono_prima(self):
        mani, mondo, occhi, cerv = self._cervello(fase="playing", muro=True)
        mondo.oggetti.append((330, 120, 20, 60, ROSSO))
        self.assertTrue(self._passo(mondo, occhi, cerv).startswith("combatto"))


VIOLA = (200, 50, 140)       # il colore della tempesta (BGR)


class TestTempesta(ConCartella):
    """La tempesta la vede da solo (schermo viola) e scappa verso dove c'e' meno viola."""

    def test_quanto_viola(self):
        from cervello import viola
        self.assertGreater(viola(np.full((360, 640, 3), VIOLA, np.uint8)), 0.95)
        self.assertLess(viola(np.full((360, 640, 3), 60, np.uint8)), 0.01)
        self.assertLess(viola(np.full((360, 640, 3), (0, 200, 255), np.uint8)), 0.01)   # oro: no

    def test_scappa_dalla_parte_giusta(self):
        cfg = cfg_test(mira={"pixel_per_passo": 0.5, "passi_per_giro": 4800})
        mani, mondo, occhi, esec, app, cerv = crea(self.base, cfg, {"ppp": 0.5}, apprendimento=False)
        # tutto viola tranne la zona sicura (da 1200 a 1800 pixel del panorama = dietro di me)
        mondo.oggetti += [(0, -400, 1200, 1200, VIOLA), (1800, -400, 600, 1200, VIOLA)]
        cerv.prossimo_guardarsi = time.monotonic() + 999
        t = time.monotonic()
        img = mondo.foto()
        self.assertEqual(cerv.passo(occhi.analizza(img), img, t), "scappo dalla tempesta")
        self.assertEqual(mondo.x_visuale(), 1200)                       # girato verso la zona sicura
        img = mondo.foto()
        self.assertEqual(cerv.passo(occhi.analizza(img), img, t + 0.1), "corro via dalla tempesta")
        self.assertTrue(mani.e_premuto("avanti"))
        self.assertTrue(mani.e_premuto("corri"))

    def test_non_riprova_all_infinito_a_misurare(self):
        cfg = cfg_test(mira={"pixel_per_passo": 0.5, "passi_per_giro": 4800})
        mani, mondo, occhi, esec, app, cerv = crea(self.base, cfg, {"ppp": 0.5})
        app.ppp_noto = app.giro_noto = False
        schermo_fermo = types.SimpleNamespace(foto=lambda: np.full((360, 640, 3), 50, np.uint8),
                                              origine=(0, 0))
        for _ in range(app.tentativi_massimi):
            self.assertTrue(app.serve_calibrare(app.prossimo_tentativo))
            app.calibra(mani, schermo_fermo, esec)
        self.assertFalse(app.serve_calibrare(time.monotonic() + 1000))   # basta: gioca con la stima


GIALLO = (0, 230, 255)       # il pulsante "Gioca di nuovo" (BGR)


class MenuFinto:
    """Schermata di fine partita: un pulsante giallo e un cursore che si muove col mouse della
    schedina, ma con una 'velocita'' che il bot non conosce (come sulla Play)."""

    def __init__(self, mani, passi_per_pixel_vero, pulsante=(430, 280, 170, 50)):
        self.mani = mani
        self.vero = passi_per_pixel_vero
        self.pulsante = pulsante
        self.cx, self.cy = 320.0, 180.0
        self.letti = 0
        self.cliccato = False
        self.origine = (0, 0)

    def _aggiorna(self):
        for riga in self.mani.storia[self.letti:]:
            if riga.startswith("muovi "):
                dx, dy = (int(v) for v in riga.split()[1:3])
                self.cx = min(639.0, max(0.0, self.cx + dx / self.vero))
                self.cy = min(359.0, max(0.0, self.cy + dy / self.vero))
            elif riga == "giu mouse 1":
                x, y, w, h = self.pulsante
                if x <= self.cx <= x + w and y <= self.cy <= y + h:
                    self.cliccato = True
        self.letti = len(self.mani.storia)

    def foto(self):
        self._aggiorna()
        img = np.full((360, 640, 3), 45, np.uint8)
        if not self.cliccato:
            x, y, w, h = self.pulsante
            cv2.rectangle(img, (x, y), (x + w, y + h), GIALLO, -1)
            cv2.putText(img, "GIOCA DI NUOVO", (x + 12, y + 32), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (20, 20, 20), 2)
        return img

    def chiudi(self):
        pass


class TestPulsanteGiallo(ConCartella):
    def test_lo_riconosce(self):
        from cervello import trova_pulsante_giallo
        menu = MenuFinto(ManiFinte({}), 1.0)
        trovato = trova_pulsante_giallo(menu.foto())
        self.assertIsNotNone(trovato)
        self.assertAlmostEqual(trovato[0], 515, delta=8)
        self.assertAlmostEqual(trovato[1], 305, delta=8)
        img = np.full((360, 640, 3), 45, np.uint8)
        cv2.rectangle(img, (300, 250), (340, 290), GIALLO, -1)          # quadrato piccolo (una cassa): no
        self.assertIsNone(trova_pulsante_giallo(img))
        img = np.full((360, 640, 3), 45, np.uint8)
        cv2.rectangle(img, (430, 40), (600, 90), GIALLO, -1)            # in alto: no
        self.assertIsNone(trova_pulsante_giallo(img))
        self.assertIsNone(trova_pulsante_giallo(np.full((360, 640, 3), GIALLO, np.uint8)))   # tutto giallo: no

    def _gioca(self, passi_per_pixel_vero):
        cfg = cfg_test(mira={"pixel_per_passo": 0.5, "passi_per_giro": 4800})
        mani, mondo, occhi, esec, app, cerv = crea(self.base, cfg, {"ppp": 0.5})
        app.ppp_noto = app.giro_noto = True
        menu = MenuFinto(mani, passi_per_pixel_vero)
        esec.schermo = menu
        cerv.schermo = menu
        cerv.prossimo_guardarsi = time.monotonic() + 9999
        t = time.monotonic()
        scritte = []
        for i in range(40):
            img = menu.foto()
            scritte.append(cerv.passo(occhi.analizza(img), img, t + i * 1.0))
            if menu.cliccato and trova_pulsante_giallo_none(menu):
                img = menu.foto()
                cerv.passo(occhi.analizza(img), img, t + (i + 1) * 1.0)
                break
        return menu, cerv, scritte

    def test_clicca_gioca_di_nuovo(self):
        menu, cerv, scritte = self._gioca(1.0)
        self.assertTrue(menu.cliccato)
        self.assertIn("clicco Gioca di nuovo", scritte)
        self.assertEqual(cerv.statistiche["partite"], 1)

    def test_si_corregge_se_il_cursore_e_piu_veloce(self):
        menu, cerv, scritte = self._gioca(2.0)          # sulla Play il cursore va il doppio
        self.assertTrue(menu.cliccato)
        self.assertGreater(scritte.count("clicco Gioca di nuovo"), 1)   # al primo colpo l'ha mancato
        self.assertEqual(cerv.statistiche["partite"], 1)                # ma la partita e' una
        cal = impostazioni.leggi_calibrazione(self.base)
        self.assertIn("passi_per_pixel", cal.get("menu", {}))           # si ricorda come fare

    def test_clicca_anche_se_crede_di_vedere_un_nemico(self):
        """Nella schermata finale c'e' il tuo personaggio: il bot lo prendeva per un nemico e non
        cliccava mai 'Gioca di nuovo'. Ora, a schermo fermo, clicca lo stesso."""
        cfg = cfg_test(mira={"pixel_per_passo": 0.5, "passi_per_giro": 4800})
        mani, mondo, occhi, esec, app, cerv = crea(self.base, cfg, {"ppp": 0.5})
        app.ppp_noto = app.giro_noto = True
        menu = MenuFinto(mani, 1.0)
        esec.schermo = menu
        cerv.schermo = menu
        cerv.prossimo_guardarsi = time.monotonic() + 9999
        t = time.monotonic()
        scritte = []
        for i in range(12):
            img = menu.foto()
            vis = occhi.analizza(img)
            vis.oggetti["nemico"] = [Box(100, 150, 60, 160, 0.9, "nemico")]      # il tuo personaggio
            scritte.append(cerv.passo(vis, img, t + i * 1.0))
            if menu.cliccato:
                break
        self.assertTrue(menu.cliccato)
        self.assertGreaterEqual(len(scritte), 5)                           # ma ci ha pensato di piu'

    def test_in_partita_non_clicca(self):
        """Uno schermo che si muove (si gioca) con qualcosa di giallo: non clicca."""
        cfg = cfg_test(mira={"pixel_per_passo": 0.5, "passi_per_giro": 4800})
        mani, mondo, occhi, esec, app, cerv = crea(self.base, cfg, {"ppp": 0.5}, apprendimento=False)
        mondo.oggetti.append((430, 280, 170, 50, GIALLO))
        t = time.monotonic()
        scritte = []
        for i in range(10):
            img = mondo.foto()
            scritte.append(cerv.passo(occhi.analizza(img), img, t + i * 1.0))
        self.assertNotIn("clicco Gioca di nuovo", scritte)


def trova_pulsante_giallo_none(menu):
    from cervello import trova_pulsante_giallo
    return trova_pulsante_giallo(menu.foto()) is None


class TestVisualeFluida(unittest.TestCase):
    """Il mouse non salta: il movimento arriva a passettini."""

    def test_passettini_e_sostituzione(self):
        mani = ManiFinte({})
        mani.usa_fluido = True
        mani.mira_fluida(200, -40, 0.2)
        time.sleep(0.05)
        meta = mani.mosso_x
        self.assertGreater(meta, 0)
        self.assertLess(meta, 150)                               # non tutto subito
        n_pezzi = sum(1 for r in mani.storia if r.startswith("muovi"))
        self.assertGreater(n_pezzi, 3)                           # tanti pezzetti, non un salto
        time.sleep(0.3)
        self.assertEqual((mani.mosso_x, mani.mosso_y), (200, -40))   # alla fine arriva giusto
        # un nuovo ordine sostituisce quello vecchio (il cervello ricalcola ogni fotogramma)
        mani.mira_fluida(1000, 0, 0.5)
        time.sleep(0.02)
        mani.mira_fluida(-30, 0, 0.02)
        time.sleep(0.2)
        self.assertLess(mani.mosso_x - 200, 200)
        # rilascia tutto ferma anche il movimento
        mani.mira_fluida(5000, 0, 1.0)
        time.sleep(0.02)
        mani.rilascia_tutto()
        prima = mani.mosso_x
        time.sleep(0.1)
        self.assertEqual(mani.mosso_x, prima)

    def test_il_cervello_non_supera_la_velocita_massima(self):
        base = tempfile.mkdtemp()
        cfg = cfg_test(mira={"pixel_per_passo": 0.5, "passi_per_giro": 3600, "velocita_massima_gradi": 360})
        mani, mondo, occhi, esec, app, cerv = crea(base, cfg, {"ppp": 0.5}, apprendimento=False)
        chiamate = []
        mani.mira_fluida = lambda dx, dy, durata: chiamate.append((dx, dy, durata))
        mondo.oggetti.append((620, 120, 24, 60, ROSSO))            # nemico lontano dal mirino
        img = mondo.foto()
        cerv.passo(occhi.analizza(img), img)
        dx, dy, durata = chiamate[-1]
        self.assertLessEqual(abs(dx), 3600 * durata + 1e-6)      # max 360 gradi/s
        self.assertGreater(dx, 0)


class TestStile(ConCartella):
    """Le 3 modalita': Normale (sbaglia un po'), Pro player (preciso), Tranquillo (evita gli scontri)."""

    def _cervello(self, chiave, oggetti, frase="vincere"):
        import obiettivo
        import stile
        impostazioni.salva_calibrazione(self.base, ["mira", "pixel_per_passo"], 0.5)
        impostazioni.salva_calibrazione(self.base, ["mira", "passi_per_giro"], 4800)
        cfg = cfg_test(mira={"pixel_per_passo": 0.5, "passi_per_giro": 4800})
        mani, mondo, occhi, esec, app, cerv = crea(self.base, cfg, {"ppp": 0.5})
        cerv.obiettivo = obiettivo.capisci(frase)
        cerv.stile = stile.STILI[chiave]
        mondo.oggetti += oggetti
        return mani, mondo, occhi, app, cerv

    def test_scelta_e_file(self):
        import stile
        self.assertEqual(stile.capisci("1").chiave, "normale")
        self.assertEqual(stile.capisci("2").chiave, "pro")
        self.assertEqual(stile.capisci("3").chiave, "tranquillo")
        self.assertEqual(stile.capisci("Pro").chiave, "pro")
        self.assertEqual(stile.capisci("pro player").chiave, "pro")
        self.assertEqual(stile.capisci("tranq").chiave, "tranquillo")
        self.assertIsNone(stile.capisci("boh"))
        self.assertEqual(stile.leggi(self.base).chiave, "normale")        # mai scelta: Normale
        risposte = iter(["7", "3"])                                        # sbaglia, poi 3
        import builtins
        vecchio = builtins.input
        try:
            builtins.input = lambda *_: next(risposte)
            self.assertEqual(stile.chiedi(self.base).chiave, "tranquillo")
            self.assertEqual(stile.leggi(self.base).chiave, "tranquillo")  # se la ricorda
            builtins.input = lambda *_: ""
            self.assertEqual(stile.chiedi(self.base).chiave, "tranquillo")  # INVIO = l'ultima
        finally:
            builtins.input = vecchio

    def test_normale_piu_lento_del_pro(self):
        import random
        random.seed(3)
        nemico = (500, 120, 24, 60, ROSSO)
        mani_p, mondo_p, occhi_p, _, cerv_p = self._cervello("pro", [nemico])
        mani_n, mondo_n, occhi_n, _, cerv_n = self._cervello("normale", [nemico])
        img = mondo_p.foto()
        cerv_p.passo(occhi_p.analizza(img), img)
        img = mondo_n.foto()
        cerv_n.passo(occhi_n.analizza(img), img)
        self.assertGreater(mani_p.mosso_x, 0)
        self.assertLess(mani_n.mosso_x, mani_p.mosso_x * 0.85)

    def test_normale_reagisce_dopo_un_attimo_ma_spara(self):
        import random
        random.seed(5)
        mani, mondo, occhi, app, cerv = self._cervello("normale", [(308, 160, 24, 60, ROSSO)])  # sul mirino
        t = time.monotonic()
        img = mondo.foto()
        cerv.passo(occhi.analizza(img), img, t)
        self.assertFalse(mani.e_premuto("spara"))               # appena visto: non spara subito
        sparato = False
        for i in range(1, 40):
            img = mondo.foto()
            cerv.passo(occhi.analizza(img), img, t + i * 0.03)
            sparato = sparato or mani.e_premuto("spara")
        self.assertTrue(sparato)                                  # poi spara

    def test_pro_spara_subito(self):
        mani, mondo, occhi, app, cerv = self._cervello("pro", [(308, 160, 24, 60, ROSSO)])
        img = mondo.foto()
        cerv.passo(occhi.analizza(img), img)
        self.assertTrue(mani.e_premuto("spara"))

    def test_solo_il_pro_impara_la_forza_della_mira(self):
        mani, mondo, occhi, app, cerv = self._cervello("normale", [(560, 120, 24, 60, ROSSO)])
        app.forza = 0.9
        t = time.monotonic()
        for i in range(30):
            img = mondo.foto()
            cerv.passo(occhi.analizza(img), img, t + i * 0.03)
        self.assertEqual(app.forza, 0.9)                         # gli errori voluti non la rovinano

    def test_tranquillo_evita_gli_scontri(self):
        medio = (330, 120, 20, 60, ROSSO)                          # nemico non vicino
        cassa = (500, 260, 50, 40, ORO)
        mani, mondo, occhi, app, cerv = self._cervello("tranquillo", [medio, cassa])
        img = mondo.foto()
        scritta = cerv.passo(occhi.analizza(img), img)
        self.assertTrue(scritta.startswith("vado verso cassa"), scritta)
        # col Pro lo stesso nemico si combatte
        mani2, mondo2, occhi2, app2, cerv2 = self._cervello("pro", [medio, cassa])
        img = mondo2.foto()
        self.assertTrue(cerv2.passo(occhi2.analizza(img), img).startswith("combatto"))

    def test_tranquillo_si_difende_ma_non_insegue(self):
        vicino = (300, 100, 60, 200, ROSSO)
        mani, mondo, occhi, app, cerv = self._cervello("tranquillo", [vicino], "eliminare piu' nemici possibili")
        img = mondo.foto()
        self.assertTrue(cerv.passo(occhi.analizza(img), img).startswith("combatto"))
        self.assertFalse(mani.e_premuto("avanti"))


class TestTelecomando(unittest.TestCase):
    """Giochi tu sulla Play dal portatile: tastiera e mouse passano alla schedina."""

    def test_nomi_dei_tasti(self):
        from telecomando import nome_tasto
        N = types.SimpleNamespace
        self.assertEqual(nome_tasto(N(vk=0x57, char="W")), "w")       # W con Maiusc
        self.assertEqual(nome_tasto(N(vk=0x31, char="!")), "1")       # 1 con Maiusc
        self.assertEqual(nome_tasto(N(vk=0x45, char="\x05")), "e")    # E con Ctrl
        self.assertEqual(nome_tasto(N(vk=None, char="e")), "e")
        self.assertEqual(nome_tasto(N(name="space")), "spazio")
        self.assertEqual(nome_tasto(N(name="shift_r")), "shift_destro")
        self.assertEqual(nome_tasto(N(name="f8")), "f8")
        for nome in ("w", "1", "e", "spazio", "shift_destro", "f8", "ctrl", "esc", "invio", "up"):
            risolvi_grezzo(nome)                                       # la schedina li sa premere

    def test_passa_tasti_e_mouse_alla_schedina(self):
        from telecomando import Telecomando
        N = types.SimpleNamespace
        mani = ManiFinte({})
        tele = Telecomando(mani, (500, 400), ogni=0.002)
        w = N(vk=0x57, char="w")
        tele.tasto_giu(w)
        tele.tasto_giu(w)                       # tasto tenuto premuto: Windows lo ripete
        tele.tasto_giu(N(name="f9"))            # F9 e' del bot: non va alla Play
        tele.tasto_giu(N(name="menu"))          # tasto che la schedina non conosce: si salta
        tele.mosso(510, 395)
        tele.mosso(503, 400)
        tele.click(500, 400, N(name="left"), True)
        tele.click(500, 400, N(name="left"), False)
        tele.rotella(500, 400, 0, 1)
        tele.tasto_su(w)
        time.sleep(0.05)
        tele.ferma()
        self.assertIsNone(tele.errore)
        self.assertEqual(mani.storia.count("giu tasto 0x1A"), 1)       # W premuto una volta sola
        self.assertIn("su tasto 0x1A", mani.storia)
        self.assertFalse(any("0x42" in r for r in mani.storia))       # niente F9
        self.assertEqual((mani.mosso_x, mani.mosso_y), (13, -5))
        self.assertIn("giu mouse 1", mani.storia)
        self.assertIn("su mouse 1", mani.storia)
        self.assertIn("rotella 1", mani.storia)
        self.assertEqual(mani.storia[-1], "rilascia tutto")             # alla fine lascia tutto

    def test_sensibilita_e_schedina_staccata(self):
        from telecomando import Telecomando
        mani = ManiFinte({})
        tele = Telecomando(mani, (0, 0), sensibilita=0.5, ogni=0.002)
        tele.mosso(20, -10)
        time.sleep(0.03)
        tele.ferma()
        self.assertEqual((mani.mosso_x, mani.mosso_y), (10, -5))

        class Staccata(ManiFinte):
            def _mouse_muovi(self, dx, dy):
                raise RuntimeError("cavo staccato")
        tele = Telecomando(Staccata({}), (0, 0), ogni=0.002)
        tele.mosso(5, 5)
        time.sleep(0.03)
        tele.ferma()
        self.assertIn("cavo staccato", str(tele.errore))


class TestSceltaObiettivo(ConCartella):
    def test_numeri(self):
        import builtins

        import obiettivo
        vecchio = builtins.input
        try:
            risposte = iter(["2", "boh", "2", "50"])         # 2, numero sbagliato, di nuovo 2, 50
            builtins.input = lambda *_: next(risposte)
            ob = obiettivo.chiedi(self.base)
            self.assertEqual((ob.tipo, ob.casse), ("casse_n", 50))
            self.assertEqual(obiettivo.leggi(self.base).casse, 50)          # salvato
            builtins.input = lambda *_: ""
            self.assertEqual(obiettivo.chiedi(self.base).casse, 50)         # INVIO = quello di prima
            builtins.input = lambda *_: "4"
            self.assertEqual(obiettivo.chiedi(self.base).tipo, "nemici")
            builtins.input = lambda *_: "sopravvivere"
            self.assertEqual(obiettivo.chiedi(self.base).tipo, "sopravvivere")
        finally:
            builtins.input = vecchio


class TestAggiorna(ConCartella):
    """Menu 13: il programma si aggiorna da solo senza toccare le tue impostazioni."""

    def test_versione_e_script(self):
        import bot
        self.assertEqual(bot.leggi_versione(self.base), 0)               # manca: 0
        with open(os.path.join(self.base, "versione.txt"), "w") as f:
            f.write("7")
        self.assertEqual(bot.leggi_versione(self.base), 7)
        script = bot.script_aggiornamento(r"C:\T\BotSparatutto", r"C:\Users\x\BotSparatutto",
                                          "BotSparatutto.exe", r"C:\T")
        self.assertIn('robocopy "C:\\T\\BotSparatutto" "C:\\Users\\x\\BotSparatutto" /E', script)
        for nome in ("impostazioni.yaml", "istruzioni.txt", "obiettivo.txt"):
            self.assertIn(nome, script.split("/XF", 1)[1].splitlines()[0])   # le tue non si toccano
        self.assertIn('start "" /D "C:\\Users\\x\\BotSparatutto" "BotSparatutto.exe"', script)
        self.assertTrue(script.endswith("\r\n"))
        self.assertNotIn("\n", script.replace("\r\n", ""))                   # righe da Windows

    def test_trenta_secondi_per_partire(self):
        cfg = impostazioni.carica(self.base)
        self.assertEqual(cfg["schermo"]["secondi_prima_di_partire"], 30)
        cfg = impostazioni.carica(QUI)                                         # il file vero
        self.assertEqual(cfg["schermo"]["secondi_prima_di_partire"], 30)


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


# ====================================================================== allenamento
class TestAllenamento(ConCartella):
    def _allenamento(self):
        from allenamento import Allenamento
        cfg = cfg_test()
        stat = {}
        return cfg, stat, Allenamento(cfg, self.base, stat, lambda *_: None)

    def test_partita_troppo_corta_non_conta(self):
        cfg, stat, al = self._allenamento()
        self.assertIsNone(al.fine_partita(adesso=al.inizio + 10))
        self.assertFalse(os.path.isfile(os.path.join(self.base, "allenamento.txt")))

    def test_casse_che_non_si_aprono(self):
        cfg, stat, al = self._allenamento()
        prima = cfg["raccolta"]["vicino_altezza"]
        stat.update(casse=3, casse_tentate=6, casse_fallite=3, bloccato=5, lasciate_perdere=4)
        al.conta_tempo("esploro", 2.0)
        riga = al.fine_partita(adesso=al.inizio + 300)
        self.assertIn("casse armi 3", riga)
        self.assertIn("non aperte 3", riga)
        self.assertIn("si avvicina di piu'", riga)
        self.assertIn("perde meno tempo con le casse irraggiungibili", riga)
        self.assertIn("si accorge prima quando e' bloccato", riga)
        self.assertGreater(cfg["raccolta"]["vicino_altezza"], prima)
        self.assertLess(cfg["raccolta"]["tempo_massimo_avvicinamento"], 10.0)
        self.assertGreater(cfg["esplorazione"]["sensibilita_blocco"], 2.5)
        cal = impostazioni.leggi_calibrazione(self.base)              # salvato per la volta dopo
        self.assertEqual(cal["raccolta"]["vicino_altezza"], cfg["raccolta"]["vicino_altezza"])
        with open(os.path.join(self.base, "allenamento.txt"), encoding="utf-8") as f:
            self.assertIn("partita 1", f.read())
        # la partita dopo conta solo le sue casse
        stat.update(casse=5, casse_tentate=8, casse_fallite=3)
        riga = al.fine_partita(adesso=al.inizio + 200)
        self.assertIn("partita 2", riga)
        self.assertIn("casse armi 2", riga)

    def test_non_esagera_mai(self):
        cfg, stat, al = self._allenamento()
        t = al.inizio
        for i in range(60):
            stat["casse_tentate"] = stat.get("casse_tentate", 0) + 10
            stat["casse_fallite"] = stat.get("casse_fallite", 0) + 10
            t += 120
            al.fine_partita(adesso=t)
        self.assertLessEqual(cfg["raccolta"]["vicino_altezza"], 0.35)
        self.assertLessEqual(cfg["raccolta"]["tempo_apertura_cassa"], 3.0)
        for i in range(200):
            stat["casse_tentate"] += 10
            stat["casse"] = stat.get("casse", 0) + 10
            t += 120
            al.fine_partita(adesso=t)
        self.assertGreaterEqual(cfg["raccolta"]["vicino_altezza"], 0.06)

    def test_esplora_tanto_senza_casse(self):
        cfg, stat, al = self._allenamento()
        al.conta_tempo("esploro", 4.0)
        al.conta_tempo("mi guardo intorno", 4.0)
        al.conta_tempo("combatto (miro)", 1.0)
        riga = al.fine_partita(adesso=al.inizio + 120)
        self.assertIn("si guarda intorno piu' spesso", riga)
        self.assertEqual(cfg["esplorazione"]["guarda_intorno_ogni"], 10.0)

    def test_fine_partita_quando_passa_alla_successiva(self):
        cfg, stat, al = self._allenamento()
        al.inizio -= 100
        mani = ManiFinte(cfg["tasti"])
        esec = Esecutore(mani, None, None, cfg, None, lambda *_: None, stat, {})
        esec.su_fine_partita = al.fine_partita
        esec.esegui(leggi_azioni("conta partita", mani.esiste, {}))
        self.assertEqual(al.numero, 1)
        self.assertEqual(stat["partite"], 1)

    def test_conta_le_casse_che_non_si_aprono(self):
        impostazioni.salva_calibrazione(self.base, ["mira", "pixel_per_passo"], 0.5)
        impostazioni.salva_calibrazione(self.base, ["mira", "passi_per_giro"], 4800)
        cfg = cfg_test(mira={"pixel_per_passo": 0.5, "passi_per_giro": 4800})
        mani, mondo, occhi, esec, app, cerv = crea(self.base, cfg, {"ppp": 0.5})
        mondo.oggetti.append((300, 300, 60, 50, ORO))          # cassa che non si apre mai
        img = mondo.foto()
        cerv.passo(occhi.analizza(img), img)
        self.assertEqual(cerv.statistiche["casse_fallite"], 1)
        self.assertEqual(cerv.statistiche["casse"], 0)

    def test_foto_piu_piccole_e_con_limite(self):
        sf = SalvaFoto(os.path.join(self.base, "foto"), massimo=2, larghezza_massima=1280)
        vis = Visione(1920, 1080)
        vis.oggetti["nemico"].append(Box(960, 540, 40, 100, 1.0, "nemico"))
        grande = np.zeros((1080, 1920, 3), np.uint8)
        self.assertTrue(sf.salva(grande, vis))
        self.assertTrue(sf.salva(grande, vis))
        self.assertFalse(sf.salva(grande, vis))                 # arrivato al limite
        cartella = os.path.join(self.base, "foto", "images")
        foto = cv2.imread(os.path.join(cartella, sorted(os.listdir(cartella))[0]))
        self.assertEqual(foto.shape[:2], (720, 1280))
        self.assertTrue(SalvaFoto(os.path.join(self.base, "foto"), massimo=2).pieno)   # si ricorda quante ne ha


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

    def esegui_code_py(self, comandi, secondi_dopo=0.0, dai_fili=False, byte_per_lettura=None):
        """dai_fili=True: i comandi arrivano dai fili GP0/GP1 (schedina sulla Play), senza USB dati.
        byte_per_lettura: i dati arrivano a pezzetti, 0.01 s l'uno (un filo che continua a ricevere)."""
        rapporti = []

        class Dispositivo:
            def __init__(self, usage):
                self.usage_page, self.usage = 0x01, usage

            def send_report(self, r):
                rapporti.append((self.usage, bytes(r)))

        orologio = {"t": 100.0, "fine": None}
        seriale = FintoSeriale(comandi)
        if byte_per_lettura:
            class FiloLento(FintoSeriale):
                @property
                def in_waiting(self):
                    return min(byte_per_lettura, len(self.dati))

                def read(self, n):
                    orologio["t"] += 0.01
                    return FintoSeriale.read(self, n)
            seriale = FiloLento(comandi)
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
            "usb_cdc": types.SimpleNamespace(data=None if dai_fili else seriale),
        }
        if dai_fili:
            aperti = []

            def uart(tx, rx, baudrate=9600, **kw):
                aperti.append((tx, rx, baudrate))
                return seriale
            moduli["board"] = types.SimpleNamespace(GP0="GP0", GP1="GP1")
            moduli["busio"] = types.SimpleNamespace(UART=uart)
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
        if dai_fili:
            self.assertEqual(aperti, [("GP0", "GP1", 115200)])     # GP0 parla, GP1 ascolta
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

    def test_comandi_dai_fili(self):
        """Schedina sulla Play: i comandi arrivano dal ponte sui fili, la risposta torna sui fili."""
        rapporti, risposta = self.esegui_code_py(b"P\nKD 4\nM 5 -5\nR\n", dai_fili=True)
        self.assertIn(b"OK BOT", risposta)
        tastiera = [r for u, r in rapporti if u == 0x06]
        mouse = [r for u, r in rapporti if u == 0x02]
        self.assertEqual(tastiera[0], bytes([0, 0, 4, 0, 0, 0, 0, 0]))
        self.assertEqual(mouse[0], bytes([0, 5, 251, 0]))
        self.assertEqual(tastiera[-1], bytes(8))

    def test_disturbi_sui_fili_non_tengono_premuto(self):
        """Se il ponte si stacca, la spazzatura sul filo non deve tenere i tasti premuti."""
        spazzatura = b"\x00\xff?\n" * 100        # 100 righe, circa 1.2 secondi di disturbi
        rapporti, _ = self.esegui_code_py(b"KD 26\n" + spazzatura, dai_fili=True, byte_per_lettura=4)
        tastiera = [r for u, r in rapporti if u == 0x06]
        self.assertEqual(tastiera[0], bytes([0, 0, 26, 0, 0, 0, 0, 0]))       # W premuto
        self.assertEqual(tastiera[-1], bytes(8))      # rilasciato mentre arrivavano ancora i disturbi

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
        # gli stessi file anche in uno .zip (se CIRCUITPY resta vuota si copiano a mano)
        import zipfile
        percorso_zip = os.path.join(tempfile.mkdtemp(), "file.zip")
        crea_uf2.scrivi_zip(file, percorso_zip)
        with zipfile.ZipFile(percorso_zip) as z:
            self.assertEqual(z.namelist(), nomi)
            self.assertEqual(z.read("code.py"), letti["code.py"])

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
