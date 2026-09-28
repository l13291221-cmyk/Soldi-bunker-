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
const PRICE_PREMIUM = parseFloat(String(process.env.PREZZO_PREMIUM || '3200').replace(',', '.')) || 3200;
// I due pacchetti mostrati sul sito e scelti nell'admin
const PACKAGES = {
  base: {
    id: 'base', name: 'Base', price: Math.round(PRICE * 100),
    description: DEFAULT_DESCRIPTION,
    features: ['Sito web completo per la tua attività', '1 anno di assistenza gratuita', 'Pannello per modificare menu, foto e prezzi da soli, dal telefono', 'Perfetto da smartphone'],
  },
  premium: {
    id: 'premium', name: 'Premium', price: Math.round(PRICE_PREMIUM * 100),
    description: 'Sito web professionale + dominio personalizzato (www.tuonome.it) + QR code + 1 anno di assistenza gratuita',
    features: ['Tutto quello che c\'è nel Base', 'Indirizzo personalizzato: www.tuonome.it', 'QR code pronto da stampare (menu, vetrina, biglietti)', 'Dominio incluso per il primo anno'],
  },
};
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
    package: o.package || 'base',
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
  const pkg = PACKAGES[req.body && req.body.package] ? req.body.package : 'base';
  if (!restaurant || !String(restaurant).trim()) return res.status(400).json({ error: 'Nome dell\'attività obbligatorio' });
  const cents = parseAmount(amount);
  if (cents === null) return res.status(400).json({ error: 'Prezzo non valido (minimo 0,50)' });
  const url = cleanUrl(siteUrl);
  if (url === null) return res.status(400).json({ error: 'Link del sito non valido' });
  const id = newCode();
  orders[id] = {
    id,
    restaurant: String(restaurant).trim().slice(0, 120),
    description: String(description || PACKAGES[pkg].description).trim().slice(0, 300),
    package: pkg,
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

app.get('/api/orders/:id/qr', loadPublicOrder, async (req, res) => {
  const o = req.order;
  if (!o.paid || !o.siteUrl || o.package !== 'premium') return res.status(404).send('QR non disponibile');
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

app.get('/api/admin/leads', requireAdmin, async (req, res) => {
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
  if (EMPTY_WORDS.test(text)) reasons.push('In costruzione o vuoto');
  else if (text.length < 400) reasons.push('Quasi vuoto');
  if (/<(font|marquee|frameset|center)\b|\.swf\b/i.test(html)) reasons.push('Grafica vecchia');
  const years = [...text.matchAll(/(?:©|&copy;|copyright)\s*(?:\d{4}\s*[-–]\s*)?((?:19|20)\d{2})/gi)].map(m => +m[1]);
  const thisYear = new Date().getFullYear();
  if (years.length && Math.max(...years) <= thisYear - 4) reasons.push(`Fermo al ${Math.max(...years)}`);
  return { bad: reasons.length > 0, reasons, ms };
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
  res.json({ types: Object.entries(LEAD_TYPES).map(([id, t]) => ({ id, label: t.label })) });
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
