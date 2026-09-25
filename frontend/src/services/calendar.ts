/**
 * A calendar file of the fixtures this reader saved — a SNAPSHOT, and nothing more.
 *
 * WHAT THIS IS, SAID ONCE AND PROPERLY
 *
 * This builds an RFC 5545 iCalendar document from the saved matches already in hand. The reader
 * downloads it and imports it. From that moment the file is a photograph: if a fixture is moved,
 * abandoned or rescheduled, the events in their calendar keep the kick-off that was stored on the
 * day they pressed the button, and nothing here will ever correct them.
 *
 * THAT IS A DIFFERENT PRODUCT FROM A SUBSCRIBED FEED, AND IT IS NOT BEING BUILT HERE. A calendar
 * a reader subscribes to is a URL their calendar application re-reads on a schedule. Doing that
 * honestly needs event identifiers that stay stable when a fixture's provider id changes, a
 * SEQUENCE that increments on every revision so a moved kick-off actually replaces the old one
 * rather than sitting beside it, a CANCELLED event for a fixture that disappears from our data,
 * and an endpoint that serves the file to an unauthenticated calendar client without leaking one
 * reader's saves to another. None of that exists, so none of it is implied:
 *
 *   - there is NO METHOD property, so no calendar client treats this as a published, managed feed;
 *   - there is NO REFRESH-INTERVAL and NO X-PUBLISHED-TTL, the two properties that tell a client
 *     "come back and re-read me" — a file carrying them while nothing is at the other end is a
 *     promise that cannot be kept;
 *   - SEQUENCE is 0 on every event and stays 0, because this file has no revision history;
 *   - the calendar's own name and description say, inside the file, that it is a snapshot and the
 *     moment it was taken. The interface says it too, beside the button. Neither is a footnote.
 *
 * NOTHING IS INVENTED. A fixture whose stored record has a kick-off time becomes a timed event; a
 * fixture that only has a calendar date becomes an all-day event and says so in its own
 * description, rather than being given a plausible 15:00. A fixture with neither is left out and
 * counted, so the caller can tell the reader how many and why instead of quietly shipping a
 * shorter file.
 *
 * THE ONE DURATION, AND WHY IT IS NOT A CLAIM. Our records hold a kick-off and no final whistle,
 * so a timed event is blocked out for two hours to keep it from rendering as a zero-length sliver
 * in a week view. That is a calendar layout decision, not a fact about the match, and every event
 * carrying it says so in its description.
 *
 * NO FORECAST, TIP OR PROBABILITY GOES INTO THIS FILE. A calendar entry is read at a glance, in a
 * context this application does not control, long after it was written. It carries the fixture,
 * the competition, the reader's own note and — for a match already played — the stored final
 * score. That is all.
 */

import type { SavedMatch } from '@/types';
import { isPlayableNow, resultDelay } from '@/utils/resultDelay';

/** Identifies the software that wrote the file, as RFC 5545 requires. */
const PRODID = '-//Soccer Predictions//Saved fixtures snapshot//EN';

/**
 * The right-hand side of every UID.
 *
 * A UID has to be globally unique and stable for the event it names. The match id supplies the
 * uniqueness; this is only the domain part. It is a fixed string rather than the current hostname
 * so that two snapshots of the same save, taken from localhost and from a deployment, still
 * produce the same UID and a re-import updates the entry instead of duplicating it.
 */
const UID_DOMAIN = 'saved-fixtures.soccer-predictions.invalid';

/** How long a timed fixture is blocked out for. A layout choice — see the note at the top. */
const BLOCKED_OUT_MINUTES = 120;

export interface CalendarSnapshot {
  /** The complete .ics document, CRLF-terminated as the format requires. */
  text: string;
  /** A filename carrying the snapshot's date, so two downloads do not overwrite each other. */
  filename: string;
  /** Events written: timed plus all-day. */
  events: number;
  /** Events written with only a date, because no kick-off time was stored. */
  dateOnly: number;
  /** Saves left out because the stored fixture carried neither a kick-off nor a date. */
  skipped: number;
  /** When the snapshot was taken, ISO-8601 UTC. The same instant the file states internally. */
  takenAt: string;
}

