// Bot WhatsApp: scrive da solo, dai numeri WhatsApp Business della tabella, alle attività trovate come in
// «Trova clienti» (senza sito, solo social o con il sito brutto). Ogni numero acceso manda 20-30 messaggi al giorno
// sparsi nelle fasce orarie scelte; a ogni attività si scrive una volta sola e chi dice «no» non viene più contattato.
// Ogni numero si collega come «dispositivo collegato» (come WhatsApp Web) con un codice o con il QR.
const fs = require('fs');
const crypto = require('crypto');
const path = require('path');
const QRCode = require('qrcode');

const TZ = process.env.BOT_TZ || 'Europe/Rome';
const DEFAULTS = {
  // «italia» = tutta Italia su OpenStreetMap; le città servono anche per Google Maps
  zones: ['italia', 'Milano', 'Roma', 'Napoli', 'Torino', 'Palermo', 'Genova', 'Bologna', 'Firenze', 'Bari', 'Catania',
    'Verona', 'Venezia', 'Padova', 'Brescia', 'Parma', 'Modena', 'Bergamo', 'Monza', 'Rimini'].join('\n'),
  types: ['ristoranti', 'pizzerie', 'bar'],
  osm: true, // OpenStreetMap: solo chi ha scritto il suo WhatsApp
  google: true, // Google Maps (se c'è la chiave): cellulari, prima di scrivere controllo che abbiano WhatsApp
  autoCities: true, // finite le zone, continua con gli altri comuni d'Italia su Google Maps
  min: 25, max: 30, // messaggi al giorno (ogni giorno un numero a caso tra i due)
  hours: '9:30-12:30, 15:00-19:30',
  days: [1, 2, 3, 4, 5, 6], // 0 = domenica
  lang: 'it',
  firma: 'Simone',
  templates: '', // primi messaggi, uno per riga (si alternano); vuoto = DEFAULT_FIRST
  autoFollow: true, // a chi risponde (e non dice di no) manda da solo video, abbonamenti, come pagare e demo
  videoUrl: '', // link del video (mp4 → arriva come video; YouTube/Drive → come link); vuoto = public/video.mp4 se c'è
  demoUrl: 'https://l13291221-cmyk.github.io/Ristorante-/',
  followUp: '', // messaggi dopo il «sì», separati da una riga «---»; vuoto = DEFAULT_FOLLOW
  warmup: true, // i primi giorni ne manda meno: un numero nuovo che scrive subito a tanti sconosciuti viene bloccato
};
// Primo messaggio: corto, senza link (sembrano spam), una domanda semplice. Uno per riga, si alternano.
// {firma} il tuo nome · {nome} nome del locale · {problema} «non avete ancora un sito web»…
// {categoria} «pizzerie», «ristoranti», «bar» · {locale} «una pizzeria come la vostra»…
const DEFAULT_FIRST = [
  'Salve, sono {firma} di Nerodoro Studio. Ho notato che {problema} e mi occupo proprio di siti per {categoria}. Posso mandarvi un video di un minuto con un esempio? 🙂',
  'Salve, sono {firma} di Nerodoro Studio 🙂 Facciamo siti web per {categoria} e ho visto che {problema}. Vi interessa vedere un esempio?',
  'Salve, sono {firma} di Nerodoro Studio. Vi scrivo perché {problema}: abbiamo un sito pronto pensato per {locale}. Vi mando un breve video per vederlo?',
  'Salve, sono {firma} di Nerodoro Studio. Ho trovato {nome} cercando {categoria} in zona e ho visto che {problema}. Vi farebbe piacere vedere un esempio di sito? 🙂',
].join('\n');
// Dopo il «sì»: prima il video (se c'è), poi questi messaggi, uno alla volta. Senza vincoli: le condizioni le vedono sul sito.
// {abbonamenti} Base e Premium con prezzo al mese · {sito} link per pagare · {demo} sito di esempio · {nome} · {firma}
const DEFAULT_FOLLOW = [
  'Se vi piace e siete interessati, ci sono due abbonamenti:\n\n{abbonamenti}',
  'Per attivarlo è semplicissimo:\n1️⃣ Andate su {sito}\n2️⃣ Scegliete Base o Premium e scrivete il nome del locale\n3️⃣ Pagate con la carta, in modo sicuro con Stripe (prima di pagare vedete il riepilogo e le condizioni)\n\nSubito dopo il pagamento ricevete il link del vostro sito, pronto da condividere, e un codice personale. Dal pannello cambiate da soli menu, foto e prezzi, anche dal telefono.',
  'Qui potete vedere un esempio di sito: {demo}\n\nPer qualsiasi domanda scrivetemi pure qui 🙂',
].join('\n---\n');
const VIDEO_CAPTION = 'Ecco il video 🎬 Così funziona il sito: si apre come un\'app, i clienti prenotano in 30 secondi e voi cambiate testi e foto con un tocco.';
// Che tipo di locale è: serve per scrivere «siti per pizzerie», «un bar come il vostro»…
const CATEGORIES = {
  pizzeria: { plurale: 'pizzerie', locale: 'una pizzeria come la vostra' },
  ristorante: { plurale: 'ristoranti', locale: 'un ristorante come il vostro' },
  gelateria: { plurale: 'gelaterie', locale: 'una gelateria come la vostra' },
  bar: { plurale: 'bar', locale: 'un bar come il vostro' },
  attivita: { plurale: 'attività come la vostra', locale: 'un\'attività come la vostra' },
};
function categoryOf(lead) {
  const kind = String(lead.kind || ''), all = kind + ' ' + (lead.name || '');
  if (lead.type === 'pizzerie' || /pizz/i.test(all)) return 'pizzeria';
  if (/gelat/i.test(kind)) return 'gelateria';
  if (lead.type === 'bar' || /\b(bar|caff|cafe|café|pub|pasticc|bistrot|enoteca)/i.test(kind)) return 'bar';
  if (lead.type === 'ristoranti' || /ristor|trattori|osteri|sushi|fast food|cucina|restaurant/i.test(all)) return 'ristorante';
  return 'attivita';
}
const blocks = s => String(s || '').split(/\n\s*-{3,}\s*\n/).map(x => x.trim()).filter(Boolean);
const lines = s => String(s || '').split('\n').map(x => x.trim()).filter(Boolean);
// Finite le zone scelte, il bot continua da solo con i comuni italiani dal più grande (solo Google Maps:
// OpenStreetMap con «italia» li copre già tutti)
const COMUNI = (() => { try { return require('./comuni-italia.json').comuni || []; } catch { return []; } })();
const WARMUP = [10, 15, 20, 25];
const MIN_GAP_MS = 4 * 60 * 1000; // mai due messaggi a meno di 4 minuti
const QUEUE_MIN = 40, QUEUE_MAX = 3000;
const RESEARCH_AFTER_MS = 30 * 864e5; // la stessa ricerca si rifà dopo 30 giorni (attività nuove)
const SEARCH_GAP_MS = 90 * 1000;
const MAX_SESSIONS = 3000;
// Nel backup vanno solo le chiavi che servono a restare collegati: le sessioni cambiano a ogni messaggio
// e si ricreano da sole, salvarle ogni 5 minuti farebbe crescere il backup senza motivo
const BACKUP_KEY_TYPES = ['pre-key', 'app-state-sync-key', 'lid-mapping', 'tctoken'];

