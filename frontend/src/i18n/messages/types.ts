/**
 * The catalogue's shape, derived from English.
 *
 * English is the source language: it is where a new string is written first, and it is the
 * fallback if anything ever goes wrong with another catalogue. Deriving the type from it means a
 * key added to `en.ts` and forgotten in `fr.ts` is a COMPILE ERROR, not a French page with an
 * English sentence in the middle of it that nobody notices until a reader reports it.
 *
 * `import('./en')` here is a TYPE-ONLY import. It is erased before the bundler sees it, so it
 * creates no module edge and does not pull English into any chunk that only needs the shape.
 */
export type MessageKey = keyof typeof import('./en').default

/** A complete catalogue. Every key, no extras. */
export type Catalog = Readonly<Record<MessageKey, string>>
