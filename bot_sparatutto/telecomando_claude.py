"""
telecomando_claude.py - per far GIOCARE (o controllare) CLAUDE quando lo colleghi al PC.

Claude non puo' guardare un video: guarda UNA FOTO, pensa e manda UNA MOSSA. Per questo ci sono
3 comandi che si usano dalla riga di comando, nella cartella del bot:

    BotSparatutto.exe foto
        fa una foto di PS Remote Play (per_claude/foto.jpg) e scrive cosa legge il bot
        (bussola, minimappa, vita, scritta "E Apri", compagni, casse e nemici visti)

    BotSparatutto.exe leggi
        come "foto" ma scrive solo quello che legge (senza salvare la foto)

    BotSparatutto.exe mossa "gira 40, corri 3, tieni e 1.2"
        manda la mossa alla schedina (stesso linguaggio di istruzioni.txt: premi X, tieni X 2,
        gira 90 / gira -45, aspetta 1, clicca...) piu' qualche parola in piu':
            corri 3        avanti + scatto per 3 secondi
            avanti 2       (anche indietro / sinistra / destra) cammina 2 secondi
            punta 290      si gira verso 290 della bussola (controlla la bussola e si corregge)
            guarda giu 20  (o su) sposta lo sguardo di 20 gradi
            spara 0.5      tiene premuto il tasto per sparare
        poi molla tutti i tasti, fa la foto e scrive cosa legge.

Aggiungi --prova per non premere niente (la schedina non serve: per provare).
"""

import os
import re
import time

import cv2

import hud

CARTELLA = "per_claude"


def _cosa_legge(img, occhi=None):
    """Quello che il bot legge dalla foto, in righe di testo semplici."""
    righe = []
    if img is None:
        return ["Nessuna foto (lo schermo non si cattura)."]
    H, W = img.shape[:2]
    righe.append("foto %dx%d" % (W, H))
    numero = hud.leggi_bussola(img)
    righe.append("bussola: %s" % (numero if numero is not None else "non letta"))
    m = hud.leggi_minimappa(img)
    nomi = {0: "?", 1: "terra", 2: "acqua", 3: "TEMPESTA"}
    if m.ok:
        def g(v):
            return "-" if v is None else "%.0f" % v
        righe.append("minimappa: sono su %s | tempesta %.0f%% acqua %.0f%% | fuori dalla tempesta verso %s | "
                     "terra verso %s | lontano dalla tempesta verso %s" % (
                         nomi.get(m.qui, "?"), 100 * m.tempesta, 100 * m.acqua, g(m.verso_fuori_tempesta()),
                         g(m.verso_terra()), g(m.lontano_dalla_tempesta())))
    else:
        righe.append("minimappa: non la vedo")
    vita, scudo = hud.leggi_vita(img)
    righe.append("vita: %s  scudo: %s" % (vita if vita is not None else "?", scudo if scudo is not None else "?"))
    righe.append("barra delle armi: %s | bus probabile: %s | spettatore: %s" % (
        "si" if hud.barra_armi(img) else "no", "si" if (numero is not None and not hud.barra_armi(img)) else "no",
        "si" if hud.spettatore(img) else "no"))
    tipo = hud.tipo_di_scritta(img)
    righe.append("scritta a destra del mirino: %s" % {None: "nessuna", "e": "SI (E: Apri/Raccogli/...)",
                                                      "spazio": "SI (tasto SPAZIO: bus o caduta)"}[tipo])
    righe.append("compagni: sopra la bussola %s | ai bordi %s | sulla minimappa %s | nomi sullo schermo %s" % (
        ", ".join("%+.0f" % d for d in hud.compagni_sulla_bussola(img)) or "-",
        ", ".join("%+.0f" % d for d in hud.compagni_ai_bordi(img)) or "-",
        ", ".join("%.0f gradi a %.0f%%" % (b, 100 * d) for b, d in hud.compagni_sulla_minimappa(img)) or "-",
        ", ".join("(%.2f, %.2f)" % xy for xy in hud.nomi_compagni(img)) or "-"))
    if occhi is not None:
        try:
            vis = occhi.analizza(img)
            for nome, lista in (("casse (luce dorata)", vis.casse), ("persone", vis.nemici)):
                righe.append("%s: %s" % (nome, ", ".join(
                    "x=%.2f y=%.2f alto=%.2f" % (b.cx / vis.larghezza, b.cy / vis.altezza, b.h / vis.altezza)
                    for b in lista[:6]) or "-"))
        except Exception as e:                       # gli occhi sono un aiuto: se sbagliano vado avanti
            righe.append("occhi: errore %s" % e)
    righe.append("(gradi della bussola: 0 nord, 90 est, 180 sud, 270 ovest; i compagni +/- = a destra/sinistra)")
    return righe


