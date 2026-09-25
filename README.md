# RistoWeb Studio

Landing page scura per vendere siti web ai ristoranti, con pagamento Stripe e una piccola area admin protetta da PIN.

## Come funziona
1. Clicchi il **lucchetto in alto a destra** → inserisci il PIN → entri nell'admin.
2. Crei un ordine (nome ristorante, prezzo, link del sito, numero WhatsApp): viene generato un **codice** tipo `K7M2-P9QX`.
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
   - `STRIPE_SECRET_KEY` = chiave segreta da dashboard.stripe.com → Sviluppatori → Chiavi API (`sk_test_...` per provare, `sk_live_...` per incassare davvero)
   - `BASE_URL` = l'indirizzo che ti dà Render (es. `https://ristoweb.onrender.com`)
4. (Consigliato) Stripe → Webhook → endpoint `BASE_URL/api/stripe-webhook`, evento `checkout.session.completed`, poi metti il segreto in `STRIPE_WEBHOOK_SECRET`.

**Importante:** gli ordini sono salvati in `data/orders.json`. Sui piani gratuiti il disco può azzerarsi a ogni riavvio: aggiungi un disco persistente montato su `data/`, oppure tieni nota degli ordini.

Per provare i pagamenti in modalità test usa la carta `4242 4242 4242 4242`, qualsiasi data futura e CVC.
