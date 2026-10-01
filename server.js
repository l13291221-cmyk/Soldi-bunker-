// Nerodoro Studio — landing + pagamenti Stripe + mini admin con PIN
const path = require('path');
const fs = require('fs');
const crypto = require('crypto');
const express = require('express');

try { process.loadEnvFile(path.join(__dirname, '.env')); } catch { /* .env opzionale */ }

const PORT = process.env.PORT || 3000;
const ADMIN_PIN = process.env.ADMIN_PIN || '';
const BASE_URL = (process.env.BASE_URL || process.env.RENDER_EXTERNAL_URL || `http://localhost:${PORT}`).replace(/\/$/, '');
const CURRENCY = (process.env.CURRENCY || 'eur').toLowerCase();
// Prezzo standard mostrato sul sito e proposto nei nuovi ordini (in euro)
const PRICE = parseFloat(String(process.env.PREZZO || '990').replace(',', '.')) || 990;
// Numero WhatsApp Business (solo cifre, con prefisso internazionale)
const WHATSAPP = String(process.env.WHATSAPP ?? '27710933377').replace(/\D/g, '');
const DEFAULT_DESCRIPTION = 'Sito web professionale per la tua attività';
// Dati per il pannello del sito del cliente, mostrati SOLO dopo il pagamento.
// Si impostano su Render (restano segreti, non finiscono mai nel codice pubblico).
const SITE_TOKEN = process.env.TOKEN_SITO || '';
const SITE_PIN = process.env.PIN_SITO || '';
const PRICE_PREMIUM = parseFloat(String(process.env.PREZZO_PREMIUM || '1490').replace(',', '.')) || 1490;
// Assistenza facoltativa: canone mensile, senza vincolo (si disdice quando si vuole)
const eur = (v, d) => { const n = parseFloat(String(v ?? '').replace(',', '.')); return Number.isFinite(n) && n >= 0 ? n : d; };
const MIN_MONTHS = 1;
const ASSIST_MONTHLY = eur(process.env.CANONE_ASSISTENZA, 20);
// 990 → "990 €", 27.5 → "27,50 €"
const euro = n => n.toLocaleString('it-IT', { minimumFractionDigits: Number.isInteger(n) ? 0 : 2, maximumFractionDigits: 2, useGrouping: 'always' }) + ' €';
// I due pacchetti mostrati sul sito e scelti nell'admin
const PACKAGES = {
  base: {
    id: 'base', name: 'Base', price: Math.round(PRICE * 100),
    description: DEFAULT_DESCRIPTION,
    features: ['Sito web completo per la tua attività', 'Pannello per modificare menu, foto e prezzi da soli, dal telefono', 'Perfetto da smartphone', 'Online in pochi giorni'],
  },
  premium: {
    id: 'premium', name: 'Premium', price: Math.round(PRICE_PREMIUM * 100),
    description: 'Sito web professionale + dominio personalizzato (www.tuonome.it) + QR code',
    features: ['Tutto quello che c\'è nel Base', 'Indirizzo personalizzato: www.tuonome.it', 'QR code pronto da stampare (menu, vetrina, biglietti)', 'Dominio incluso per il primo anno'],
  },
  assistenza: {
    id: 'assistenza', name: 'Assistenza', recurring: true, months: MIN_MONTHS,
    price: 0, monthly: Math.round(ASSIST_MONTHLY * 100),
    description: `Assistenza per il tuo sito: ${euro(ASSIST_MONTHLY)} al mese, disdici quando vuoi.`,
    features: ['Ti aiutiamo per dubbi e problemi con il sito', 'Ti spieghiamo come usare il pannello', 'Disdici quando vuoi'],
  },
};
// Pagamento a rate con Klarna: sul sito il prezzo si mostra come rata mensile
// (prezzo diviso per le rate, arrotondato per eccesso ai 10 centesimi: 990 € → 27,50 €, 1.490 € → 41,40 €)
const RATE_MESI = Math.max(1, Math.round(eur(process.env.RATE_KLARNA, 36))) || 36;
const rateOf = cents => Math.ceil(cents / RATE_MESI / 10) * 10;
for (const p of Object.values(PACKAGES)) if (!p.recurring) Object.assign(p, { rateMonthly: rateOf(p.price), rateMonths: RATE_MESI });
const isPremium = pkg => String(pkg || '').startsWith('premium');
const stripe = process.env.STRIPE_SECRET_KEY ? require('stripe')(process.env.STRIPE_SECRET_KEY) : null;

if (!ADMIN_PIN) console.warn('⚠️  ADMIN_PIN non impostato: l\'area admin è disattivata.');
if (!stripe) console.warn('⚠️  STRIPE_SECRET_KEY non impostata: i pagamenti non funzioneranno.');

// ---------- Archivio ordini (file JSON) ----------
const DB_FILE = path.join(__dirname, 'data', 'orders.json');
function loadOrders() {
  try { return JSON.parse(fs.readFileSync(DB_FILE, 'utf8')); } catch { return {}; }
}
let orders = loadOrders();
function saveOrders() {
  fs.mkdirSync(path.dirname(DB_FILE), { recursive: true });
  const tmp = DB_FILE + '.tmp';
  fs.writeFileSync(tmp, JSON.stringify(orders, null, 2));
  fs.renameSync(tmp, DB_FILE);
}
// Codice ordine leggibile, es. "K7M2-P9QX" (senza 0/O/1/I/L per evitare confusione)
const CODE_ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789';
function newCode() {
  let id;
  do {
    id = Array.from(crypto.randomBytes(8), b => CODE_ALPHABET[b % CODE_ALPHABET.length]).join('');
  } while (orders[id]);
  return id;
}
function formatCode(id) {
  return /^[A-Z0-9]{8}$/.test(id) ? `${id.slice(0, 4)}-${id.slice(4)}` : id;
}
function findOrder(raw) {
  const s = String(raw || '').trim();
  return orders[s] || orders[s.toUpperCase().replace(/[^A-Z0-9]/g, '')] || null;
}
function adminOrder(o) {
  // il testo completo delle condizioni accettate si scarica a parte (prova .txt)
  const acceptance = o.acceptance && { ...o.acceptance, termsText: undefined };
  return { ...o, acceptance, rateMonthly: o.monthly ? 0 : rateOf(o.amount), rateMonths: RATE_MESI, code: formatCode(o.id), payUrl: `${BASE_URL}/paga/${o.id}` };
}
function publicOrder(o) {
  return {
    id: o.id,
    code: formatCode(o.id),
    restaurant: o.restaurant,
    description: o.description,
    amount: o.amount,
    currency: CURRENCY,
    package: o.package || 'base',
    monthly: o.monthly || 0,
    months: o.months || 0,
    rateMonthly: o.monthly ? 0 : rateOf(o.amount),
    rateMonths: RATE_MESI,
    approvalText: o.paid ? null : approvalText(o),
    paid: o.paid,
    // Il link del sito si vede SOLO dopo il pagamento
    siteUrl: o.paid ? o.siteUrl || null : null,
    panelPin: o.paid ? (o.panelPin || SITE_PIN || null) : null,
    siteToken: o.paid ? (o.siteToken || SITE_TOKEN || null) : null,
  };
}
function markPaid(orderId, session) {
  const o = orders[orderId];
  if (!o || o.paid) return;
  o.paid = true;
  o.paidAt = new Date().toISOString();
  o.stripeSessionId = session.id;
  if (session.subscription) {
    o.subscriptionId = typeof session.subscription === 'string' ? session.subscription : session.subscription.id;
    o.subStatus = 'attivo';
    const end = new Date(); end.setMonth(end.getMonth() + (o.months || MIN_MONTHS));
    o.commitmentEnd = end.toISOString();
  }
  const cd = session.customer_details || {};
  o.payer = {
    name: cd.name || null,
    email: cd.email || null,
    phone: cd.phone || null,
    address: cd.address || null,
    taxIds: (cd.tax_ids || []).map(t => ({ type: t.type, value: t.value })),
    stripeCustomerId: typeof session.customer === 'string' ? session.customer : (session.customer && session.customer.id) || null,
    amountPaid: session.amount_total ?? null,
  };
  saveOrders();
  savePaymentMethod(o, session).catch(err => console.error('Metodo di pagamento non letto:', err.message));
}
// Come ha pagato (carta o Klarna) e, per la carta, tipo, ultime 4 cifre, scadenza e paese
// (Stripe non dà mai il numero completo)
async function savePaymentMethod(o, session) {
  if (!stripe) return;
  let pm = null;
  if (o.subscriptionId) pm = (await stripe.subscriptions.retrieve(o.subscriptionId, { expand: ['default_payment_method'] })).default_payment_method;
  else if (session.payment_intent) pm = (await stripe.paymentIntents.retrieve(String(session.payment_intent), { expand: ['payment_method'] })).payment_method;
  if (!pm || typeof pm !== 'object') return;
  const c = pm.card;
  o.payer = {
    ...o.payer,
    method: pm.type,
    ...(c && { card: { brand: c.brand, last4: c.last4, expMonth: c.exp_month, expYear: c.exp_year, country: c.country, funding: c.funding } }),
  };
  saveOrders();
}