// ------------------------------------------------------------------------ RFC 5545 plumbing
/**
 * Escape a value for a TEXT property: backslash, semicolon and comma are delimiters, and a literal
 * newline is written as `\n`. A team name with a comma in it breaks the file without this.
 */
function escapeText(value: string): string {
  return value
    .replace(/\\/g, '\\\\')
    .replace(/;/g, '\\;')
    .replace(/,/g, '\\,')
    .replace(/\r\n|\r|\n/g, '\\n');
}

const utf8 = typeof TextEncoder === 'undefined' ? null : new TextEncoder();

/** Byte length of a string in UTF-8. Folding is specified in OCTETS, not characters. */
function octets(value: string): number {
  // `TextEncoder` exists in every browser this application supports; the fallback keeps the
  // module usable in a bare runtime rather than throwing, and only over-counts, never under.
  return utf8 ? utf8.encode(value).length : value.length * 4;
}

/**
 * Fold one content line to 75 octets, continuing with a leading space.
 *
 * Folded on character boundaries, never inside a multi-byte character: a split UTF-8 sequence
 * produces a file some calendar clients reject outright and others import with a replacement
 * character in the middle of a club's name.
 */
function foldLine(line: string): string {
  if (octets(line) <= 75) return line;
  const parts: string[] = [];
  let current = '';
  // The first line may hold 75 octets; every continuation loses one to its leading space.
  let budget = 75;
  for (const char of line) {
    if (octets(current) + octets(char) > budget) {
      parts.push(current);
      current = char;
      budget = 74;
    } else {
      current += char;
    }
  }
  parts.push(current);
  return parts.join('\r\n ');
}

/** `20260919T143000Z` — the UTC form, which needs no VTIMEZONE and cannot be misread. */
function stampUtc(at: Date): string {
  const pad = (value: number, width = 2) => String(value).padStart(width, '0');
  return `${at.getUTCFullYear()}${pad(at.getUTCMonth() + 1)}${pad(at.getUTCDate())}`
    + `T${pad(at.getUTCHours())}${pad(at.getUTCMinutes())}${pad(at.getUTCSeconds())}Z`;
}

/** `20260919` from a `YYYY-MM-DD` calendar date, or null when it is not one. */
function stampDate(date: string | null | undefined): string | null {
  if (typeof date !== 'string') return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(date);
  return match ? `${match[1]}${match[2]}${match[3]}` : null;
}

/** The day after `YYYYMMDD`, for an all-day event's exclusive DTEND. */
function nextDayStamp(stamp: string): string {
  const at = new Date(Date.UTC(
    Number(stamp.slice(0, 4)), Number(stamp.slice(4, 6)) - 1, Number(stamp.slice(6, 8)),
  ));
  at.setUTCDate(at.getUTCDate() + 1);
  return stampUtc(at).slice(0, 8);
}

/** A usable kick-off instant, or null. Never a guess. */
function kickoffAt(entry: SavedMatch): Date | null {
  const raw = entry.match.kickoffUtc;
  if (!raw) return null;
  const at = new Date(raw);
  return Number.isNaN(at.getTime()) ? null : at;
}

/**
 * What to sort an entry by.
 *
 * A fixture with only a date still has a place in the running order, and putting every one of
 * them at the end would file a date-only fixture on Tuesday after a timed one on Friday. This is
 * ordering only: it never reaches DTSTART, so nothing gains a kick-off time it does not have.
 */
function sortKey(entry: SavedMatch): number {
  const at = kickoffAt(entry);
  if (at) return at.getTime();
  const day = stampDate(entry.match.date);
  if (!day) return Number.POSITIVE_INFINITY;
  return Date.UTC(Number(day.slice(0, 4)), Number(day.slice(4, 6)) - 1, Number(day.slice(6, 8)));
}

