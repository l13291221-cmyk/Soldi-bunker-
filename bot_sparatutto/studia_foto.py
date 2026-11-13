"""
studia_foto.py - L'IA STUDIA LE FOTO (menu 16).

Il bot salva da solo le foto delle partite in foto_per_ia, con dei rettangoli (le
"etichette") scritti da lui: ma sono spesso sbagliati (prende il TUO personaggio per un
nemico e la punta dorata del piccone o le icone gialle per casse).
Qui ogni foto va all'IA che guarda (meglio Gemini: menu 15) che, sapendo come funziona
Fortnite (fortnite.txt), dice dove sono DAVVERO i nemici, le casse, le casse dei materiali
e le armi. Le etichette giuste vengono riscritte nella cartella labels: con quelle si
addestra l'occhio del tuo gioco (guida, parte F) e il bot riconosce nemici e casse molto meglio.

Le foto gia' studiate sono scritte in foto_per_ia/studiate.txt: se interrompi (Ctrl+C) o
finiscono le richieste gratis, la volta dopo riparte da dove era arrivato.
"""

import json
import os
import re
import time

import ia as modulo_ia
from apprendimento import CLASSI_DATASET

# i nomi che usa l'IA (inglese) -> le classi del bot (stesso ordine di dataset.yaml)
NOMI = {
    "enemy": "nemico", "player": "nemico", "opponent": "nemico", "nemico": "nemico",
    "chest": "cassa", "cassa": "cassa",
    "ammo_box": "materiali", "ammo box": "materiali", "ammo": "materiali", "supply": "materiali",
    "materials": "materiali", "materiali": "materiali",
    "weapon": "arma", "item": "arma", "arma": "arma",
}

DOMANDA_FOTO = (
    "This is a screenshot of Fortnite (third-person battle royale). Find ONLY these things in the 3D world:\n"
    "- enemy: an OPPONENT player (a character of another team). NOT the player's own character "
    "(the one in the lower middle of the screen, usually seen from behind), NOT teammates (they have a "
    "colored name tag above the head), NOT animals or pets following the player, NOT characters in "
    "menus, lobby, reward or end-of-match screens.\n"
    "- chest: a loot chest (wooden chest with gold trim, glowing gold and sparkling when closed). "
    "NOT the glowing tip of the player's pickaxe, NOT yellow icons or markers of the interface "
    "(icons with a distance in meters), NOT lamps, lights or yellow leaves.\n"
    "- ammo_box: an ammo box or small supply box (small grey/green box).\n"
    "- weapon: a weapon or item lying on the ground (floor loot, often with a colored glow).\n"
    "Ignore everything of the interface (HUD): health bars, minimap, compass, inventory, kill feed, "
    "icons, texts.\n"
    "Answer ONLY with one JSON object, no other text:\n"
    '{"objects": [{"label": "enemy|chest|ammo_box|weapon", "box_2d": [ymin, xmin, ymax, xmax]}]}\n'
    "box_2d = the box around the object, with coordinates from 0 to 1000 (0,0 = top left). "
    'If there is nothing, answer {"objects": []}.'
)


def leggi_oggetti(testo):
    """Dal testo dell'IA alla lista [(classe, x1, y1, x2, y2)] con coordinate da 0 a 1.
    None se la risposta non si capisce (cosi' la foto si riprova la volta dopo)."""
    if testo is None:
        return None
    testo = str(testo)
    dati = None
    for pezzo in (re.search(r"\{.*\}", testo, re.S), re.search(r"\[.*\]", testo, re.S)):
        if pezzo is None:
            continue
        try:
            valore = json.loads(pezzo.group(0))
        except ValueError:
            continue
        if isinstance(valore, dict) and isinstance(valore.get("objects", valore.get("oggetti")), list):
            dati = valore.get("objects", valore.get("oggetti"))      # {"objects": [...]}
        elif isinstance(valore, list):
            dati = valore                                            # [...] da solo
        elif isinstance(valore, dict) and ("label" in valore or "box_2d" in valore):
            dati = [valore]                                          # un oggetto solo
        if dati is not None:
            break
    if not isinstance(dati, list):
        return None
    risultato = []
    for o in dati:
        if not isinstance(o, dict):
            continue
        nome = str(o.get("label") or o.get("class") or o.get("classe") or "").strip().lower()
        classe = NOMI.get(nome)
        box = o.get("box_2d") or o.get("box")
        if classe is None or not isinstance(box, (list, tuple)) or len(box) != 4:
            continue
        try:
            y1, x1, y2, x2 = [float(v) for v in box]
        except (TypeError, ValueError):
            continue
        scala = 1000.0 if max(abs(v) for v in (x1, y1, x2, y2)) > 1.0 else 1.0
        x1, x2 = sorted((min(1.0, max(0.0, x1 / scala)), min(1.0, max(0.0, x2 / scala))))
        y1, y2 = sorted((min(1.0, max(0.0, y1 / scala)), min(1.0, max(0.0, y2 / scala))))
        if x2 - x1 < 0.003 or y2 - y1 < 0.003:
            continue
        risultato.append((classe, x1, y1, x2, y2))
    return risultato


def righe_yolo(oggetti):
    """[(classe, x1, y1, x2, y2)] -> righe dell'etichetta YOLO ("classe cx cy w h")."""
    righe = []
    for classe, x1, y1, x2, y2 in oggetti:
        if classe not in CLASSI_DATASET:
            continue
        righe.append("%d %.6f %.6f %.6f %.6f" % (CLASSI_DATASET.index(classe), (x1 + x2) / 2, (y1 + y2) / 2,
                                                 x2 - x1, y2 - y1))
    return righe


