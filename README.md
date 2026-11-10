# Preme il tasto P da solo (Windows)

## ⬇️ [Scarica AutoClicker.exe](https://github.com/l13291221-cmyk/Soldi-bunker-/releases/latest/download/AutoClicker.exe)

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
Succede con tutti i programmi scaricati che non hanno una firma digitale a pagamento.

---

L'exe viene ricreato da GitHub ogni volta che cambia `auto_clicker.py`.
In alternativa, con Python installato: `pip install pyautogui` e poi `python auto_clicker.py`.

---

# Schedina per la PlayStation (Raspberry Pi Pico)

## ⬇️ [Scarica SchedinaPico.zip](https://github.com/l13291221-cmyk/Soldi-bunker-/releases/latest/download/SchedinaPico.zip)

Una schedina Raspberry Pi Pico attaccata alla Play fa da **tastiera + mouse** e fa da sola:
- **gioca a caso**: cammina, gira, spara, spara in aria, salta, si accovaccia, ricarica, sta fermo;
- **in sottofondo i due dadi da 1.000.000 di facce**: uno decide quando cliccare (attesa da 0 a 40 secondi),
  l'altro dove (spostamento casuale intorno al punto); 1 volta su 10 pausa lunga di 2-4 minuti.

Dentro lo zip c'è tutto, compresa la guida passo passo (`LEGGIMI_GUIDA.txt`).
Le impostazioni si cambiano nel file `impostazioni.txt` sulla schedina, con Blocco note.
