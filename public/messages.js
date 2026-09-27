// Messaggi WhatsApp pronti per i potenziali clienti, in più lingue.
// Ogni lingua ha 3 versioni che si alternano, così i messaggi non sono tutti identici.
window.LEAD_MESSAGES = (function () {
  // Come descrivere il "problema" dell'attività in ogni lingua
  const PROBLEMS = {
    it: {
      nosite: 'non avete ancora un sito web', social: 'online vi si trova solo sui social',
      'Non adatto al telefono': 'dal telefono il vostro sito non si legge bene',
      'Non sicuro (senza https)': 'Chrome segnala il vostro sito come «non sicuro»',
      lento: 'il vostro sito è lento a caricarsi', fermo: 'il vostro sito sembra fermo al {y}',
      'In costruzione o vuoto': 'il vostro sito risulta ancora in costruzione',
      rotto: 'il vostro sito al momento non si apre', 'Sito gratuito fai-da-te': 'il vostro sito è su una piattaforma gratuita',
      'Grafica vecchia': 'il vostro sito ha una grafica un po\' datata', 'Quasi vuoto': 'il vostro sito ha pochissime informazioni',
      'Rimanda solo ai social': 'il vostro sito rimanda solo ai social', generic: 'il vostro sito si potrebbe migliorare parecchio',
    },
    en: {
      nosite: "you don't have a website yet", social: 'online you can only be found on social media',
      'Non adatto al telefono': "your website is hard to read on a phone",
      'Non sicuro (senza https)': 'Chrome marks your website as "not secure"',
      lento: 'your website is slow to load', fermo: 'your website seems stuck in {y}',
      'In costruzione o vuoto': 'your website still shows as under construction',
      rotto: "your website isn't opening at the moment", 'Sito gratuito fai-da-te': 'your website is on a free builder platform',
      'Grafica vecchia': 'your website looks a bit outdated', 'Quasi vuoto': 'your website has very little information',
      'Rimanda solo ai social': 'your website only redirects to social media', generic: 'your website could be improved a lot',
    },
    fr: {
      nosite: "vous n'avez pas encore de site web", social: 'en ligne on vous trouve seulement sur les réseaux sociaux',
      'Non adatto al telefono': 'votre site est difficile à lire sur téléphone',
      'Non sicuro (senza https)': 'Chrome indique votre site comme « non sécurisé »',
      lento: 'votre site est lent à charger', fermo: 'votre site semble arrêté en {y}',
      'In costruzione o vuoto': 'votre site apparaît encore en construction',
      rotto: "votre site ne s'ouvre pas en ce moment", 'Sito gratuito fai-da-te': 'votre site est sur une plateforme gratuite',
      'Grafica vecchia': 'votre site a un design un peu daté', 'Quasi vuoto': 'votre site contient très peu d\'informations',
      'Rimanda solo ai social': 'votre site renvoie seulement vers les réseaux sociaux', generic: 'votre site pourrait être beaucoup amélioré',
    },
    es: {
      nosite: 'todavía no tenéis página web', social: 'en internet solo se os encuentra en redes sociales',
      'Non adatto al telefono': 'vuestra web se lee mal desde el móvil',
      'Non sicuro (senza https)': 'Chrome marca vuestra web como «no segura»',
      lento: 'vuestra web tarda mucho en cargar', fermo: 'vuestra web parece parada en {y}',
      'In costruzione o vuoto': 'vuestra web aparece todavía en construcción',
      rotto: 'vuestra web no se abre en este momento', 'Sito gratuito fai-da-te': 'vuestra web está en una plataforma gratuita',
      'Grafica vecchia': 'vuestra web tiene un diseño algo anticuado', 'Quasi vuoto': 'vuestra web tiene muy poca información',
      'Rimanda solo ai social': 'vuestra web solo redirige a redes sociales', generic: 'vuestra web se podría mejorar mucho',
    },
    de: {
      nosite: 'Sie noch keine Website haben', social: 'man Sie online nur in den sozialen Medien findet',
      'Non adatto al telefono': 'Ihre Website auf dem Handy schwer lesbar ist',
      'Non sicuro (senza https)': 'Chrome Ihre Website als „nicht sicher“ markiert',
      lento: 'Ihre Website langsam lädt', fermo: 'Ihre Website seit {y} nicht aktualisiert wurde',
      'In costruzione o vuoto': 'Ihre Website noch als „im Aufbau“ erscheint',
      rotto: 'Ihre Website sich im Moment nicht öffnet', 'Sito gratuito fai-da-te': 'Ihre Website auf einer kostenlosen Plattform liegt',
      'Grafica vecchia': 'Ihre Website etwas veraltet aussieht', 'Quasi vuoto': 'Ihre Website sehr wenige Informationen hat',
      'Rimanda solo ai social': 'Ihre Website nur auf soziale Medien weiterleitet', generic: 'Ihre Website stark verbessert werden könnte',
    },
  };

  // {nome} attività · {problema} · {firma} · {esempio} link demo · {sito} il tuo sito
  const TEMPLATES = {
    it: [
      'Buongiorno {nome}! Sono {firma} di Nerodoro Studio. Ho notato che {problema} e vi scrivo perché realizziamo siti web per attività come la vostra: perfetti da telefono, con contatti WhatsApp, mappa e orari.\n\nQui un esempio dal vivo: {esempio}\n\nSe vi interessa vi preparo una proposta senza impegno. Se invece non vi interessa, nessun problema: rispondete pure "no" e non vi scrivo più. Buona giornata!',
      'Salve {nome}, mi chiamo {firma} (Nerodoro Studio). Cercandovi online ho visto che {problema}. Creiamo siti eleganti e veloci, pronti in pochi giorni e con 1 anno di assistenza inclusa.\n\nPotete vedere un esempio qui: {esempio}\nChi siamo: {sito}\n\nVi andrebbe di ricevere un\'idea per il vostro? Se non è il momento basta dirmelo, grazie!',
      'Ciao {nome}! Sono {firma} di Nerodoro Studio. Vi scrivo in breve: ho visto che {problema}, e oggi molti clienti scelgono dove andare proprio dal telefono.\n\nVi mostro come potrebbe essere il vostro sito: {esempio}\n\nSe volete ve ne preparo una bozza gratuita con il vostro nome. Se non vi interessa rispondete "no" e non vi disturbo più 🙂',
    ],
    en: [
      'Hello {nome}! I\'m {firma} from Nerodoro Studio. I noticed that {problema}, and I\'m reaching out because we build websites for businesses like yours: mobile-friendly, with WhatsApp contact, map and opening hours.\n\nHere is a live example: {esempio}\n\nIf you\'re interested I can prepare a free proposal. If not, no problem at all: just reply "no" and I won\'t message again. Have a great day!',
      'Hi {nome}, my name is {firma} (Nerodoro Studio). While looking you up online I saw that {problema}. We create elegant, fast websites, ready in a few days with 1 year of support included.\n\nExample: {esempio}\nAbout us: {sito}\n\nWould you like an idea for yours? If it\'s not the right time just tell me, thanks!',
      'Hello {nome}! {firma} from Nerodoro Studio here. Quick message: I saw that {problema}, and today most customers choose where to go from their phone.\n\nThis is what your website could look like: {esempio}\n\nI can prepare a free draft with your name if you like. If you\'re not interested, reply "no" and I won\'t bother you again 🙂',
    ],
    fr: [
      'Bonjour {nome} ! Je suis {firma} de Nerodoro Studio. J\'ai remarqué que {problema}, et je vous écris car nous créons des sites web pour des commerces comme le vôtre : adaptés au téléphone, avec contact WhatsApp, plan et horaires.\n\nUn exemple en ligne : {esempio}\n\nSi cela vous intéresse, je vous prépare une proposition sans engagement. Sinon, aucun problème : répondez simplement « non » et je ne vous écrirai plus. Bonne journée !',
      'Bonjour {nome}, je m\'appelle {firma} (Nerodoro Studio). En vous cherchant en ligne, j\'ai vu que {problema}. Nous créons des sites élégants et rapides, prêts en quelques jours avec 1 an d\'assistance inclus.\n\nExemple : {esempio}\nQui sommes-nous : {sito}\n\nVoulez-vous recevoir une idée pour le vôtre ? Si ce n\'est pas le moment, dites-le-moi, merci !',
      'Bonjour {nome} ! {firma} de Nerodoro Studio. Un message rapide : j\'ai vu que {problema}, et aujourd\'hui la plupart des clients choisissent depuis leur téléphone.\n\nVoici à quoi pourrait ressembler votre site : {esempio}\n\nJe peux vous préparer une maquette gratuite à votre nom. Si cela ne vous intéresse pas, répondez « non » et je ne vous dérangerai plus 🙂',
    ],
    es: [
      '¡Hola {nome}! Soy {firma} de Nerodoro Studio. He visto que {problema} y os escribo porque creamos páginas web para negocios como el vuestro: perfectas en el móvil, con contacto por WhatsApp, mapa y horarios.\n\nAquí un ejemplo real: {esempio}\n\nSi os interesa os preparo una propuesta sin compromiso. Si no, ningún problema: responded "no" y no os escribo más. ¡Buen día!',
      'Hola {nome}, me llamo {firma} (Nerodoro Studio). Buscándoos en internet he visto que {problema}. Creamos webs elegantes y rápidas, listas en pocos días y con 1 año de asistencia incluido.\n\nEjemplo: {esempio}\nQuiénes somos: {sito}\n\n¿Os gustaría recibir una idea para la vuestra? Si no es el momento, decídmelo, ¡gracias!',
      '¡Hola {nome}! {firma} de Nerodoro Studio. Un mensaje rápido: he visto que {problema}, y hoy la mayoría de clientes elige desde el móvil.\n\nAsí podría ser vuestra web: {esempio}\n\nSi queréis os preparo un borrador gratis con vuestro nombre. Si no os interesa, responded "no" y no os molesto más 🙂',
    ],
    de: [
      'Guten Tag {nome}! Ich bin {firma} von Nerodoro Studio. Mir ist aufgefallen, dass {problema}. Wir erstellen Websites für Betriebe wie Ihren: optimiert für das Handy, mit WhatsApp-Kontakt, Karte und Öffnungszeiten.\n\nHier ein Live-Beispiel: {esempio}\n\nWenn Sie Interesse haben, erstelle ich Ihnen gern ein unverbindliches Angebot. Wenn nicht, kein Problem: antworten Sie einfach „nein“ und ich schreibe nicht mehr. Schönen Tag!',
      'Hallo {nome}, mein Name ist {firma} (Nerodoro Studio). Bei der Suche nach Ihnen habe ich gesehen, dass {problema}. Wir erstellen elegante, schnelle Websites, in wenigen Tagen fertig und mit 1 Jahr Support inklusive.\n\nBeispiel: {esempio}\nÜber uns: {sito}\n\nMöchten Sie eine Idee für Ihre Website bekommen? Wenn es gerade nicht passt, sagen Sie es mir einfach, danke!',
      'Hallo {nome}! Hier ist {firma} von Nerodoro Studio. Kurz gesagt: Ich habe gesehen, dass {problema}, und heute wählen die meisten Kunden direkt am Handy aus.\n\nSo könnte Ihre Website aussehen: {esempio}\n\nGern erstelle ich Ihnen kostenlos einen Entwurf mit Ihrem Namen. Kein Interesse? Antworten Sie „nein“ und ich störe nicht mehr 🙂',
    ],
  };

  function problemKey(reason) {
    if (/^Fermo al (\d{4})/.test(reason)) return ['fermo', reason.match(/\d{4}/)[0]];
    if (/^Lento/.test(reason)) return ['lento'];
    if (/non si apre|errore|non esiste|non valido/i.test(reason)) return ['rotto'];
    return [reason];
  }

  // lead: { name, website, social }, check: { bad, reasons } o null
  function problem(lang, lead, check) {
    const P = PROBLEMS[lang] || PROBLEMS.it;
    if (!lead.website) return lead.social ? P.social : P.nosite;
    const reasons = (check && check.reasons) || [];
    // Il difetto più "visibile" per primo
    const order = ['rotto', 'In costruzione o vuoto', 'Non adatto al telefono', 'fermo', 'Non sicuro (senza https)', 'Grafica vecchia', 'lento', 'Quasi vuoto', 'Sito gratuito fai-da-te', 'Rimanda solo ai social'];
    const keys = reasons.map(problemKey).sort((a, b) => order.indexOf(a[0]) - order.indexOf(b[0]));
    const k = keys.find(([key]) => P[key]);
    return k ? P[k[0]].replace('{y}', k[1] || '') : P.generic;
  }

  function build({ lang, variant, lead, check, firma, esempio, sito }) {
    const list = TEMPLATES[lang] || TEMPLATES.it;
    return list[variant % list.length]
      .replace('{nome}', lead.name)
      .replace('{problema}', problem(lang, lead, check))
      .replace('{firma}', firma || 'Nerodoro Studio')
      .replace('{esempio}', esempio)
      .replace('{sito}', sito);
  }

  return {
    build,
    languages: [['it', '🇮🇹 Italiano'], ['en', '🇬🇧 English'], ['fr', '🇫🇷 Français'], ['es', '🇪🇸 Español'], ['de', '🇩🇪 Deutsch']],
  };
})();
