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
- **Base** (`PREZZO`, default 990 €): sito + 1 anno di assistenza.
- **Premium** (`PREZZO_PREMIUM`, default 1490 €): Base + dominio personalizzato + QR code.
Nell'admin scegli il pacchetto quando crei l'ordine. Per il Premium il cliente, dopo aver pagato, vede e scarica il QR code del suo sito; dall'admin il pulsante 🔳 QR code lo genera per qualsiasi ordine con un link.
