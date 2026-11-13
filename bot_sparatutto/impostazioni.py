"""
impostazioni.py - Legge impostazioni.yaml (quello che scrivi tu) e
calibrazione.yaml (quello che scrive il bot quando calibri).

calibrazione.yaml vince su impostazioni.yaml. Per tornare indietro basta
cancellare calibrazione.yaml (o la riga che non ti piace).
"""

import copy
import os

import yaml

PREDEFINITE = {
    "comandi": {"modo": "schedina", "porta": "auto", "scrivi_comandi_in_prova": False},
    "tasti_bot": {"pausa": "f8", "esci": "f9"},
    "telecomando": {"sensibilita_mouse": 1.0},
    # l'IA che guarda (ia.py): la accende e la collega il menu "Collega le IA" (file ia.yaml)
    "ia": {
        "attiva": False,
        "ogni_secondi": 3,               # ogni quanto le manda una foto
        "validita_secondi": 8,           # casse, muri, tempesta: dopo questo tempo il consiglio e' vecchio
        "validita_fase_secondi": 45,     # bus, caduta, menu: cambiano piu' piano
        "fidati_delle_casse": True,      # se l'IA non vede casse, quelle trovate col colore sono finte
        "fornitori": ["ollama", "pollinations", "gemini", "github", "openrouter", "groq", "mistral", "zai",
                      "personale"],
        "chiavi": {},
        "modelli": {},
        "personale": {"url": "", "modello": "", "chiave": ""},
    },
    "schermo": {
        "monitor": 1,
        "zona_cattura": None,
        "fps_massimi": 60,
        "scala_analisi": 0.5,
        "titolo_finestra_gioco": "",
        "zone_interfaccia_fortnite": True,
        "secondi_prima_di_partire": 30,
        "mirino": [0.5, 0.5],
        "zone_ignorate": [],
        "mostra_finestra": False,
    },
    # comandi stile Fortnite (tastiera e mouse, quelli predefiniti)
    "tasti": {
        "avanti": "w", "indietro": "s", "sinistra": "a", "destra": "d",
        "salta": "spazio", "accovacciati": "ctrl", "corri": "shift",
        "spara": "mouse_sinistro", "mira": "mouse_destro", "ricarica": "r", "interagisci": "e",
        "piccone": "1", "arma_1": "2", "arma_2": "3", "arma_3": "4", "arma_4": "5", "arma_5": "6",
        "muro": "f1", "pavimento": "f2", "scale": "f3", "tetto": "f4", "trappola": "f5",
        "modifica": "g", "costruisci": "muro",
        "mappa": "m", "inventario": "i", "emote": "b",
        "cura": "arma_5",
    },
    "mira": {
        "pixel_per_passo": 1.0,
        "passi_per_giro": 3600,
        "forza": 0.6,
        "altezza_mira_universale": 0.15,
        "massimo_passi": 400,
        "velocita_massima_gradi": 540,
        "altezza_mira": 0.2,
        "spostamento_y": 0,
        "anticipo": 0.05,
        "tolleranza": 0.35,
        "tolleranza_minima_px": 4,
        "rinculo": 0,
        "mira_col_tasto_destro": False,
    },
    "combattimento": {
        "attivo": True,
        "spara": "tieni",
        "raffica_secondi": 0.25,
        "pausa_raffica_secondi": 0.12,
        "schiva": True,
        "salta_ogni_tanto": False,
        "insegui": True,
        "distanza_insegui": 0.08,
        "memoria_secondi": 0.35,
        "ricarica_dopo": True,
        "macro_quando_colpito": "muro",
        "vita_persa_per_costruire": 15,
        "attesa_tra_muri": 3.0,
    },
    "raccolta": {
        "casse": True,
        "casse_materiali": True,
        "armi": True,
        "conferma_fotogrammi": 3,
        "tentativi_per_cassa": 2,
        "priorita_casse": 2.0,
        "priorita_materiali": 1.6,
        "priorita_armi": 1.0,
        "tempo_apertura_cassa": 1.2,
        "tempo_raccolta_arma": 0.1,
        "immagine_interazione": "",
        "vicino_altezza": 0.12,
        "vicino_fondo": 0.85,
        "tempo_massimo_avvicinamento": 10.0,
        "forza_giro": 0.35,
    },
    "esplorazione": {
        "corri": True,
        "guarda_intorno_ogni": 12.0,
        "passi_giro_intorno": 8,
        "velocita_giro_gradi": 120,
        "sensibilita_blocco": 2.5,
        "rimetti_visuale_dritta": True,
    },
    "vita": {
        "zona": None,
        "colore": [],
        "cura_sotto": 40,
        "macro_cura": "cura",
    },
    "colori": {
        "nemico": [],
        "cassa": [{"tinta": [20, 32], "saturazione": [160, 255], "luminosita": [200, 255]}],
        "materiali": [],
        "arma": [],
        "testa": [],
        "alleato": [],
    },
    "rilevamento": {
        "area_minima": 0.00015,
        "oggetto_larghezza_massima": 0.25,
        "oggetto_altezza_massima": 0.35,
        "unisci_pixel": 5,
        "massimo_per_categoria": 12,
        "scala_immagini": 0.5,
        "somiglianza_immagini": 0.8,
    },
    "modello_ia": {"file": "", "dimensione": 640, "confidenza": 0.4,
                   "classi": ["nemico", "cassa", "materiali", "arma"]},
    "rilevatore_universale": {"attivo": True, "file": "auto", "confidenza": 0.45, "tempo_massimo": 0.035,
                              "usa_gpu": False, "scarica_se_manca": True},
    "apprendimento": {"attivo": True, "calibra_da_solo": True, "mira_adattiva": True,
                      "impara_cose_attaccate": True, "allenamento": True,
                      "salva_foto_ogni": 5, "foto_massime": 3000, "foto_in_impara_ogni": 2.0},
    "regole": {"attesa_tra_ripetizioni": 3.0, "controlla_ogni": 0.2},
    "menu": {"passi_per_pixel": 1.0},
    "macro": {
        "muro": "premi muro, aspetta 0.05, clicca, aspetta 0.05, premi arma_1",
        "scatola": ("premi muro, aspetta 0.05, clicca, gira 90, clicca, gira 90, clicca, gira 90, clicca, "
                    "gira 90, premi arma_1"),
        "cura": "premi cura, aspetta 0.2, tieni spara 4, premi arma_1",
    },
}


