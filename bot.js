// Bot WhatsApp: scrive da solo, dal WhatsApp Business collegato, alle attività trovate come in «Trova clienti»
// (senza sito, solo social o con il sito brutto). Manda 20-30 messaggi al giorno sparsi nelle fasce orarie scelte,
// un solo messaggio per numero, e segna chi risponde (chi dice «no» non viene più contattato).
// Il WhatsApp si collega come «dispositivo collegato» (come WhatsApp Web) con un codice o con il QR.
const fs = require('fs');
const path = require('path');
const QRCode = require('qrcode');

const TZ = process.env.BOT_TZ || 'Europe/Rome';
const DEFAULTS = {
  // «italia» = tutta Italia su OpenStreetMap; le città servono anche per Google Maps
  zones: ['italia', 'Milano', 'Roma', 'Napoli', 'Torino', 'Palermo', 'Genova', 'Bologna', 'Firenze', 'Bari', 'Catania',
    'Verona', 'Venezia', 'Padova', 'Brescia', 'Parma', 'Modena', 'Bergamo', 'Monza', 'Rimini'].join('\n'),
  types: ['ristoranti', 'bar'],
  osm: true, // OpenStreetMap: solo chi ha scritto il suo WhatsApp
  google: true, // Google Maps (se c'è la chiave): cellulari, prima di scrivere controllo che abbiano WhatsApp
  min: 25, max: 30, // messaggi al giorno (ogni giorno un numero a caso tra i due)
  hours: '9:30-12:30, 15:00-19:30',
  days: [1, 2, 3, 4, 5, 6], // 0 = domenica
  lang: 'it',
  firma: 'Simone',
  templates: '', // messaggi propri, uno per riga; vuoto = quelli già pronti
  autoReply: '', // risposta automatica a chi dice «sì»; vuoto = nessuna
  warmup: true, // i primi giorni ne manda meno: un numero nuovo che scrive subito a tanti sconosciuti viene bloccato
};
const WARMUP = [10, 15, 20, 25];
const MIN_GAP_MS = 4 * 60 * 1000; // mai due messaggi a meno di 4 minuti
const QUEUE_MIN = 40, QUEUE_MAX = 3000;
const RESEARCH_AFTER_MS = 30 * 864e5; // la stessa ricerca si rifà dopo 30 giorni (attività nuove)
const SEARCH_GAP_MS = 90 * 1000;
const MAX_SESSIONS = 3000;
// Nel backup vanno solo le chiavi che servono a restare collegati: le sessioni cambiano a ogni messaggio
// e si ricreano da sole, salvarle ogni 5 minuti farebbe crescere il backup senza motivo
const BACKUP_KEY_TYPES = ['pre-key', 'app-state-sync-key', 'lid-mapping', 'tctoken'];

