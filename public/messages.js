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

  // Primo messaggio CORTO: niente link e niente video (sembrano spam).
  // Fa una domanda semplice; il video si manda solo a chi risponde "sì".
  // {nome} attività · {problema} · {firma} · {sito} (non usato nel primo messaggio)
  const TEMPLATES = {
    it: [
      'Ciao {nome}! Sono {firma}, faccio siti web per locali. Ho visto che {problema}: vi posso mandare un video di 1 minuto con un esempio? 🙂',
      'Buongiorno {nome}, sono {firma} di Nerodoro Studio. Ho notato che {problema}. Vi interesserebbe vedere un esempio di sito per il vostro locale? Sono 30 secondi 🙂',
      'Salve {nome}! Sono {firma}, realizzo siti per ristoranti e ho visto che {problema}. Posso mandarvi un breve video di esempio?',
    ],
    en: [
      'Hi {nome}! I\'m {firma}, I build websites for restaurants. I noticed that {problema}: can I send you a 1-minute example video? 🙂',
      'Hello {nome}, {firma} from Nerodoro Studio here. I noticed that {problema}. Would you like to see an example website for your place? It takes 30 seconds 🙂',
      'Hi {nome}! I\'m {firma}, I make websites for restaurants and I saw that {problema}. May I send you a short example video?',
    ],
    fr: [
      'Bonjour {nome} ! Je suis {firma}, je crée des sites web pour les restaurants. J\'ai vu que {problema} : je peux vous envoyer une vidéo d\'exemple d\'1 minute ? 🙂',
      'Bonjour {nome}, {firma} de Nerodoro Studio. J\'ai remarqué que {problema}. Voulez-vous voir un exemple de site pour votre établissement ? 30 secondes 🙂',
      'Bonjour {nome} ! Je suis {firma}, je fais des sites pour les restaurants et j\'ai vu que {problema}. Je peux vous envoyer une courte vidéo d\'exemple ?',
    ],
    es: [
      '¡Hola {nome}! Soy {firma}, hago páginas web para locales. He visto que {problema}: ¿os puedo enviar un vídeo de ejemplo de 1 minuto? 🙂',
      'Hola {nome}, soy {firma} de Nerodoro Studio. He visto que {problema}. ¿Os gustaría ver un ejemplo de web para vuestro local? Son 30 segundos 🙂',
      '¡Hola {nome}! Soy {firma}, hago webs para restaurantes y he visto que {problema}. ¿Os puedo mandar un vídeo corto de ejemplo?',
    ],
    de: [
      'Hallo {nome}! Ich bin {firma} und erstelle Websites für Restaurants. Mir ist aufgefallen, dass {problema}. Darf ich Ihnen ein 1-minütiges Beispielvideo schicken? 🙂',
      'Guten Tag {nome}, hier ist {firma} von Nerodoro Studio. Mir ist aufgefallen, dass {problema}. Möchten Sie ein Beispiel für eine Website Ihres Lokals sehen? Dauert 30 Sekunden 🙂',
      'Hallo {nome}! Ich bin {firma}, ich mache Websites für Restaurants und habe gesehen, dass {problema}. Darf ich Ihnen ein kurzes Beispielvideo schicken?',
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

  function build({ lang, variant, lead, check, firma, sito }) {
    const list = TEMPLATES[lang] || TEMPLATES.it;
    return list[variant % list.length]
      .replace('{nome}', lead.name)
      .replace('{problema}', problem(lang, lead, check))
      .replace('{firma}', firma || 'Simone')
      .replace('{sito}', sito);
  }

  return {
    build,
    languages: [['it', '🇮🇹 Italiano'], ['en', '🇬🇧 English'], ['fr', '🇫🇷 Français'], ['es', '🇪🇸 Español'], ['de', '🇩🇪 Deutsch']],
  };
})();