def leggi_studiate(cartella):
    try:
        with open(os.path.join(cartella, "studiate.txt"), "r", encoding="utf-8") as f:
            return {r.strip() for r in f if r.strip() and not r.startswith("#")}
    except OSError:
        return set()


def segna_studiata(cartella, nome):
    with open(os.path.join(cartella, "studiate.txt"), "a", encoding="utf-8") as f:
        f.write(nome + "\n")


def scegli_fornitori(cfg):
    """Le IA collegate, prima quelle online (Gemini...). Ollama solo se c'e' davvero sul PC, e per
    ultima: e' lenta e trova male i rettangoli."""
    fornitori = modulo_ia.fornitori_da_cfg(cfg.get("ia", {}) or {})
    online = [f for f in fornitori if f["tipo"] != "ollama"]
    ollama = [f for f in fornitori if f["tipo"] == "ollama"]
    modello = modulo_ia.ollama_pronto() if ollama else None
    if modello:
        return online + [dict(ollama[0], modello=modello)]
    return online


def studia(base, cfg, log=print, invia=None, pausa=4.0, massimo=None, dormi=time.sleep):
    """Manda ogni foto di foto_per_ia all'IA e riscrive le etichette. -> quante foto ha studiato."""
    import cv2
    import numpy as np
    invia = invia or modulo_ia.invia_http
    cartella = os.path.join(base, "foto_per_ia")
    immagini = os.path.join(cartella, "images")
    etichette = os.path.join(cartella, "labels")
    print("\n" + "=" * 70)
    print("  L'IA STUDIA LE FOTO (trova nemici e casse nelle foto di foto_per_ia)")
    print("=" * 70)
    if not os.path.isdir(immagini):
        print("Non ci sono ancora foto: il bot le salva da solo mentre gioca (cartella foto_per_ia).")
        return 0
    fornitori = scegli_fornitori(cfg)
    if not fornitori:
        print("Non c'e' nessuna IA collegata. Collega Gemini con il tuo account Google (menu 15) e riprova.")
        return 0
    os.makedirs(etichette, exist_ok=True)
    gia = leggi_studiate(cartella)
    foto = sorted(f for f in os.listdir(immagini) if f.lower().endswith((".jpg", ".jpeg", ".png"))
                  and f not in gia)
    if massimo:
        foto = foto[:int(massimo)]
    if not foto:
        print("Tutte le foto sono gia' state studiate (%d). Quando il bot ne salva altre, rifallo." % len(gia))
        return 0
    conoscenza = modulo_ia.leggi_conoscenza(base) if (cfg.get("ia", {}) or {}).get("usa_conoscenza", True) else ""
    print("Foto da studiare: %d (gia' fatte: %d). IA: %s" % (len(foto), len(gia),
                                                             ", ".join(f["nome"] for f in fornitori)))
    print("Ci vogliono alcuni secondi a foto. Ctrl+C per fermarti: la prossima volta riparte da qui.")
    print("ATTENZIONE: le foto vengono mandate all'IA scelta.\n")
    studiate = 0
    conteggio = {c: 0 for c in CLASSI_DATASET}
    riposo = {}                                   # fornitore -> fino a quando non lo uso
    try:
        for i, nome in enumerate(foto):
            img = cv2.imdecode(np.fromfile(os.path.join(immagini, nome), np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                continue
            jpeg = modulo_ia.jpeg_base64(img, 1024, 85)
            oggetti = None
            for tentativo in range(3):
                pronti = [f for f in fornitori if riposo.get(f["nome"], 0) <= time.monotonic()]
                if not pronti:
                    attesa = max(1, int(min(riposo.values()) - time.monotonic()) + 1)
                    print("   aspetto %d secondi e riprovo..." % attesa, flush=True)
                    dormi(attesa)
                    continue
                f = pronti[0]
                try:
                    url, intest, corpo = modulo_ia.richiesta(f, jpeg, DOMANDA_FOTO, conoscenza, lunghezza=900)
                    testo = modulo_ia.testo_della_risposta(f, invia(url, intest, corpo, max(60, f["attesa"])))
                    oggetti = leggi_oggetti(testo)
                    if oggetti is None:
                        raise RuntimeError("risposta che non capisco: %r" % str(testo)[:80])
                    break
                except Exception as e:
                    riposo[f["nome"]] = time.monotonic() + (60.0 if "429" in str(e) else 15.0)
                    print("   %s: %s" % (f["nome"], e), flush=True)
            if oggetti is None:
                print("[%d/%d] %s: non ci sono riuscito, la riprovo la prossima volta" % (i + 1, len(foto), nome))
                continue
            righe = righe_yolo(oggetti)
            base_nome = os.path.splitext(nome)[0]
            with open(os.path.join(etichette, base_nome + ".txt"), "w", encoding="utf-8") as fl:
                fl.write("\n".join(righe) + ("\n" if righe else ""))
            segna_studiata(cartella, nome)
            studiate += 1
            trovati = {}
            for classe, *_ in oggetti:
                conteggio[classe] += 1
                trovati[classe] = trovati.get(classe, 0) + 1
            print("[%d/%d] %s: %s" % (i + 1, len(foto), nome, ", ".join(
                "%d %s" % (n, c) for c, n in trovati.items()) or "niente (ne' nemici ne' casse)"), flush=True)
            if pausa and i + 1 < len(foto):
                dormi(pausa)                      # per non finire subito le richieste gratis
    except KeyboardInterrupt:
        print("\nFermato: la prossima volta riparto da qui.")
    print("\nFoto studiate: %d. Trovati: %s." % (studiate, ", ".join("%d %s" % (n, c) for c, n in conteggio.items())))
    print("Le etichette giuste sono in foto_per_ia/labels: ora puoi addestrare l'occhio del tuo gioco "
          "(guida, parte F).")
    return studiate
