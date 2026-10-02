# Nerodoro Studio

Landing page scura per vendere siti web a ogni tipo di attività, con pagamento Stripe e una piccola area admin protetta da PIN.

## Come funziona
1. Clicchi il **lucchetto in alto a destra** → inserisci il PIN → entri nell'admin.
2. Crei un ordine (nome attività, prezzo, link del sito, numero WhatsApp): viene generato un **codice** tipo `K7M2-P9QX`.
3. Premi **"Invia su WhatsApp"**: il messaggio con il codice e l'indirizzo del sito è già scritto.
4. Il cliente va sul sito, nella sezione **"Hai ricevuto un codice?"** inserisce il codice e apre il pagamento.
5. Paga con carta su **Stripe** e subito dopo **compare il link del suo sito**.
   Se non avevi ancora messo il link, lo aggiungi dall'admin e il cliente lo vede reinserendo il codice.

## Avvio in locale
```bash
npm install
cp .env.example .env   # poi compila ADMIN_PIN e STRIPE_SECRET_KEY
npm start              # http://localhost:3000
```

## Metterlo online (es. Render.com, gratis)
1. New → Web Service → collega questo repository.
2. Build command: `npm install` — Start command: `npm start`.
3. Environment variables:
   - `ADMIN_PIN` = il tuo PIN
   - `WHATSAPP` = (opzionale) il tuo numero WhatsApp Business, solo cifre con prefisso; di base è 27710933377
   - `STRIPE_SECRET_KEY` = chiave segreta da dashboard.stripe.com → Sviluppatori → Chiavi API (`sk_test_...` per provare, `sk_live_...` per incassare davvero)
   - `BASE_URL` = non serve su Render (lo prende da solo); mettilo solo se usi un dominio tuo
4. (Consigliato) Stripe → Webhook → endpoint `BASE_URL/api/stripe-webhook`, evento `checkout.session.completed`, poi metti il segreto in `STRIPE_WEBHOOK_SECRET`.

**Importante:** gli ordini sono salvati in `data/orders.json`. Sui piani gratuiti il disco può azzerarsi a ogni riavvio: aggiungi un disco persistente montato su `data/`, oppure tieni nota degli ordini.

Per provare i pagamenti in modalità test usa la carta `4242 4242 4242 4242`, qualsiasi data futura e CVC.

## Sveglia siti (anti-spegnimento)
Nell'admin, sezione **⏰ Sveglia siti**: aggiungi i link dei siti da tenere svegli.
Ogni 5 minuti il server li visita e visita anche se stesso (`/healthz`), così Render gratuito non li spegne.
L'auto-ping si attiva da solo su Render (usa `RENDER_EXTERNAL_URL`, che Render imposta in automatico).

Attenzione ai limiti del piano gratuito di Render:
- **750 ore gratis al mese per account**: un servizio sempre acceso ne usa ~744. Con 2 o più web service
  gratuiti sempre svegli sullo stesso account finisci le ore e Render li sospende fino al mese dopo.
- I siti dei clienti conviene pubblicarli come **Static Site** su Render: sono gratis, non si spengono mai
  e non consumano ore (non serve pingarli).
- Il piano gratuito non ha disco permanente: `data/*.json` (ordini ed elenco siti) si azzera a ogni deploy o riavvio.

## Trova clienti
Nell'admin, pulsante **🔎 Trova clienti**: scrivi un comune e il tipo di attività (ristoranti, bar, parrucchieri, negozi...).
Mostra solo le attività **senza sito** o con un **sito brutto** (controllato in automatico: non funziona, non va da telefono, senza https, lento, fermo da anni, in costruzione), con i pulsanti Chiama, Maps e "+ Ordine".
I dati vengono da OpenStreetMap (gratis): prima di chiamare controlla la scheda Google Maps.
I siti moderni (Next.js, React, Webflow...) non vengono più segnati come "quasi vuoti": caricano i testi con JavaScript.