def unisci(base, sopra):
    """Unisce due dizionari: i valori di 'sopra' vincono, i sotto-dizionari si uniscono."""
    risultato = copy.deepcopy(base)
    for k, v in (sopra or {}).items():
        if isinstance(v, dict) and isinstance(risultato.get(k), dict):
            risultato[k] = unisci(risultato[k], v)
        else:
            risultato[k] = copy.deepcopy(v)
    return risultato


class ErroreImpostazioni(ValueError):
    pass


def _leggi_yaml(percorso):
    if not os.path.isfile(percorso):
        return {}
    with open(percorso, "r", encoding="utf-8-sig") as f:
        try:
            dati = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            riga = ""
            if hasattr(e, "problem_mark") and e.problem_mark is not None:
                riga = " (vicino alla riga %d)" % (e.problem_mark.line + 1)
            raise ErroreImpostazioni("%s scritto male%s: %s" % (os.path.basename(percorso), riga, e))
    if not isinstance(dati, dict):
        raise ErroreImpostazioni("%s scritto male" % os.path.basename(percorso))
    return dati


def leggi_calibrazione(cartella):
    """Solo quello che il bot ha imparato/calibrato (calibrazione.yaml)."""
    try:
        return _leggi_yaml(os.path.join(cartella, "calibrazione.yaml"))
    except ErroreImpostazioni:
        return {}


def carica(cartella):
    cfg = unisci(PREDEFINITE, _leggi_yaml(os.path.join(cartella, "impostazioni.yaml")))
    cfg = unisci(cfg, _leggi_yaml(os.path.join(cartella, "calibrazione.yaml")))
    # l'IA che guarda: chiavi e IA collegate stanno in ia.yaml (lo scrive il menu "Collega le IA")
    try:
        ia = _leggi_yaml(os.path.join(cartella, "ia.yaml"))
    except ErroreImpostazioni:
        ia = {}
    if ia:
        cfg = unisci(cfg, {"ia": ia})
    # i tasti scritti come numeri (1, 2...) diventano testo
    cfg["tasti"] = {str(k): str(v) for k, v in (cfg.get("tasti") or {}).items() if v is not None}
    return cfg


def salva_calibrazione(cartella, percorso_chiavi, valore):
    """Scrive un valore in calibrazione.yaml, es. salva_calibrazione(c, ['mira', 'pixel_per_passo'], 0.8)."""
    p = os.path.join(cartella, "calibrazione.yaml")
    dati = _leggi_yaml(p)
    d = dati
    for k in percorso_chiavi[:-1]:
        if not isinstance(d.get(k), dict):
            d[k] = {}
        d = d[k]
    d[percorso_chiavi[-1]] = valore
    with open(p, "w", encoding="utf-8") as f:
        f.write("# Scritto dal bot quando calibri. Vince su impostazioni.yaml.\n"
                "# Cancella questo file (o una riga) per tornare alle impostazioni di prima.\n")
        yaml.safe_dump(dati, f, allow_unicode=True, sort_keys=False, default_flow_style=None)
    return p
