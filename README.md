# Schedina per la PlayStation (Raspberry Pi Pico)

## ⬇️ [Scarica SchedinaPico.uf2](https://github.com/l13291221-cmyk/Soldi-bunker-/releases/download/auto-clicker/SchedinaPico.uf2)

Un solo file con dentro già tutto (CircuitPython + `code.py` + `impostazioni.txt` + guida).
La schedina attaccata alla Play fa da **tastiera + mouse** e fa da sola:
- **gioca a caso**: cammina, gira, spara, spara in aria, salta, si accovaccia, ricarica, sta fermo;
- **in sottofondo i due dadi da 1.000.000 di facce**: uno decide quando cliccare (attesa da 0 a 40 secondi),
  l'altro dove (spostamento casuale intorno al punto); 1 volta su 10 pausa lunga di 2-4 minuti.

Il click funziona nei giochi e nelle schermate della Play dove compare il cursore del mouse.

1. Clicca il link qui sopra **dal computer**: si scarica `SchedinaPico.uf2`.
2. Tieni premuto il pulsantino bianco **BOOTSEL** sulla schedina, attaccala al PC e lascia il pulsante.
   Compare la chiavetta **RPI-RP2**: **trascinaci dentro il file**. Dopo qualche secondo diventa
   **CIRCUITPY**, con dentro già tutto.
3. **Subito dopo premi BLOC MAIUSC** sul PC (lucina fissa = ferma, non muove il mouse del PC). Stacca la schedina.
4. Trova il punto da cliccare con la modalità *righello* (è già impostata) e poi scegli la modalità in
   `impostazioni.txt`: è tutto spiegato nella guida, che trovi anche sulla chiavetta (`LEGGIMI_GUIDA.txt`).

Gli stessi file separati, come prima: [SchedinaPico.zip](https://github.com/l13291221-cmyk/Soldi-bunker-/releases/download/auto-clicker/SchedinaPico.zip)

---

# Preme il tasto P da solo (Windows)

## ⬇️ [Scarica AutoClicker.exe](https://github.com/l13291221-cmyk/Soldi-bunker-/releases/download/auto-clicker/AutoClicker.exe)

1. Clicca il link qui sopra: si scarica `AutoClicker.exe`.
2. Aprilo con **doppio click**. Non serve installare Python né altro.
3. Hai 5 secondi: clicca sulla finestra dove vuoi che prema **P** e lasciala in primo piano.
   Da lì in poi preme P da solo.

**Quando preme:** a ogni giro tira un dado da 1 a 1.000.000 e aspetta
(dado / 1.000.000) × 40 secondi, quindi sempre meno di 40 secondi.
Con un altro dado, una volta su 10 fa una pausa lunga di 2-4 minuti.

**Per fermarlo:** chiudi la finestra nera con la X, oppure cliccaci sopra e premi **CTRL+C**
(o porta il mouse in un angolo dello schermo).

**Se Windows mostra "Windows ha protetto il PC":** clicca *Ulteriori informazioni* → *Esegui comunque*.

---

# Bot sparatutto (Raspberry Pi Pico + PC)

## ⬇️ [Scarica il file per la schedina (BotSparatutto_Schedina.uf2)](https://github.com/l13291221-cmyk/Soldi-bunker-/releases/download/bot-sparatutto/BotSparatutto_Schedina.uf2)

**È già tutto pronto, 3 passi:**

1. Clicca il link qui sopra: si scarica `BotSparatutto_Schedina.uf2`.
2. Tieni premuto il pulsantino bianco **BOOTSEL** sulla Raspberry Pi Pico, attaccala al PC
   (con un cavo che passa i dati) e lascia il pulsante. Compare la chiavetta **RPI-RP2**:
   **trascinaci dentro il file**. Dopo qualche secondo diventa la chiavetta **CIRCUITPY**,
   con dentro già tutto.
3. Nella chiavetta CIRCUITPY fai **doppio click su `AVVIA IL BOT`**. La prima volta scarica da solo
   il programma per il PC (circa 100 MB, in `Documenti\BotSparatutto`) e mette un collegamento sul
   desktop. Nel menu scegli **1** e clicca sulla finestra del gioco.

**F8** = pausa / riprendi, **F9** = chiude. Se chiudi il programma o stacchi la schedina,
la schedina rilascia da sola tutti i tasti.

## Cosa fa

**Obiettivo (scritto nel codice):** vincere la partita (restare vivo ed eliminare i nemici)
e aprire più casse possibili (casse delle armi e casse dei materiali).

- Il programma sul PC **guarda lo schermo** e decide; la schedina **Raspberry Pi Pico** fa da
  tastiera + mouse e preme i tasti. Il gioco gira sullo stesso PC, oppure sulla **Play**:
  il PC la guarda con PS Remote Play e un Arduino UNO fa da ponte verso la schedina
  attaccata alla Play (guida, parte G).
- **Si adatta a ogni gioco:** un "occhio universale" (rete neurale YOLOX) riconosce i personaggi
  in qualsiasi gioco; a inizio partita impara da solo sensibilità del mouse e giro completo,
  mentre spara impara la forza giusta della mira, e capisce da solo che il tuo personaggio
  non è un nemico. Con *Impara guardando me* impara i colori delle casse guardando te giocare.
- **Comandi stile Fortnite** (tastiera e mouse) già impostati in `impostazioni.yaml`, modificabili.
- **Impara guardando te** (menu 4): giochi tu una partita e lui impara i colori delle casse, dove mirare
  e **i pulsanti da cliccare per passare alla partita successiva**. Non ti copia: poi gioca a modo suo.
- **L'obiettivo lo scrivi tu** (menu 11 o `obiettivo.txt`), es. *aprire 50 casse a partita*,
  *aprire più casse possibili*, *eliminare più nemici possibili*, *sopravvivere*.
- **Le tue istruzioni** in `istruzioni.txt`, es.
  `QUANDO vedi squadra_eliminata FAI aspetta 3, clicca gioca_ancora` (passa da solo alla partita successiva).

Guida completa: [`bot_sparatutto/GUIDA.txt`](bot_sparatutto/GUIDA.txt)
(sul PC: `Documenti\BotSparatutto\LEGGIMI_GUIDA.txt`).
Da usare solo nei giochi/modalità dove è permesso (contro personaggi offline).

Il programma per il PC da solo, se serve:
[BotSparatutto.zip](https://github.com/l13291221-cmyk/Soldi-bunker-/releases/download/bot-sparatutto/BotSparatutto.zip).
I file vengono ricreati da GitHub ogni volta che cambia la cartella `bot_sparatutto`.