// Le risposte si leggono in minuscolo e senza accenti («Sì» → «si»).
// Chi non vuole essere contattato (anche «nn ci interessa», «abbiamo già il sito», 👎…)
const OPT_OUT = /^\W*(no+|nono+)\b|\bstop\b|\bbasta\b|non (ci |mi )?(interessa|serve|servono)|nn (ci |mi )?(interessa|serve)|non (siamo|sono) interessat|non interessat|non grazie|no,? grazie|abbiamo gia|ce l'?abbiamo|gia (un|il|lo) sito|ne abbiamo gia|non scriv|non contatt|non disturb|lasci(a|ate)? perdere|cancell|rimuov|togliet|spam|unsubscribe|not interested|no thanks|don'?t (text|write|contact)|no me interesa|no gracias|pas interess|kein interesse|nein danke|👎/i;
// Chi dice sì, in tutti i modi: «si», «sisi», «siii», «ok», «okok», «okk», «va bene», «certo», «mandate», «mi interessa», 👍…
const YES = /^\W*((s+i+)+\b|s+y+|(o+k+)+|okay|okey|okei|oki|va\s*be|vabbe|vabene|certo|certamente|sicuro|volentieri|perche\s*no|mand|invia|dai\b|vai\b|d'?accordo|esatto|perfetto|yes|yep|yeah|sure|oui|ja\b|claro|vale)|interess|👍|👌|✅|😊|🙂/i;
// Messaggi automatici del WhatsApp Business del locale (benvenuto, assenza): non sono una risposta vera
const AUTO_REPLY = /grazie per (averci|aver|avermi|il|la) ?(contattat|scritt|messaggio)|grazie (del|per il) (messaggio|contatto)|(vi|ti) risponderemo|risponderemo (il prima|al piu|appena|a breve|quanto prima)|messaggio automatico|risposta automatica|al momento non (siamo|possiamo|sono)|siamo chiusi|siamo in ferie|orari di apertura|benvenut[oiae]|thank you for (contacting|your message|reaching)|we will (reply|get back|respond)|auto.?reply|fuori orario/i;
const plain = t => String(t || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[’`]/g, "'");

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
// Numero scritto a mano → cifre con il prefisso internazionale (cc = prefisso scelto, es. 39, 27, 44).
// «+27 71…» o «0027 71…» restano così; con +39: «333 123 4567» → 393331234567, «06…» → 3906…;
// con gli altri prefissi lo 0 iniziale del numero nazionale si toglie: +27 e «071 093 3377» → 27710933377
function normPhone(raw, cc = '39') {
  const s = String(raw || '').trim();
  const d = digitsOf(s);
  if (/^(\+|00)/.test(s)) return d.replace(/^00/, '');
  cc = digitsOf(cc) || '39';
  if (cc === '39') return /^3\d{8,9}$/.test(d) || /^0[1-9]\d{4,10}$/.test(d) ? '39' + d : d;
  if (d.startsWith(cc) && d.length - cc.length >= 8) return d; // c'era già il prefisso, senza il +
  return cc + d.replace(/^0/, '');
}
const jidUser = jid => digitsOf(String(jid || '').split('@')[0].split(':')[0]);
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

module.exports = function createBot({ dataDir, isReady, searchLeads, checkSite, leadTypes, googleOn, messages, siteUrl, publicDir, packages }) {
  const BOT_FILE = path.join(dataDir, 'bot.json');
  const AUTH_FILE = path.join(dataDir, 'wa-auth.json');
  const readJson = (f, rev) => { try { return JSON.parse(fs.readFileSync(f, 'utf8'), rev); } catch { return {}; } };
  const writeJson = (f, data, rep) => {
    fs.mkdirSync(path.dirname(f), { recursive: true });
    fs.writeFileSync(f + '.tmp', JSON.stringify(data, rep));
    fs.renameSync(f + '.tmp', f);
  };

  // D = { config, state, numbers, queue, contacted, sent, replies, searched, jids }
  //   numbers = la tabella: [{ id, phone, label, enabled, addedAt, st: { day, sent, target, nextAt, days, total, … } }]
  // A = { accounts: { id: { creds, keys, t } } } = le chiavi di WhatsApp di ogni numero
  // Finché il backup non è ripreso non si tocca nulla: un disco appena svuotato non deve coprire i dati buoni
  let D = readJson(BOT_FILE);
  let A = readJson(AUTH_FILE, reviver);
  const cfg = () => ({ ...DEFAULTS, ...(D.config || {}) });
  const S = () => (D.state ||= {});
  const queue = () => (D.queue ||= []);
  const contacted = () => (D.contacted ||= {});
  const numbers = () => (D.numbers ||= []);
  const rowOf = id => numbers().find(n => n.id === id);
  const accounts = () => (A.accounts ||= {});
  const authOf = id => (accounts()[id] ||= {});
  const newId = () => crypto.randomBytes(4).toString('hex');
  let saveTimer = null, authTimer = null;
  const save = () => { clearTimeout(saveTimer); saveTimer = setTimeout(() => writeJson(BOT_FILE, D), 1000); };
  const saveAuth = () => { clearTimeout(authTimer); authTimer = setTimeout(() => writeJson(AUTH_FILE, A, replacer), 1000); };

  // La prima versione aveva un solo WhatsApp: le sue chiavi e i contatori di oggi diventano una riga della tabella
  const DAY_KEYS = ['day', 'sent', 'target', 'nextAt', 'days', 'lastDay', 'pauseUntil', 'pauseWhy', 'warned', 'lastError'];
  function migrate() {
    const st = S();
    if (A.creds) {
      const old = { creds: A.creds, keys: A.keys || {}, t: A.t || {} };
      const me = old.creds.me ? jidUser(old.creds.me.id) : '';
      A = { accounts: { ...(A.accounts || {}) } };
      if (!numbers().some(n => n.phone === me && linked(n.id))) {
        const id = newId();
        A.accounts[id] = old;
        numbers().push({ id, phone: me, label: '', enabled: true, addedAt: Date.now(), st: Object.fromEntries(DAY_KEYS.map(k => [k, st[k]])) });
      }
      saveAuth();
    }
    if (DAY_KEYS.some(k => k in st)) { DAY_KEYS.forEach(k => delete st[k]); save(); }
    // chiavi di numeri tolti dalla tabella
    for (const id of Object.keys(accounts())) if (!rowOf(id)) { delete accounts()[id]; saveAuth(); }
  }

  // ---------- Chiavi di WhatsApp (una cassetta per numero) ----------
  function keyStore(id) {
    return {
      get: async (type, ids) => {
        const a = accounts()[id] || {};
        const t = (a.keys && a.keys[type]) || {};
        const out = {};
        for (const k of ids) {
          let v = t[k];
          if (v && type === 'app-state-sync-key') v = B.proto.Message.AppStateSyncKeyData.fromObject(v);
          if (v !== undefined) out[k] = v;
        }
        return out;
      },
      set: async data => {
        if (!rowOf(id)) return; // numero eliminato nel frattempo
        const a = authOf(id);
        a.keys ||= {}; a.t ||= {};
        for (const type in data) {
          const t = (a.keys[type] ||= {});
          for (const k in data[type]) {
            const v = data[type][k];
            if (v) t[k] = v; else delete t[k];
            if (type === 'session') { if (v) a.t[k] = Date.now(); else delete a.t[k]; }
          }
        }
        // Tengo le sessioni usate più di recente: le altre WhatsApp le ricrea quando servono
        const sessions = Object.keys(a.keys.session || {});
        if (sessions.length > MAX_SESSIONS) {
          sessions.sort((x, y) => (a.t[x] || 0) - (a.t[y] || 0)).slice(0, sessions.length - MAX_SESSIONS * 0.9)
            .forEach(k => { delete a.keys.session[k]; delete a.t[k]; });
        }
        saveAuth();
      },
    };
  }
  function wipe(id) { accounts()[id] = {}; saveAuth(); }
  // «account» arriva solo a collegamento riuscito (con il codice «me» c'è già prima)
  const linked = id => { const a = accounts()[id]; return !!(a && a.creds && a.creds.me && a.creds.account); };

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

  // Una connessione per numero: tutti i numeri collegati restano in ascolto delle risposte,
  // mandano i primi messaggi solo quelli con «Manda» acceso
  const conns = new Map();
  function conn(id) {
    let c = conns.get(id);
    if (!c) conns.set(id, c = { id, sock: null, timer: null, sending: false, failures: 0, status: 'off', qr: null, code: null, error: null, info: null, linking: false, linkUntil: 0, useCode: false, retries: 0, lock: null, cap: null, limitsAt: 0 });
    return c;
  }
  const botMsgIds = new Set(); // messaggi mandati dal bot (per capire se un «fromMe» l'ha scritto una persona)

  async function connect(c) {
    clearTimeout(c.timer);
    if (c.sock) { const old = c.sock; c.sock = null; try { old.end(undefined); } catch {} }
    await lib();
    if (!agent && process.env.WA_PROXY) {
      try { const { HttpsProxyAgent } = await import('https-proxy-agent'); agent = new HttpsProxyAgent(process.env.WA_PROXY); }
      catch { console.warn('WA_PROXY impostato ma manca il pacchetto https-proxy-agent'); }
    }
    const a = authOf(c.id);
    a.creds ||= B.initAuthCreds();
    c.status = c.linking ? 'linking' : 'connecting';
    const v = await waVersion();
    const s = B.makeWASocket({
      ...(v && { version: v }),
      auth: { creds: a.creds, keys: B.makeCacheableSignalKeyStore(keyStore(c.id), logger) },
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
    c.sock = s;
    let asked = false;
    s.ev.on('creds.update', saveAuth);
    s.ev.on('connection.update', async u => {
      if (s !== c.sock) return;
      if (u.qr) {
        // Non collegato e nessuno sta collegando dalla pagina: chiudo, non serve tenere aperto
        if (!c.linking || Date.now() > c.linkUntil) { stopLinking(c, 'Tempo scaduto: premi di nuovo «Collega».'); return; }
        c.qr = await QRCode.toDataURL(u.qr, { margin: 1, width: 300 }).catch(() => null);
        const row = rowOf(c.id);
        if (c.useCode && !asked && row && s === c.sock) {
          asked = true;
          try { c.code = await s.requestPairingCode(row.phone); }
          catch (err) { c.error = 'Non riesco a chiedere il codice: ' + err.message + '. Prova con il QR.'; }
        }
      }
      if (u.connection === 'open') onOpen(c, s);
      if (u.connection === 'close') onClose(c, u.lastDisconnect && u.lastDisconnect.error);
    });
    s.ev.on('messages.upsert', ev => onMessages(c, ev).catch(err => console.error('Bot: messaggio ricevuto non letto:', err.message)));
  }
  function endSock(c) {
    clearTimeout(c.timer);
    const s = c.sock; c.sock = null;
    try { s && s.end(undefined); } catch {}
    return s;
  }
  function onOpen(c, s) {
    const row = rowOf(c.id);
    if (!row) { endSock(c); return; }
    const me = jidUser(s.user && s.user.id);
    // Lo stesso WhatsApp è già in un'altra riga: tengo quella e scollego questo
    const dup = me && numbers().find(n => n.id !== c.id && n.phone === me);
    if (dup) {
      endSock(c);
      s.logout().catch(() => {});
      wipe(c.id);
      Object.assign(c, { status: 'off', linking: false, qr: null, code: null, info: null, error: `Hai collegato +${me}, che è già in un'altra riga della tabella.` });
      return;
    }
    c.info = me && row.phone !== me ? `Hai collegato +${me} invece di +${row.phone}: ho corretto il numero.` : null;
    if (me) row.phone = me;
    row.linkedAt ||= Date.now();
    save();
    Object.assign(c, { status: 'open', linking: false, qr: null, code: null, error: null, retries: 0 });
    console.log('Bot WhatsApp collegato:', '+' + me);
    checkLimits(c, true);
  }
  function stopLinking(c, msg) {
    endSock(c);
    if (!linked(c.id)) wipe(c.id);
    Object.assign(c, { status: 'off', linking: false, qr: null, code: null, error: msg || null });
  }
  function onClose(c, err) {
    c.sock = null;
    if (!B || !rowOf(c.id)) { c.status = 'off'; return; } // libreria non caricata o numero eliminato
    const code = err && err.output && err.output.statusCode;
    const R = B.DisconnectReason;
    if (code === R.loggedOut) {
      autoOff(c.id, 'WhatsApp ha scollegato il bot');
      wipe(c.id);
      Object.assign(c, { status: 'off', linking: false, qr: null, code: null, error: 'WhatsApp è stato scollegato (dal telefono o da WhatsApp). Ricollegalo per farlo ripartire.' });
      console.warn('Bot WhatsApp: scollegato', '+' + rowOf(c.id).phone);
      return;
    }
    if (code === R.forbidden) {
      autoOff(c.id, 'WhatsApp ha rifiutato il bot');
      Object.assign(c, { status: 'off', linking: false, error: 'WhatsApp ha rifiutato il collegamento (403): il numero potrebbe essere limitato o bloccato. Controlla l\'app WhatsApp Business.' });
      return;
    }
    if (c.linking && !linked(c.id) && code !== R.restartRequired) {
      stopLinking(c, code === R.timedOut ? 'Tempo scaduto: premi di nuovo «Collega».' : 'Collegamento non riuscito, riprova.');
      return;
    }
    if (!linked(c.id) && !c.linking) { c.status = 'off'; return; }
    // Dopo il collegamento WhatsApp chiede sempre di riconnettersi (515): lo faccio subito
    const delay = code === R.restartRequired ? 500 : code === R.connectionReplaced ? 60000 : Math.min(120000, 5000 * 2 ** c.retries++);
    c.status = 'connecting';
    if (code === R.connectionReplaced) c.error = 'Il bot era aperto anche da un\'altra parte (es. durante un deploy): riprovo tra un minuto.';
    c.timer = setTimeout(() => connect(c).catch(e => { c.error = e.message; onClose(c); }), delay);
  }
  async function startLink(row, { qr = false } = {}) {
    const c = conn(row.id);
    if (linked(row.id)) {
      if (c.status === 'open') throw new Error('Questo numero è già collegato');
      Object.assign(c, { linking: false, error: null, retries: 0 });
      return connect(c);
    }
    wipe(row.id);
    Object.assign(c, { linking: true, linkUntil: Date.now() + 4 * 60e3, useCode: !qr, qr: null, code: null, error: null, info: null, retries: 0 });
    try { await connect(c); }
    catch (err) { Object.assign(c, { linking: false, status: 'off', error: 'Non riesco a contattare WhatsApp: ' + err.message }); }
  }
  async function unlink(row) {
    const c = conn(row.id);
    const s = endSock(c);
    if (s) { try { await s.logout(); } catch {} }
    wipe(row.id);
    Object.assign(c, { status: 'off', linking: false, qr: null, code: null, error: null, info: null });
  }

  // Limiti di WhatsApp per i messaggi a persone nuove: se avvisa o blocca, il numero rallenta o si ferma da solo
  async function checkLimits(c, force) {
    if (!c.sock || c.status !== 'open' || (!force && Date.now() - c.limitsAt < 30 * 60e3)) return;
    c.limitsAt = Date.now();
    try { c.lock = await c.sock.fetchAccountReachoutTimelock(); } catch { c.lock = null; }
    try { c.cap = await c.sock.fetchNewChatMessageCap(); } catch { c.cap = null; }
    if (c.lock && c.lock.isActive) autoOff(c.id, 'WhatsApp ha limitato i messaggi a persone nuove');
  }
  // WhatsApp ha scollegato o limitato il bot: il numero smette di scrivere e non riparte da solo.
  // Riprovare porta di solito al blocco del numero intero; si riaccende solo a mano dalla tabella
  function autoOff(id, why) {
    const row = rowOf(id);
    if (!row || (!row.enabled && row.autoOff)) return;
    row.enabled = false;
    row.autoOff = { at: Date.now(), why };
    if (row.st) row.st.nextAt = null;
    save();
    console.warn('Bot WhatsApp: numero spento da solo', '+' + row.phone, '-', why);
  }
  function limitPause(c) {
    const now = Date.now();
    if (c.lock && c.lock.isActive) {
      const until = c.lock.timeEnforcementEnds ? new Date(c.lock.timeEnforcementEnds).getTime() : now + 24 * 3600e3;
      return { until, why: 'WhatsApp ha limitato i messaggi a persone nuove' };
    }
    const cap = c.cap;
    if (cap && (cap.capping_status === 'CAPPED' || (cap.total_quota && cap.used_quota >= cap.total_quota))) {
      const end = +cap.cycle_end_timestamp;
      return { until: end ? (end < 1e12 ? end * 1000 : end) : now + 24 * 3600e3, why: 'Raggiunto il limite di WhatsApp per le chat nuove' };
    }
    return null;
  }

  // ---------- Risposte dei clienti ----------
  async function numberOf(c, k) {
    for (const j of [k.remoteJid, k.remoteJidAlt, k.senderPn]) if (j && /@s\.whatsapp\.net$/.test(j)) return jidUser(j);
    const lid = k.remoteJid && k.remoteJid.endsWith('@lid') ? k.remoteJid : null;
    if (!lid) return null;
    if (D.jids && D.jids[lid]) return D.jids[lid];
    try {
      const pn = await c.sock.signalRepository.lidMapping.getPNForLID(lid);
      if (pn) return jidUser(pn);
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
  async function onMessages(c, { messages: list, type }) {
    for (const m of list || []) {
      const k = m.key || {};
      if (!k.remoteJid || /@(g\.us|broadcast|newsletter)$/.test(k.remoteJid)) continue;
      if (!k.fromMe && type !== 'notify') continue;
      const num = await numberOf(c, k);
      const ct = num && contacted()[num];
      if (!ct || !['invio', 'inviato', 'risposto', 'no'].includes(ct.s)) continue; // solo chi ha scritto il bot
      if (k.fromMe) {
        // Una persona ha risposto dal telefono: da qui in poi niente risposte automatiche
        if (!botMsgIds.has(k.id) && !ct.human) { ct.human = Date.now(); save(); }
        continue;
      }
      const text = textOf(m.message).trim();
      if (!text) continue;
      const row = rowOf(c.id), t = plain(text);
      const no = OPT_OUT.test(t), yes = !no && YES.test(t);
      // Benvenuto/assenza automatici del WhatsApp Business del locale: li segno ma non sono una risposta
      const auto = !no && !yes && (AUTO_REPLY.test(t) || (Date.now() - (ct.at || 0) < 25000 && text.length > 60));
      (D.replies ||= []).unshift({ n: num, name: ct.n, text: text.slice(0, 500), at: Date.now(), no, yes, auto, to: row && row.phone });
      D.replies = D.replies.slice(0, 300);
      if (auto) { ct.autoMsg = text.slice(0, 300); save(); continue; }
      ct.s = no ? 'no' : 'risposto';
      ct.r = text.slice(0, 500); ct.rAt = Date.now();
      if (yes) ct.yes = Date.now();
      save();
      // «No»: va negli archiviati (anche su WhatsApp) e non riceve più niente
      if (no) { archiveChat(c, m); continue; }
      // «Sì», «ok», «okok», una domanda… (tutto tranne il no): video, abbonamenti, come si paga e demo, una volta sola
      const cf = cfg();
      if (cf.autoFollow && !ct.follow && !ct.human) {
        ct.follow = Date.now(); save();
        const jid = k.remoteJid;
        setTimeout(async () => {
          if (!c.sock || c.status !== 'open' || ct.human || ct.s === 'no') { if (ct.s !== 'no') { ct.follow = null; save(); } return; }
          try { await sendFollowUp(c, jid, ct, num); ct.followDone = Date.now(); save(); }
          catch (err) { console.error('Bot: risposta al sì non completata:', err.message); ct.followErr = err.message.slice(0, 200); save(); }
        }, rand(30, 90) * 1000);
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
    if (c.google && googleOn() && c.autoCities) {
      const mine = new Set(zones.map(z => z.city.toLowerCase()));
      for (const city of COMUNI) if (!mine.has(city.toLowerCase())) for (const type of c.types) out.push({ source: 'google', city, type, need: 'wa' });
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
      const mine = new Set(numbers().map(n => n.phone)); // ai nostri numeri non si scrive
      const queued = new Set(queue().map(l => l.wa));
      const cand = [];
      for (const l of leads) {
        const wa = (l.whatsapps || []).map(digitsOf).find(n => n.length >= 9 && !contacted()[n] && !queued.has(n) && !mine.has(n));
        if (wa) { queued.add(wa); cand.push({ l, wa }); }
      }
      // Il sito lo controllo poco prima di scrivere (precheck): una ricerca su tutta Italia ne trova centinaia
      const q = queue();
      const fresh = shuffle(cand).slice(0, Math.max(0, QUEUE_MAX - q.length)).map(({ l, wa }) => ({
        id: l.id, name: l.name, kind: l.kind, wa, waGuess: !!l.waGuess, website: l.website || '', social: l.social || '',
        address: l.address || '', maps: l.maps || '', reasons: [], checked: !l.website, source: job.source, type: job.type, zone: job.city, at: Date.now(),
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
    const own = lines(c.templates).length ? lines(c.templates) : lines(DEFAULT_FIRST);
    const cat = CATEGORIES[categoryOf(lead)];
    // Il «problema» (senza sito, solo social, difetto del sito) lo prendo dai messaggi di Trova clienti
    const problema = messages.problem('it', lead, { reasons: lead.reasons });
    let text = own[variant % own.length].replace(/\{nome\}/g, lead.name).replace(/\{problema\}/g, problema)
      .replace(/\{categoria\}/g, cat.plurale).replace(/\{locale\}/g, cat.locale).replace(/\{firma\}/g, c.firma).replace(/\{sito\}/g, siteUrl);
    if (local().min >= 14 * 60) text = text.replace(/^Buongiorno\b/, 'Buonasera');
    return text;
  }

  // ---------- Dopo il «sì»: video, abbonamenti, come si paga, demo ----------
  const euro = cents => (cents / 100).toLocaleString('it-IT', { minimumFractionDigits: cents % 100 ? 2 : 0 }) + ' €';
  // I due abbonamenti con il prezzo al mese e cosa comprendono (senza vincoli: stanno nelle condizioni sul sito)
  function plansText() {
    const icons = ['✅', '⭐'];
    return packages().map((p, i) => `${icons[i] || '•'} *${p.name} – ${euro(p.monthly)} al mese*\n` +
      p.features.map(f => '• ' + f.replace(/\bla tua\b/g, 'la vostra').replace(/\bil tuo\b/g, 'il vostro')).join('\n')).join('\n\n');
  }
  function followTexts(ct) {
    const c = cfg();
    const list = blocks(c.followUp).length ? blocks(c.followUp) : blocks(DEFAULT_FOLLOW);
    return list.map(t => t
      .replace(/\{abbonamenti\}/g, plansText()).replace(/\{sito\}/g, siteUrl + '/#prezzi').replace(/\{demo\}/g, c.demoUrl || siteUrl)
      .replace(/\{nome\}/g, (ct && ct.n) || '').replace(/\{firma\}/g, c.firma));
  }
  // Il video: un file del sito (es. /video.mp4) o un link .mp4 arrivano come video; YouTube, Drive… come link
  function videoSource() {
    const v = String(cfg().videoUrl || '').trim();
    if (v.startsWith('/')) {
      const f = path.join(publicDir, path.normalize(v).replace(/^[/\\]+/, ''));
      if (f.startsWith(publicDir + path.sep) && fs.existsSync(f)) return { file: f, link: siteUrl + v };
      return { link: siteUrl + v };
    }
    if (/^https?:\/\//i.test(v)) return /\.(mp4|m4v|mov|3gp)(\?|#|$)/i.test(v) ? { url: v, link: v } : { link: v };
    const f = path.join(publicDir, 'video.mp4');
    return fs.existsSync(f) ? { file: f, link: siteUrl + '/video.mp4' } : null;
  }
  async function sendVideo(c, jid) {
    const v = videoSource();
    if (!v) return null;
    if (v.file || v.url) {
      try {
        try { await c.sock.sendPresenceUpdate('composing', jid); } catch {}
        await sleep(rand(2000, 5000));
        const messageId = B.generateMessageIDV2(c.sock.user && c.sock.user.id);
        botMsgIds.add(messageId);
        // Anteprima: se accanto al video c'è un .jpg con lo stesso nome (es. video.jpg) la uso, su Render non c'è ffmpeg
        const thumb = v.file && v.file.replace(/\.[^.]+$/, '.jpg');
        const jpegThumbnail = thumb && fs.existsSync(thumb) ? fs.readFileSync(thumb).toString('base64') : undefined;
        return await c.sock.sendMessage(jid, { video: { url: v.file || v.url }, caption: VIDEO_CAPTION, mimetype: 'video/mp4', ...(jpegThumbnail && { jpegThumbnail }) }, { messageId });
      } catch (err) {
        console.error('Bot: video non mandato, mando il link:', err.message);
      }
    }
    return sendText(c, jid, VIDEO_CAPTION + '\n' + v.link);
  }
  // Manda tutto, un messaggio alla volta come farebbe una persona. «log» = segna nei messaggi mandati
  async function sendFollowUp(c, jid, ct, num, log = true) {
    const from = (rowOf(c.id) || {}).phone;
    const r = await sendVideo(c, jid);
    if (r && log) logSent(num, ct.n, '🎬 ' + VIDEO_CAPTION, r, 'dopo il sì', from);
    for (const text of followTexts(ct)) {
      await sleep(rand(4000, 9000));
      if (!c.sock || c.status !== 'open') throw new Error('WhatsApp scollegato a metà');
      await typing(c, jid, text);
      const m = await sendText(c, jid, text);
      if (log) logSent(num, ct.n, text, m, 'dopo il sì', from);
    }
  }
  // Chi dice di no: chat archiviata anche nell'app WhatsApp
  async function archiveChat(c, m) {
    await sleep(rand(3000, 8000));
    try { await c.sock.chatModify({ archive: true, lastMessages: [{ key: m.key, messageTimestamp: m.messageTimestamp }] }, m.key.remoteJid); }
    catch (err) { console.warn('Bot: chat non archiviata su WhatsApp:', err.message); }
  }

  // L'ID lo scelgo io e lo segno prima: WhatsApp rimanda subito il messaggio come «mio» e non deve
  // sembrare scritto a mano dal telefono (che spegne le risposte automatiche)
  function sendText(c, jid, text) {
    const messageId = B.generateMessageIDV2(c.sock.user && c.sock.user.id);
    botMsgIds.add(messageId);
    return c.sock.sendMessage(jid, { text }, { messageId });
  }
  async function typing(c, jid, text) {
    try { await c.sock.presenceSubscribe(jid); } catch {}
    await sleep(rand(1500, 4000));
    try { await c.sock.sendPresenceUpdate('composing', jid); } catch {}
    await sleep(Math.min(14000, 2500 + text.length * 45) * rand(0.8, 1.2));
    try { await c.sock.sendPresenceUpdate('paused', jid); } catch {}
  }
  function logSent(num, name, text, r, kind, from) {
    (D.sent ||= []).unshift({ n: num, name, text, id: r && r.key && r.key.id, at: Date.now(), kind, from });
    D.sent = D.sent.slice(0, 500);
    save();
  }
  function mark(num, lead, s, extra = {}) {
    contacted()[num] = { n: lead.name, s, at: Date.now(), src: lead.source, ...extra };
    save();
  }

  // Manda il prossimo messaggio della coda dal numero «row». Ritorna { ok, skipped, error, text }
  async function sendNext(c, row) {
    if (c.sending) return { error: 'Questo numero sta già mandando un messaggio' };
    if (!c.sock || c.status !== 'open') return { error: 'Il numero +' + row.phone + ' non è collegato' };
    c.sending = true;
    try {
      const q = queue();
      let lead;
      while ((lead = q.shift()) && contacted()[lead.wa]) { /* già contattato nel frattempo */ }
      save();
      if (!lead) { refill(true).catch(() => {}); return { error: 'Nessun cliente in coda: sto cercando' }; }
      if (lead.website && !lead.checked && !(await checkLead(lead))) { dropOk(lead); save(); return { skipped: true }; }
      let jid;
      try {
        const [r] = (await c.sock.onWhatsApp(lead.wa)) || [];
        if (!r || !r.exists) { mark(lead.wa, lead, 'senza-wa'); return { skipped: true }; }
        jid = r.jid;
      } catch (err) {
        q.unshift(lead); save();
        return { error: 'Controllo WhatsApp non riuscito: ' + err.message };
      }
      const text = buildText(lead, S().total || 0);
      // Segno prima di mandare: se il server si spegne a metà, meglio perdere un messaggio che mandarne due
      mark(lead.wa, lead, 'invio', { from: row.phone });
      try {
        await typing(c, jid, text);
        const r = await sendText(c, jid, text);
        if (r && r.key && r.key.remoteJid && r.key.remoteJid !== jid) (D.jids ||= {})[r.key.remoteJid] = lead.wa;
        (D.jids ||= {})[jid] = lead.wa;
        mark(lead.wa, lead, 'inviato', { from: row.phone });
        logSent(lead.wa, lead.name, text, r, undefined, row.phone);
        c.failures = 0;
        return { ok: true, text, lead };
      } catch (err) {
        mark(lead.wa, lead, 'errore', { from: row.phone, err: err.message.slice(0, 200) });
        if (++c.failures >= 3) { Object.assign(row.st, { pauseUntil: Date.now() + 3600e3, pauseWhy: 'Tre invii di fila non riusciti: riprovo tra un\'ora' }); c.failures = 0; save(); }
        return { error: 'Invio non riuscito: ' + err.message };
      }
    } finally {
      c.sending = false;
    }
  }
  // Dopo un invio riuscito: contatori del numero e di tutto il bot
  function counted(row) {
    const st = row.st, g = S(), day = local().day;
    st.sent = (st.sent || 0) + 1; st.total = (st.total || 0) + 1; g.total = (g.total || 0) + 1;
    if (st.lastDay !== day) { st.days = (st.days || 0) + 1; st.lastDay = day; }
    st.nextAt = planNext(st, false);
    save();
  }

  // ---------- Orari (per ogni numero) ----------
  // La partenza graduale vale per ogni numero: un numero nuovo riparte da 10 al giorno
  function dayTarget(st) {
    const c = cfg();
    let t = randInt(Math.min(c.min, c.max), Math.max(c.min, c.max));
    if (c.warmup && (st.days || 0) < WARMUP.length) t = Math.min(t, WARMUP[st.days || 0]);
    return t;
  }
  function rollDay(row, L) {
    const st = (row.st ||= {});
    if (st.day !== L.day) { Object.assign(st, { day: L.day, sent: 0, target: dayTarget(st), nextAt: null, warned: false }); save(); }
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
  function planNext(st, first) {
    const L = local();
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
  const paused = st => st.pauseUntil && Date.now() < st.pauseUntil;

  async function tickRow(row, L) {
    const c = conns.get(row.id), st = row.st;
    if (!c || c.status !== 'open') return;
    await checkLimits(c);
    if (st.sent >= st.target || paused(st)) return;
    const lp = limitPause(c);
    if (lp) { st.pauseUntil = lp.until; st.pauseWhy = lp.why; save(); return; }
    // Primo avviso di WhatsApp sulle chat nuove: oggi la metà
    if (c.cap && /WARNING/.test(c.cap.capping_status || '') && !st.warned) {
      st.target = Math.min(st.target, st.sent + Math.ceil((st.target - st.sent) / 2)); st.warned = true; st.nextAt = null; save();
    }
    if (!st.nextAt || local(st.nextAt).day !== L.day) { st.nextAt = planNext(st, true); save(); return; }
    if (Date.now() < st.nextAt) return;
    const r = await sendNext(c, row);
    if (r.ok) return counted(row);
    if (r.skipped) st.nextAt = Date.now() + rand(20, 60) * 1000; // numero senza WhatsApp o sito ok: passo al prossimo
    else { st.lastError = r.error; st.nextAt = Date.now() + 5 * 60e3; }
    save();
  }
  let ticking = false;
  async function tick() {
    if (ticking || !isReady()) return;
    ticking = true;
    try {
      const g = S(), c = cfg(), L = local();
      for (const row of numbers()) rollDay(row, L);
      precheck().catch(err => console.error('Bot: controllo siti:', err.message));
      if (!g.enabled) return;
      if (queue().length < QUEUE_MIN) refill().catch(err => console.error('Bot: ricerca:', err.message));
      if (!c.days.includes(L.wd) || !inWindow(L.min)) return;
      for (const row of numbers()) if (row.enabled) await tickRow(row, L);
    } catch (err) {
      console.error('Bot WhatsApp:', err.message);
    } finally {
      ticking = false;
    }
  }

  // ---------- Cosa sta facendo, in una frase ----------
  const at = t => new Date(t).toLocaleTimeString('it-IT', { timeZone: TZ, hour: '2-digit', minute: '2-digit' });
  const when = t => new Date(t).toLocaleString('it-IT', { timeZone: TZ, day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
  function rowNote(row) {
    const c = conns.get(row.id) || {}, st = row.st || {};
    if (c.status === 'linking') return 'In collegamento…';
    if (!linked(row.id)) return 'Da collegare';
    if (c.status !== 'open') return 'Mi ricollego…';
    if (!row.enabled && row.autoOff) return `Spento da solo: ${row.autoOff.why}`;
    if (!row.enabled) return 'Spento: non scrive a nessuno, ma vede le risposte';
    if (paused(st)) return `In pausa fino al ${when(st.pauseUntil)}: ${st.pauseWhy || ''}`;
    if ((st.sent || 0) >= (st.target || 0)) return 'Finito per oggi';
    return st.nextAt ? `Prossimo messaggio verso le ${at(st.nextAt)}` : 'Pronto';
  }
  function note() {
    const g = S(), c = cfg(), L = local();
    if (!g.enabled) return 'Il bot è spento.';
    if (!numbers().length) return 'Aggiungi un numero WhatsApp nella tabella qui sotto.';
    const rows = numbers().filter(n => n.enabled);
    if (!rows.length) return 'Nessun numero acceso: accendi «Scrive» su un numero della tabella.';
    const open = rows.filter(n => (conns.get(n.id) || {}).status === 'open');
    if (!open.length) return rows.some(n => linked(n.id)) ? 'Mi sto ricollegando a WhatsApp…' : 'Collega il numero WhatsApp nella tabella qui sotto.';
    if (!c.days.includes(L.wd)) return 'Oggi è un giorno di riposo.';
    const working = open.filter(n => (n.st.sent || 0) < (n.st.target || 0));
    if (!working.length) return `Finito per oggi (${open.reduce((s, n) => s + (n.st.sent || 0), 0)} messaggi). Riparto domani.`;
    if (!inWindow(L.min)) {
      const nx = parseHours(c.hours).find(([a]) => a > L.min);
      return nx ? `Fuori orario: riparto alle ${hhmm(nx[0])}.` : 'Fasce orarie finite per oggi: riparto domani.';
    }
    const free = working.filter(n => !paused(n.st));
    if (!free.length) return `In pausa: ${working[0].st.pauseWhy || ''}`;
    if (!queue().length) return refilling ? 'Sto cercando nuovi clienti…' : (nextJob() ? 'Coda vuota: cerco nuovi clienti tra poco.' : 'Ho scritto a tutti quelli trovati: aggiungi zone o tipi di attività.');
    const next = free.filter(n => n.st.nextAt).sort((a, b) => a.st.nextAt - b.st.nextAt)[0];
    return next ? `Prossimo messaggio verso le ${at(next.st.nextAt)} da +${next.phone}.` : 'Preparo il prossimo messaggio…';
  }

  function status() {
    const g = S(), c = cfg();
    const all = Object.values(contacted());
    const count = s => all.filter(x => x.s === s).length;
    const rows = numbers().map(n => {
      const cn = conns.get(n.id) || {}, st = n.st || {};
      return {
        id: n.id, phone: n.phone, label: n.label, enabled: !!n.enabled, autoOff: n.autoOff || null, addedAt: n.addedAt, linked: linked(n.id),
        status: cn.status || 'off', qr: cn.qr || null, code: cn.code || null, error: cn.error || null, info: cn.info || null, lock: cn.lock || null, cap: cn.cap || null,
        sent: st.sent || 0, target: st.target || 0, total: st.total || 0, nextAt: st.nextAt || null,
        warmupDay: c.warmup && (st.days || 0) < WARMUP.length ? (st.days || 0) + 1 : 0,
        note: rowNote(n),
      };
    });
    return {
      ready: isReady(),
      numbers: rows,
      enabled: !!g.enabled,
      note: note(),
      today: { sent: rows.reduce((s, n) => s + n.sent, 0), target: rows.filter(n => n.enabled && n.linked).reduce((s, n) => s + n.target, 0) },
      stats: { total: count('inviato') + count('risposto') + count('no'), replies: count('risposto'), no: count('no'), noWa: count('senza-wa'), errors: count('errore') },
      config: { ...c, templates: lines(c.templates).length ? c.templates : DEFAULT_FIRST, followUp: blocks(c.followUp).length ? c.followUp : DEFAULT_FOLLOW },
      defaults: { templates: DEFAULT_FIRST, followUp: DEFAULT_FOLLOW, demoUrl: DEFAULTS.demoUrl },
      follow: { video: (videoSource() || {}).link || null, caption: VIDEO_CAPTION, messages: followTexts({ n: 'Pizzeria Da Mario' }) },
      queue: queue().slice(0, 30).map(l => ({ ...l, category: categoryOf(l), preview: buildText(l, g.total || 0) })),
      queueLength: queue().length,
      refilling, lastSearch, exhausted: !queue().length && !nextJob(), jobsTotal: jobs().length,
      sent: (D.sent || []).slice(0, 100).map(x => ({ ...x, s: (contacted()[x.n] || {}).s })),
      replies: (D.replies || []).filter(x => (contacted()[x.n] || {}).s !== 'no').slice(0, 100)
        .map(x => { const ct = contacted()[x.n] || {}; return { ...x, follow: ct.followDone ? 'fatto' : ct.follow ? 'in corso' : ct.followErr ? 'errore' : null, human: !!ct.human }; }),
      // Chi ha detto no: archiviati (anche nell'app WhatsApp)
      archived: Object.entries(contacted()).filter(([, x]) => x.s === 'no').sort((a, b) => (b[1].rAt || b[1].at) - (a[1].rAt || a[1].at)).slice(0, 200)
        .map(([n, x]) => ({ n, name: x.n, text: x.r || '', at: x.rAt || x.at, from: x.from })),
      archivedTotal: Object.values(contacted()).filter(x => x.s === 'no').length,
      repliesSeenAt: g.repliesSeenAt || 0,
      types: Object.entries(leadTypes()).map(([id, t]) => ({ id, label: t.label })),
      languages: messages.languages,
      google: googleOn(),
      comuni: COMUNI.length,
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
    if (b.autoCities !== undefined) out.autoCities = !!b.autoCities;
    const num = (v, d) => { const n = Math.round(+v); return Number.isFinite(n) ? Math.min(60, Math.max(1, n)) : d; };
    if (b.min !== undefined) out.min = num(b.min, c.min);
    if (b.max !== undefined) out.max = num(b.max, c.max);
    if (out.min > out.max) [out.min, out.max] = [out.max, out.min];
    if (b.hours !== undefined) {
      if (!parseHours(b.hours).length) throw new Error('Orari non validi: scrivi ad esempio 9:30-12:30, 15:00-19:30');
      out.hours = parseHours(b.hours).map(([a, z]) => `${hhmm(a)}-${hhmm(z)}`).join(', ');
    }
    if (Array.isArray(b.days)) out.days = [...new Set(b.days.map(Number).filter(d => d >= 0 && d <= 6))];
    if (b.firma !== undefined) out.firma = String(b.firma).trim().slice(0, 40) || c.firma;
    if (b.templates !== undefined) out.templates = String(b.templates).slice(0, 4000);
    if (b.autoFollow !== undefined) out.autoFollow = !!b.autoFollow;
    if (b.followUp !== undefined) out.followUp = String(b.followUp).slice(0, 6000);
    const link = (v, what) => {
      const x = String(v || '').trim().slice(0, 500);
      if (x && !/^(https?:\/\/|\/)\S+$/i.test(x)) throw new Error(`${what}: scrivi un link che inizia con https://`);
      return x;
    };
    if (b.videoUrl !== undefined) out.videoUrl = link(b.videoUrl, 'Video');
    if (b.demoUrl !== undefined) out.demoUrl = link(b.demoUrl, 'Demo');
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
    const PHONE_ERR = 'Numero non valido: scegli il prefisso (+39, +27, +44…) e scrivi il numero, es. 333 1234567';
    const findRow = (req, res, next) => { req.row = rowOf(req.params.id); return req.row ? next() : res.status(404).json({ error: 'Numero non trovato' }); };
    const only = keep => numbers().forEach(n => { if (n !== keep && n.enabled) { n.enabled = false; } });
    app.get(r, requireAdmin, (req, res) => res.json(isReady() ? status() : { ready: false }));

    // Tabella dei numeri: aggiungi (e collega subito con il codice), accendi/spegni, collega, scollega, elimina
    app.post(r + '/numbers', requireAdmin, ready, async (req, res) => {
      const b = req.body || {};
      const phone = normPhone(b.phone, b.cc);
      if (phone.length < 10 || phone.length > 15) return res.status(400).json({ error: PHONE_ERR });
      if (numbers().some(n => n.phone === phone)) return res.status(400).json({ error: 'Questo numero è già nella tabella' });
      if (numbers().length >= 10) return res.status(400).json({ error: 'Massimo 10 numeri: elimina quelli che non usi più' });
      const row = { id: newId(), phone, label: String(b.label || '').trim().slice(0, 40), enabled: true, addedAt: Date.now(), st: {} };
      if (b.only) only(row);
      numbers().push(row);
      rollDay(row, local());
      save();
      await startLink(row, { qr: !!b.qr });
      res.json(status());
    });
    app.patch(r + '/numbers/:id', requireAdmin, ready, findRow, (req, res) => {
      const b = req.body || {}, row = req.row;
      if (b.label !== undefined) row.label = String(b.label).trim().slice(0, 40);
      if (b.enabled !== undefined) { row.enabled = !!b.enabled; row.autoOff = null; row.st.nextAt = null; row.st.pauseUntil = null; row.st.pauseWhy = null; }
      if (b.only) { only(row); row.enabled = true; }
      save();
      res.json(status());
    });
    app.post(r + '/numbers/:id/link', requireAdmin, ready, findRow, async (req, res) => {
      try { await startLink(req.row, { qr: !!(req.body && req.body.qr) }); }
      catch (err) { return res.status(400).json({ error: err.message }); }
      res.json(status());
    });
    app.post(r + '/numbers/:id/link/cancel', requireAdmin, findRow, (req, res) => { stopLinking(conn(req.row.id), null); res.json(status()); });
    app.post(r + '/numbers/:id/unlink', requireAdmin, ready, findRow, async (req, res) => { await unlink(req.row); res.json(status()); });
    app.delete(r + '/numbers/:id', requireAdmin, ready, findRow, async (req, res) => {
      const row = req.row;
      await unlink(row);
      conns.delete(row.id);
      delete accounts()[row.id]; saveAuth();
      D.numbers = numbers().filter(n => n !== row);
      save();
      res.json(status());
    });
    // Prova: manda al numero scritto (es. il tuo personale) il messaggio che riceverebbe il primo della coda
    app.post(r + '/numbers/:id/test', requireAdmin, ready, findRow, async (req, res) => {
      const phone = normPhone(req.body && req.body.phone);
      if (phone.length < 10) return res.status(400).json({ error: PHONE_ERR });
      const c = conns.get(req.row.id);
      if (!c || !c.sock || c.status !== 'open') return res.status(400).json({ error: 'Questo numero non è collegato' });
      const sample = queue()[0] || { name: 'Pizzeria Da Mario', website: '', social: '', reasons: [] };
      const text = buildText(sample, S().total || 0);
      try {
        const [x] = (await c.sock.onWhatsApp(phone)) || [];
        if (!x || !x.exists) return res.status(400).json({ error: 'Il numero ' + '+' + phone + ' non ha WhatsApp' });
        await sendText(c, x.jid, '🤖 PROVA del bot: qui sotto il primo messaggio, poi (tra un minuto) quello che riceve chi risponde «sì».');
        await sleep(1500);
        await sendText(c, x.jid, text);
        res.json({ ok: true, text });
        // La risposta al «sì» la mando dopo, senza far aspettare la pagina
        setTimeout(() => sendFollowUp(c, x.jid, { n: sample.name }, phone, false).catch(err => console.error('Bot: prova non completata:', err.message)), 20000);
      } catch (err) { res.status(500).json({ error: 'Invio non riuscito: ' + err.message }); }
    });

    app.post(r + '/toggle', requireAdmin, ready, (req, res) => {
      S().enabled = !!(req.body && req.body.enabled);
      for (const n of numbers()) Object.assign(n.st ||= {}, { nextAt: null, pauseUntil: null, pauseWhy: null });
      save(); tick().catch(() => {});
      res.json(status());
    });
    app.put(r + '/config', requireAdmin, ready, (req, res) => {
      try { D.config = cleanConfig(req.body || {}); }
      catch (err) { return res.status(400).json({ error: err.message }); }
      // Nuovi limiti: ricalcolo il numero di oggi e il prossimo orario di ogni numero
      for (const n of numbers()) if (n.st && n.st.day) { n.st.target = Math.max(n.st.sent || 0, dayTarget(n.st)); n.st.nextAt = null; }
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
      if (!S().enabled) return res.status(400).json({ error: 'Accendi prima il bot' });
      const row = numbers().find(n => n.enabled && (conns.get(n.id) || {}).status === 'open' && (n.st.sent || 0) < (n.st.target || 0));
      if (!row) return res.status(400).json({ error: 'Nessun numero acceso e collegato che possa scrivere ancora oggi' });
      const out = await sendNext(conns.get(row.id), row);
      if (out.ok) counted(row);
      if (out.error) return res.status(400).json({ error: out.error });
      res.json({ ok: true, skipped: !!out.skipped, text: out.text, from: row.phone });
    });
    // Ripristina un archiviato (es. ha detto no per sbaglio): torna tra le risposte, il bot non gli scrive comunque di nuovo
    app.post(r + '/archived/restore', requireAdmin, ready, (req, res) => {
      const ct = contacted()[digitsOf(req.body && req.body.wa)];
      if (!ct || ct.s !== 'no') return res.status(404).json({ error: 'Non è negli archiviati' });
      ct.s = 'risposto'; save();
      res.json({ ok: true });
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
  const backupKeys = a => {
    const keys = {};
    for (const t of BACKUP_KEY_TYPES) if (a.keys && a.keys[t]) keys[t] = a.keys[t];
    return toPlain({ creds: a.creds, keys });
  };
  const backupFiles = {
    'bot.json': { file: () => BOT_FILE, get: () => D, set: v => { D = v || {}; } },
    'wa-auth.json': {
      file: () => AUTH_FILE,
      get: () => {
        if (A.creds) return backupKeys(A); // formato della prima versione, non ancora convertito
        const out = {};
        for (const [id, a] of Object.entries(A.accounts || {})) if (a.creds) out[id] = backupKeys(a);
        return Object.keys(out).length ? { accounts: out } : {};
      },
      set: v => { A = revive(v); },
    },
  };

  // Parte quando il backup è ripreso: ricollega da soli i numeri già collegati
  function start() {
    const wait = setInterval(() => {
      if (!isReady()) return;
      clearInterval(wait);
      migrate();
      for (const n of numbers()) if (linked(n.id)) connect(conn(n.id)).catch(err => { conn(n.id).error = err.message; console.error('Bot WhatsApp:', err.message); });
      setInterval(tick, 20000);
      tick();
    }, 1000);
  }

  return { routes, backupFiles, start, _test: { parseHours, parseZones, local, planNext, availAfter, clockAfter, normPhone, OPT_OUT, YES, AUTO_REPLY, plain, buildText, followTexts, videoSource, state: () => D, auth: () => A, migrate } };
};
