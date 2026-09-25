// RistoWeb Studio — landing + pagamenti Stripe + mini admin con PIN
const path = require('path');
const fs = require('fs');
const crypto = require('crypto');
const express = require('express');

try { process.loadEnvFile(path.join(__dirname, '.env')); } catch { /* .env opzionale */ }

const PORT = process.env.PORT || 3000;
const ADMIN_PIN = process.env.ADMIN_PIN || '';
const BASE_URL = (process.env.BASE_URL || `http://localhost:${PORT}`).replace(/\/$/, '');
const CURRENCY = (process.env.CURRENCY || 'eur').toLowerCase();
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
function publicOrder(o) {
  return {
    id: o.id,
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
// Blocco anti-tentativi: max 5 PIN sbagliati ogni 15 minuti per IP
const failedLogins = new Map();
function tooManyAttempts(ip) {
  const f = failedLogins.get(ip);
  if (!f) return false;
  if (Date.now() - f.first > 15 * 60 * 1000) { failedLogins.delete(ip); return false; }
  return f.count >= 5;
}
function recordFailure(ip) {
  const f = failedLogins.get(ip);
  if (!f || Date.now() - f.first > 15 * 60 * 1000) failedLogins.set(ip, { count: 1, first: Date.now() });
  else f.count++;
}

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
  if (tooManyAttempts(ip)) return res.status(429).json({ error: 'Troppi tentativi. Riprova tra 15 minuti.' });
  if (!pinMatches((req.body && req.body.pin) || '')) {
    recordFailure(ip);
    return res.status(401).json({ error: 'PIN errato' });
  }
  failedLogins.delete(ip);
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
    .map(o => ({ ...o, payUrl: `${BASE_URL}/paga/${o.id}` }));
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
  if (!restaurant || !String(restaurant).trim()) return res.status(400).json({ error: 'Nome del ristorante obbligatorio' });
  const cents = parseAmount(amount);
  if (cents === null) return res.status(400).json({ error: 'Prezzo non valido (minimo 0,50)' });
  const url = cleanUrl(siteUrl);
  if (url === null) return res.status(400).json({ error: 'Link del sito non valido' });
  const id = crypto.randomBytes(9).toString('base64url');
  orders[id] = {
    id,
    restaurant: String(restaurant).trim().slice(0, 120),
    description: String(description || 'Sito web professionale per il tuo ristorante').trim().slice(0, 300),
    amount: cents,
    siteUrl: url,
    phone: String(phone || '').replace(/[^\d+]/g, '').slice(0, 20),
    paid: false,
    createdAt: new Date().toISOString(),
  };
  saveOrders();
  res.json({ order: { ...orders[id], payUrl: `${BASE_URL}/paga/${id}` } });
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
  res.json({ order: { ...o, payUrl: `${BASE_URL}/paga/${o.id}` } });
});

app.delete('/api/admin/orders/:id', requireAdmin, (req, res) => {
  if (!orders[req.params.id]) return res.status(404).json({ error: 'Ordine non trovato' });
  delete orders[req.params.id];
  saveOrders();
  res.json({ ok: true });
});

// ---------- API pubbliche (cliente) ----------
app.get('/api/orders/:id', (req, res) => {
  const o = orders[req.params.id];
  if (!o) return res.status(404).json({ error: 'Ordine non trovato' });
  res.json({ order: publicOrder(o) });
});

app.post('/api/orders/:id/checkout', async (req, res) => {
  const o = orders[req.params.id];
  if (!o) return res.status(404).json({ error: 'Ordine non trovato' });
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
          product_data: { name: `Sito web — ${o.restaurant}`, description: o.description },
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
app.post('/api/orders/:id/verify', async (req, res) => {
  const o = orders[req.params.id];
  if (!o) return res.status(404).json({ error: 'Ordine non trovato' });
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

app.listen(PORT, () => console.log(`RistoWeb Studio attivo su ${BASE_URL}`));
