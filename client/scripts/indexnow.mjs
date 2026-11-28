#!/usr/bin/env node
/**
 * Tell IndexNow search engines (Bing, Yandex, Naver, Seznam, Yep, ...) which
 * URLs exist, straight from the live sitemap.
 *
 *   node scripts/indexnow.mjs [--site https://www.museforge.studio] [--dry]
 *
 * WHY THE SITEMAP AND NOT A HAND-KEPT LIST. The sitemap is already the one
 * list of what is indexable (noindex routes are left out of it on purpose), so
 * a submission built from it cannot nominate a page the site itself refuses.
 *
 * Google does not read IndexNow. For Google, submit /sitemap.xml in Search
 * Console. Brave has no submission endpoint and finds pages by crawling.
 *
 * The key is public by design: the protocol proves ownership by fetching
 * /<key>.txt from the host, so it lives in client/public.
 */
import { readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const args = process.argv.slice(2);
const flag = (name) => args.includes(name);
const value = (name, fallback) => {
  const i = args.indexOf(name);
  return i >= 0 && args[i + 1] ? args[i + 1] : fallback;
};

const site = value("--site", "https://www.museforge.studio").replace(/\/$/, "");
const publicDir = join(dirname(fileURLToPath(import.meta.url)), "..", "public");
const keyFile = readdirSync(publicDir).find((f) => /^[0-9a-f]{32}\.txt$/.test(f));
if (!keyFile) {
  console.error("No IndexNow key file (32 hex characters + .txt) in client/public");
  process.exit(1);
}
const key = keyFile.replace(".txt", "");
const host = new URL(site).host;

const xml = await (await fetch(`${site}/sitemap.xml`)).text();
const urls = [...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1].trim());
if (!urls.length) {
  console.error(`No <loc> entries found at ${site}/sitemap.xml`);
  process.exit(1);
}

const served = await fetch(`${site}/${keyFile}`);
if (!served.ok || (await served.text()).trim() !== key) {
  console.error(`${site}/${keyFile} does not serve the key; deploy first.`);
  process.exit(1);
}

console.log(`${urls.length} URLs from ${site}/sitemap.xml`);
if (flag("--dry")) process.exit(0);

const res = await fetch("https://api.indexnow.org/indexnow", {
  method: "POST",
  headers: { "Content-Type": "application/json; charset=utf-8" },
  body: JSON.stringify({ host, key, keyLocation: `${site}/${keyFile}`, urlList: urls }),
});
console.log(`IndexNow responded ${res.status} (200 or 202 means accepted)`);
process.exit(res.status === 200 || res.status === 202 ? 0 : 1);
