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

## Pagamento a rate (Klarna)
Sul sito Base e Premium si mostrano come rata mensile: prezzo diviso per `RATE_KLARNA` (predefinito 36), arrotondato per eccesso
ai 10 centesimi (990 € → **27,50 €/mese**, 1.490 € → **41,40 €/mese**), con sotto «Pagamento con Klarna in 36 rate».
Il prezzo intero e tutto il dettaglio del pagamento sono al punto 12 delle condizioni, che il cliente legge prima di pagare.
Le 36 rate sono senza interessi (TAN 0%, TAEG 0%): Klarna mostra al cliente la rata esatta e se la richiesta è approvata; può anche pagare tutto con carta.
Per farlo funzionare: dashboard Stripe → Impostazioni → Metodi di pagamento → attiva **Klarna**. Stripe Checkout mostra da solo i metodi attivi.
Nella pagina di pagamento il pulsante «Paga X € al mese con Klarna» porta il cliente **direttamente su Klarna** (senza la pagina Stripe con il totale grande); «Oppure paga tutto con carta» usa Stripe Checkout.
Per il pagamento diretto con Klarna aggiungi al webhook Stripe anche l'evento `payment_intent.succeeded`.
Tu incassi subito l'intero importo (meno la commissione Klarna); le rate le gestisce Klarna. Su Stripe il prodotto si chiama «Sito web».

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