def _schermo(cfg):
    from occhi import Schermo
    sch = cfg.get("schermo", {}) or {}
    return Schermo(int(sch.get("monitor", 1) or 1), sch.get("zona_cattura"))


def _occhi(base, cfg):
    try:
        from occhi import Occhi
        return Occhi(cfg, base, lambda *a: None, universale=bool((cfg.get("rilevatore_universale") or {}).get("attivo")))
    except Exception:
        return None


def foto(base, cfg, salva=True, schermo=None, occhi=None):
    """-> (percorso della foto o None, righe di testo)."""
    hud.imposta_scala(float((cfg.get("hud", {}) or {}).get("scala", 1.0) or 1.0))
    schermo = schermo or _schermo(cfg)
    img = schermo.foto()
    percorso = None
    if salva and img is not None:
        cartella = os.path.join(base, CARTELLA)
        os.makedirs(cartella, exist_ok=True)
        piccola = img
        if img.shape[1] > 1280:
            piccola = cv2.resize(img, (1280, int(img.shape[0] * 1280 / img.shape[1])), interpolation=cv2.INTER_AREA)
        percorso = os.path.join(cartella, "foto.jpg")
        cv2.imwrite(percorso, piccola, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return percorso, _cosa_legge(img, occhi if occhi is not None else _occhi(base, cfg))


# parole in piu' rispetto al linguaggio di istruzioni.txt
_MUOVI = {"avanti": "avanti", "indietro": "indietro", "sinistra": "sinistra", "destra": "destra"}


def traduci(testo):
    """Le parole in piu' (corri, avanti, guarda, spara) -> il linguaggio di istruzioni.txt.
    -> lista di pezzi: ("istruzione", testo) oppure ("guarda", gradi) oppure ("corri", secondi)."""
    pezzi = []
    testo = re.sub(r"(\d),(\d)", r"\1.\2", testo)        # "1,5" = 1.5 (come si scrive in italiano)
    for parte in re.split(r"[,;\n]+", testo):
        p = " ".join(parte.lower().split())
        if not p:
            continue
        parole = p.split(" ")
        if parole[0] == "corri" and len(parole) == 2:
            pezzi.append(("corri", float(parole[1])))
        elif parole[0] in _MUOVI and len(parole) == 2:
            pezzi.append(("istruzione", "tieni %s %s" % (_MUOVI[parole[0]], parole[1])))
        elif parole[0] == "guarda" and len(parole) == 3 and parole[1] in ("giu", "giù", "su"):
            gradi = float(parole[2])
            pezzi.append(("guarda", gradi if parole[1] != "su" else -gradi))
        elif parole[0] == "punta" and len(parole) == 2:
            pezzi.append(("punta", float(parole[1]) % 360.0))
        elif parole[0] == "spara" and len(parole) == 2:
            pezzi.append(("istruzione", "tieni spara %s" % parole[1]))
        else:
            pezzi.append(("istruzione", p))
    return pezzi


def _punta(esecutore, schermo, voluti, tentativi=4, tolleranza=4.0):
    """Si gira finche' la bussola dice 'voluti' (la sensibilita' puo' essere sbagliata: si corregge)."""
    letto = None
    for _ in range(tentativi):
        letto = hud.leggi_bussola(schermo.foto())
        if letto is None:
            return "punta %.0f: bussola non letta (giro non fatto)" % voluti
        manca = hud.differenza(voluti, letto)
        if abs(manca) <= tolleranza:
            return "punta %.0f (bussola %d)" % (voluti, letto)
        esecutore.gira(manca)
        time.sleep(0.25)
    letto = hud.leggi_bussola(schermo.foto())
    return "punta %.0f: arrivato a %s" % (voluti, letto if letto is not None else "?")


def prepara_mossa(testo, tasto_esiste):
    """Controlla TUTTA la mossa prima di premere qualcosa (un errore a meta' lascerebbe il
    personaggio girato o fermo a meta'). -> lista di (tipo, valore) pronta da eseguire."""
    from istruzioni import leggi_azioni
    pronta = []
    for tipo, valore in traduci(testo):
        if tipo == "istruzione":
            pronta.append(("azioni", (valore, leggi_azioni(valore, tasto_esiste))))
        else:
            pronta.append((tipo, valore))
    if not pronta:
        raise ValueError("mossa vuota")
    return pronta


def mossa(base, cfg, testo, prova=False, log=print, mani=None, schermo=None, occhi=None):
    """Esegue la mossa con la schedina, molla i tasti, fa la foto. -> (percorso, righe)."""
    from istruzioni import Esecutore
    from mani import crea_mani
    mani = mani or crea_mani(cfg, log, "prova" if prova else None)
    try:
        pronta = prepara_mossa(testo, mani.esiste)
    except Exception as e:
        try:
            mani.chiudi()
        except Exception:
            pass
        return None, ["NON FATTO (non ho capito la mossa): %s" % e]
    schermo = schermo or _schermo(cfg)
    occhi = occhi if occhi is not None else _occhi(base, cfg)
    esecutore = Esecutore(mani, occhi, schermo, cfg, None, log, {}, {})
    fatto = []
    try:
        for tipo, valore in pronta:
            if tipo == "corri":
                for nome in ("avanti", "corri"):
                    if mani.esiste(nome):
                        mani.giu(nome)
                try:
                    time.sleep(max(0.0, min(15.0, valore)))
                finally:
                    for nome in ("corri", "avanti"):
                        if mani.esiste(nome):
                            mani.su(nome)
                fatto.append("corri %.1f" % valore)
            elif tipo == "punta":
                fatto.append(_punta(esecutore, schermo, valore))
            elif tipo == "guarda":
                passi = valore / 360.0 * esecutore.passi_per_giro
                pezzi = 20
                for _ in range(pezzi):
                    mani.muovi(0, passi / pezzi)
                    time.sleep(0.01)
                fatto.append("guarda %s %.0f" % ("giu" if valore >= 0 else "su", abs(valore)))
            else:
                scritto, azioni = valore
                esecutore.esegui(azioni)
                fatto.append(scritto)
    finally:
        try:
            mani.rilascia_tutto()
        except Exception:
            pass
    time.sleep(0.3)
    percorso, righe = foto(base, cfg, True, schermo, occhi)
    try:
        mani.chiudi()
    except Exception:
        pass
    return percorso, ["fatto: " + " | ".join(fatto)] + righe


def comando(base, cfg, argomenti, log=print):
    """Dalla riga di comando: foto | leggi | mossa "..." [--prova]."""
    prova = "--prova" in argomenti
    argomenti = [a for a in argomenti if a != "--prova"]
    if not argomenti:
        print(__doc__)
        return 1
    cosa = argomenti[0].lower()
    if cosa == "foto":
        percorso, righe = foto(base, cfg)
        print("FOTO: %s" % percorso)
    elif cosa == "leggi":
        percorso, righe = foto(base, cfg, salva=False)
    elif cosa == "mossa":
        if len(argomenti) < 2:
            print('Scrivi la mossa, es:  mossa "gira 40, corri 3, tieni e 1.2"')
            return 1
        percorso, righe = mossa(base, cfg, " ".join(argomenti[1:]), prova=prova, log=log)
        if percorso is None and righe and righe[0].startswith("NON FATTO"):
            print(righe[0])
            return 1
        print("FOTO: %s" % percorso)
    else:
        print(__doc__)
        return 1
    for r in righe:
        print(r)
    return 0