// --------------------------------------------------------------------------- the document
/** Whatever score the stored result row carries, whether or not the match has finished. */
function storedScore(entry: SavedMatch): string | null {
  const result = entry.match.result;
  if (!result) return null;
  const { homeScore, awayScore } = result;
  if (typeof homeScore !== 'number' || typeof awayScore !== 'number') return null;
  return `${homeScore}-${awayScore}`;
}

/**
 * A FINISHED fixture's score, or null.
 *
 * A fixture that is `live` or `halftime` carries a result row as well — the score as it stands at
 * this second — and a calendar entry saying "Final score as stored: 1-0" for a match still being
 * played is wrong the moment the next goal goes in. This file never updates, so that line would
 * stay wrong forever. An in-play score is not withheld, it is labelled for what it is: see
 * `descriptionFor`. `postponed` and `cancelled` are excluded too — whatever the row holds, the
 * match did not finish that way.
 */
function finalScore(entry: SavedMatch): string | null {
  return entry.match.status === 'finished' ? storedScore(entry) : null;
}

/**
 * The score of a match that is being played as the snapshot is taken, or null.
 *
 * `isPlayableNow` rather than the stored status, because a fixture whose final score has not arrived
 * keeps `live` or `halftime` until one does, and this file is written once and never corrected. Its line
 * says "with the match still being played", in the present tense, in a file that will sit in a
 * reader's calendar for months: the one place in this product where a wrong tense cannot be
 * repaired by the next refresh.
 */
function inPlayScore(entry: SavedMatch): string | null {
  return isPlayableNow(entry.match) ? storedScore(entry) : null;
}

/**
 * Why a fixture carries no score in this snapshot even though its kickoff has long passed.
 *
 * Without it the entry says nothing at all about such a fixture, and a reader opening their
 * calendar weeks later finds a kickoff time and silence where a result should be. This says which
 * silence it is, and it is deliberately not a score.
 */
function unresolvedLine(entry: SavedMatch): string | null {
  const delay = resultDelay(entry.match);
  if (!delay) return null;
  /*
   * Both sentences stay on the facts the row carries: when a result was due, that none had reached
   * us, and whether we had stopped asking. Stopping is a limit of ours, so the given-up sentence
   * says a result may still exist, and says where to look — this file cannot be updated with it.
   * Neither sentence says the match was or was not being played: what is known is that the row
   * had stopped changing, which is evidence about our data, not about the football.
   */
  return delay.state === 'given_up'
    ? 'No result for this fixture had reached us when this snapshot was taken, and we had stopped '
      + 'asking for it. That is a limit of ours, not a sign that no result exists. Nothing here is '
      + 'a score, and this file will not be updated with one; check the match page.'
    : 'A result for this fixture was due before this snapshot was taken and had not reached us. '
      + 'It was not shown as in play at that moment, and nothing here is a score.';
}

/** What a reader sees in their calendar's list view. Postponed and cancelled say so. */
function summaryFor(entry: SavedMatch): string {
  const { homeTeam, awayTeam, status } = entry.match;
  const fixture = `${homeTeam.name} v ${awayTeam.name}`;
  if (status === 'postponed') return `${fixture} (postponed)`;
  if (status === 'cancelled') return `${fixture} (cancelled)`;
  return fixture;
}

function descriptionFor(entry: SavedMatch, timed: boolean, takenAt: string): string {
  const lines: string[] = [];
  if (entry.match.league?.name) lines.push(entry.match.league.name);
  const score = finalScore(entry);
  if (score) lines.push(`Final score as stored: ${score}`);
  const unresolved = unresolvedLine(entry);
  if (unresolved) lines.push(unresolved);
  const running = inPlayScore(entry);
  if (running) {
    lines.push(
      `Score when this snapshot was taken, with the match still being played: ${running}. That is `
      + 'not the final score, and nothing here will fill it in later.',
    );
  }
  if (entry.note) lines.push(`Your note: ${entry.note}`);
  lines.push(timed
    ? `Blocked out for ${BLOCKED_OUT_MINUTES / 60} hours. Only the kick-off time is stored, not an `
      + 'end time, so the finish shown here is a placeholder rather than a fact about the match.'
    : 'Only a calendar date is stored for this fixture, not a kick-off time, so it is written as '
      + 'an all-day entry rather than given a time it might not have.');
  lines.push(
    `Snapshot taken ${takenAt}. This entry does not update: if the fixture is moved or called off, `
    + 'nothing will correct it here. Check the fixture before travelling.',
  );
  return lines.join('\n');
}

