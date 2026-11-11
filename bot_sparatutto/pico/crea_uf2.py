"""
crea_uf2.py - Crea UN SOLO file .uf2 per la Raspberry Pi Pico con dentro:
  - CircuitPython (il "sistema" della schedina)
  - la chiavetta CIRCUITPY gia' piena: boot.py, code.py, "AVVIA IL BOT.cmd"...

Cosi' basta trascinare il file sulla schedina (tenendo premuto BOOTSEL) e
e' tutto pronto: niente file da copiare a mano, niente da staccare e riattaccare.

Uso (lo fa GitHub da solo):
  python crea_uf2.py --circuitpython adafruit-circuitpython-raspberry_pi_pico-en_US-10.3.1.uf2 \\
                     --uscita BotSparatutto_Schedina.uf2 --versione 12 --url-zip https://...

Dove va la chiavetta nella memoria (CircuitPython 10, chip RP2040 della Pico):
  ports/raspberrypi/mpconfigport.h -> CIRCUITPY_FIRMWARE_SIZE = 1020 KB, poi 4 KB di NVM,
  poi la chiavetta da 0x100000 fino alla fine dei 2 MB: 2048 blocchi da 512 byte (FAT12).
"""

import argparse
import os
import struct
import time

# ------------------------------------------------------------------ UF2
UF2_MAGIC0 = 0x0A324655
UF2_MAGIC1 = 0x9E5D5157
UF2_MAGIC_FINE = 0x0AB16F30
UF2_CON_FAMIGLIA = 0x00002000
FAMIGLIA_RP2040 = 0xE48BFF56
INIZIO_FLASH = 0x10000000
INDIRIZZO_CHIAVETTA = INIZIO_FLASH + 0x100000
FINE_FIRMWARE = INIZIO_FLASH + 1020 * 1024
SETTORE = 512
SETTORI_CHIAVETTA = 2048
_FORMATO = "<IIIIIIII476sI"