// Chi non vuole essere contattato (in più lingue) e chi dice sì
const OPT_OUT = /^\s*(no+|nono)\b|\bstop\b|\bbasta\b|non (ci |mi )?(interessa|serve)|non siamo interessat|non sono interessat|non scriv|non contatt|cancell|rimuov|togliet|spam|unsubscribe|not interested|no thanks|don'?t (text|write|contact)|no me interesa|no gracias|pas int[ée]ress|kein interesse|nein danke/i;
const YES = /^\s*(s[iìí]+|certo|ok|okay|va bene|volentieri|perch[eé] no|mandate|manda|mandami|inviate|invia|yes|sure|oui|ja|claro|vale|d'accordo|👍)/i;

// Stessa conversione di Baileys (BufferJSON): le chiavi di WhatsApp sono Buffer, nel file diventano base64
const replacer = (k, v) => (Buffer.isBuffer(v) || v instanceof Uint8Array || (v && v.type === 'Buffer'))
  ? { type: 'Buffer', data: Buffer.from((v && v.data) || v).toString('base64') } : v;
const reviver = (k, v) => {
  if (v && typeof v === 'object' && v.type === 'Buffer' && typeof v.data === 'string') return Buffer.from(v.data, 'base64');
  if (v && typeof v === 'object' && !Array.isArray(v)) {
    const ks = Object.keys(v);
    if (ks.length && ks.every(x => !isNaN(parseInt(x, 10))) && Object.values(v).every(x => typeof x === 'number')) return Buffer.from(Object.values(v));
  }
  return v;
};
const toPlain = o => JSON.parse(JSON.stringify(o, replacer));
const revive = o => JSON.parse(JSON.stringify(o || {}), reviver);

const rand = (a, b) => a + Math.random() * (b - a);
const randInt = (a, b) => Math.floor(rand(a, b + 1));
const sleep = ms => new Promise(r => setTimeout(r, ms));
const digitsOf = n => String(n || '').replace(/\D/g, '');
const shuffle = a => { for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; };

// Ora italiana (il server di Render è in UTC)
const WD = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const clock = new Intl.DateTimeFormat('en-GB', { timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', weekday: 'short', hourCycle: 'h23' });
function local(t = Date.now()) {
  const p = Object.fromEntries(clock.formatToParts(new Date(t)).map(x => [x.type, x.value]));
  return { day: `${p.year}-${p.month}-${p.day}`, min: +p.hour * 60 + +p.minute + +p.second / 60, wd: WD.indexOf(p.weekday) };
}
const hhmm = m => `${Math.floor(m / 60)}:${String(Math.floor(m % 60)).padStart(2, '0')}`;
// "9:30-12:30, 15-19:30" → [[570, 750], [900, 1170]] (minuti dalla mezzanotte)
function parseHours(s) {
  const out = [];
  for (const part of String(s || '').split(/[,;\n]+/)) {
    const m = part.trim().match(/^(\d{1,2})(?:[:.](\d{2}))?\s*-\s*(\d{1,2})(?:[:.](\d{2}))?$/);
    if (!m) continue;
    const a = +m[1] * 60 + +(m[2] || 0), b = +m[3] * 60 + +(m[4] || 0);
    if (a < b && b <= 24 * 60) out.push([a, b]);
  }
  return out.sort((x, y) => x[0] - y[0]);
}
// "Monza" = comune; "provincia: Bergamo", "regione: Lombardia", "italia"
function parseZones(s) {
  return String(s || '').split('\n').map(x => x.trim()).filter(Boolean).map(line => {
    if (/^(tutta\s+(l')?)?italia$/i.test(line)) return { scope: 'italia', city: 'Italia' };
    const m = line.match(/^(comune|provincia|regione)\s*[:-]\s*(.+)$/i);
    return m ? { scope: m[1].toLowerCase(), city: m[2].trim() } : { scope: 'comune', city: line };
  });
}

module.exports = function createBot({ dataDir, isReady, searchLeads, checkSite, leadTypes, googleOn, messages, siteUrl }) {
  const BOT_FILE = path.join(dataDir, 'bot.json');
  const AUTH_FILE = path.join(dataDir, 'wa-auth.json');
  const readJson = (f, rev) => { try { return JSON.parse(fs.readFileSync(f, 'utf8'), rev); } catch { return {}; } };
  const writeJson = (f, data, rep) => {
    fs.mkdirSync(path.dirname(f), { recursive: true });
    fs.writeFileSync(f + '.tmp', JSON.stringify(data, rep));
    fs.renameSync(f + '.tmp', f);
  };

  // D = { config, state, queue, contacted, sent, replies, searched, jids }
  // Finché il backup non è ripreso non si tocca nulla: un disco appena svuotato non deve coprire i dati buoni
  let D = readJson(BOT_FILE);
  let auth = readJson(AUTH_FILE, reviver); // { creds, keys: { tipo: { id: valore } }, t: { id sessione: ultimo uso } }
  const cfg = () => ({ ...DEFAULTS, ...(D.config || {}) });
  const S = () => (D.state ||= {});
  const queue = () => (D.queue ||= []);
  const contacted = () => (D.contacted ||= {});
  let saveTimer = null, authTimer = null;
  const save = () => { clearTimeout(saveTimer); saveTimer = setTimeout(() => writeJson(BOT_FILE, D), 1000); };
  const saveAuth = () => { clearTimeout(authTimer); authTimer = setTimeout(() => writeJson(AUTH_FILE, auth, replacer), 1000); };

  // ---------- Chiavi di WhatsApp ----------
  const keyStore = {
    get: async (type, ids) => {
      const t = (auth.keys && auth.keys[type]) || {};
      const out = {};
      for (const id of ids) {
        let v = t[id];
        if (v && type === 'app-state-sync-key') v = B.proto.Message.AppStateSyncKeyData.fromObject(v);
        if (v !== undefined) out[id] = v;
      }
      return out;
    },
    set: async data => {
      auth.keys ||= {}; auth.t ||= {};
      for (const type in data) {
        const t = (auth.keys[type] ||= {});
        for (const id in data[type]) {
          const v = data[type][id];
          if (v) t[id] = v; else delete t[id];
          if (type === 'session') { if (v) auth.t[id] = Date.now(); else delete auth.t[id]; }
        }
      }
      // Tengo le sessioni usate più di recente: le altre WhatsApp le ricrea quando servono
      const sessions = Object.keys(auth.keys.session || {});
      if (sessions.length > MAX_SESSIONS) {
        sessions.sort((a, b) => (auth.t[a] || 0) - (auth.t[b] || 0)).slice(0, sessions.length - MAX_SESSIONS * 0.9)
          .forEach(id => { delete auth.keys.session[id]; delete auth.t[id]; });
      }
      saveAuth();
    },
  };
  function wipeAuth() { auth = {}; saveAuth(); }
  // «account» arriva solo a collegamento riuscito (con il codice «me» c'è già prima)
  const linked = () => !!(auth.creds && auth.creds.me && auth.creds.account);

  // ---------- Collegamento a WhatsApp ----------
  let B = null; // libreria Baileys (si carica solo quando serve)
  const lib = async () => (B ||= await import('@whiskeysockets/baileys'));
  const quiet = () => {};
  const logger = {
    level: process.env.BOT_DEBUG ? 'info' : 'silent', child() { return logger; },
    trace: quiet, debug: quiet, info: process.env.BOT_DEBUG ? (...a) => console.log('[wa]', ...a) : quiet,
    warn: process.env.BOT_DEBUG ? (...a) => console.warn('[wa]', ...a) : quiet,
    error: process.env.BOT_DEBUG ? (...a) => console.error('[wa]', ...a) : quiet, fatal: (...a) => console.error('[wa]', ...a),
  };
  let agent; // facoltativo: WA_PROXY per chi esce su internet da un proxy (su Render non serve)
  let version = null, versionAt = 0;
  async function waVersion() {
    if (version && Date.now() - versionAt < 6 * 3600e3) return version;
    const r = await B.fetchLatestWaWebVersion().catch(() => null);
    if (r && r.version) { version = r.version; versionAt = Date.now(); }
    return version || undefined;
  }

  let sock = null, reconnectTimer = null;
  const W = { status: 'off', qr: null, code: null, phone: '', error: null, linking: false, linkUntil: 0, retries: 0, lock: null, cap: null, limitsAt: 0 };
  const botMsgIds = new Set(); // messaggi mandati dal bot (per capire se un «fromMe» l'ha scritto una persona)

  async function connect() {
    clearTimeout(reconnectTimer);
    if (sock) { const old = sock; sock = null; try { old.end(undefined); } catch {} }
    await lib();
    if (!agent && process.env.WA_PROXY) {
      try { const { HttpsProxyAgent } = await import('https-proxy-agent'); agent = new HttpsProxyAgent(process.env.WA_PROXY); }
      catch { console.warn('WA_PROXY impostato ma manca il pacchetto https-proxy-agent'); }
    }
    auth.creds ||= B.initAuthCreds();
    W.status = W.linking ? 'linking' : 'connecting';
    const v = await waVersion();
    const s = B.makeWASocket({
      ...(v && { version: v }),
      auth: { creds: auth.creds, keys: B.makeCacheableSignalKeyStore(keyStore, logger) },
      logger,
      browser: B.Browsers.ubuntu('Chrome'), // con «macOS Desktop» WhatsApp rifiuta il collegamento
      countryCode: 'IT',
      markOnlineOnConnect: false, // così il telefono continua a ricevere le notifiche
      syncFullHistory: false,
      shouldSyncHistoryMessage: () => false,
      shouldIgnoreJid: jid => /@(g\.us|broadcast|newsletter)$/.test(jid || ''),
      getMessage: async key => {
        const m = (D.sent || []).find(x => x.id === key.id);
        return m ? { conversation: m.text } : undefined;
      },
      ...(agent && { agent }),
    });
    sock = s;
    let asked = false;
    s.ev.on('creds.update', saveAuth);
    s.ev.on('connection.update', async u => {
      if (s !== sock) return;
      if (u.qr) {
        // Non collegato e nessuno sta collegando dalla pagina: chiudo, non serve tenere aperto
        if (!W.linking || Date.now() > W.linkUntil) { stopLinking('Tempo scaduto: premi di nuovo «Collega WhatsApp».'); return; }
        W.qr = await QRCode.toDataURL(u.qr, { margin: 1, width: 300 }).catch(() => null);
        if (W.phone && !asked) {
          asked = true;
          try { W.code = await s.requestPairingCode(W.phone); }
          catch (err) { W.error = 'Non riesco a chiedere il codice: ' + err.message + '. Prova con il QR.'; }
        }
      }
      if (u.connection === 'open') {
        Object.assign(W, { status: 'open', linking: false, qr: null, code: null, error: null, retries: 0 });
        const st = S();
        if (!st.linkedAt) { st.linkedAt = new Date().toISOString(); save(); }
        console.log('Bot WhatsApp collegato come', (s.user && s.user.id) || '?');
        checkLimits(true);
      }
      if (u.connection === 'close') onClose(u.lastDisconnect && u.lastDisconnect.error);
    });
    s.ev.on('messages.upsert', ev => onMessages(ev).catch(err => console.error('Bot: messaggio ricevuto non letto:', err.message)));
  }
  function stopLinking(msg) {
    const s = sock; sock = null;
    try { s && s.end(undefined); } catch {}
    if (!linked()) wipeAuth();
    Object.assign(W, { status: 'off', linking: false, qr: null, code: null, error: msg || null });
  }
  function onClose(err) {
    sock = null;
    if (!B) { W.status = 'off'; return; } // libreria non caricata: niente da ricollegare
    const code = err && err.output && err.output.statusCode;
    const R = B.DisconnectReason;
    if (code === R.loggedOut) {
      wipeAuth();
      Object.assign(W, { status: 'off', linking: false, qr: null, code: null, error: 'WhatsApp è stato scollegato (dal telefono o da WhatsApp). Ricollegalo per far ripartire il bot.' });
      console.warn('Bot WhatsApp: scollegato');
      return;
    }
    if (code === R.forbidden) {
      Object.assign(W, { status: 'off', linking: false, error: 'WhatsApp ha rifiutato il collegamento (403): il numero potrebbe essere limitato o bloccato. Controlla l\'app WhatsApp Business.' });
      return;
    }
    if (W.linking && !linked() && code !== R.restartRequired) {
      stopLinking(code === R.timedOut ? 'Tempo scaduto: premi di nuovo «Collega WhatsApp».' : 'Collegamento non riuscito, riprova.');
      return;
    }
    if (!linked() && !W.linking) { W.status = 'off'; return; }
    // Dopo il collegamento WhatsApp chiede sempre di riconnettersi (515): lo faccio subito
    const delay = code === R.restartRequired ? 500 : code === R.connectionReplaced ? 60000 : Math.min(120000, 5000 * 2 ** W.retries++);
    W.status = 'connecting';
    if (code === R.connectionReplaced) W.error = 'Il bot era aperto anche da un\'altra parte (es. durante un deploy): riprovo tra un minuto.';
    reconnectTimer = setTimeout(() => connect().catch(e => { W.error = e.message; onClose(); }), delay);
  }

  // Limiti di WhatsApp per i messaggi a persone nuove: se avvisa o blocca, il bot rallenta o si ferma da solo
  async function checkLimits(force) {
    if (!sock || W.status !== 'open' || (!force && Date.now() - W.limitsAt < 30 * 60e3)) return;
    W.limitsAt = Date.now();
    try { W.lock = await sock.fetchAccountReachoutTimelock(); } catch { W.lock = null; }
    try { W.cap = await sock.fetchNewChatMessageCap(); } catch { W.cap = null; }
  }
  function limitPause() {
    const now = Date.now();
    if (W.lock && W.lock.isActive) {
      const until = W.lock.timeEnforcementEnds ? new Date(W.lock.timeEnforcementEnds).getTime() : now + 24 * 3600e3;
      return { until, why: 'WhatsApp ha limitato i messaggi a persone nuove' };
    }
    const c = W.cap;
    if (c && (c.capping_status === 'CAPPED' || (c.total_quota && c.used_quota >= c.total_quota))) {
      const end = +c.cycle_end_timestamp;
      return { until: end ? (end < 1e12 ? end * 1000 : end) : now + 24 * 3600e3, why: 'Raggiunto il limite di WhatsApp per le chat nuove' };
    }
    return null;
  }

  // ---------- Risposte dei clienti ----------
  async function numberOf(k) {
    for (const j of [k.remoteJid, k.remoteJidAlt, k.senderPn]) if (j && /@s\.whatsapp\.net$/.test(j)) return digitsOf(j.split('@')[0].split(':')[0]);
    const lid = k.remoteJid && k.remoteJid.endsWith('@lid') ? k.remoteJid : null;
    if (!lid) return null;
    if (D.jids && D.jids[lid]) return D.jids[lid];
    try {
      const pn = await sock.signalRepository.lidMapping.getPNForLID(lid);
      if (pn) return digitsOf(pn.split('@')[0].split(':')[0]);
    } catch {}
    return null;
  }
  function textOf(msg) {
    let m = msg || {};
    m = (m.ephemeralMessage && m.ephemeralMessage.message) || (m.viewOnceMessage && m.viewOnceMessage.message) || (m.viewOnceMessageV2 && m.viewOnceMessageV2.message) || m;
    if (m.conversation) return m.conversation;
    if (m.extendedTextMessage) return m.extendedTextMessage.text || '';
    if (m.reactionMessage) return m.reactionMessage.text ? m.reactionMessage.text + ' (reazione)' : '';
    if (m.imageMessage) return '📷 Foto' + (m.imageMessage.caption ? ': ' + m.imageMessage.caption : '');
    if (m.videoMessage) return '🎬 Video' + (m.videoMessage.caption ? ': ' + m.videoMessage.caption : '');
    if (m.audioMessage) return '🎤 Messaggio vocale';
    if (m.documentMessage) return '📄 Documento';
    if (m.stickerMessage) return 'Sticker';
    if (m.contactMessage || m.contactsArrayMessage) return '👤 Contatto';
    if (m.locationMessage) return '📍 Posizione';
    if (m.buttonsResponseMessage) return m.buttonsResponseMessage.selectedDisplayText || '';
    return '';
  }
  async function onMessages({ messages: list, type }) {
    for (const m of list || []) {
      const k = m.key || {};
      if (!k.remoteJid || /@(g\.us|broadcast|newsletter)$/.test(k.remoteJid)) continue;
      if (!k.fromMe && type !== 'notify') continue;
      const num = await numberOf(k);
      const ct = num && contacted()[num];
      if (!ct || !['invio', 'inviato', 'risposto', 'no'].includes(ct.s)) continue; // solo chi ha scritto il bot
      if (k.fromMe) {
        // Una persona ha risposto dal telefono: da qui in poi niente risposte automatiche
        if (!botMsgIds.has(k.id) && !ct.human) { ct.human = Date.now(); save(); }
        continue;
      }
      const text = textOf(m.message).trim();
      if (!text) continue;
      const no = OPT_OUT.test(text);
      ct.s = no ? 'no' : (ct.s === 'no' ? 'no' : 'risposto');
      ct.r = text.slice(0, 500); ct.rAt = Date.now();
      (D.replies ||= []).unshift({ n: num, name: ct.n, text: text.slice(0, 500), at: Date.now(), no });
      D.replies = D.replies.slice(0, 300);
      save();
      const c = cfg();
      if (!no && c.autoReply.trim() && !ct.auto && !ct.human && text.length < 80 && YES.test(text)) {
        ct.auto = Date.now(); save();
        const jid = k.remoteJid;
        setTimeout(async () => {
          if (!sock || W.status !== 'open' || ct.human) return;
          const reply = c.autoReply.replace(/\{sito\}/g, siteUrl).replace(/\{nome\}/g, ct.n || '').replace(/\{firma\}/g, c.firma);
          try { await typing(jid, reply); const r = await sendText(jid, reply); logSent(num, ct.n, reply, r, 'risposta automatica'); }
          catch (err) { console.error('Bot: risposta automatica non mandata:', err.message); }
        }, rand(40, 120) * 1000);
      }
    }
  }

  // ---------- Ricerca dei clienti (come «Trova clienti») ----------
  let refilling = false, lastSearchAt = 0;
  const lastSearch = { at: null, label: '', found: 0, added: 0, error: null };
  function jobs() {
    const c = cfg(), out = [], zones = parseZones(c.zones);
    const italia = zones.some(z => z.scope === 'italia'); // con «italia» le altre zone su OpenStreetMap sarebbero doppioni
    for (const z of zones) for (const type of c.types) {
      if (c.osm && (!italia || z.scope === 'italia')) out.push({ source: 'osm', scope: z.scope, city: z.city, type, need: 'wa' });
      if (c.google && googleOn() && z.scope !== 'italia') out.push({ source: 'google', city: z.city, type, need: 'wa' });
    }
    return out;
  }
  const jobKey = j => [j.source, j.scope || '', j.city.toLowerCase(), j.type].join('|');
  const nextJob = () => jobs().find(j => !((D.searched || {})[jobKey(j)] > Date.now() - RESEARCH_AFTER_MS));
  async function pool(items, n, fn) {
    const q = [...items];
    await Promise.all(Array.from({ length: n }, async () => { while (q.length) await fn(q.shift()); }));
  }
  async function refill(force) {
    if (refilling || (!force && Date.now() - lastSearchAt < SEARCH_GAP_MS)) return;
    const job = nextJob();
    if (!job) return;
    refilling = true; lastSearchAt = Date.now();
    const label = `${job.city} · ${(leadTypes()[job.type] || {}).label || job.type} · ${job.source === 'google' ? 'Google Maps' : 'OpenStreetMap'}`;
    Object.assign(lastSearch, { at: new Date().toISOString(), label, found: 0, added: 0, error: null, running: true });
    try {
      const { leads } = await searchLeads(job);
      const me = digitsOf(auth.creds && auth.creds.me && auth.creds.me.id.split(':')[0].split('@')[0]);
      const queued = new Set(queue().map(l => l.wa));
      const cand = [];
      for (const l of leads) {
        const wa = (l.whatsapps || []).map(digitsOf).find(n => n.length >= 9 && !contacted()[n] && !queued.has(n) && n !== me);
        if (wa) { queued.add(wa); cand.push({ l, wa }); }
      }
      // Il sito lo controllo poco prima di scrivere (precheck): una ricerca su tutta Italia ne trova centinaia
      const q = queue();
      const fresh = shuffle(cand).slice(0, Math.max(0, QUEUE_MAX - q.length)).map(({ l, wa }) => ({
        id: l.id, name: l.name, kind: l.kind, wa, waGuess: !!l.waGuess, website: l.website || '', social: l.social || '',
        address: l.address || '', maps: l.maps || '', reasons: [], checked: !l.website, source: job.source, zone: job.city, at: Date.now(),
      }));
      q.push(...fresh);
      Object.assign(lastSearch, { found: cand.length, added: fresh.length });
      (D.searched ||= {})[jobKey(job)] = Date.now();
      save();
    } catch (err) {
      lastSearch.error = err.message;
      // Zona scritta male (404) o Google spento (400): la salto per 30 giorni. Server occupato: riprovo più tardi
      if (err.status === 400 || err.status === 404) { (D.searched ||= {})[jobKey(job)] = Date.now(); save(); }
      else lastSearchAt = Date.now() + 10 * 60e3;
    } finally {
      refilling = false; lastSearch.running = false;
    }
  }

  // Controllo dei siti dei primi in coda: chi ha un sito fatto bene esce dalla coda (non è un cliente per noi)
  let prechecking = false;
  async function checkLead(l) {
    const r = await checkSite(l.website).catch(() => null);
    l.checked = true;
    if (r && r.bad) { l.reasons = r.reasons || []; return true; }
    return false;
  }
  function dropOk(l) {
    const q = queue(), i = q.indexOf(l);
    if (i >= 0) q.splice(i, 1);
    contacted()[l.wa] ||= { n: l.name, s: 'sito-ok', at: Date.now(), src: l.source };
  }
  async function precheck() {
    const todo = queue().slice(0, 15).filter(l => l.website && !l.checked);
    if (prechecking || !todo.length) return;
    prechecking = true;
    try {
      await pool(todo, 3, async l => { if (!(await checkLead(l))) dropOk(l); });
      save();
    } finally {
      prechecking = false;
    }
  }

  // ---------- Invio ----------
  function buildText(lead, variant) {
    const c = cfg();
    const own = String(c.templates || '').split('\n').map(x => x.trim()).filter(Boolean);
    let text;
    if (own.length) {
      // Il «problema» (senza sito, solo social, difetto del sito) lo prendo dai messaggi pronti, nella lingua scelta
      const problema = messages.problem(c.lang, lead, { reasons: lead.reasons });
      text = own[variant % own.length].replace(/\{nome\}/g, lead.name).replace(/\{problema\}/g, problema).replace(/\{firma\}/g, c.firma).replace(/\{sito\}/g, siteUrl);
    } else {
      text = messages.build({ lang: c.lang, variant, lead: { name: lead.name, website: lead.website, social: lead.social }, check: { reasons: lead.reasons }, firma: c.firma, sito: siteUrl });
    }
    if (c.lang === 'it' && local().min >= 14 * 60) text = text.replace(/^Buongiorno\b/, 'Buonasera');
    return text;
  }
  // L'ID lo scelgo io e lo segno prima: WhatsApp rimanda subito il messaggio come «mio» e non deve
  // sembrare scritto a mano dal telefono (che spegne le risposte automatiche)
  function sendText(jid, text) {
    const messageId = B.generateMessageIDV2(sock.user && sock.user.id);
    botMsgIds.add(messageId);
    return sock.sendMessage(jid, { text }, { messageId });
  }
  async function typing(jid, text) {
    try { await sock.presenceSubscribe(jid); } catch {}
    await sleep(rand(1500, 4000));
    try { await sock.sendPresenceUpdate('composing', jid); } catch {}
    await sleep(Math.min(14000, 2500 + text.length * 45) * rand(0.8, 1.2));
    try { await sock.sendPresenceUpdate('paused', jid); } catch {}
  }
  function logSent(num, name, text, r, kind) {
    (D.sent ||= []).unshift({ n: num, name, text, id: r && r.key && r.key.id, at: Date.now(), kind });
    D.sent = D.sent.slice(0, 500);
    save();
  }
  function mark(num, lead, s, extra = {}) {
    contacted()[num] = { n: lead.name, s, at: Date.now(), src: lead.source, ...extra };
    save();
  }

  let sending = false, failures = 0;
  // Manda il prossimo messaggio. Ritorna { ok, skipped, error, text }
  async function sendNext() {
    if (sending) return { error: 'Sto già mandando un messaggio' };
    if (!sock || W.status !== 'open') return { error: 'WhatsApp non è collegato' };
    sending = true;
    try {
      const q = queue();
      let lead;
      while ((lead = q.shift()) && contacted()[lead.wa]) { /* già contattato nel frattempo */ }
      save();
      if (!lead) { refill(true).catch(() => {}); return { error: 'Nessun cliente in coda: sto cercando' }; }
      if (lead.website && !lead.checked && !(await checkLead(lead))) { dropOk(lead); save(); return { skipped: true }; }
      let jid;
      try {
        const [r] = (await sock.onWhatsApp(lead.wa)) || [];
        if (!r || !r.exists) { mark(lead.wa, lead, 'senza-wa'); return { skipped: true }; }
        jid = r.jid;
      } catch (err) {
        q.unshift(lead); save();
        return { error: 'Controllo WhatsApp non riuscito: ' + err.message };
      }
      const st = S();
      const text = buildText(lead, st.total || 0);
      // Segno prima di mandare: se il server si spegne a metà, meglio perdere un messaggio che mandarne due
      mark(lead.wa, lead, 'invio');
      try {
        await typing(jid, text);
        const r = await sendText(jid, text);
        if (r && r.key && r.key.remoteJid && r.key.remoteJid !== jid) (D.jids ||= {})[r.key.remoteJid] = lead.wa;
        (D.jids ||= {})[jid] = lead.wa;
        mark(lead.wa, lead, 'inviato');
        logSent(lead.wa, lead.name, text, r);
        failures = 0;
        return { ok: true, text, lead };
      } catch (err) {
        mark(lead.wa, lead, 'errore', { err: err.message.slice(0, 200) });
        if (++failures >= 3) { st.pauseUntil = Date.now() + 3600e3; st.pauseWhy = 'Tre invii di fila non riusciti: riprovo tra un\'ora'; failures = 0; save(); }
        return { error: 'Invio non riuscito: ' + err.message };
      }
    } finally {
      sending = false;
    }
  }

  // ---------- Orari ----------
  function dayTarget() {
    const c = cfg(), st = S();
    let t = randInt(Math.min(c.min, c.max), Math.max(c.min, c.max));
    if (c.warmup && (st.days || 0) < WARMUP.length) t = Math.min(t, WARMUP[st.days || 0]);
    return t;
  }
  // Minuti di fascia oraria che restano oggi dopo «from» e l'ora (in minuti) dopo aver «consumato» n minuti di fascia
  function availAfter(from) { return parseHours(cfg().hours).reduce((s, [a, b]) => s + Math.max(0, b - Math.max(a, from)), 0); }
  function clockAfter(from, n) {
    for (const [a, b] of parseHours(cfg().hours)) {
      const start = Math.max(a, from);
      if (start >= b) continue;
      if (n <= b - start) return start + n;
      n -= b - start;
    }
    return null;
  }
  const inWindow = m => parseHours(cfg().hours).some(([a, b]) => m >= a && m < b);
  // Il prossimo invio: i messaggi che mancano sparsi a caso nel tempo di fascia che resta
  function planNext(first) {
    const st = S(), L = local();
    const left = (st.target || 0) - (st.sent || 0);
    if (left <= 0) return null;
    const avail = availAfter(L.min);
    if (avail <= 0) return null;
    const avg = avail / left;
    const gap = first ? Math.min(avg, 40) * rand(0.05, 0.6) : avg * rand(0.6, 1.4);
    const at = clockAfter(L.min, Math.min(gap, avail - 0.5));
    if (at == null) return null;
    return Date.now() + Math.max(first ? 30000 : MIN_GAP_MS, (at - L.min) * 60e3);
  }

  let ticking = false;
  async function tick() {
    if (ticking || !isReady()) return;
    ticking = true;
    try {
      const st = S(), c = cfg(), L = local();
      if (st.day !== L.day) { Object.assign(st, { day: L.day, sent: 0, target: dayTarget(), nextAt: null, warned: false }); save(); }
      precheck().catch(err => console.error('Bot: controllo siti:', err.message));
      if (!st.enabled) return;
      if (queue().length < QUEUE_MIN) refill().catch(err => console.error('Bot: ricerca:', err.message));
      if (W.status !== 'open') return;
      await checkLimits();
      if (!c.days.includes(L.wd) || !inWindow(L.min) || st.sent >= st.target) return;
      if (st.pauseUntil && Date.now() < st.pauseUntil) return;
      const lp = limitPause();
      if (lp) { st.pauseUntil = lp.until; st.pauseWhy = lp.why; save(); return; }
      // Primo avviso di WhatsApp sulle chat nuove: oggi la metà
      const warn = W.cap && /WARNING/.test(W.cap.capping_status || '');
      if (warn && !st.warned) { st.target = Math.min(st.target, st.sent + Math.ceil((st.target - st.sent) / 2)); st.warned = true; st.nextAt = null; save(); }
      if (!st.nextAt || local(st.nextAt).day !== L.day) { st.nextAt = planNext(true); save(); return; }
      if (Date.now() < st.nextAt) return;
      const r = await sendNext();
      if (r.ok) {
        st.sent = (st.sent || 0) + 1; st.total = (st.total || 0) + 1;
        if (st.lastDay !== L.day) { st.days = (st.days || 0) + 1; st.lastDay = L.day; }
        st.nextAt = planNext(false);
      } else if (r.skipped) {
        st.nextAt = Date.now() + rand(20, 60) * 1000; // numero senza WhatsApp: passo al prossimo
      } else {
        st.lastError = r.error; st.nextAt = Date.now() + 5 * 60e3;
      }
      save();
    } catch (err) {
      console.error('Bot WhatsApp:', err.message);
    } finally {
      ticking = false;
    }
  }

  // Cosa sta facendo il bot, in una frase
  function note() {
    const st = S(), c = cfg(), L = local();
    if (!st.enabled) return 'Il bot è spento.';
    if (W.status !== 'open') return linked() ? 'Mi sto ricollegando a WhatsApp…' : 'Collega WhatsApp per partire.';
    if (st.pauseUntil && Date.now() < st.pauseUntil) return `In pausa fino a ${new Date(st.pauseUntil).toLocaleString('it-IT', { timeZone: TZ })}: ${st.pauseWhy || ''}`;
    if (!c.days.includes(L.wd)) return 'Oggi è un giorno di riposo.';
    if ((st.sent || 0) >= (st.target || 0)) return `Finito per oggi (${st.sent || 0} messaggi). Riparto domani.`;
    if (!inWindow(L.min)) {
      const nx = parseHours(c.hours).find(([a]) => a > L.min);
      return nx ? `Fuori orario: riparto alle ${hhmm(nx[0])}.` : 'Fasce orarie finite per oggi: riparto domani.';
    }
    if (!queue().length) return refilling ? 'Sto cercando nuovi clienti…' : (nextJob() ? 'Coda vuota: cerco nuovi clienti tra poco.' : 'Ho scritto a tutti quelli trovati: aggiungi zone o tipi di attività.');
    return st.nextAt ? `Prossimo messaggio verso le ${new Date(st.nextAt).toLocaleTimeString('it-IT', { timeZone: TZ, hour: '2-digit', minute: '2-digit' })}.` : 'Preparo il prossimo messaggio…';
  }

  function status() {
    const st = S(), c = cfg();
    const all = Object.values(contacted());
    const count = s => all.filter(x => x.s === s).length;
    return {
      ready: isReady(),
      wa: { status: W.status, linked: linked(), me: auth.creds && auth.creds.me ? { id: auth.creds.me.id.split(':')[0].split('@')[0], name: auth.creds.me.name } : null, qr: W.qr, code: W.code, error: W.error, lock: W.lock, cap: W.cap },
      enabled: !!st.enabled,
      note: note(),
      today: { day: st.day, sent: st.sent || 0, target: st.target || 0, nextAt: st.nextAt || null, warmupDay: c.warmup && (st.days || 0) < WARMUP.length ? (st.days || 0) + 1 : 0 },
      stats: { total: count('inviato') + count('risposto') + count('no'), replies: count('risposto'), no: count('no'), noWa: count('senza-wa'), errors: count('errore') },
      config: c,
      queue: queue().slice(0, 30).map(l => ({ ...l, preview: buildText(l, st.total || 0) })),
      queueLength: queue().length,
      refilling, lastSearch, exhausted: !queue().length && !nextJob(), jobsTotal: jobs().length,
      sent: (D.sent || []).slice(0, 100).map(x => ({ ...x, s: (contacted()[x.n] || {}).s })),
      replies: (D.replies || []).slice(0, 100),
      repliesSeenAt: st.repliesSeenAt || 0,
      types: Object.entries(leadTypes()).map(([id, t]) => ({ id, label: t.label })),
      languages: messages.languages,
      google: googleOn(),
      tz: TZ,
    };
  }

  function cleanConfig(b) {
    const c = cfg();
    const out = { ...c };
    if (b.zones !== undefined) out.zones = String(b.zones).split('\n').map(x => x.trim()).filter(Boolean).slice(0, 200).join('\n').slice(0, 6000);
    if (Array.isArray(b.types)) out.types = b.types.filter(t => leadTypes()[t]);
    if (b.osm !== undefined) out.osm = !!b.osm;
    if (b.google !== undefined) out.google = !!b.google;
    const num = (v, d) => { const n = Math.round(+v); return Number.isFinite(n) ? Math.min(60, Math.max(1, n)) : d; };
    if (b.min !== undefined) out.min = num(b.min, c.min);
    if (b.max !== undefined) out.max = num(b.max, c.max);
    if (out.min > out.max) [out.min, out.max] = [out.max, out.min];
    if (b.hours !== undefined) {
      if (!parseHours(b.hours).length) throw new Error('Orari non validi: scrivi ad esempio 9:30-12:30, 15:00-19:30');
      out.hours = parseHours(b.hours).map(([a, z]) => `${hhmm(a)}-${hhmm(z)}`).join(', ');
    }
    if (Array.isArray(b.days)) out.days = [...new Set(b.days.map(Number).filter(d => d >= 0 && d <= 6))];
    if (b.lang !== undefined && messages.languages.some(([k]) => k === b.lang)) out.lang = b.lang;
    if (b.firma !== undefined) out.firma = String(b.firma).trim().slice(0, 40) || c.firma;
    if (b.templates !== undefined) out.templates = String(b.templates).slice(0, 4000);
    if (b.autoReply !== undefined) out.autoReply = String(b.autoReply).slice(0, 1000);
    if (b.warmup !== undefined) out.warmup = !!b.warmup;
    if (!out.types.length) throw new Error('Scegli almeno un tipo di attività');
    if (!out.days.length) throw new Error('Scegli almeno un giorno');
    if (!out.osm && !out.google) throw new Error('Scegli almeno una fonte (OpenStreetMap o Google Maps)');
    return out;
  }

  // ---------- API dell'admin ----------
  function routes(app, requireAdmin) {
    const ready = (req, res, next) => isReady() ? next() : res.status(503).json({ error: 'Sto ancora riprendendo i dati, riprova tra qualche secondo' });
    const r = '/api/admin/bot';
    app.get(r, requireAdmin, (req, res) => res.json(isReady() ? status() : { ready: false }));
    app.post(r + '/link', requireAdmin, ready, async (req, res) => {
      const phone = digitsOf(req.body && req.body.phone);
      if (phone && (phone.length < 10 || phone.length > 15)) return res.status(400).json({ error: 'Scrivi il numero con il prefisso, es. 39 333 1234567' });
      if (linked() && W.status === 'open') return res.status(400).json({ error: 'WhatsApp è già collegato' });
      if (linked()) { W.linking = false; W.error = null; W.retries = 0; connect().catch(err => { W.error = err.message; }); return res.json({ ok: true }); }
      wipeAuth();
      Object.assign(W, { linking: true, linkUntil: Date.now() + 4 * 60e3, phone, qr: null, code: null, error: null, retries: 0 });
      try { await connect(); } catch (err) { W.linking = false; W.status = 'off'; return res.status(500).json({ error: 'Non riesco a contattare WhatsApp: ' + err.message }); }
      res.json({ ok: true });
    });
    app.post(r + '/link/cancel', requireAdmin, (req, res) => { stopLinking(null); res.json({ ok: true }); });
    app.post(r + '/unlink', requireAdmin, ready, async (req, res) => {
      clearTimeout(reconnectTimer);
      const s = sock; sock = null;
      if (s) { try { await s.logout(); } catch {} try { s.end(undefined); } catch {} }
      wipeAuth();
      Object.assign(W, { status: 'off', linking: false, qr: null, code: null, error: null });
      res.json({ ok: true });
    });
    app.post(r + '/toggle', requireAdmin, ready, (req, res) => {
      const st = S();
      st.enabled = !!(req.body && req.body.enabled);
      st.nextAt = null; st.pauseUntil = null; st.pauseWhy = null;
      save(); tick().catch(() => {});
      res.json(status());
    });
    app.put(r + '/config', requireAdmin, ready, (req, res) => {
      try { D.config = cleanConfig(req.body || {}); }
      catch (err) { return res.status(400).json({ error: err.message }); }
      const st = S();
      // Nuovi limiti: ricalcolo il numero di oggi e il prossimo orario
      if (st.day) { st.target = Math.max(st.sent || 0, dayTarget()); st.nextAt = null; }
      save();
      res.json(status());
    });
    app.post(r + '/search', requireAdmin, ready, (req, res) => {
      if (refilling) return res.json({ ok: true, running: true });
      if (!nextJob()) return res.status(400).json({ error: 'Ho già cercato in tutte le zone e tipi scelti (si rifà dopo 30 giorni): aggiungi zone o tipi di attività' });
      refill(true).catch(err => console.error('Bot: ricerca:', err.message));
      res.json({ ok: true });
    });
    app.post(r + '/skip', requireAdmin, ready, (req, res) => {
      const wa = digitsOf(req.body && req.body.wa);
      const i = queue().findIndex(l => l.wa === wa);
      if (i < 0) return res.status(404).json({ error: 'Non è più in coda' });
      const [lead] = queue().splice(i, 1);
      mark(wa, lead, 'saltato');
      res.json({ ok: true });
    });
    app.post(r + '/send-now', requireAdmin, ready, async (req, res) => {
      const st = S();
      if (!st.enabled) return res.status(400).json({ error: 'Accendi prima il bot' });
      if ((st.sent || 0) >= (st.target || 0)) return res.status(400).json({ error: 'Per oggi il bot ha già mandato tutti i messaggi' });
      const out = await sendNext();
      if (out.ok) { st.sent = (st.sent || 0) + 1; st.total = (st.total || 0) + 1; if (st.lastDay !== st.day) { st.days = (st.days || 0) + 1; st.lastDay = st.day; } st.nextAt = planNext(false); save(); }
      if (out.error) return res.status(400).json({ error: out.error });
      res.json({ ok: true, skipped: !!out.skipped, text: out.text });
    });
    // Prova: manda al numero scritto (es. il tuo personale) il messaggio che riceverebbe il primo della coda
    app.post(r + '/test', requireAdmin, ready, async (req, res) => {
      const phone = digitsOf(req.body && req.body.phone);
      if (phone.length < 10) return res.status(400).json({ error: 'Scrivi il numero con il prefisso, es. 39 333 1234567' });
      if (!sock || W.status !== 'open') return res.status(400).json({ error: 'WhatsApp non è collegato' });
      const sample = queue()[0] || { name: 'Pizzeria Da Mario', website: '', social: '', reasons: [] };
      const text = buildText(sample, S().total || 0);
      try {
        const [x] = (await sock.onWhatsApp(phone)) || [];
        if (!x || !x.exists) return res.status(400).json({ error: 'Questo numero non ha WhatsApp' });
        await sendText(x.jid, '🤖 PROVA del bot (il cliente riceverà solo il testo qui sotto):\n\n' + text);
        res.json({ ok: true, text });
      } catch (err) { res.status(500).json({ error: 'Invio non riuscito: ' + err.message }); }
    });
    app.post(r + '/replies/seen', requireAdmin, ready, (req, res) => { S().repliesSeenAt = Date.now(); save(); res.json({ ok: true }); });
    // Numeri già contattati (dal bot o a mano da Trova clienti): così nessuno riceve due messaggi
    app.get(r + '/contacted', requireAdmin, (req, res) => {
      const out = {};
      if (isReady()) for (const [n, x] of Object.entries(contacted())) if (x.s !== 'sito-ok') out[n] = { s: x.s, at: x.at };
      res.json({ contacted: out });
    });
    app.post(r + '/contacted', requireAdmin, ready, (req, res) => {
      const wa = digitsOf(req.body && req.body.wa);
      if (wa.length < 9) return res.status(400).json({ error: 'Numero non valido' });
      if (!contacted()[wa]) mark(wa, { name: String((req.body && req.body.name) || '').slice(0, 120), source: 'manuale' }, 'a mano');
      const i = queue().findIndex(l => l.wa === wa);
      if (i >= 0) { queue().splice(i, 1); save(); }
      res.json({ ok: true });
    });
  }

  // ---------- Backup (ramo backup-bot, solo l'ultima copia) ----------
  const backupFiles = {
    'bot.json': { file: () => BOT_FILE, get: () => D, set: v => { D = v || {}; } },
    'wa-auth.json': {
      file: () => AUTH_FILE,
      get: () => {
        if (!auth.creds) return {};
        const keys = {};
        for (const t of BACKUP_KEY_TYPES) if (auth.keys && auth.keys[t]) keys[t] = auth.keys[t];
        return toPlain({ creds: auth.creds, keys });
      },
      set: v => { auth = revive(v); },
    },
  };

  // Parte quando il backup è ripreso: si ricollega da solo se WhatsApp era già collegato
  function start() {
    const wait = setInterval(() => {
      if (!isReady()) return;
      clearInterval(wait);
      if (linked()) connect().catch(err => { W.error = err.message; console.error('Bot WhatsApp:', err.message); });
      setInterval(tick, 20000);
      tick();
    }, 1000);
  }

  return { routes, backupFiles, start, _test: { parseHours, parseZones, local, planNext, availAfter, clockAfter, OPT_OUT, YES, state: () => D } };
};