/**
 * Build the snapshot.
 *
 * `saved` is whatever the caller wants in the file — pass the reader's saves. Order is by
 * kick-off, earliest first, with undated entries last, so the file reads the way a calendar does.
 */
export function buildSavedFixturesCalendar(
  saved: SavedMatch[],
  now: Date = new Date(),
): CalendarSnapshot {
  const takenAt = now.toISOString();
  const dtstamp = stampUtc(now);
  const lines: string[] = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    `PRODID:${PRODID}`,
    'CALSCALE:GREGORIAN',
    `X-WR-CALNAME:${escapeText(`Saved fixtures (snapshot, ${takenAt.slice(0, 10)})`)}`,
    `X-WR-CALDESC:${escapeText(
      `A one-time snapshot of the fixtures you saved, taken ${takenAt}. It does not update. `
      + 'If a fixture is rescheduled or called off after this file was made, these entries will '
      + 'still show the old time. This is not a subscribed calendar feed.',
    )}`,
  ];

  const ordered = [...saved].sort((a, b) => sortKey(a) - sortKey(b));

  let events = 0;
  let dateOnly = 0;
  let skipped = 0;

  for (const entry of ordered) {
    const at = kickoffAt(entry);
    const day = at ? null : stampDate(entry.match.date);
    // Neither a kick-off nor a date: there is no honest event to write, so it is counted and the
    // caller tells the reader. Writing it at midnight today would be an invented time.
    if (!at && !day) { skipped += 1; continue; }

    const body: string[] = [
      'BEGIN:VEVENT',
      `UID:${escapeText(entry.matchId)}@${UID_DOMAIN}`,
      `DTSTAMP:${dtstamp}`,
      // Always 0: this file has no revision history, and an incrementing SEQUENCE is precisely
      // what a self-updating feed would need. See the note at the top of the module.
      'SEQUENCE:0',
    ];

    if (at) {
      const end = new Date(at.getTime() + BLOCKED_OUT_MINUTES * 60_000);
      body.push(`DTSTART:${stampUtc(at)}`, `DTEND:${stampUtc(end)}`);
    } else if (day) {
      dateOnly += 1;
      body.push(`DTSTART;VALUE=DATE:${day}`, `DTEND;VALUE=DATE:${nextDayStamp(day)}`);
    }

    body.push(`SUMMARY:${escapeText(summaryFor(entry))}`);
    body.push(`DESCRIPTION:${escapeText(descriptionFor(entry, at !== null, takenAt))}`);
    if (entry.match.venue) body.push(`LOCATION:${escapeText(entry.match.venue)}`);
    // A fixture our data says is off is marked off, so a calendar client can grey it out.
    if (entry.match.status === 'cancelled') body.push('STATUS:CANCELLED');
    // Nobody is expected to turn up to a football match in their own calendar's eyes: a fixture
    // is an appointment, so TRANSP defaults to OPAQUE, which is what a reader would expect.
    body.push('END:VEVENT');

    lines.push(...body);
    events += 1;
  }

  lines.push('END:VCALENDAR');

  return {
    text: `${lines.map(foldLine).join('\r\n')}\r\n`,
    filename: `saved-fixtures-snapshot-${takenAt.slice(0, 10)}.ics`,
    events,
    dateOnly,
    skipped,
    takenAt,
  };
}

export default buildSavedFixturesCalendar;