### Fonte Google Maps (facoltativa)
**Senza chiave** (gratis): scegli **📍 Google Maps (apre l'app)**, scrivi la città e il tipo e premi **Apri Maps**: si apre Google Maps
(l'app sul telefono) già sulla ricerca, es. «Pizzerie a Monza». Le schede le guardi lì: i risultati non arrivano nella pagina e il bot
WhatsApp continua a usare solo OpenStreetMap.

**Con la chiave** i risultati arrivano direttamente nella pagina e nel bot:
Nel menu **Fonte** puoi scegliere **Google Maps** invece di OpenStreetMap: trova più attività, con telefono e sito aggiornati
(massimo 60 risultati per ricerca, quindi cerca città per città o per quartiere). I cellulari vengono proposti come WhatsApp "probabile".
Serve una chiave Google: su [Google Cloud](https://console.cloud.google.com) crea un progetto, attiva **Places API (New)**,
crea una chiave API (limitala a Places API) e aggiungila su Render come `GOOGLE_PLACES_KEY`. Google chiede un metodo di pagamento
ma ogni mese c'è una quota gratuita: controlla il listino e imposta un limite di spesa/avviso di budget.
Lo stato (chiamato / interessato / no) e gli appunti restano salvati nel browser del dispositivo che usi.

### Messaggi WhatsApp
Filtro **"Solo WhatsApp dichiarato"** + pulsante **💬 Scrivi su WhatsApp**: apre WhatsApp con un messaggio già scritto,
personalizzato con il nome dell'attività e il suo problema (senza sito, solo social, difetto del sito), in 5 lingue
(IT, EN, FR, ES, DE) e 3 versioni che si alternano. Il limite di messaggi al giorno si sceglie (30, 50, 75 o 100, predefinito 100); ogni 30 messaggi in un'ora consiglia una pausa.
Se il bot WhatsApp ha già scritto a un'attività, nella scheda compare «🤖 …»; se scrivi tu a mano, il bot non le scriverà più.

## 🤖 Bot WhatsApp (messaggi automatici)
Nell'admin, pulsante **🤖 Bot** (`/bot`): il sito scrive **da solo** dal vostro WhatsApp Business alle attività senza sito,
con solo i social o con il sito brutto, **20-30 messaggi al giorno sparsi nelle fasce orarie**, tutti i giorni, finché è acceso.

**Come si attiva**
1. Apri `/bot` → nella tabella **📱 Numeri WhatsApp** scegli il prefisso (🇮🇹 +39, 🇿🇦 +27, 🇬🇧 +44…) e scrivi il numero
   del WhatsApp Business (es. `333 1234567` o `071 093 3377`) → **Aggiungi e collega**.
2. Sul telefono: WhatsApp Business → ⋮ / Impostazioni → **Dispositivi collegati** → **Collega un dispositivo** →
   **Collega con il numero di telefono** → scrivi il codice che compare sotto il numero. (Oppure **QR** e inquadralo da un altro schermo.)
3. Controlla le impostazioni (zone, tipi di attività, fasce orarie, il tuo nome) e premi **Salva**.
4. Premi **Prova** sulla riga del numero e scrivi un tuo numero personale per vedere come arriva il messaggio.
5. Accendi l'interruttore in alto. Fine: il bot lavora da solo, anche a pagina chiusa.

**Cambiare numero**: aggiungi il numero nuovo nella tabella (con «Scrive solo questo numero» spunta, il vecchio si spegne da solo)
e collegalo. Ogni riga ha:
- **Scrive** (acceso/spento): solo i numeri accesi mandano i primi messaggi, ognuno con i suoi messaggi al giorno.
  I numeri spenti ma collegati restano in ascolto: le risposte dei clienti arrivano lo stesso nella pagina.
- **Collega / QR / Riprova / Prova / Scollega / Elimina**. Eliminare un numero lo scollega anche da WhatsApp.
- Stato, messaggi di oggi e in tutto, e la partenza graduale: **ogni numero nuovo riparte da 10 messaggi al giorno**.
Chi ha già ricevuto un messaggio da un numero non viene ricontattato dagli altri. Massimo 10 numeri.

**Cosa fa**
- **🎯 A chi scrivere**: Tutti, oppure solo Ristoranti, Pizzerie, Bar (e, se vuoi, altre attività). Si sceglie toccando, si salva da solo.
- Cerca i clienti come «Trova clienti»: **OpenStreetMap** (solo chi ha dichiarato il suo WhatsApp; con la zona «italia» cerca in
  tutta Italia) e, se c'è `GOOGLE_PLACES_KEY`, **Google Maps** (cellulari, città per città: più città e quartieri scrivi, più ne trova).
  Rifà le stesse ricerche ogni 30 giorni per trovare le attività nuove. Finite le zone scelte, con Google Maps continua da solo
  con gli altri comuni d'Italia, dal più grande al più piccolo (1.531 comuni sopra gli 8.000 abitanti, in `comuni-italia.json`):
  così anche con più numeri accesi (es. 3 numeri = 75-90 messaggi al giorno) il bot non resta senza locali a cui scrivere.
- Poco prima di scrivere controlla il sito (stessi controlli di «Trova clienti»): chi ha un sito fatto bene viene saltato.
- Controlla che il numero abbia davvero WhatsApp, simula la scrittura e manda il **primo messaggio**: corto, senza link,
  sempre «Salve, sono Simone di Nerodoro Studio…» e un po' diverso ogni volta (4 versioni che si alternano, con il problema
  del sito e il tipo di locale: «siti per pizzerie», «un bar come il vostro»…). I testi si cambiano nelle impostazioni.
- **A ognuno scrive una volta sola**, mai due. Le risposte compaiono in **📬 Risposte** (e nell'app, dove continuate voi):
  - **«No»** (anche «no grazie», «nn ci interessa», «abbiamo già il sito», «stop», 👎…) → va negli **🗄️ Archiviati**,
    la chat viene archiviata anche nell'app WhatsApp e non riceve più niente.
  - **Tutto il resto** («sì», «sii», «sisi», «ok», «okok», «okk», «va bene», «certo», «mandate», «mi interessa», 👍, una domanda…)
    → 30-90 secondi dopo il bot manda da solo, un messaggio alla volta: il **video** (`public/video.mp4`, arriva come video
    WhatsApp), i **due abbonamenti** Base e Premium con il prezzo al mese e cosa comprendono (presi dal sito, senza vincoli),
    il **link del sito per pagare** con la spiegazione di come si paga e come funziona, e il **link della demo**
    (https://l13291221-cmyk.github.io/Ristorante-/). Una volta sola, e non se avete già risposto voi dal telefono.
  - I messaggi automatici del WhatsApp Business del locale («Grazie per averci contattato, vi risponderemo…») non contano.
- **Prova** sulla riga del numero manda al tuo numero personale il primo messaggio e, poco dopo, tutto quello che riceve chi dice sì.
- Per cambiare il video: sostituisci `public/video.mp4` (sotto 16 MB) e `public/video.jpg` (anteprima), oppure metti un link nelle impostazioni.
- Ogni giorno, per ogni numero acceso, sceglie a caso quanti messaggi mandare (tra «da» e «a», predefinito 25-30) e li sparge a caso nelle fasce orarie
  (predefinito 9:30-12:30 e 15:00-19:30, ora italiana, dal lunedì al sabato), con almeno 4 minuti tra uno e l'altro.
- **Partenza graduale**: i primi 4 giorni manda 10, 15, 20, 25 messaggi. Se WhatsApp avvisa o limita le chat nuove,
  il bot dimezza o si mette in pausa da solo fino a quando WhatsApp lo permette di nuovo.

**Da sapere**
- Il bot si collega come «dispositivo collegato» (come WhatsApp Web, nella lista appare «Chrome (Ubuntu)»), con la libreria
  [Baileys](https://github.com/WhiskeySockets/Baileys). Non è l'API ufficiale di Meta: WhatsApp può limitare o bloccare i numeri
  che scrivono a tanti sconosciuti e ricevono segnalazioni. Usate un numero di lavoro e non alzate troppo i messaggi al giorno.
- Il telefono può restare spento, ma aprite WhatsApp Business almeno una volta ogni 14 giorni, altrimenti WhatsApp scollega i dispositivi.
- Privacy: per la legge italiana i messaggi pubblicitari automatici richiedono di norma il consenso. Scrivere solo a chi ha
  pubblicato il WhatsApp come contatto dell'attività, una volta sola e smettendo al primo «no», riduce il problema ma non lo elimina.
- Su Render gratuito il server deve restare sveglio: ci pensa già la «Sveglia siti» (auto-ping ogni 5 minuti).

**Backup del bot**: il collegamento di ogni numero a WhatsApp e l'elenco di chi ha già ricevuto il messaggio sono salvati (cifrati come gli altri
backup) dall'azione **Backup dati** sul ramo **`backup-bot`**, che tiene **solo l'ultima copia** (cambiano a ogni messaggio:
con la cronologia il repository crescerebbe di continuo). Dopo un deploy o un riavvio il sito li riprende e il bot riparte da solo.
L'azione con l'orario funziona solo dal ramo **main**: copiate su main il file `.github/workflows/backup.yml` di questo ramo,
altrimenti la pagina del bot mostra un avviso e a ogni riavvio di Render bisogna ricollegare WhatsApp.

## Pacchetti
- **Base** (`PREZZO`, default 990 €): sito web completo (assistenza non inclusa).
- **Premium** (`PREZZO_PREMIUM`, default 1490 €): Base + dominio personalizzato + QR code.
Nell'admin scegli il pacchetto quando crei l'ordine. Per il Premium il cliente, dopo aver pagato, vede e scarica il QR code del suo sito; dall'admin il pulsante 🔳 QR code lo genera per qualsiasi ordine con un link.

## Assistenza (facoltativa)
Il sito si vende a **pagamento unico** (Base `PREZZO`, Premium `PREZZO_PREMIUM`). L'assistenza non è inclusa: se il cliente la vuole,
nell'admin crei un ordine a parte con il pacchetto **Assistenza** (`CANONE_ASSISTENZA`, predefinito 20 € al mese, senza vincolo).
Il cliente accetta le condizioni, paga il primo mese e poi Stripe addebita il canone ogni mese finché non disdice.
Nel webhook Stripe attiva anche `invoice.paid`, `invoice.payment_failed` e `customer.subscription.deleted` per vedere nell'admin se paga.
Disdette dalla dashboard di Stripe (Abbonamenti).

## Guida nuovo cliente
Nell'admin, pulsante **📋 Guida cliente** (`/guida`): i passi per creare la copia del sito di ogni cliente dal modello
Ristorante- (copia, GitHub Pages, token solo per quel sito, PIN nuovo, collegamento all'ordine). Scrivi il nome del cliente
e i link si compilano da soli; le spunte restano salvate sul telefono.

## Backup automatico su GitHub (nessuna chiave da impostare)
Render gratuito cancella `data/` a ogni Manual Deploy o riavvio. Ogni 5 minuti l'azione **Backup dati**
(`.github/workflows/backup.yml`) scarica dal sito ordini (con accettazioni, disdette, dati dei clienti e tutto ciò che serve
per le ricevute), siti pronti (con PIN e token) e sveglia siti, e li salva sul ramo **`backup-dati`** di questo repository.
Usa il permesso che GitHub Actions ha già: non serve nessun token. Dopo un deploy il sito riprende tutto da lì da solo.
Il repository è pubblico, quindi i file (`backup/*.enc.json`) sono **cifrati** (AES-256-GCM) con una chiave ricavata da
`STRIPE_SECRET_KEY`: senza quella chiave nessuno può leggerli. Se un giorno cambi la chiave Stripe, metti quella vecchia in `BACKUP_KEY`.
- L'azione con l'orario funziona solo quando il file è sul ramo **main** del repository.
- Prima di un Manual Deploy, per salvare subito: GitHub → Actions → Backup dati → **Run workflow** (o «Salva ora» nell'admin).
- Se il sito su Render ha un altro indirizzo, cambia `SITE` nel file dell'azione.
- I dati del bot WhatsApp vanno sul ramo **`backup-bot`** (solo l'ultima copia, vedi «Bot WhatsApp»).

## Assistenza con pagamento diretto
Il link di pagamento dell'assistenza (20 €/mese, ricorrente, solo carta) **lo crea il sito da solo su Stripe** al primo avvio
con la chiave Stripe e poi lo ritrova. Nella home «Attiva l'assistenza» porta lì; dopo il pagamento il cliente vede l'**attestato**
con la data di scadenza presa da Stripe (si aggiorna a ogni rinnovo) e lo manda su WhatsApp: aprendo il link vedi se è attiva.
Se preferisci un tuo Payment Link, mettilo in `ASSISTENZA_LINK`.

## Acquisto diretto dal sito
Nella home «Scegli Base» / «Scegli Premium» chiedono solo il nome dell'attività e portano subito al riepilogo
(condizioni, vincolo, nome, email, telefono e pagamento con carta): nessun codice da mandare. Dopo il pagamento il cliente
riceve il primo sito pronto e il suo codice personale (per ritrovarlo e per chiudere l'abbonamento). Nell'admin questi ordini
hanno «🛒 Dal sito». Massimo 5 ordini all'ora per indirizzo. Gli ordini creati dall'admin con il codice funzionano come prima.

## Siti pronti
Nell'admin, sezione **🌐 Siti pronti**, incolli le copie del sito già online, una per riga: `link PIN token`
(PIN e token facoltativi). Quando un cliente paga, se il suo ordine non ha già un link, riceve **da solo** il primo sito
libero (link, PIN e token compaiono nella sua pagina) e nella lista risulta «Usato da …». Come creare le copie: `/guida`.
I dati stanno in `data/siti-pronti.json`.

## Abbonamento con vincolo (Base e Premium)
Base e Premium sono **abbonamenti mensili con carta** (Stripe), con vincolo di `VINCOLO_MESI` mesi (predefinito 24).
- Canoni: `CANONE_BASE` (predefinito 59) e `CANONE_PREMIUM` (predefinito 99), in euro al mese.
- Il cliente vede canone, «Vincolo 24 mesi» e «Oggi paghi»; nelle condizioni (punto 12) c'è il totale del vincolo e cosa
  succede se disdice prima, e lo approva con la seconda casella.
- Prima di Stripe il cliente scrive **nome e cognome, email e telefono** sulla nostra pagina: Stripe li riceve già compilati
  (il cliente Stripe viene creato con quei dati) e non li richiede.
- **Disdetta**: dalla pagina del suo ordine (codice + email usata per pagare). Prima della fine del vincolo vede l'importo
  esatto (mesi che mancano × canone): gli viene addebitato subito sulla carta dell'abbonamento e poi l'abbonamento si chiude.
  Se l'addebito non riesce l'abbonamento **resta attivo**. Dopo il vincolo si chiude a fine mese, senza costi.
- Nell'admin: «Totale vincoli firmati» (canone × mesi di tutti gli abbonamenti pagati) e, per ogni ordine, fine del vincolo,
  stato (attivo / insoluto / chiuso) e l'eventuale addebito della disdetta.
- Nel webhook Stripe attiva `checkout.session.completed`, `invoice.paid`, `invoice.payment_failed` e `customer.subscription.deleted`.
- Attenzione: se il cliente blocca la carta, l'addebito fallisce; i canoni restano dovuti per contratto ma vanno chiesti a parte.

Il noleggio (`/api/orders/:id/noleggio`) e Klarna diretto (`/api/orders/:id/klarna`) restano nel server ma la pagina non li usa più.

## 📋 Abbonamenti venduti (nell'admin)
In cima all'admin c'è l'elenco di ogni sito venduto in abbonamento: attività, titolare, telefono, email, partita IVA, da quando,
fino a quando dura il vincolo e quanti canoni ha pagato. Il riquadro diventa **rosso** con un avviso quando:
- **ha chiuso l'abbonamento senza pagare i mesi restanti** (carta bloccata, pagamenti falliti, chiuso da Stripe…), con l'importo che manca;
- **il canone del mese non è stato pagato** (Stripe riprova da solo per qualche giorno);
- **ha contestato un addebito con la banca** (il sito lo controlla da solo ogni 6 ore): si risponde da Stripe allegando la prova di accettazione.

Pulsanti: **💬 Scrivi su WhatsApp** e **✉️ Manda email** con il messaggio già scritto (cortese, con l'importo e il punto 12),
**💳 Crea link per pagare** (link Stripe per saldare con la carta, che finisce da solo nel messaggio; quando paga il riquadro torna
a posto) e **Segna come risolto**.

## 💬 Risposte pronte (`/risposte`)
Nell'admin («Risposte pronte», anche dalla pagina del bot) i messaggi già scritti, con **Copia**, **WhatsApp** e **Email**:
- **Domande e obiezioni**: «Quanto costa?», «Ci penso», «Abbiamo già Facebook», «Abbiamo già un sito», «Costa troppo»,
  «C'è un vincolo?» (risposta chiara: 24 mesi), «Chi siete?», «Posso modificarlo io?», «Come si paga?»…
- **Dopo X giorni**: nessuna risposta (una volta sola), video visto ma nessuna risposta, «ci penso», volevano pagare ma non l'hanno fatto.
- **Nuovi clienti**: benvenuto con cosa serve (logo, foto, menu, orari), sito pronto, «come va?», recensione e passaparola.
- **Chi non paga**: canone non pagato (gentile), sollecito, mesi che mancano dopo la chiusura e **⚖️ ultimo avviso prima delle vie
  legali** (15 giorni, poi avvocato e decreto ingiuntivo con interessi e spese, con la possibilità di pagare a rate).
In alto si scrivono i dati del cliente (nome, locale, numero, importo, mesi, link per pagare, data) e finiscono in tutti i messaggi;
da un riquadro rosso di «Abbonamenti venduti» il pulsante «⚖️ Solleciti e ultimo avviso» apre la pagina già compilata.
I testi si possono cambiare: le modifiche restano salvate sul telefono.

## Condizioni e prova di accettazione
Prima di pagare il cliente spunta **«Accetto le condizioni»** nel riepilogo (dove vede canone e **«Vincolo 24 mesi»**, senza il totale), poi si apre
un foglio con le condizioni complete (con il dettaglio del pagamento in fondo) e spunta la **seconda casella**: dichiara di acquistare
per la sua attività, con partita IVA, e non come consumatore, e approva in modo specifico (artt. 1341-1342 c.c.) i punti 6 e 12
(nessun recesso, vincolo di 24 mesi, canoni che mancano dovuti se disdice prima o smette di pagare). Poi scrive nome del titolare,
**partita IVA** (controllata), email e telefono. Senza tutto questo il server non apre il pagamento. Anche la pagina di Stripe dice
«Abbonamento con VINCOLO DI 24 MESI» (senza il totale).

Il servizio è **per le attività con partita IVA**: contratto tra imprese, niente recesso di 14 giorni (punto 6). Gli ordini accettati
con le vecchie condizioni per i privati tengono i loro 14 giorni. Le condizioni prevedono anche gli interessi di mora e le spese di
recupero dei contratti tra imprese (D.Lgs. 231/2002) e la possibilità di cedere i crediti a terzi (recupero crediti, factoring, noleggio).
Nell'admin, in ogni ordine, **🧾 Prova di accettazione**: data e ora, IP, dispositivo, importi accettati, metodo (carta o Klarna)
e i dati inseriti su Stripe (nome, email, telefono, indirizzo, P.IVA, carta: solo tipo e ultime 4 cifre).
Con **Scarica la prova completa (.txt)** hai anche il testo esatto delle condizioni accettate con la sua impronta SHA-256.
Il testo delle condizioni sta in `public/condizioni.html`, dentro `#termsBody`.
