const https = require('https');

const TICKET_URL = 'https://cbiletom.ru/poster/index.php?id=369500';
const CACHE_TTL = 60 * 60 * 1000;
let cache = { at: 0, data: null };

const MONTHS = {
  'января':1,'февраля':2,'марта':3,'апреля':4,'мая':5,'июня':6,
  'июля':7,'августа':8,'сентября':9,'октября':10,'ноября':11,'декабря':12
};

function fetchHtml(url) {
  return new Promise((resolve, reject) => {
    https.get(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (compatible; EcstaticDanceNN/1.0)',
        'Accept-Language': 'ru-RU,ru;q=0.9'
      }
    }, (res) => {
      if ([301,302,303,307,308].includes(res.statusCode) && res.headers.location) {
        return fetchHtml(res.headers.location).then(resolve, reject);
      }
      if (res.statusCode !== 200) return reject(new Error('HTTP ' + res.statusCode));
      let body = '';
      res.setEncoding('utf8');
      res.on('data', (c) => body += c);
      res.on('end', () => resolve(body));
    }).on('error', reject);
  });
}

function parseEvent(html) {
  const result = { start: null, date: null, time: null, title: null, venue: null, city: 'Нижний Новгород', ticket_url: TICKET_URL };

  const jsonLdBlocks = html.match(/<script[^>]+type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi) || [];
  for (const block of jsonLdBlocks) {
    try {
      const raw = block.replace(/<script[^>]*>/i, '').replace(/<\/script>/i, '');
      const json = JSON.parse(raw);
      const events = Array.isArray(json) ? json : [json];
      for (const ev of events) {
        if (ev && ev['@type'] === 'Event' && ev.startDate) {
          const d = new Date(ev.startDate);
          if (!isNaN(d)) {
            result.start = ev.startDate;
            result.title = ev.name || result.title;
            if (ev.location) result.venue = typeof ev.location === 'string' ? ev.location : (ev.location.name || ev.location.address?.streetAddress || null);
            return result;
          }
        }
      }
    } catch (e) {}
  }

  const ogDate = matchMeta(html, 'event:start_time') || matchMeta(html, 'og:start_time') || matchMeta(html, 'article:published_time');
  if (ogDate) { const d = new Date(ogDate); if (!isNaN(d)) { result.start = ogDate; return result; } }

  const dateRe = /(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+(\d{4})/i;
  const timeRe = /(\d{1,2}):(\d{2})/;
  const dateMatch = html.match(dateRe);
  const timeMatch = html.match(timeRe);
  if (dateMatch) {
    const day = String(dateMatch[1]).padStart(2,'0');
    const month = String(MONTHS[dateMatch[2].toLowerCase()]).padStart(2,'0');
    const year = dateMatch[3];
    const hh = timeMatch ? String(timeMatch[1]).padStart(2,'0') : '00';
    const mm = timeMatch ? timeMatch[2] : '00';
    result.date = `${parseInt(day,10)} ${dateMatch[2]} ${year}`;
    result.time = `${hh}:${mm}`;
    result.start = `${year}-${month}-${day}T${hh}:${mm}:00+03:00`;
  }
  return result;
}

function matchMeta(html, property) {
  const re = new RegExp(`<meta[^>]+(?:property|name)=["']${property}["'][^>]+content=["']([^"']+)["']`, 'i');
  const m = html.match(re);
  return m ? m[1] : null;
}

exports.handler = async () => {
  const headers = { 'Content-Type': 'application/json; charset=utf-8', 'Access-Control-Allow-Origin': '*', 'Cache-Control': 'public, max-age=3600' };
  try {
    if (cache.data && Date.now() - cache.at < CACHE_TTL) return { statusCode: 200, headers, body: JSON.stringify(cache.data) };
    const html = await fetchHtml(TICKET_URL);
    const data = parseEvent(html);
    if (!data.start && !data.date) throw new Error('Не удалось распарсить дату');
    cache = { at: Date.now(), data };
    return { statusCode: 200, headers, body: JSON.stringify(data) };
  } catch (error) {
    return { statusCode: 502, headers, body: JSON.stringify({ error: error.message }) };
  }
};
