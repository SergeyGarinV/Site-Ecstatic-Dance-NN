// .github/scripts/fetch-event.js
// Скачивает страницу cbiletom.ru и сохраняет дату в event.json.

const fs = require('fs');
const https = require('https');

const TICKET_URL = 'https://cbiletom.ru/poster/index.php?id=369500';
const OUTPUT_FILE = 'event.json';

const MONTHS = {
  'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4,
  'мая': 5, 'июня': 6, 'июля': 7, 'августа': 8,
  'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12
};

function fetchHtml(url, redirectsLeft = 5) {
  return new Promise((resolve, reject) => {
    https.get(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (compatible; EcstaticDanceBot/1.0)',
        'Accept-Language': 'ru-RU,ru;q=0.9'
      }
    }, (res) => {
      if ([301, 302, 303, 307, 308].includes(res.statusCode)
          && res.headers.location && redirectsLeft > 0) {
        const next = new URL(res.headers.location, url).href;
        return fetchHtml(next, redirectsLeft - 1).then(resolve, reject);
      }
      if (res.statusCode !== 200) {
        return reject(new Error('HTTP ' + res.statusCode));
      }
      let body = '';
      res.setEncoding('utf8');
      res.on('data', (c) => body += c);
      res.on('end', () => resolve(body));
    }).on('error', reject);
  });
}

function matchMeta(html, property) {
  const re = new RegExp(
    `<meta[^>]+(?:property|name)=["']${property}["'][^>]+content=["']([^"']+)["']`,
    'i'
  );
  const m = html.match(re);
  return m ? m[1] : null;
}

function parseEvent(html) {
  const result = {
    start: null,
    date: null,
    time: null,
    title: null,
    venue: null,
    city: 'Нижний Новгород',
    ticket_url: TICKET_URL
  };

  // 1) JSON-LD — самый надёжный источник
  const ldBlocks = html.match(
    /<script[^>]+type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi
  ) || [];

  for (const block of ldBlocks) {
    try {
      const raw = block
        .replace(/<script[^>]*>/i, '')
        .replace(/<\/script>/i, '');
      const json = JSON.parse(raw);
      const arr = Array.isArray(json) ? json : [json];

      for (const ev of arr) {
        if (ev && ev['@type'] === 'Event' && ev.startDate) {
          const d = new Date(ev.startDate);
          if (!isNaN(d)) {
            result.start = ev.startDate;
            if (ev.name) result.title = String(ev.name);
            if (ev.location) {
              result.venue = typeof ev.location === 'string'
                ? ev.location
                : (ev.location.name
                  || (ev.location.address && ev.location.address.streetAddress)
                  || null);
            }
            return result;
          }
        }
      }
    } catch (e) { /* битый JSON-LD — пропускаем */ }
  }

  // 2) Meta-теги OG
  const ogDate =
    matchMeta(html, 'event:start_time') ||
    matchMeta(html, 'og:start_time') ||
    matchMeta(html, 'article:published_time');

  if (ogDate) {
    const d = new Date(ogDate);
    if (!isNaN(d)) {
      result.start = ogDate;
      return result;
    }
  }

  // 3) Регулярка по видимому тексту
  const dateRe = /(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+(\d{4})/i;
  const timeRe = /(\d{1,2}):(\d{2})/;

  const dm = html.match(dateRe);
  const tm = html.match(timeRe);

  if (dm) {
    const day   = String(dm[1]).padStart(2, '0');
    const month = String(MONTHS[dm[2].toLowerCase()]).padStart(2, '0');
    const year  = dm[3];
    const hh    = tm ? String(tm[1]).padStart(2, '0') : '00';
    const mm    = tm ? tm[2] : '00';

    result.date  = `${parseInt(day, 10)} ${dm[2]} ${year}`;
    result.time  = `${hh}:${mm}`;
    result.start = `${year}-${month}-${day}T${hh}:${mm}:00+03:00`;
  }

  return result;
}

(async () => {
  try {
    console.log('Fetching:', TICKET_URL);
    const html = await fetchHtml(TICKET_URL);
    const data = parseEvent(html);

    if (!data.start && !data.date) {
      throw new Error('Не удалось найти дату на странице');
    }

    fs.writeFileSync(
      OUTPUT_FILE,
      JSON.stringify(data, null, 2) + '\n',
      'utf8'
    );

    console.log('✓ Сохранено в', OUTPUT_FILE);
    console.log(JSON.stringify(data, null, 2));
  } catch (err) {
    console.error('✗ Ошибка:', err.message);
    process.exit(1);
  }
})();