def leggi_uf2(dati):
    """-> lista di (indirizzo, contenuto) dei blocchi di un file UF2."""
    blocchi = []
    for i in range(0, len(dati) - 511, 512):
        m0, m1, flag, indirizzo, n, _, _, famiglia, contenuto, mf = struct.unpack(_FORMATO, dati[i:i + 512])
        if m0 != UF2_MAGIC0 or m1 != UF2_MAGIC1 or mf != UF2_MAGIC_FINE:
            raise ValueError("il file non e' un UF2 valido (blocco %d)" % (i // 512))
        if flag & UF2_CON_FAMIGLIA and famiglia != FAMIGLIA_RP2040:
            raise ValueError("questo UF2 non e' per la Raspberry Pi Pico (RP2040)")
        blocchi.append((indirizzo, contenuto[:n]))
    return blocchi


def scrivi_uf2(blocchi):
    uscita = bytearray()
    for numero, (indirizzo, contenuto) in enumerate(blocchi):
        uscita += struct.pack(_FORMATO, UF2_MAGIC0, UF2_MAGIC1, UF2_CON_FAMIGLIA, indirizzo, len(contenuto),
                              numero, len(blocchi), FAMIGLIA_RP2040, contenuto.ljust(476, b"\x00"),
                              UF2_MAGIC_FINE)
    return bytes(uscita)


# ------------------------------------------------------------------ chiavetta FAT12
_VALIDI_83 = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789$%'-_@~`!(){}^#&")


def _data_dos(t):
    data = ((t.tm_year - 1980) << 9) | (t.tm_mon << 5) | t.tm_mday
    ora = (t.tm_hour << 11) | (t.tm_min << 5) | (t.tm_sec // 2)
    return data, ora


def _nome_83(nome, usati):
    """-> (11 byte del nome corto, flag maiuscole/minuscole, serve il nome lungo?)"""
    base, _, est = nome.rpartition(".") if "." in nome else (nome, "", "")
    ok = (1 <= len(base) <= 8 and len(est) <= 3 and nome.count(".") <= 1
          and all(c.upper() in _VALIDI_83 for c in base + est))
    if ok and (base.isupper() or base.islower() or not any(c.isalpha() for c in base)) \
            and (est.isupper() or est.islower() or not any(c.isalpha() for c in est)):
        flag = (0x08 if base.islower() else 0) | (0x10 if est.islower() else 0)
        corto = (base.upper().ljust(8) + est.upper().ljust(3)).encode("ascii")
        if corto not in usati:
            return corto, flag, False
    pulito = "".join(c for c in base.upper() if c in _VALIDI_83) or "FILE"
    est_pulita = "".join(c for c in est.upper() if c in _VALIDI_83)[:3]
    for n in range(1, 100):
        coda = "~%d" % n
        corto = ((pulito[:8 - len(coda)] + coda).ljust(8) + est_pulita.ljust(3)).encode("ascii")
        if corto not in usati:
            return corto, 0, True
    raise ValueError("troppi file con nomi simili")


def _somma_lfn(corto):
    s = 0
    for c in corto:
        s = (((s & 1) << 7) + (s >> 1) + c) & 0xFF
    return s


def _voci_lfn(nome, corto):
    caratteri = list(nome.encode("utf-16-le"))
    unita = [caratteri[i] | (caratteri[i + 1] << 8) for i in range(0, len(caratteri), 2)]
    if len(unita) % 13:          # fine del nome (non serve se riempie esattamente l'ultimo pezzo)
        unita.append(0x0000)
        while len(unita) % 13:
            unita.append(0xFFFF)
    pezzi = [unita[i:i + 13] for i in range(0, len(unita), 13)]
    somma = _somma_lfn(corto)
    voci = []
    for i, p in enumerate(pezzi, 1):
        ordine = i | (0x40 if i == len(pezzi) else 0)
        voce = struct.pack("<B5HBBB6HH2H", ordine, *p[0:5], 0x0F, 0, somma, *p[5:11], 0, *p[11:13])
        voci.append(voce)
    return list(reversed(voci))


def crea_fat12(file, etichetta="CIRCUITPY", settori=SETTORI_CHIAVETTA, quando=None):
    """file = lista di (nome, contenuto bytes). Restituisce l'immagine della chiavetta (bytes)."""
    t = time.gmtime(quando if quando is not None else time.time())
    data, ora = _data_dos(t)
    voci_root = 512
    settori_root = voci_root * 32 // SETTORE
    riservati = 1
    num_fat = 1
    settori_fat = 1
    while True:
        dati = settori - riservati - num_fat * settori_fat - settori_root
        byte_fat = ((dati + 2) * 3 + 1) // 2
        servono = (byte_fat + SETTORE - 1) // SETTORE
        if servono <= settori_fat:
            break
        settori_fat = servono
    cluster_totali = dati
    if cluster_totali >= 4085:
        raise ValueError("troppo grande per FAT12")

    img = bytearray(settori * SETTORE)
    # settore di avvio
    bs = bytearray(SETTORE)
    bs[0:3] = b"\xEB\xFE\x90"
    bs[3:11] = b"MSDOS5.0"
    struct.pack_into("<HBHBHHBHHHII", bs, 11, SETTORE, 1, riservati, num_fat, voci_root, settori, 0xF8,
                     settori_fat, 63, 255, 0, 0)
    struct.pack_into("<BBBI", bs, 36, 0x80, 0, 0x29, int(time.mktime(t)) & 0xFFFFFFFF)
    bs[43:54] = etichetta.upper().ljust(11)[:11].encode("ascii")
    bs[54:62] = b"FAT12   "
    bs[510:512] = b"\x55\xAA"
    img[0:SETTORE] = bs

    fat = bytearray(settori_fat * SETTORE)

    def metti_fat(n, v):
        o = n + n // 2
        if n % 2 == 0:
            fat[o] = v & 0xFF
            fat[o + 1] = (fat[o + 1] & 0xF0) | ((v >> 8) & 0x0F)
        else:
            fat[o] = (fat[o] & 0x0F) | ((v & 0x0F) << 4)
            fat[o + 1] = (v >> 4) & 0xFF
    metti_fat(0, 0xFF8)
    metti_fat(1, 0xFFF)

    inizio_root = (riservati + num_fat * settori_fat) * SETTORE
    inizio_dati = inizio_root + settori_root * SETTORE
    root = bytearray()
    root += struct.pack("<11sBBBHHHHHHHI", etichetta.upper().ljust(11)[:11].encode("ascii"), 0x08, 0, 0,
                        ora, data, data, 0, ora, data, 0, 0)
    usati = set()
    prossimo = 2
    for nome, contenuto in file:
        corto, flag, lungo = _nome_83(nome, usati)
        usati.add(corto)
        n_cluster = (len(contenuto) + SETTORE - 1) // SETTORE
        primo = prossimo if n_cluster else 0
        if prossimo + n_cluster - 2 > cluster_totali:
            raise ValueError("i file non entrano nella chiavetta")
        for i in range(n_cluster):
            c = prossimo + i
            metti_fat(c, c + 1 if i + 1 < n_cluster else 0xFFF)
            pos = inizio_dati + (c - 2) * SETTORE
            pezzo = contenuto[i * SETTORE:(i + 1) * SETTORE]
            img[pos:pos + len(pezzo)] = pezzo
        prossimo += n_cluster
        if lungo:
            for v in _voci_lfn(nome, corto):
                root += v
        root += struct.pack("<11sBBBHHHHHHHI", corto, 0x20, flag, 0, ora, data, data, 0, ora, data,
                            primo, len(contenuto))
    if len(root) > voci_root * 32:
        raise ValueError("troppi file")
    for k in range(num_fat):
        o = (riservati + k * settori_fat) * SETTORE
        img[o:o + len(fat)] = fat
    img[inizio_root:inizio_root + len(root)] = root
    return bytes(img)


def uf2_con_chiavetta(dati_circuitpython, immagine):
    blocchi = leggi_uf2(dati_circuitpython)
    for indirizzo, contenuto in blocchi:
        if indirizzo + len(contenuto) > FINE_FIRMWARE:
            raise ValueError("questo CircuitPython usa una memoria diversa (blocco a 0x%08X)" % indirizzo)
    for i in range(0, len(immagine), 256):
        blocchi.append((INDIRIZZO_CHIAVETTA + i, immagine[i:i + 256]))
    return scrivi_uf2(blocchi)


# ------------------------------------------------------------------ i file della schedina del bot
QUI = os.path.dirname(os.path.abspath(__file__))
FILE_SCHEDINA = [
    # (nome sulla chiavetta, file qui)
    ("AVVIA IL BOT.cmd", "avvia_il_bot.cmd"),
    ("LEGGIMI.txt", "leggimi_chiavetta.txt"),
    ("boot.py", "boot.py"),
    ("code.py", "code.py"),
    ("installa.ps1", "installa.ps1"),
]


def file_del_bot(versione, url_zip):
    risultato = []
    for nome, sorgente in FILE_SCHEDINA:
        with open(os.path.join(QUI, sorgente), "rb") as f:
            contenuto = f.read()
        if sorgente.endswith((".cmd", ".ps1", ".txt")):
            testo = contenuto.decode("utf-8").replace("\r\n", "\n")
            testo = testo.replace("__VERSIONE__", str(versione)).replace("__URL_ZIP__", url_zip)
            contenuto = testo.replace("\n", "\r\n").encode("utf-8-sig" if sorgente.endswith(".ps1") else "utf-8")
        risultato.append((nome, contenuto))
    return risultato


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--circuitpython", required=True, help="il file .uf2 di CircuitPython per la Raspberry Pi Pico")
    p.add_argument("--uscita", required=True)
    p.add_argument("--versione", default="1")
    p.add_argument("--url-zip", required=True, help="da dove 'AVVIA IL BOT' scarica il programma per il PC")
    p.add_argument("--immagine", help="salva anche l'immagine della chiavetta (per controllarla)")
    a = p.parse_args()
    immagine = crea_fat12(file_del_bot(a.versione, a.url_zip))
    if a.immagine:
        with open(a.immagine, "wb") as f:
            f.write(immagine)
    with open(a.circuitpython, "rb") as f:
        dati = f.read()
    with open(a.uscita, "wb") as f:
        f.write(uf2_con_chiavetta(dati, immagine))
    print("Creato %s (%d KB)" % (a.uscita, os.path.getsize(a.uscita) // 1024))


if __name__ == "__main__":
    main()
