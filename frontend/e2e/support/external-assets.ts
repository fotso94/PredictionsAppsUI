import type { BrowserContext, Page, Route } from '@playwright/test';

/**
 * What the pages load from other people's servers, and how the browser tests keep a slow one from
 * deciding whether a test passes.
 *
 * Two kinds of asset come from third parties: club crests from the providers' image hosts, and the
 * web font index.html links (Google Fonts). Neither is what any test is about, yet a request to
 * either that the network does not answer keeps the page from going quiet - `networkidle` - or
 * from firing its load event, and the test waiting on that times out. That happened in the mocked
 * suite on 2026-10-05 (a crest arriving 17 s late; a font stylesheet at 04:35 UTC holding five page
 * loads) and in the live suite on 2026-10-07 (two crests unanswered for 45 s at 04:00 UTC while the
 * same CDN answered in 0.4 s a few minutes later).
 *
 * The answer: fetch the asset for real, at most once per worker and never waiting longer than a
 * few seconds; serve it from memory after that; and when it cannot be fetched now, serve a stand-in
 * that is a valid response of the same kind - a one-pixel PNG, an empty stylesheet - so nothing
 * waits and nothing reads as a failure. The mocked suite does not fetch crests at all: its fixtures
 * point at the CDN only because they were captured from the real backend.
 */

/** A one-pixel PNG: a real image response that costs nothing. */
export const PIXEL_PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
  'base64',
);

/**
 * The providers' image hosts. The captured fixtures point club crests at the live score
 * provider's CDN; API-Football and TheSportsDB serve theirs from these hosts.
 */
export const PROVIDER_IMAGE_HOSTS = /^https:\/\/(cdn\.live-score-api\.com|media\.api-sports\.io|(www\.|r2\.)?thesportsdb\.com)\//;

/** The web font index.html links (Google Fonts): its stylesheet, and the files that names. */
export const WEB_FONT_HOSTS = /^https:\/\/fonts\.(googleapis|gstatic)\.com\//;

/** How long one real fetch may take before the stand-in is served instead. */
const DEADLINE_MS = 5_000;
/** After a fetch fails, how long the same kind of asset is not tried again. */
const BACK_OFF_MS = 60_000;

type Stored = { status: number; headers: Record<string, string>; body: Buffer };
const fetched = new Map<string, Stored>();
const unreachableUntil = new Map<string, number>();

/**
 * Serve `route` from a real fetch made at most once per worker, or `standIn()` when that fetch
 * cannot complete within the deadline. `kind` groups assets that fail together (one host's outage
 * should not cost a five-second wait per crest).
 */
async function passThrough(route: Route, kind: string, standIn: () => Stored): Promise<void> {
  const url = route.request().url();
  let found = fetched.get(url);
  if (!found && Date.now() >= (unreachableUntil.get(kind) ?? 0)) {
    try {
      const response = await route.fetch({ timeout: DEADLINE_MS });
      if (response.ok()) {
        // The body comes back decoded, so the encoding and length it travelled with no longer apply.
        const headers = Object.fromEntries(Object.entries(response.headers())
          .filter(([name]) => !['content-encoding', 'content-length', 'transfer-encoding'].includes(name.toLowerCase())));
        found = { status: response.status(), headers, body: await response.body() };
        fetched.set(url, found);
      }
    } catch {
      unreachableUntil.set(kind, Date.now() + BACK_OFF_MS);
    }
  }
  return route.fulfill(found ?? standIn());
}

/**
 * The web font, for real when it can be had in time; otherwise an empty stylesheet (the page then
 * renders in its fallback font) or an empty font file with the CORS header a font request needs.
 */
export function serveWebFont(route: Route): Promise<void> {
  const stylesheet = route.request().url().startsWith('https://fonts.googleapis.com/');
  return passThrough(route, 'web-font', () => ({
    status: 200, body: Buffer.alloc(0),
    headers: { 'content-type': stylesheet ? 'text/css' : 'font/woff2', 'access-control-allow-origin': '*' },
  }));
}

/** A provider crest, for real when it can be had in time; otherwise a one-pixel PNG. */
export function serveProviderImage(route: Route): Promise<void> {
  return passThrough(route, 'provider-image', () => ({
    status: 200, body: PIXEL_PNG, headers: { 'content-type': 'image/png' },
  }));
}

/** A crest answered locally at once, never fetched: the mocked suite's crests are fixtures. */
export function servePixel(route: Route): Promise<void> {
  return route.fulfill({ status: 200, contentType: 'image/png', body: PIXEL_PNG });
}

/**
 * Route both kinds of third-party asset on `target` (a page, or a whole context so every page it
 * opens is covered). `crests: 'pixel'` answers crests locally; `'real'` fetches them under the
 * deadline, for the live suite, whose pages show what the real backend serves.
 */
export async function guardExternalAssets(target: Page | BrowserContext, crests: 'pixel' | 'real'): Promise<void> {
  await target.route(PROVIDER_IMAGE_HOSTS, crests === 'pixel' ? servePixel : serveProviderImage);
  await target.route(WEB_FONT_HOSTS, serveWebFont);
}
