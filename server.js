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
const PRICE = parseFloat(String(process.env.PREZZO || '2671').replace(',', '.')) || 2671;
// Numero WhatsApp Business (solo cifre, con prefisso internazionale)
const WHATSAPP = String(process.env.WHATSAPP ?? '27710933377').replace(/\D/g, '');
const DEFAULT_DESCRIPTION = 'Sito web professionale per la tua attività + 1 anno di assistenza gratuita';
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
  return { ...o, code: formatCode(o.id), payUrl: `${BASE_URL}/paga/${o.id}` };
}
function publicOrder(o) {
  return {
    id: o.id,
    code: formatCode(o.id),
    restaurant: o.restaurant,
    description: o.description,
    amount: o.amount,
    currency: CURRENCY,
    paid: o.paid,
    // Il link del sito si vede SOLO dopo il pagamento
    siteUrl: o.paid ? o.siteUrl || null : null,
  };
}
function markPaid(orderId, sessionId) {
  const o = orders[orderId];
  if (!o || o.paid) return;
  o.paid = true;
  o.paidAt = new Date().toISOString();
  o.stripeSessionId = sessionId;
  saveOrders();
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
    if (s.payment_status === 'paid' && s.metadata && s.metadata.orderId) markPaid(s.metadata.orderId, s.id);
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

app.get('/api/admin/me', (req, res) => res.json({ admin: isAdmin(req) }));

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
  if (!restaurant || !String(restaurant).trim()) return res.status(400).json({ error: 'Nome dell\'attività obbligatorio' });
  const cents = parseAmount(amount);
  if (cents === null) return res.status(400).json({ error: 'Prezzo non valido (minimo 0,50)' });
  const url = cleanUrl(siteUrl);
  if (url === null) return res.status(400).json({ error: 'Link del sito non valido' });
  const id = newCode();
  orders[id] = {
    id,
    restaurant: String(restaurant).trim().slice(0, 120),
    description: String(description || DEFAULT_DESCRIPTION).trim().slice(0, 300),
    amount: cents,
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
  if (b.amount !== undefined && !o.paid) {
    const cents = parseAmount(b.amount);
    if (cents === null) return res.status(400).json({ error: 'Prezzo non valido' });
    o.amount = cents;
  }
  saveOrders();
  res.json({ order: adminOrder(o) });
});

app.delete('/api/admin/orders/:id', requireAdmin, (req, res) => {
  if (!orders[req.params.id]) return res.status(404).json({ error: 'Ordine non trovato' });
  delete orders[req.params.id];
  saveOrders();
  res.json({ ok: true });
});

// ---------- API pubbliche (cliente) ----------
app.get('/api/config', (req, res) => res.json({ price: Math.round(PRICE * 100), currency: CURRENCY, description: DEFAULT_DESCRIPTION, whatsapp: WHATSAPP }));

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

app.post('/api/orders/:id/checkout', loadPublicOrder, async (req, res) => {
  const o = req.order;
  if (o.paid) return res.status(400).json({ error: 'Ordine già pagato' });
  if (!stripe) return res.status(503).json({ error: 'Pagamenti non ancora configurati' });
  try {
    const session = await stripe.checkout.sessions.create({
      mode: 'payment',
      line_items: [{
        quantity: 1,
        price_data: {
          currency: CURRENCY,
          unit_amount: o.amount,
          product_data: { name: `Sito web — ${o.restaurant}`, description: `${o.description} (codice ${formatCode(o.id)})` },
        },
      }],
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

// Verifica il pagamento al ritorno da Stripe (funziona anche senza webhook)
app.post('/api/orders/:id/verify', loadPublicOrder, async (req, res) => {
  const o = req.order;
  const sessionId = req.body && req.body.sessionId;
  if (!o.paid && stripe && sessionId) {
    try {
      const s = await stripe.checkout.sessions.retrieve(String(sessionId));
      if (s.payment_status === 'paid' && s.metadata && s.metadata.orderId === o.id) markPaid(o.id, s.id);
    } catch (err) {
      console.error('Verify error:', err.message);
    }
  }
  res.json({ order: publicOrder(o) });
});

app.get('/paga/:id', (req, res) => res.sendFile(path.join(__dirname, 'public', 'pay.html')));

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
  if (selfPingEnabled) selfStatus.last = await pingUrl(`${SELF_URL}/healthz`);
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
