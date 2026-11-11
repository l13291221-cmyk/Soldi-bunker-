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
  tastiera + mouse e preme i tasti. Il gioco deve girare sullo stesso PC.
- **Si adatta a ogni gioco:** un "occhio universale" (rete neurale YOLOX) riconosce i personaggi
  in qualsiasi gioco; a inizio partita impara da solo sensibilità del mouse e giro completo,
  mentre spara impara la forza giusta della mira, e capisce da solo che il tuo personaggio
  non è un nemico. Con *Impara guardando me* impara i colori delle casse guardando te giocare.
- **Comandi stile Fortnite** (tastiera e mouse) già impostati in `impostazioni.yaml`, modificabili.
- **Le tue istruzioni** in `istruzioni.txt`, es.
  `QUANDO vedi squadra_eliminata FAI aspetta 3, clicca gioca_ancora` (passa da solo alla partita successiva).

Guida completa: [`bot_sparatutto/GUIDA.txt`](bot_sparatutto/GUIDA.txt)
(sul PC: `Documenti\BotSparatutto\LEGGIMI_GUIDA.txt`).
Da usare solo nei giochi/modalità dove è permesso (contro personaggi offline).

Il programma per il PC da solo, se serve:
[BotSparatutto.zip](https://github.com/l13291221-cmyk/Soldi-bunker-/releases/download/bot-sparatutto/BotSparatutto.zip).
I file vengono ricreati da GitHub ogni volta che cambia la cartella `bot_sparatutto`.
