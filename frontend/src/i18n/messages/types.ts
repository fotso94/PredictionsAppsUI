/**
 * The catalogue's shape, derived from English — and the seam that lets three packages write into
 * it at once.
 *
 * ── WHY THE CATALOGUE IS IN AREAS ───────────────────────────────────────────────────────────
 *
 * It used to be one object of 568 lines per language. That is fine with one author and is a
 * single merge conflict with three: the auth screens, the expert screens and the reader screens
 * are being translated in parallel, and every one of them would have appended to the same lines
 * of the same two files. So each area is a module of its own —
 *
 *   ./core.en.ts    ./core.fr.ts      the shell, matchday, freshness, the measured record, home
 *   ./auth.en.ts    ./auth.fr.ts      sign in, register, password, profile, subscription
 *   ./expert.en.ts  ./expert.fr.ts    the expert screens
 *   ./reader.en.ts  ./reader.fr.ts    the remaining reader screens
 *
 * — and ./en.ts and ./fr.ts compose the four into the one catalogue the rest of the application
 * imports. Nothing outside this directory changed: `import en from './messages/en'` still returns
 * every key, `MessageKey` is still the union of all of them, and `t()` is unchanged.
 *
 * ── WHERE TO ADD A KEY ──────────────────────────────────────────────────────────────────────
 *
 * In the area it belongs to, English first. `Area<'expert'>` is derived from ./expert.en.ts, so
 * ./expert.fr.ts stops compiling the moment the English grows a key the French does not have —
 * and it fails IN THE FRENCH AREA FILE, naming the missing key, rather than somewhere in a
 * composed object three imports away. That is the only mechanism that reliably stops a
 * half-translated page shipping, and it now points at the file whose author can fix it.
 *
 * `import('./en')` and the imports below are TYPE-ONLY. They are erased before the bundler sees
 * them, so they create no module edge and pull nothing into any chunk that only needs the shape.
 */

/** Every key in the composed catalogue. */
export type MessageKey = keyof typeof import('./en').default

/** A complete catalogue. Every key, no extras. */
export type Catalog = Readonly<Record<MessageKey, string>>

/**
 * The English side of each area, which is what every other language's area is measured against.
 *
 * Adding an area is three steps: a pair of files, an entry here, and a spread in ./en.ts and
 * ./fr.ts. `frontend/e2e/mocked/localisation.spec.ts` fails if two areas claim the same key, so
 * a collision between two packages is caught rather than silently resolved by spread order.
 */
interface EnglishAreas {
  core: typeof import('./core.en').default
  auth: typeof import('./auth.en').default
  expert: typeof import('./expert.en').default
  reader: typeof import('./reader.en').default
}

/** The areas by name. */
export type AreaName = keyof EnglishAreas

/** One area of the catalogue in a language that is not the source language. */
export type Area<Name extends AreaName> = Readonly<Record<keyof EnglishAreas[Name], string>>
