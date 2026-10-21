import type { Page, Route } from '@playwright/test';

/**
 * The live backend, and the guard that keeps a mocked spec off it.
 *
 * WHAT IT FENCES OFF. The live API, :8000 on this machine, under every name a browser can reach it
 * by. Nothing else. In particular NOT the frontend origin: the page under test IS that origin. The
 * mocked projects used to be served from :3100 by default, with an API base of :8000
 * (frontend/.env), and a guard that also claimed :3100 aborted the spec's own `page.goto`, its HTML
 * and every Vite module (review finding #12). Since the 2026-10-21 review they load from the
 * isolated frontend (:3101, API :8001) by default and the preflight refuses :3100 for them; this
 * fence stays for a frontend whose build still points its API at :8000.
 *
 * WHY THE CONTEXT, NOT THE PAGE. Playwright answers a request from the page's routes before the
 * context's, whatever order they were registered in. So every stub a spec puts on the page — the
 * catch-all `**\/api/v1/**` in api-stub.ts included — answers first, on whichever host the build
 * points its API at, and only a request that NO stub answered reaches this guard. On :3101 (API on
 * the isolated :8001) the guard therefore never sees the stubbed traffic; on a frontend whose API is
 * :8000 it does not see it either, because the stubs got there first. Registered with
 * `page.route` and last, as three of these specs had it, the guard outranked the stubs and aborted
 * every stubbed :8000 call (evidence: review-fix-before-live-stack-guard.log).
 *
 * WHAT A HIT MEANS. A request to :8000 that no stub answered, which from such a frontend would have gone
 * to the live backend. It is aborted in the browser (it never leaves it) and recorded, and the spec
 * fails on the record in its afterEach, naming the request.
 */
export const LIVE_API = /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\]|0\.0\.0\.0):8000(\/|$)/;

/** The afterEach message every spec using the guard fails with. */
export const LIVE_API_MESSAGE = 'nothing may reach the live backend (:8000): this request was answered by no stub';

/**
 * Abort, and record in `hits`, every request to the live API that no page-level stub answered.
 * Call it at any point before the first navigation; its position among the page's routes does not
 * matter, because it is not one of them.
 */
export async function fenceLiveApi(page: Page, hits: string[]): Promise<void> {
  await page.context().route(LIVE_API, (route: Route) => {
    hits.push(`${route.request().method()} ${route.request().url()}`);
    return route.abort('blockedbyclient');
  });
}
