import { Page } from '@playwright/test';
import fr from '../../src/i18n/messages/fr';
import { OFFERED_ZONES } from '../../src/i18n/zones';
import type { ApiMatch } from './api-stub';

/**
 * THE ALLOW-LIST WALK: every word a French page shows must be accounted for.
 *
 * Moved here from e2e/mocked/expert-localisation.spec.ts, which built it for the match picker,
 * so that e2e/mocked/expert-composer-localisation.spec.ts can walk the composer with the same
 * rules rather than a copy of them. The reasoning is in that file's header; in short, a deny-list
 * of known English can only find what is already on the list, so this iterates the PAGE instead
 * and requires each word to come from one of four derived sources:
 *
 *   1. the French catalogue, all four areas of it, with the ICU holes stripped out first — a
 *      parameter is named `{home}` and `{total}` in both languages and would otherwise smuggle
 *      "home" and "total" into the vocabulary of allowed French;
 *   2. the fixtures the calling test injected — club names, competitions, countries, venues —
 *      which are data and shown as the provider published them, in every language;
 *   3. the zone cities in src/i18n/zones.ts, for the zone named beside the day;
 *   4. what `Intl` itself calls the months and weekdays in French, for spelled-out dates.
 *
 * WHAT IT CANNOT DO. It cannot see a BAD translation, and it cannot catch an English string whose
 * every word also happens to be in the French catalogue — single words are its weakest case.
 */

/** Words from one message, ICU holes removed, lowercased. Anything under two letters is noise. */
export function wordsOf(value: string, into: Set<string>): void {
  value
    .replace(/\{[^}]*\}/g, ' ')
    .toLowerCase()
    .split(/[^\p{L}]+/u)
    .forEach(word => { if (word.length >= 2) into.add(word); });
}

/**
 * Every word a French page may legitimately show, derived from four sources and typed in none.
 *
 * `fixtures` is what the calling test put on the wire; nothing else about the data is assumed.
 * `withVenue` adds each fixture's venue, round and provider identifiers, which the composer's
 * evidence panel and its advanced section print and the match picker does not.
 */
export function frenchVocabulary(fixtures: ApiMatch[], options: { withVenue?: boolean } = {}): Set<string> {
  const allowed = new Set<string>();

  for (const value of Object.values(fr)) wordsOf(value, allowed);

  for (const match of fixtures) {
    const competition = match.competition as { name?: string; country?: string } | undefined;
    const names = [match.home?.name, match.home?.short_name, match.home?.country,
      match.away?.name, match.away?.short_name, match.away?.country,
      competition?.name, competition?.country];
    if (options.withVenue) {
      names.push(match.venue as string | undefined, match.round as string | undefined,
        match.provider as string | undefined, match.external_id as string | undefined, match.id);
    }
    names.forEach(name => { if (name) wordsOf(name, allowed); });
  }

  for (const zone of OFFERED_ZONES) wordsOf(zone.city, allowed);
  // `zoneLabel` writes the offset as "UTC+01:00"; the city list already carries "UTC" itself.

  for (let month = 0; month < 12; month += 1) {
    wordsOf(new Intl.DateTimeFormat('fr-FR', { month: 'long' }).format(new Date(Date.UTC(2026, month, 15))), allowed);
    wordsOf(new Intl.DateTimeFormat('fr-FR', { month: 'short' }).format(new Date(Date.UTC(2026, month, 15))), allowed);
  }
  for (let day = 4; day <= 10; day += 1) {
    wordsOf(new Intl.DateTimeFormat('fr-FR', { weekday: 'long' }).format(new Date(Date.UTC(2026, 0, day))), allowed);
  }

  return allowed;
}

/**
 * Everything the page shows or announces, inside the element `selector` names.
 *
 * `skipVerbatim` leaves out every text node inside a `[data-verbatim]` element: the backend's own
 * sentences, which are English on every page by policy (docs/known-limitations.md) and which the
 * calling test asserts EXACTLY, against the stub, through `verbatimStrings` below — so excluding
 * them here hides nothing that is not checked there.
 */
export async function pageStringsIn(page: Page, selector: string, options: { skipVerbatim?: boolean } = {}): Promise<string[]> {
  return page.evaluate(([css, skip]) => {
    const root = document.querySelector(css as string);
    if (!root) return [];
    const found: string[] = [];
    const keep = (value: string | null) => {
      const trimmed = (value ?? '').replace(/\s+/g, ' ').trim();
      if (trimmed) found.push(trimmed);
    };

    // Text nodes, including the visually hidden ones a screen reader is the only reader of.
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      if (skip && node.parentElement?.closest('[data-verbatim]')) continue;
      keep(node.textContent);
    }

    // And everything announced rather than drawn.
    root.querySelectorAll('[aria-label]').forEach(el => keep(el.getAttribute('aria-label')));
    root.querySelectorAll('[placeholder]').forEach(el => keep(el.getAttribute('placeholder')));
    root.querySelectorAll('[title]').forEach(el => keep(el.getAttribute('title')));
    root.querySelectorAll('img[alt]').forEach(el => keep(el.getAttribute('alt')));
    return found;
  }, [selector, Boolean(options.skipVerbatim)] as const);
}

/** The same, inside the element carrying `data-testid={testId}`. */
export async function pageStrings(page: Page, testId: string, options: { skipVerbatim?: boolean } = {}): Promise<string[]> {
  return pageStringsIn(page, `[data-testid="${testId}"]`, options);
}

/** The text of every `[data-verbatim]` element inside `selector`, with its `lang`. */
export async function verbatimStrings(page: Page, selector: string): Promise<Array<{ text: string; lang: string | null }>> {
  return page.evaluate(css => {
    const root = document.querySelector(css);
    if (!root) return [];
    return [...root.querySelectorAll('[data-verbatim]')].map(el => ({
      text: (el.textContent ?? '').replace(/\s+/g, ' ').trim(),
      lang: el.getAttribute('lang'),
    }));
  }, selector);
}

/** Each unaccounted-for word, with one string it appeared in, so a failure names the sentence. */
export function unaccountedWords(strings: string[], allowed: Set<string>): string[] {
  const offences = new Map<string, string>();
  for (const value of strings) {
    const seen = new Set<string>();
    wordsOf(value, seen);
    for (const word of seen) if (!allowed.has(word) && !offences.has(word)) offences.set(word, value);
  }
  return [...offences].map(([word, inside]) => `${word} — in: ${inside}`).sort();
}