// ---------- Prova di accettazione delle condizioni ----------
// Testo delle condizioni (public/condizioni.html, dentro #termsBody)
const TERMS_HTML = (() => {
  try {
    const html = fs.readFileSync(path.join(__dirname, 'public', 'condizioni.html'), 'utf8');
    const m = html.match(/<div id="termsBody"[^>]*>([\s\S]*?)<\/div>\s*<!-- \/termsBody -->/);
    return m ? m[1] : '';
  } catch { return ''; }
})();
if (!TERMS_HTML) console.warn('⚠️  Testo delle condizioni non trovato in public/condizioni.html');
// Condizioni con pacchetto, prezzo e rate di questo ordine. In fondo il dettaglio del pagamento:
// per il sito le rate Klarna, per l'assistenza il canone mensile.
function termsHtmlFor(o) {
  const assist = o.package === 'assistenza';
  const put = (cls, val) => h => h.replace(new RegExp(`(<(\\w+) class="${cls}">)[^<]*(</\\2>)`, 'g'), (_, a, t, b) => a + escapeHtml(val) + b);
  let h = TERMS_HTML;
  h = assist
    ? h.replace(/<!--sito-->[\s\S]*?<!--\/sito-->/g, '').replace(/<!--assistenza([\s\S]*?)\/assistenza-->/g, '$1')
    : h.replace(/<!--assistenza[\s\S]*?\/assistenza-->/g, '');
  h = put('js-pkg', (PACKAGES[o.package] || PACKAGES.base).name)(h);
  h = put('js-price', euro(o.amount / 100))(h);
  h = put('js-rate', euro(rateOf(o.amount) / 100))(h);
  h = put('js-rate-n', String(RATE_MESI))(h);
  h = put('js-assist', euro((assist && o.monthly ? o.monthly : PACKAGES.assistenza.monthly) / 100))(h);
  h = h.replace(/(<a class="js-wa" href=")[^"]*/g, `$1https://wa.me/${WHATSAPP}`);
  return h.replace(/<!--[\s\S]*?-->/g, '');
}
function termsTextFor(o) {
  return termsHtmlFor(o)
    .replace(/<li[^>]*>/g, '- ').replace(/<\/(p|li|h2|div|ul|ol)>|<br\s*\/?>/g, '\n').replace(/<h2[^>]*>/g, '\n')
    .replace(/<[^>]+>/g, '').replace(/&amp;/g, '&').replace(/&nbsp;/g, ' ').replace(/&#39;|&apos;/g, "'").replace(/&quot;/g, '"').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
    .split('\n').map(l => l.replace(/\s+/g, ' ').trim()).filter(Boolean).join('\n');
}
function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
// Seconda casella: richiesta espressa di iniziare subito, con la perdita del recesso a servizio
// eseguito (art. 59, c. 1, lett. a, Codice del Consumo), e approvazione del dettaglio del pagamento
function approvalText(o) {
  if (o.package === 'assistenza') {
    return 'Chiedo che l\'assistenza inizi subito, senza aspettare la fine dei 14 giorni per il recesso. So che se recedo entro i 14 giorni pago i giorni già usati (punto 6). Approvo l\'addebito automatico del canone ogni mese sulla stessa carta, fino alla disdetta (punto 10).';
  }
  return `Chiedo che il lavoro sul mio sito inizi subito, senza aspettare la fine dei 14 giorni per il recesso. So che se recedo prima della consegna pago il lavoro già fatto e che, una volta consegnato il sito, perdo il diritto di recesso (punto 6). Approvo il dettaglio del pagamento (punto 12): ${RATE_MESI} rate con Klarna, secondo le sue condizioni.`;
}
function acceptanceFor(o, req) {
  const termsText = termsTextFor(o);
  return {
    at: new Date().toISOString(),
    ip: req.ip,
    userAgent: String(req.get('user-agent') || '').slice(0, 400),
    language: String(req.get('accept-language') || '').slice(0, 120),
    package: o.package || 'base',
    price: o.amount, currency: CURRENCY,
    ...(o.monthly ? { monthly: o.monthly } : { rateMonthly: rateOf(o.amount), rateMonths: RATE_MESI }),
    termsHash: crypto.createHash('sha256').update(termsText).digest('hex'),
    specificApproval: approvalText(o),
    termsText,
  };
}
// Stato dell'abbonamento aggiornato dagli eventi Stripe (rinnovi, pagamenti falliti, disdette)
function orderBySubscription(subId) {
  return subId ? Object.values(orders).find(o => o.subscriptionId === subId) : null;
}
function invoiceSubscription(inv) {
  const s = inv.subscription || (inv.parent && inv.parent.subscription_details && inv.parent.subscription_details.subscription);
  return typeof s === 'string' ? s : s && s.id;
}

// ---------- Sessioni admin (cookie httpOnly) ----------
const adminSessions = new Map(); // token -> scadenza
const SESSION_MS = 12 * 60 * 60 * 1000;
function getCookie(req, name) {
  const m = (req.headers.cookie || '').match(new RegExp('(?:^|; )' + name + '=([^;]+)'));
  return m ? decodeURIComponent(m[1]) : null;
}
function isAdmin(req) {
  const t = getCookie(req, 'admin');
  const exp = t && adminSessions.get(t);
  if (!exp) return false;
  if (exp < Date.now()) { adminSessions.delete(t); return false; }
  return true;
}
function requireAdmin(req, res, next) {
  if (!isAdmin(req)) return res.status(401).json({ error: 'Non autorizzato' });
  next();
}
function pinMatches(pin) {
  const a = crypto.createHash('sha256').update(String(pin)).digest();
  const b = crypto.createHash('sha256').update(ADMIN_PIN).digest();
  return ADMIN_PIN.length > 0 && crypto.timingSafeEqual(a, b);
}
// Blocco anti-tentativi per IP, finestra di 15 minuti
function attemptLimiter(max) {
  const hits = new Map();
  const WINDOW = 15 * 60 * 1000;
  return {
    blocked(ip) {
      const f = hits.get(ip);
      if (!f) return false;
      if (Date.now() - f.first > WINDOW) { hits.delete(ip); return false; }
      return f.count >= max;
    },
    fail(ip) {
      const f = hits.get(ip);
      if (!f || Date.now() - f.first > WINDOW) hits.set(ip, { count: 1, first: Date.now() });
      else f.count++;
    },
    reset(ip) { hits.delete(ip); },
  };
}
const pinLimiter = attemptLimiter(5);   // 5 PIN sbagliati
const codeLimiter = attemptLimiter(30); // 30 codici ordine inesistenti

const app = express();
app.set('trust proxy', 1);

// ---------- Webhook Stripe (body grezzo, va prima di express.json) ----------
app.post('/api/stripe-webhook', express.raw({ type: 'application/json' }), (req, res) => {
  if (!stripe || !process.env.STRIPE_WEBHOOK_SECRET) return res.status(400).end();
  let event;
  try {
    event = stripe.webhooks.constructEvent(req.body, req.headers['stripe-signature'], process.env.STRIPE_WEBHOOK_SECRET);
  } catch (err) {
    return res.status(400).send(`Webhook error: ${err.message}`);
  }
  if (event.type === 'checkout.session.completed' || event.type === 'checkout.session.async_payment_succeeded') {
    const s = event.data.object;
    if (s.payment_status === 'paid' && s.metadata && s.metadata.orderId) markPaid(s.metadata.orderId, s);
  } else if (event.type === 'payment_intent.succeeded') {
    // Solo i pagamenti Klarna diretti: quelli con la pagina Stripe arrivano già da checkout.session.completed
    const pi = event.data.object;
    if (pi.metadata && pi.metadata.via === 'klarna_diretto' && pi.metadata.orderId) markPaid(pi.metadata.orderId, sessionFromKlarna(pi));
  } else if (event.type === 'invoice.paid' || event.type === 'invoice.payment_failed') {
    const o = orderBySubscription(invoiceSubscription(event.data.object));
    if (o) {
      o.subStatus = event.type === 'invoice.paid' ? 'attivo' : 'insoluto';
      if (event.type === 'invoice.paid') o.lastPaidAt = new Date().toISOString();
      saveOrders();
    }
  } else if (event.type === 'customer.subscription.deleted') {
    const o = orderBySubscription(event.data.object.id);
    if (o) { o.subStatus = 'chiuso'; saveOrders(); }
  }
  res.json({ received: true });
});

app.use(express.json());
app.use(express.static(path.join(__dirname, 'public'), { extensions: ['html'] }));

// ---------- API admin ----------
app.post('/api/admin/login', (req, res) => {
  const ip = req.ip;
  if (pinLimiter.blocked(ip)) return res.status(429).json({ error: 'Troppi tentativi. Riprova tra 15 minuti.' });
  if (!pinMatches((req.body && req.body.pin) || '')) {
    pinLimiter.fail(ip);
    return res.status(401).json({ error: 'PIN errato' });
  }
  pinLimiter.reset(ip);
  const token = crypto.randomBytes(32).toString('hex');
  adminSessions.set(token, Date.now() + SESSION_MS);
  const secure = BASE_URL.startsWith('https') ? '; Secure' : '';
  res.setHeader('Set-Cookie', `admin=${token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=${SESSION_MS / 1000}${secure}`);
  res.json({ ok: true });
});

app.post('/api/admin/logout', (req, res) => {
  const t = getCookie(req, 'admin');
  if (t) adminSessions.delete(t);
  res.setHeader('Set-Cookie', 'admin=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0');
  res.json({ ok: true });
});

app.get('/api/admin/me', (req, res) => res.json({ admin: isAdmin(req), tokenSet: !!SITE_TOKEN, pinSet: !!SITE_PIN }));

app.get('/api/admin/orders', requireAdmin, (req, res) => {
  const list = Object.values(orders)
    .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
    .map(adminOrder);
  res.json({ orders: list, currency: CURRENCY });
});

function parseAmount(v) {
  const n = Math.round(parseFloat(String(v).replace(',', '.')) * 100);
  return Number.isFinite(n) && n >= 50 ? n : null; // Stripe: minimo 0,50
}
function cleanUrl(v) {
  const s = String(v || '').trim();
  if (!s) return '';
  try {
    const u = new URL(/^https?:\/\//i.test(s) ? s : 'https://' + s);
    return u.protocol === 'http:' || u.protocol === 'https:' ? u.toString() : null;
  } catch { return null; }
}

app.post('/api/admin/orders', requireAdmin, (req, res) => {
  const { restaurant, description, amount, siteUrl, phone } = req.body || {};
  const pkg = PACKAGES[req.body && req.body.package] ? req.body.package : 'base';
  if (!restaurant || !String(restaurant).trim()) return res.status(400).json({ error: 'Nome dell\'attività obbligatorio' });
  // Assistenza: niente prezzo iniziale, solo il canone mensile
  const cents = PACKAGES[pkg].recurring && !parseFloat(String(amount || '0').replace(',', '.')) ? 0 : parseAmount(amount);
  if (cents === null) return res.status(400).json({ error: 'Prezzo non valido (minimo 0,50)' });
  const url = cleanUrl(siteUrl);
  if (url === null) return res.status(400).json({ error: 'Link del sito non valido' });
  let monthly = 0;
  if (PACKAGES[pkg].recurring) {
    monthly = req.body.monthly !== undefined && String(req.body.monthly).trim() !== '' ? parseAmount(req.body.monthly) : PACKAGES[pkg].monthly;
    if (monthly === null) return res.status(400).json({ error: 'Canone mensile non valido' });
  }
  const id = newCode();
  orders[id] = {
    id,
    restaurant: String(restaurant).trim().slice(0, 120),
    description: String(description || PACKAGES[pkg].description).trim().slice(0, 300),
    package: pkg,
    amount: cents,
    ...(monthly && { monthly, months: MIN_MONTHS }),
    siteUrl: url,
    phone: String(phone || '').replace(/[^\d+]/g, '').slice(0, 20),
    paid: false,
    createdAt: new Date().toISOString(),
  };
  saveOrders();
  res.json({ order: adminOrder(orders[id]) });
});

app.patch('/api/admin/orders/:id', requireAdmin, (req, res) => {
  const o = orders[req.params.id];
  if (!o) return res.status(404).json({ error: 'Ordine non trovato' });
  const b = req.body || {};
  if (b.siteUrl !== undefined) {
    const url = cleanUrl(b.siteUrl);
    if (url === null) return res.status(400).json({ error: 'Link del sito non valido' });
    o.siteUrl = url;
  }
  if (b.restaurant !== undefined && String(b.restaurant).trim()) o.restaurant = String(b.restaurant).trim().slice(0, 120);
  if (b.phone !== undefined) o.phone = String(b.phone).replace(/[^\d+]/g, '').slice(0, 20);
  if (b.panelPin !== undefined) o.panelPin = String(b.panelPin).replace(/\D/g, '').slice(0, 12);
  if (b.siteToken !== undefined) o.siteToken = String(b.siteToken).trim().slice(0, 300);
  if (b.amount !== undefined && !o.paid) {
    const cents = parseAmount(b.amount);
    if (cents === null) return res.status(400).json({ error: 'Prezzo non valido' });
    o.amount = cents;
  }
  saveOrders();
  res.json({ order: adminOrder(o) });
});

// Prova di accettazione in un file di testo: dati del cliente, IP, dispositivo e condizioni accettate
app.get('/api/admin/orders/:id/prova', requireAdmin, (req, res) => {
  const o = orders[req.params.id];
  if (!o) return res.status(404).json({ error: 'Ordine non trovato' });
  const a = o.acceptance || {}, p = o.payer || {}, c = p.card || {};
  const when = iso => iso ? `${new Date(iso).toLocaleString('it-IT', { timeZone: 'Europe/Rome' })} (ora italiana) · ${iso}` : '—';
  const addr = p.address ? [p.address.line1, p.address.line2, [p.address.postal_code, p.address.city, p.address.state].filter(Boolean).join(' '), p.address.country].filter(Boolean).join(', ') : '';
  const price = a.price ?? o.amount;
  const lines = [
    'PROVA DI ACCETTAZIONE DELLE CONDIZIONI — Nerodoro Studio', '',
    `Ordine: ${formatCode(o.id)}`, `Attività: ${o.restaurant}`, `WhatsApp (dall'ordine): ${o.phone || '—'}`, `Pacchetto: ${(PACKAGES[a.package || o.package] || PACKAGES.base).name}`, '',
    'ACCETTAZIONE',
    `Data e ora: ${when(a.at || o.termsAcceptedAt)}`,
    `Indirizzo IP: ${a.ip || o.termsAcceptedIp || '—'}`,
    `Browser e dispositivo: ${a.userAgent || '—'}`,
    `Lingua del browser: ${a.language || '—'}`,
    o.monthly
      ? `Importi accettati: canone ${euro((a.monthly ?? o.monthly) / 100)} al mese${price ? ` · attivazione ${euro(price / 100)}` : ''}`
      : `Importi accettati: prezzo del sito ${euro(price / 100)} · con Klarna ${a.rateMonths || RATE_MESI} rate da ${euro((a.rateMonthly ?? rateOf(price)) / 100)} al mese`,
    `Prima casella spuntata: Accetto le condizioni`,
    `Seconda casella spuntata: ${a.specificApproval || '—'}`,
    `Impronta SHA-256 del testo accettato: ${a.termsHash || '—'}`, '',
    'PAGAMENTO (dati inseriti dal cliente su Stripe)',
    `Pagato: ${o.paid ? when(o.paidAt) : 'non ancora'}`,
    `Importo incassato: ${p.amountPaid != null ? euro(p.amountPaid / 100) : '—'}`,
    `Metodo: ${p.method === 'klarna' ? 'Klarna' : p.method === 'card' ? 'Carta' : p.method || '—'}`,
    `Nome: ${p.name || '—'}`, `Email: ${p.email || '—'}`, `Telefono: ${p.phone || '—'}`, `Indirizzo di fatturazione: ${addr || '—'}`,
    `Partita IVA / codici: ${(p.taxIds || []).map(t => `${t.value} (${t.type})`).join(', ') || '—'}`,
    `Carta: ${c.last4 ? `${c.brand} •••• ${c.last4}, scadenza ${String(c.expMonth).padStart(2, '0')}/${c.expYear}, paese ${c.country || '—'}, tipo ${c.funding || '—'}` : '—'}`,
    `Cliente Stripe: ${p.stripeCustomerId || '—'}`, ...(o.subscriptionId ? [`Abbonamento Stripe: ${o.subscriptionId}`] : []), `Sessione di pagamento Stripe: ${o.stripeSessionId || '—'}`, '',
    'TESTO DELLE CONDIZIONI ACCETTATE', a.termsText || '(non salvato: ordine accettato prima di questa funzione)',
  ];
  res.set('Content-Type', 'text/plain; charset=utf-8');
  res.set('Content-Disposition', `attachment; filename="prova-${formatCode(o.id)}.txt"`);
  res.send(lines.join('\n') + '\n');
});

app.delete('/api/admin/orders/:id', requireAdmin, (req, res) => {
  if (!orders[req.params.id]) return res.status(404).json({ error: 'Ordine non trovato' });
  delete orders[req.params.id];
  saveOrders();
  res.json({ ok: true });
});

// ---------- API pubbliche (cliente) ----------
app.get('/api/config', (req, res) => res.json({ price: Math.round(PRICE * 100), currency: CURRENCY, description: DEFAULT_DESCRIPTION, whatsapp: WHATSAPP, packages: PACKAGES }));

// QR code (PNG) del sito del cliente: solo per ordini Premium pagati, oppure per l'admin
const QRCode = require('qrcode');
async function sendQr(res, url, name) {
  const png = await QRCode.toBuffer(url, { width: 1200, margin: 2, errorCorrectionLevel: 'M', color: { dark: '#111111', light: '#ffffff' } });
  res.setHeader('Content-Type', 'image/png');
  res.setHeader('Content-Disposition', `inline; filename="QR-${String(name).replace(/[^\w-]+/g, '-').slice(0, 40)}.png"`);
  res.send(png);
}
app.get('/api/admin/qr', requireAdmin, async (req, res) => {
  const url = cleanUrl(req.query.url);
  if (!url) return res.status(400).send('Link non valido');
  await sendQr(res, url, req.query.name || 'sito');
});

// Trova l'ordine dal codice (con o senza trattino, maiuscole/minuscole indifferenti)
function loadPublicOrder(req, res, next) {
  if (codeLimiter.blocked(req.ip)) return res.status(429).json({ error: 'Troppi tentativi. Riprova tra 15 minuti.' });
  const o = findOrder(req.params.id);
  if (!o) {
    codeLimiter.fail(req.ip);
    return res.status(404).json({ error: 'Codice non valido. Controlla di averlo scritto bene.' });
  }
  req.order = o;
  next();
}
app.get('/api/orders/:id', loadPublicOrder, (req, res) => {
  const o = req.order;
  res.json({ order: publicOrder(o) });
});

// Condizioni complete con i dati di questo ordine: il cliente le legge nel foglio prima di pagare
app.get('/api/orders/:id/terms', loadPublicOrder, (req, res) => {
  res.json({ html: termsHtmlFor(req.order) });
});

app.post('/api/orders/:id/checkout', loadPublicOrder, async (req, res) => {
  const o = req.order;
  if (o.paid) return res.status(400).json({ error: 'Ordine già pagato' });
  if (!stripe) return res.status(503).json({ error: 'Pagamenti non ancora configurati' });
  // Prima di pagare il cliente deve spuntare entrambe le caselle: condizioni e approvazione specifica
  if (!(req.body && req.body.accept === true)) {
    return res.status(400).json({ error: 'Per pagare devi accettare le condizioni.' });
  }
  if (req.body.approve !== true) {
    return res.status(400).json({ error: 'Per pagare spunta anche l\'approvazione dei punti indicati.' });
  }
  const oneOff = {
    quantity: 1,
    price_data: {
      currency: CURRENCY,
      unit_amount: o.amount,
      product_data: {
        name: 'Sito web',
        ...(!o.monthly && { description: `${euro(rateOf(o.amount) / 100)} al mese · Pagamento con Klarna in ${RATE_MESI} rate` }),
      },
    },
  };
  try {
    o.acceptance = acceptanceFor(o, req);
    o.termsAcceptedAt = o.acceptance.at;
    o.termsAcceptedIp = o.acceptance.ip;
    saveOrders();
    const session = await stripe.checkout.sessions.create({
      ...(o.monthly ? {
        mode: 'subscription',
        line_items: [{
          quantity: 1,
          price_data: {
            currency: CURRENCY,
            unit_amount: o.monthly,
            recurring: { interval: 'month' },
            product_data: { name: `Assistenza sito web — ${o.restaurant}` },
          },
        }, ...(o.amount > 0 ? [oneOff] : [])],
        subscription_data: { metadata: { orderId: o.id }, description: `Assistenza mensile, disdici quando vuoi (codice ${formatCode(o.id)})` },
        custom_text: { submit: { message: `Assistenza: ${euro(o.monthly / 100)} al mese, addebitati ogni mese sulla stessa carta. Disdici quando vuoi. Condizioni: ${BASE_URL}/condizioni` } },
      } : {
        mode: 'payment',
        line_items: [oneOff],
        // Cliente Stripe sempre creato: così restano salvati anche i dati di fatturazione e la partita IVA
        customer_creation: 'always',
        // Nel pannello Stripe si vede comunque chi ha pagato
        payment_intent_data: { description: `Sito web — ${o.restaurant} (codice ${formatCode(o.id)})`, metadata: { orderId: o.id } },
        custom_text: { submit: { message: `Con Klarna paghi in ${RATE_MESI} rate da circa ${euro(rateOf(o.amount) / 100)} al mese, senza interessi (TAN 0%, TAEG 0%): rata esatta e approvazione li indica Klarna prima di confermare. Condizioni accettate: ${BASE_URL}/condizioni` } },
      }),
      // Dati del cliente per la prova di accettazione e la ricevuta
      billing_address_collection: 'required',
      phone_number_collection: { enabled: true },
      tax_id_collection: { enabled: true },
      metadata: { orderId: o.id },
      client_reference_id: o.id,
      success_url: `${BASE_URL}/paga/${o.id}?session_id={CHECKOUT_SESSION_ID}`,
      cancel_url: `${BASE_URL}/paga/${o.id}?annullato=1`,
    });
    res.json({ url: session.url });
  } catch (err) {
    console.error('Stripe error:', err.message);
    res.status(500).json({ error: 'Impossibile avviare il pagamento. Riprova.' });
  }
});

// Klarna diretto: il cliente salta la pagina di Stripe e va subito su Klarna, dove vede la rata al mese
function sessionFromKlarna(pi) {
  // markPaid lavora con una sessione Checkout: le passo gli stessi campi presi dal pagamento
  return { id: pi.id, payment_intent: pi.id, amount_total: pi.amount, customer_details: { email: pi.metadata.email || null } };
}
app.post('/api/orders/:id/klarna', loadPublicOrder, async (req, res) => {
  const o = req.order;
  if (o.paid) return res.status(400).json({ error: 'Ordine già pagato' });
  if (!stripe) return res.status(503).json({ error: 'Pagamenti non ancora configurati' });
  if (o.monthly) return res.status(400).json({ error: 'Klarna si usa solo per il sito, non per l\'assistenza.' });
  if (!(req.body && req.body.accept === true)) return res.status(400).json({ error: 'Per pagare devi accettare le condizioni.' });
  if (req.body.approve !== true) return res.status(400).json({ error: 'Per pagare spunta anche l\'approvazione dei punti indicati.' });
  const email = String(req.body.email || '').trim().slice(0, 200);
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return res.status(400).json({ error: 'Scrivi la tua email: serve a Klarna per le rate.' });
  try {
    o.acceptance = acceptanceFor(o, req);
    o.termsAcceptedAt = o.acceptance.at;
    o.termsAcceptedIp = o.acceptance.ip;
    saveOrders();
    const pi = await stripe.paymentIntents.create({
      amount: o.amount,
      currency: CURRENCY,
      payment_method_types: ['klarna'],
      payment_method_data: { type: 'klarna', billing_details: { email, address: { country: 'IT' } } },
      confirm: true,
      return_url: `${BASE_URL}/paga/${o.id}`,
      description: `Sito web — ${o.restaurant} (codice ${formatCode(o.id)})`,
      metadata: { orderId: o.id, via: 'klarna_diretto', email },
    });
    const url = pi.next_action && pi.next_action.redirect_to_url && pi.next_action.redirect_to_url.url;
    if (!url) throw new Error('Klarna non ha restituito il link (stato ' + pi.status + ')');
    res.json({ url });
  } catch (err) {
    console.error('Klarna error:', err.message);
    res.status(500).json({ error: 'Klarna non è disponibile in questo momento. Puoi pagare con carta.' });
  }
});

// Verifica il pagamento al ritorno da Stripe (funziona anche senza webhook)
app.post('/api/orders/:id/verify', loadPublicOrder, async (req, res) => {
  const o = req.order;
  const sessionId = req.body && req.body.sessionId;
  const piId = req.body && req.body.paymentIntent;
  if (!o.paid && stripe && piId) {
    try {
      const pi = await stripe.paymentIntents.retrieve(String(piId));
      if (pi.status === 'succeeded' && pi.metadata && pi.metadata.orderId === o.id) markPaid(o.id, sessionFromKlarna(pi));
    } catch (err) {
      console.error('Verify Klarna error:', err.message);
    }
  }
  if (!o.paid && stripe && sessionId) {
    try {
      const s = await stripe.checkout.sessions.retrieve(String(sessionId));
      if (s.payment_status === 'paid' && s.metadata && s.metadata.orderId === o.id) markPaid(o.id, s);
    } catch (err) {
      console.error('Verify error:', err.message);
    }
  }
  res.json({ order: publicOrder(o) });
});

app.get('/api/orders/:id/qr', loadPublicOrder, async (req, res) => {
  const o = req.order;
  if (!o.paid || !o.siteUrl || !isPremium(o.package)) return res.status(404).send('QR non disponibile');
  await sendQr(res, o.siteUrl, o.restaurant);
});

app.get('/paga/:id', (req, res) => res.sendFile(path.join(__dirname, 'public', 'pay.html')));

// ---------- Trova clienti: attività da OpenStreetMap (gratis, senza chiavi) ----------
const OVERPASS_URLS = (process.env.OVERPASS_URL || [
  'https://overpass-api.de/api/interpreter',
  'https://overpass.private.coffee/api/interpreter',
  'https://maps.mail.ru/osm/tools/overpass/api/interpreter',
  'https://overpass.kumi.systems/api/interpreter',
  'https://overpass.osm.jp/api/interpreter',
].join(','))
  .split(',').map(s => s.trim()).filter(Boolean);
const LEAD_TYPES = {
  ristoranti: { label: 'Ristoranti e pizzerie', q: ['nwr["amenity"~"^(restaurant|fast_food)$"]'] },
  bar: { label: 'Bar, caffè, gelaterie', q: ['nwr["amenity"~"^(cafe|bar|pub|ice_cream)$"]'] },
  bellezza: { label: 'Parrucchieri ed estetica', q: ['nwr["shop"~"^(hairdresser|beauty|cosmetics|massage|tattoo)$"]'] },
  negozi: { label: 'Negozi', q: ['nwr["shop"]["shop"!~"^(hairdresser|beauty|supermarket|convenience|vacant|kiosk)$"]'] },
  alimentari: { label: 'Alimentari e botteghe', q: ['nwr["shop"~"^(bakery|butcher|pastry|greengrocer|deli|cheese|wine|alcohol|seafood|confectionery|coffee)$"]'] },
  artigiani: { label: 'Artigiani e officine', q: ['nwr["craft"]', 'nwr["shop"~"^(car_repair|tyres|bicycle)$"]'] },
  alloggi: { label: 'B&B, hotel, agriturismi', q: ['nwr["tourism"~"^(hotel|guest_house|hostel|apartment|chalet)$"]'] },
  professionisti: { label: 'Studi e professionisti', q: ['nwr["office"]', 'nwr["healthcare"]["healthcare"!~"^(pharmacy|hospital)$"]', 'nwr["amenity"~"^(dentist|doctors|veterinary)$"]'] },
};
const leadCache = new Map(); // "città|tipo" -> { at, leads }
const SOCIAL_RE = /facebook\.com|instagram\.com|fb\.com|tiktok\.com|linktr\.ee|tripadvisor\.|thefork\.|justeat\.|deliveroo\.|glovoapp\./i;
const TYPE_IT = {
  restaurant: 'Ristorante', fast_food: 'Fast food', cafe: 'Bar/Caffè', bar: 'Bar', pub: 'Pub', ice_cream: 'Gelateria',
  hairdresser: 'Parrucchiere', beauty: 'Centro estetico', cosmetics: 'Cosmetica', massage: 'Massaggi', tattoo: 'Tatuaggi',
  bakery: 'Panetteria', butcher: 'Macelleria', pastry: 'Pasticceria', greengrocer: 'Fruttivendolo', deli: 'Gastronomia',
  cheese: 'Formaggi', wine: 'Enoteca', alcohol: 'Enoteca', seafood: 'Pescheria', confectionery: 'Dolciumi', coffee: 'Torrefazione',
  car_repair: 'Officina', tyres: 'Gommista', bicycle: 'Bici', hotel: 'Hotel', guest_house: 'B&B', hostel: 'Ostello',
  apartment: 'Appartamenti', chalet: 'Chalet', dentist: 'Dentista', doctors: 'Studio medico', veterinary: 'Veterinario',
  clothes: 'Abbigliamento', shoes: 'Scarpe', florist: 'Fiorista', jewelry: 'Gioielleria', optician: 'Ottica', furniture: 'Arredamento',
};

// Separa più numeri scritti insieme ("+39 333...;+39 334..." o "+39333...+39334...")
// e tiene solo quelli validi, in formato internazionale (+39...)
function splitPhones(raw) {
  const chunks = raw.replace(/https?:\/\/(api\.)?wa\.me\/|https?:\/\/api\.whatsapp\.com\/send\?phone=/gi, ';')
    .split(/[;,/|\n]|(?=\+)/).map(c => c.trim()).filter(Boolean);
  const out = [];
  const add = n => {
    let d = n.replace(/[^\d+]/g, '');
    if (d.startsWith('00')) d = '+' + d.slice(2);
    if (!d.startsWith('+')) d = /^39\d{9,10}$/.test(d) ? '+' + d : '+39' + d;
    const digits = d.slice(1);
    if (digits.length >= 9 && digits.length <= 13 && !out.includes(d)) out.push(d);
  };
  for (const c0 of chunks) {
    const c = c0.replace(/^00/, '+');
    const digits = c.replace(/\D/g, '');
    if (digits.length <= 13) { add(c); continue; }
    // troppe cifre: più numeri separati da spazi. Li ricompongo pezzo per pezzo:
    // un numero è completo quando ha almeno 9 cifre (senza il prefisso +39)
    let cur = '';
    const national = x => x.replace(/\D/g, '').replace(/^39(?=\d{9})/, '').length;
    for (const tok of c.split(/\s+/)) {
      cur += tok;
      if (national(cur) >= 9) { add(cur); cur = ''; }
    }
    if (cur) add(cur);
  }
  return out;
}

function leadFromOsm(e) {
  const t = e.tags || {};
  if (!t.name) return null;
  const phones = splitPhones([t.phone, t['contact:phone'], t['contact:mobile'], t.mobile].filter(Boolean).join(';'));
  // WhatsApp dichiarato dall'attività su OpenStreetMap (uno o più numeri o link wa.me)
  const whatsapps = splitPhones(String(t['contact:whatsapp'] || t.whatsapp || ''));
  const site = t.website || t['contact:website'] || t.url || '';
  const social = [t['contact:facebook'], t['contact:instagram'], t.facebook, t.instagram, SOCIAL_RE.test(site) ? site : '']
    .filter(Boolean)[0] || '';
  const realSite = site && !SOCIAL_RE.test(site) ? site : '';
  const kind = t.amenity || t.shop || t.craft || t.tourism || t.office || t.healthcare || '';
  const street = [t['addr:street'], t['addr:housenumber']].filter(Boolean).join(' ');
  const city = t['addr:city'] || '';
  const address = [street, city].filter(Boolean).join(', ');
  return {
    id: `${e.type[0]}${e.id}`,
    name: t.name,
    kind: TYPE_IT[kind] || (t.craft ? 'Artigiano' : t.office ? 'Studio/Ufficio' : kind.replace(/_/g, ' ')),
    phones: [...new Set(phones)].slice(0, 3),
    whatsapp: whatsapps[0] || '',
    whatsapps,
    website: realSite ? (/^https?:\/\//i.test(realSite) ? realSite : 'https://' + realSite) : '',
    social: social ? (/^https?:\/\//i.test(social) ? social : 'https://' + social) : '',
    address,
    maps: 'https://www.google.com/maps/search/?api=1&query=' + encodeURIComponent([t.name, street, city].filter(Boolean).join(' ')),
  };
}

const NOMINATIM_URL = process.env.NOMINATIM_URL || 'https://nominatim.openstreetmap.org/search';
const cityAreaCache = new Map();
async function findArea(name, scope = 'comune') {
  const k = scope + '|' + name.toLowerCase();
  if (cityAreaCache.has(k)) return cityAreaCache.get(k);
  const url = `${NOMINATIM_URL}?format=jsonv2&countrycodes=it&limit=10&accept-language=it&q=${encodeURIComponent(name)}`;
  const r = await fetch(url, { headers: { 'User-Agent': OSM_UA }, signal: AbortSignal.timeout(10000) });
  if (!r.ok) throw new Error('Nominatim ' + r.status);
  const list = (await r.json()).filter(x => x.osm_type === 'relation');
  const re = SCOPES[scope] && SCOPES[scope].types;
  const hit = (re && list.find(x => re.test(x.addresstype || x.type))) || (scope === 'comune' ? list[0] : null);
  const id = hit ? 3600000000 + Number(hit.osm_id) : null;
  if (id) cityAreaCache.set(k, id);
  return id;
}

const OSM_UA = 'Nerodoro-Studio/1.0 (+https://github.com/l13291221-cmyk/Soldi-bunker-)';
async function overpassOnce(url, query, signal) {
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'User-Agent': OSM_UA, 'Accept': 'application/json' },
    body: 'data=' + encodeURIComponent(query),
    signal,
  });
  const text = await r.text();
  if (!r.ok) throw new Error(`${new URL(url).hostname}: HTTP ${r.status}`);
  let data;
  try { data = JSON.parse(text); } catch { throw new Error(`${new URL(url).hostname}: risposta non valida`); }
  if (data.remark && /timed out|runtime error|out of memory/i.test(data.remark) && !(data.elements || []).length) {
    throw new Error(`${new URL(url).hostname}: ${data.remark.slice(0, 80)}`);
  }
  return data;
}
async function overpass(query, timeoutMs = 80000) {
  // Chiedo a tutti i server insieme e tengo la prima risposta valida.
  // Se un server è occupato (429/504) riprovo una volta dopo qualche secondo.
  const controllers = OVERPASS_URLS.map(() => new AbortController());
  const attempts = OVERPASS_URLS.map(async (url, i) => {
    const signal = AbortSignal.any([controllers[i].signal, AbortSignal.timeout(timeoutMs)]);
    try {
      return { data: await overpassOnce(url, query, signal), i };
    } catch (err) {
      if (signal.aborted || !/HTTP (429|502|503|504)/.test(err.message)) throw err;
      await new Promise(r => setTimeout(r, 4000 + i * 1500));
      return { data: await overpassOnce(url, query, signal), i };
    }
  });
  try {
    const { data, i } = await Promise.any(attempts);
    controllers.forEach((c, j) => j !== i && c.abort());
    return data;
  } catch (err) {
    const reasons = (err.errors || [err]).map(e => e.name === 'TimeoutError' ? 'timeout' : e.cause ? `${e.message} (${e.cause.code || e.cause.message})` : e.message);
    const e2 = new Error(reasons.join(' · '));
    throw e2;
  }
}

const SCOPES = {
  comune: { label: 'Comune', types: /^(city|town|village|municipality|suburb|quarter|borough|hamlet|city_district)$/, limit: 1500, timeout: 60 },
  provincia: { label: 'Provincia', types: /^(county|province|state_district)$/, limit: 3000, timeout: 90 },
  regione: { label: 'Regione', types: /^(state|region)$/, limit: 4000, timeout: 120 },
  italia: { label: 'Tutta Italia', types: null, limit: 5000, timeout: 170 },
};
// Filtri applicati direttamente sul server mappe: arrivano solo le attività contattabili
const NEED_TAGS = {
  wa: ['["contact:whatsapp"]', '["whatsapp"]'],
  phone: ['["phone"]', '["contact:phone"]', '["contact:mobile"]', '["contact:whatsapp"]', '["whatsapp"]'],
  all: [''],
};

// ---------- Trova clienti: Google Maps (Places API, serve la chiave GOOGLE_PLACES_KEY) ----------
const GOOGLE_PLACES_KEY = process.env.GOOGLE_PLACES_KEY || '';
const GOOGLE_QUERY = {
  ristoranti: 'ristoranti e pizzerie', bar: 'bar e caffè', bellezza: 'parrucchieri ed estetiste', negozi: 'negozi',
  alimentari: 'panetterie macellerie e alimentari', artigiani: 'artigiani e officine', alloggi: 'B&B e hotel', professionisti: 'studi professionali',
};
const isMobileIt = p => /^3\d{8,9}$/.test(p.replace(/\D/g, '').replace(/^39(?=3\d{8,9}$)/, ''));
function leadFromGoogle(p) {
  if (!p.displayName || p.businessStatus === 'CLOSED_PERMANENTLY') return null;
  const phones = splitPhones(p.internationalPhoneNumber || p.nationalPhoneNumber || '');
  const site = p.websiteUri || '';
  const social = SOCIAL_RE.test(site) ? site : '';
  return {
    id: 'g' + p.id,
    name: p.displayName.text,
    kind: (p.primaryTypeDisplayName && p.primaryTypeDisplayName.text) || '',
    phones,
    // Google non dice chi ha WhatsApp: un cellulare di un'attività quasi sempre ce l'ha
    whatsapps: phones.filter(isMobileIt),
    whatsapp: phones.find(isMobileIt) || '',
    waGuess: true,
    website: site && !social ? site : '',
    social,
    address: (p.formattedAddress || '').replace(/, Italia$/, ''),
    maps: p.googleMapsUri || 'https://www.google.com/maps/search/?api=1&query=' + encodeURIComponent(p.displayName.text),
    source: 'google',
  };
}
async function googleLeads(type, city) {
  const fields = ['id', 'displayName', 'formattedAddress', 'nationalPhoneNumber', 'internationalPhoneNumber', 'websiteUri',
    'googleMapsUri', 'businessStatus', 'primaryTypeDisplayName'].map(f => 'places.' + f).join(',') + ',nextPageToken';
  const out = [];
  let pageToken = '';
  // Google dà al massimo 60 risultati (3 pagine da 20) per ricerca
  for (let page = 0; page < 3; page++) {
    const r = await fetch('https://places.googleapis.com/v1/places:searchText', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Goog-Api-Key': GOOGLE_PLACES_KEY, 'X-Goog-FieldMask': fields },
      body: JSON.stringify({ textQuery: `${GOOGLE_QUERY[type]} a ${city}`, languageCode: 'it', regionCode: 'IT', pageSize: 20, ...(pageToken && { pageToken }) }),
      signal: AbortSignal.timeout(20000),
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error('Google ' + r.status + ': ' + ((d.error && d.error.message) || 'errore').slice(0, 200));
    out.push(...(d.places || []));
    if (!d.nextPageToken) break;
    pageToken = d.nextPageToken;
  }
  return out.map(leadFromGoogle).filter(Boolean);
}

app.get('/api/admin/leads', requireAdmin, async (req, res) => {
  if (req.query.source === 'google') {
    if (!GOOGLE_PLACES_KEY) return res.status(400).json({ error: 'Google Maps non è attivo: manca la chiave GOOGLE_PLACES_KEY su Render.' });
    const city = String(req.query.city || '').trim().slice(0, 60);
    const type = GOOGLE_QUERY[req.query.type] ? req.query.type : 'ristoranti';
    if (city.length < 2) return res.status(400).json({ error: 'Scrivi il nome della zona' });
    const key = ['google', city.toLowerCase(), type].join('|');
    const cached = leadCache.get(key);
    if (cached && Date.now() - cached.at < 24 * 60 * 60 * 1000) return res.json({ leads: cached.leads, city, type, source: 'google' });
    try {
      let leads = await googleLeads(type, city);
      if (req.query.need === 'wa') leads = leads.filter(l => l.whatsapps.length);
      else if (req.query.need !== 'all') leads = leads.filter(l => l.phones.length);
      leadCache.set(key, { at: Date.now(), leads });
      return res.json({ leads, city, type, source: 'google' });
    } catch (err) {
      console.error('Google Places error:', err.message);
      return res.status(502).json({ error: 'Google Maps non risponde.', detail: err.message });
    }
  }
  const scope = SCOPES[req.query.scope] ? req.query.scope : 'comune';
  const city = scope === 'italia' ? 'Italia' : String(req.query.city || '').trim().replace(/["\\]/g, '').slice(0, 60);
  const type = LEAD_TYPES[req.query.type] ? req.query.type : 'ristoranti';
  let need = NEED_TAGS[req.query.need] ? req.query.need : 'phone';
  if (need === 'all' && scope !== 'comune') need = 'phone'; // zone grandi: solo chi ha un contatto
  if (city.length < 2) return res.status(400).json({ error: 'Scrivi il nome della zona' });
  const key = [city.toLowerCase(), type, scope, need].join('|');
  const cached = leadCache.get(key);
  if (cached && Date.now() - cached.at < 60 * 60 * 1000) return res.json({ leads: cached.leads, city, type, scope, need });

  let areaPart;
  if (scope === 'italia') {
    areaPart = 'area["ISO3166-1"="IT"]["admin_level"="2"]->.a;';
  } else {
    // Veloce: trovo prima la zona con Nominatim e cerco solo dentro quell'area
    const areaId = await findArea(city, scope).catch(() => null);
    if (areaId) areaPart = `area(id:${areaId})->.a;`;
    else if (scope === 'comune') {
      const cityRe = '^' + city.replace(/[.*+?^${}()|[\]]/g, '\\$&') + '$';
      areaPart = `area["ISO3166-1"="IT"]["admin_level"="2"]->.it;
rel["boundary"="administrative"]["admin_level"~"^(8|9|10)$"]["name"~"${cityRe}",i](area.it);
map_to_area->.a;`;
    } else {
      return res.status(404).json({ error: `Non trovo la ${SCOPES[scope].label.toLowerCase()} "${city}". Scrivila per intero, es. "Emilia-Romagna" o "Bologna".` });
    }
  }
  const sc = SCOPES[scope];
  const parts = LEAD_TYPES[type].q.flatMap(q => NEED_TAGS[need].map(t => q + t + '(area.a);'));
  const query = `[out:json][timeout:${sc.timeout}][maxsize:268435456];
${areaPart}
(${parts.join('')});
out tags center ${sc.limit};`;
  try {
    const data = await overpass(query, (sc.timeout + 15) * 1000);
    const seen = new Set();
    const leads = (data.elements || []).map(leadFromOsm).filter(l => {
      // stesso nome in città diverse è normale: doppione solo se coincide anche il contatto
      const k = l && (l.name.toLowerCase() + '|' + (l.whatsapp || l.phones[0] || l.address));
      if (!l || seen.has(k)) return false;
      seen.add(k);
      return true;
    });
    leadCache.set(key, { at: Date.now(), leads });
    res.json({ leads, city, type, scope, need });
  } catch (err) {
    console.error('Overpass error:', err.message);
    res.status(502).json({ error: 'Il servizio mappe non risponde, riprova tra un minuto.', detail: err.message.slice(0, 400) });
  }
});
// Controllo qualità del sito di un'attività: trova i siti "da rifare"
const dns = require('dns').promises;
const net = require('net');
const siteCheckCache = new Map();
const FREE_BUILDERS = /(\.wixsite\.com|\.altervista\.org|\.jimdo(site)?\.com|\.webnode\.|\.blogspot\.|\.wordpress\.com|\.business\.site|\.weebly\.com|\.site123\.me|\.godaddysites\.com|\.paginegialle\.it|\.sites\.google\.com)/i;
const EMPTY_WORDS = /(sito in costruzione|in allestimento|under construction|coming soon|domain (is )?for sale|dominio in vendita|questo dominio|parked (free|domain)|default web page|index of \/|it works!)/i;
const MODERN_SITE = /\/_next\/|__NEXT_DATA__|__NUXT__|id="__nuxt"|data-reactroot|id="root"><\/div>|id="app"><\/div>|astro-island|\/_astro\/|___gatsby|\/_app\/immutable\/|static\.parastorage\.com|squarespace-cdn\.com|assets\.website-files\.com|webflow\.com/i;
function isPrivateIp(ip) {
  if (net.isIPv4(ip)) {
    const [a, b] = ip.split('.').map(Number);
    return a === 10 || a === 127 || a === 0 || (a === 169 && b === 254) || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168) || a >= 224;
  }
  return ip === '::1' || /^f[cd]/i.test(ip) || /^fe80/i.test(ip) || /^::ffff:(10|127|192\.168)\./.test(ip);
}
async function checkSite(rawUrl) {
  const reasons = [];
  let url;
  try { url = new URL(rawUrl); } catch { return { bad: true, reasons: ['Link del sito non valido'] }; }
  if (!/^https?:$/.test(url.protocol)) return { bad: true, reasons: ['Link del sito non valido'] };
  if (FREE_BUILDERS.test(url.hostname)) reasons.push('Sito gratuito fai-da-te');
  try {
    const { address } = await dns.lookup(url.hostname);
    if (isPrivateIp(address) && !process.env.SITECHECK_ALLOW_PRIVATE) return { bad: true, reasons: ['Indirizzo non valido'] };
  } catch {
    return { bad: true, reasons: ['Il sito non esiste più (dominio scaduto)'] };
  }
  const started = Date.now();
  let r, html = '';
  try {
    r = await fetch(url, {
      redirect: 'follow',
      signal: AbortSignal.timeout(15000),
      headers: { 'User-Agent': 'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/126 Mobile Safari/537.36', 'Accept-Language': 'it-IT,it' },
    });
    const reader = r.body.getReader();
    let bytes = 0;
    const dec = new TextDecoder();
    while (bytes < 400000) {
      const { done, value } = await reader.read();
      if (done) break;
      bytes += value.length;
      html += dec.decode(value, { stream: true });
    }
    reader.cancel().catch(() => {});
  } catch (err) {
    return { bad: true, reasons: [err.name === 'TimeoutError' ? 'Il sito non si apre (troppo lento)' : 'Il sito non si apre'] };
  }
  const ms = Date.now() - started;
  if (r.status >= 400) return { bad: true, reasons: [`Il sito dà errore (${r.status})`] };
  const finalUrl = new URL(r.url || url);
  if (finalUrl.protocol === 'http:') reasons.push('Non sicuro (senza https)');
  if (FREE_BUILDERS.test(finalUrl.hostname) && !reasons.includes('Sito gratuito fai-da-te')) reasons.push('Sito gratuito fai-da-te');
  if (/facebook\.com|instagram\.com/i.test(finalUrl.hostname)) reasons.push('Rimanda solo ai social');
  if (!/<meta[^>]+name=["']?viewport/i.test(html)) reasons.push('Non adatto al telefono');
  if (ms > 5000) reasons.push(`Lento (${(ms / 1000).toFixed(1)}s)`);
  const text = html.replace(/<script[\s\S]*?<\/script>|<style[\s\S]*?<\/style>|<[^>]+>/gi, ' ').replace(/\s+/g, ' ');
  // Siti moderni (Next.js, React, Nuxt...) caricano i testi con JavaScript: l'HTML sembra
  // vuoto ma il sito è pieno. Se è anche https e adatto al telefono, è fatto da un professionista.
  const modern = MODERN_SITE.test(html) && finalUrl.protocol === 'https:' && !reasons.includes('Non adatto al telefono');
  if (EMPTY_WORDS.test(text)) reasons.push('In costruzione o vuoto');
  else if (text.length < 400 && !modern) reasons.push('Quasi vuoto');
  if (/<(font|marquee|frameset|center)\b|\.swf\b/i.test(html)) reasons.push('Grafica vecchia');
  const years = [...text.matchAll(/(?:©|&copy;|copyright)\s*(?:\d{4}\s*[-–]\s*)?((?:19|20)\d{2})/gi)].map(m => +m[1]);
  const thisYear = new Date().getFullYear();
  if (years.length && Math.max(...years) <= thisYear - 4) reasons.push(`Fermo al ${Math.max(...years)}`);
  return { bad: reasons.length > 0, reasons, ms, modern };
}
app.get('/api/admin/site-check', requireAdmin, async (req, res) => {
  const u = String(req.query.url || '').slice(0, 500);
  const c = siteCheckCache.get(u);
  if (c && Date.now() - c.at < 24 * 60 * 60 * 1000) return res.json(c.result);
  const result = await checkSite(u).catch(() => ({ bad: true, reasons: ['Il sito non si apre'] }));
  siteCheckCache.set(u, { at: Date.now(), result });
  res.json(result);
});
// Diagnosi: prova Nominatim e ogni server mappe con una richiesta minuscola
app.get('/api/admin/leads-debug', requireAdmin, async (req, res) => {
  const out = {};
  const t = async (name, fn) => {
    const s0 = Date.now();
    try { out[name] = { ok: true, info: await fn(), ms: Date.now() - s0 }; }
    catch (e) { out[name] = { ok: false, error: e.name === 'TimeoutError' ? 'timeout' : (e.message + (e.cause ? ' (' + (e.cause.code || e.cause.message) + ')' : '')), ms: Date.now() - s0 }; }
  };
  await Promise.all([
    t('nominatim', async () => 'area ' + await findArea(String(req.query.city || 'Monza'), SCOPES[req.query.scope] ? req.query.scope : 'comune')),
    ...OVERPASS_URLS.map(u => t(new URL(u).hostname, async () => {
      const d = await overpassOnce(u, '[out:json][timeout:10];node(1);out;', AbortSignal.timeout(20000));
      return (d.elements || []).length + ' risultati';
    })),
  ]);
  res.json(out);
});
app.get('/api/admin/lead-types', requireAdmin, (req, res) => {
  res.json({ types: Object.entries(LEAD_TYPES).map(([id, t]) => ({ id, label: t.label })), google: !!GOOGLE_PLACES_KEY });
});

// ---------- Sveglia siti: visita i link ogni 5 minuti (anti-spegnimento Render gratuito) ----------
const MONITORS_FILE = path.join(__dirname, 'data', 'monitors.json');
const PING_EVERY_MS = 5 * 60 * 1000;
// Render imposta RENDER_EXTERNAL_URL da solo; in locale non ci auto-pinghiamo
const SELF_URL = (process.env.RENDER_EXTERNAL_URL || BASE_URL).replace(/\/$/, '');
const selfPingEnabled = !/localhost|127\.0\.0\.1/.test(SELF_URL);
let monitors = (() => { try { return JSON.parse(fs.readFileSync(MONITORS_FILE, 'utf8')); } catch { return []; } })();
const selfStatus = { url: SELF_URL, enabled: selfPingEnabled };
function saveMonitors() {
  fs.mkdirSync(path.dirname(MONITORS_FILE), { recursive: true });
  fs.writeFileSync(MONITORS_FILE, JSON.stringify(monitors, null, 2));
}

async function pingUrl(url) {
  const started = Date.now();
  try {
    // 60 secondi: un sito Render addormentato può metterci ~50s a svegliarsi
    const r = await fetch(url, {
      signal: AbortSignal.timeout(60000),
      headers: { 'User-Agent': 'Nerodoro-Sveglia/1.0' },
      redirect: 'follow',
    });
    await r.body?.cancel();
    return { ok: r.status < 500, status: r.status, ms: Date.now() - started, at: new Date().toISOString() };
  } catch (err) {
    return { ok: false, status: 0, error: err.name === 'TimeoutError' ? 'Timeout' : 'Non raggiungibile', ms: Date.now() - started, at: new Date().toISOString() };
  }
}
async function pingMonitor(m) {
  m.last = await pingUrl(m.url);
  saveMonitors();
  return m;
}
async function pingAll() {
  if (selfPingEnabled) selfStatus.last = await pingUrl(`${SELF_URL}/`);
  await Promise.all(monitors.map(pingMonitor));
}
setInterval(() => pingAll().catch(err => console.error('Ping error:', err.message)), PING_EVERY_MS);
setTimeout(() => pingAll().catch(() => {}), 10000);

app.get('/healthz', (req, res) => res.type('text').send('ok'));

app.get('/api/admin/monitors', requireAdmin, (req, res) => {
  res.json({ monitors, self: selfStatus, everyMinutes: PING_EVERY_MS / 60000 });
});
app.post('/api/admin/monitors', requireAdmin, async (req, res) => {
  const url = cleanUrl(req.body && req.body.url);
  if (!url) return res.status(400).json({ error: 'Link non valido' });
  if (monitors.some(m => m.url === url)) return res.status(400).json({ error: 'Questo link è già nell\'elenco' });
  if (monitors.length >= 50) return res.status(400).json({ error: 'Massimo 50 siti' });
  const m = {
    id: crypto.randomBytes(6).toString('hex'),
    url,
    name: String((req.body && req.body.name) || '').trim().slice(0, 80) || new URL(url).hostname,
    createdAt: new Date().toISOString(),
  };
  monitors.push(m);
  await pingMonitor(m);
  res.json({ monitor: m });
});
app.post('/api/admin/monitors/:id/ping', requireAdmin, async (req, res) => {
  const m = monitors.find(x => x.id === req.params.id);
  if (!m) return res.status(404).json({ error: 'Non trovato' });
  res.json({ monitor: await pingMonitor(m) });
});
app.delete('/api/admin/monitors/:id', requireAdmin, (req, res) => {
  const before = monitors.length;
  monitors = monitors.filter(x => x.id !== req.params.id);
  if (monitors.length === before) return res.status(404).json({ error: 'Non trovato' });
  saveMonitors();
  res.json({ ok: true });
});

app.listen(PORT, () => console.log(`Nerodoro Studio attivo su ${BASE_URL}`));
