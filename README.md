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
- Canoni: `CANONE_BASE` (predefinito 60) e `CANONE_PREMIUM` (predefinito 99), in euro al mese.
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

## Condizioni e prova di accettazione
Prima di pagare il cliente spunta **«Accetto le condizioni»** nel riepilogo, poi si apre un foglio con le condizioni complete
(con prezzo e rate del suo ordine, il dettaglio del pagamento in fondo) e spunta la **seconda casella**: chiede che il lavoro inizi
subito e riconosce che, a sito consegnato, perde il diritto di recesso (art. 59 Codice del Consumo), e approva il dettaglio del
pagamento. Senza tutte e due il server non apre il pagamento.

Il servizio è per i privati: valgono i **14 giorni di recesso** (punto 6 delle condizioni). Se il cliente recede prima della consegna
paga solo il lavoro già fatto e gli rimborsi il resto da Stripe (con Klarna il rimborso riduce o annulla le rate); dopo la consegna non può più recedere.
Nell'admin, in ogni ordine, **🧾 Prova di accettazione**: data e ora, IP, dispositivo, importi accettati, metodo (carta o Klarna)
e i dati inseriti su Stripe (nome, email, telefono, indirizzo, P.IVA, carta: solo tipo e ultime 4 cifre).
Con **Scarica la prova completa (.txt)** hai anche il testo esatto delle condizioni accettate con la sua impronta SHA-256.
Il testo delle condizioni sta in `public/condizioni.html`, dentro `#termsBody`.
