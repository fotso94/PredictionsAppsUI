/**
 * The message format, and the reason this application has one at all.
 *
 * THE TRAP THIS EXISTS TO AVOID. Most of the sentences on this site are built at runtime out of
 * measured values: "None of the 12 fixtures listed here has been played yet", "3 of 4 sources have
 * a measured record", "overdue by 1 hour". The cheap way to translate those is to translate the
 * fragments and keep the English assembly — `${count} ${word}${count === 1 ? '' : 's'}` with a
 * French `word` — and it produces text that is wrong in three separate ways at once:
 *
 *   1. THE PLURAL RULE IS NOT THE SAME. English is singular at 1 and plural everywhere else.
 *      French is singular at 0 AND 1: "0 match", "1 match", "2 matchs". An English-shaped
 *      pluraliser writes "0 matchs", which is simply a mistake, and it writes it on the empty
 *      state — the screen a reader is most likely to be confused by already.
 *   2. AGREEMENT RUNS BACKWARDS THROUGH THE SENTENCE. "Aucun des 12 matchs" but "Aucune des 12
 *      compétitions"; "Tous les 12 matchs ont commencé" but "Toutes les 12 rencontres ont
 *      commencé". The determiner, the pronoun and the past participle all agree with a noun that
 *      appears later, so no amount of translating the noun on its own can fix the words in front
 *      of it.
 *   3. THE WORD ORDER IS NOT THE SAME EITHER. "the next attempt is overdue by 2 hours" is "la
 *      prochaine tentative a 2 heures de retard" — the duration lands in the middle, not at the
 *      end. A sentence concatenated in English order cannot be reordered by translating its parts.
 *
 * So a message is ONE string per language, with holes in it, and the language's own catalogue
 * decides where the holes go, which plural form surrounds them and which gendered words agree
 * with what. That is what this file parses.
 *
 * WHAT IS SUPPORTED, which is a deliberate subset of ICU MessageFormat:
 *
 *   {name}                                    a value, formatted by its type (see below)
 *   {count, plural, one {…} other {…}}        Intl.PluralRules for the active language
 *   {count, plural, =0 {…} one {…} other {…}} an exact match, which wins over the category
 *   {gender, select, f {…} m {…} other {…}}   any closed set of variants: gender, tone, state
 *   {value, number}                           Intl.NumberFormat for the active language
 *   #                                         inside a plural branch: the formatted count
 *
 * A COUNT MAY ARRIVE ALREADY FORMATTED. Several call sites format a figure on its way in, so the
 * value in a plural hole can be the string "1 234" rather than the number 1234. That is read back
 * with the locale's own separators (see `countFrom`), so the branch is still chosen correctly and
 * `#` prints the identical string the caller passed.
 *
 * WHAT IS DELIBERATELY NOT SUPPORTED, AND WHY. ICU's apostrophe quoting. In ICU, `'` starts a
 * literal and `''` is one apostrophe, which would mean every French message in the catalogue —
 * "l'expert", "n'a pas", "aujourd'hui" — had to be written with doubled apostrophes, and a single
 * missed one silently swallows the rest of the sentence. French is half the point of this package,
 * so the escape character is the one that goes. Only `{`, `}` and `#` are special here, and a
 * literal brace is written `{lb}` / `{rb}` via the parameters. No message in the catalogue needs
 * one today.
 *
 * NOTHING HERE FORMATS A DATE OR A TIME. Those need the reader's chosen time zone, which this
 * module knows nothing about; they are formatted by the caller (see src/i18n/zones.ts) and passed
 * in as already-formatted strings. A date formatter that silently used the device's zone is
 * exactly the defect C3 of this package exists to prevent.
 */

/** A value a message may be given. Objects are rejected rather than stringified as "[object Object]". */
export type MessageParam = string | number | boolean | null | undefined

export type MessageParams = Record<string, MessageParam>

// --------------------------------------------------------------------------- the parsed shape

type Node = LiteralNode | ArgumentNode | PluralNode | SelectNode | HashNode

interface LiteralNode { kind: 'literal'; text: string }
interface ArgumentNode { kind: 'argument'; name: string; format: 'string' | 'number' }
interface HashNode { kind: 'hash' }
interface PluralNode { kind: 'plural'; name: string; branches: Map<string, Node[]> }
interface SelectNode { kind: 'select'; name: string; branches: Map<string, Node[]> }

/** A message compiled once and reusable. Compiling is not free; every catalogue entry is cached. */
export type CompiledMessage = Node[]

// --------------------------------------------------------------------------- the parser

class Parser {
  private at = 0

  constructor(private readonly source: string) {}

  /** Parse until the end of the input, or until an unmatched `}` when inside a branch. */
  parse(insideBranch: boolean): Node[] {
    const nodes: Node[] = []
    let literal = ''

    const flush = () => {
      if (literal) {
        nodes.push({ kind: 'literal', text: literal })
        literal = ''
      }
    }

    while (this.at < this.source.length) {
      const char = this.source[this.at]

      if (char === '}' && insideBranch) break

      if (char === '{') {
        flush()
        nodes.push(this.parsePlaceholder())
        continue
      }

      if (char === '#' && insideBranch) {
        flush()
        nodes.push({ kind: 'hash' })
        this.at += 1
        continue
      }

      literal += char
      this.at += 1
    }

    flush()
    return nodes
  }

  private parsePlaceholder(): Node {
    this.at += 1 // past '{'
    this.skipSpace()
    const name = this.readName()
    this.skipSpace()

    if (this.source[this.at] === '}') {
      this.at += 1
      return { kind: 'argument', name, format: 'string' }
    }

    this.expect(',')
    this.skipSpace()
    const type = this.readName()
    this.skipSpace()

    if (type === 'number') {
      this.expect('}')
      return { kind: 'argument', name, format: 'number' }
    }

    if (type !== 'plural' && type !== 'select') {
      throw new Error(`Unknown placeholder type "${type}" in message: ${this.source}`)
    }

    this.expect(',')
    const branches = this.parseBranches()
    return type === 'plural' ? { kind: 'plural', name, branches } : { kind: 'select', name, branches }
  }

  private parseBranches(): Map<string, Node[]> {
    const branches = new Map<string, Node[]>()
    for (;;) {
      this.skipSpace()
      if (this.source[this.at] === '}') {
        this.at += 1
        break
      }
      if (this.at >= this.source.length) {
        throw new Error(`Unterminated branch list in message: ${this.source}`)
      }
      const key = this.readBranchKey()
      this.skipSpace()
      this.expect('{')
      branches.set(key, this.parse(true))
      this.expect('}')
    }
    if (branches.size === 0) {
      throw new Error(`No branches in message: ${this.source}`)
    }
    return branches
  }

  private readName(): string {
    const start = this.at
    while (this.at < this.source.length && /[A-Za-z0-9_]/.test(this.source[this.at])) this.at += 1
    if (this.at === start) throw new Error(`Expected a name at ${start} in message: ${this.source}`)
    return this.source.slice(start, this.at)
  }

  /** `one`, `other`, `f`, or an exact match written `=0`. */
  private readBranchKey(): string {
    const start = this.at
    while (this.at < this.source.length && /[A-Za-z0-9_=-]/.test(this.source[this.at])) this.at += 1
    if (this.at === start) throw new Error(`Expected a branch key at ${start} in message: ${this.source}`)
    return this.source.slice(start, this.at)
  }

  private skipSpace(): void {
    while (this.at < this.source.length && /\s/.test(this.source[this.at])) this.at += 1
  }

  private expect(char: string): void {
    if (this.source[this.at] !== char) {
      throw new Error(`Expected "${char}" at ${this.at} in message: ${this.source}`)
    }
    this.at += 1
  }
}

/** Compile one message. Throws on a malformed message, which is a bug in the catalogue. */
export function compileMessage(source: string): CompiledMessage {
  return new Parser(source).parse(false)
}

// --------------------------------------------------------------------------- rendering

/**
 * `Intl.PluralRules` per language, built once.
 *
 * This is where the difference that matters lives: `new Intl.PluralRules('fr').select(0)` is
 * `"one"` and `new Intl.PluralRules('en').select(0)` is `"other"`. Neither catalogue has to know
 * that; each simply writes the branches its own language has.
 */
const pluralRules = new Map<string, Intl.PluralRules>()

function rulesFor(locale: string): Intl.PluralRules {
  let rules = pluralRules.get(locale)
  if (!rules) {
    rules = new Intl.PluralRules(locale)
    pluralRules.set(locale, rules)
  }
  return rules
}

const numberFormats = new Map<string, Intl.NumberFormat>()

/** A number in the reader's own convention: 1 234 in French, 1,234 in English. */
export function formatNumber(locale: string, value: number): string {
  let format = numberFormats.get(locale)
  if (!format) {
    format = new Intl.NumberFormat(locale)
    numberFormats.set(locale, format)
  }
  return format.format(value)
}

/**
 * The separators this locale writes numbers with, learned from the formatter itself.
 *
 * Nothing here hardcodes "," or " ". `formatToParts` is asked what THIS locale actually does, so
 * the answer stays right when a runtime's CLDR data changes — French switched its group separator
 * from U+00A0 to U+202F in recent ICU, and a hand-written list of separators would have gone
 * quietly wrong on the day that shipped.
 */
interface NumberSyntax { group: string; decimal: string; minus: string }

const numberSyntaxes = new Map<string, NumberSyntax>()

function syntaxFor(locale: string): NumberSyntax {
  let syntax = numberSyntaxes.get(locale)
  if (!syntax) {
    const parts = new Intl.NumberFormat(locale).formatToParts(-12345.6)
    syntax = {
      group: parts.find(part => part.type === 'group')?.value ?? ',',
      decimal: parts.find(part => part.type === 'decimal')?.value ?? '.',
      minus: parts.find(part => part.type === 'minusSign')?.value ?? '-',
    }
    numberSyntaxes.set(locale, syntax)
  }
  return syntax
}

/**
 * The count a plural must choose its branch by, from a value that may ALREADY BE FORMATTED.
 *
 * WHY THIS IS NOT JUST `Number(raw)`. Several call sites pass a figure that has been through
 * `formatNumber` on its way in — the measured record hands the panel "1 234" so the digits are
 * grouped the reader's way, and the coverage line does the same. `Number("1 234")` is `NaN`, so a
 * plural keyed on one of those would have silently printed `{sample}` on the page the moment a
 * sample passed a thousand: the message would have looked right in every test written with small
 * numbers and broken on the installation that grew. Reading the formatted form back with the
 * locale's own separators removes that cliff, and for an integer the round trip is exact, so `#`
 * prints back the identical string the caller passed in.
 *
 * A value that is not a number in any reading still returns NaN, and the caller still renders
 * `{name}` loudly rather than guessing a branch.
 */
function countFrom(locale: string, raw: MessageParam): number {
  if (typeof raw === 'number') return raw
  if (typeof raw !== 'string' || raw.trim() === '') return Number.NaN

  const direct = Number(raw)
  if (Number.isFinite(direct)) return direct

  const { group, decimal, minus } = syntaxFor(locale)
  const plain = raw
    .split(group).join('')
    .replace(/\s/g, '')
    .split(minus).join('-')
    .split(decimal).join('.')
  return plain === '' ? Number.NaN : Number(plain)
}

function branchFor(branches: Map<string, Node[]>, keys: string[]): Node[] {
  for (const key of keys) {
    const found = branches.get(key)
    if (found) return found
  }
  // `other` is required of every plural and every select, so this is a catalogue bug, not a
  // runtime condition. Rendering nothing would delete a sentence; the key is shown instead so it
  // is found the first time anybody looks at the page.
  return [{ kind: 'literal', text: `[missing branch: ${keys.join('/')}]` }]
}

function renderNodes(
  nodes: CompiledMessage,
  locale: string,
  params: MessageParams,
  hashValue: string | null,
): string {
  let out = ''
  for (const node of nodes) {
    switch (node.kind) {
      case 'literal':
        out += node.text
        break

      case 'hash':
        out += hashValue ?? ''
        break

      case 'argument': {
        const value = params[node.name]
        if (value === null || value === undefined) {
          // Deliberately loud. A silently empty hole is how "3 of 4 sources" becomes "of 4
          // sources" in one language only, which is exactly the class of defect this package is
          // meant to remove rather than introduce.
          out += `{${node.name}}`
          break
        }
        out += node.format === 'number' && typeof value === 'number'
          ? formatNumber(locale, value)
          : String(value)
        break
      }

      case 'plural': {
        const count = countFrom(locale, params[node.name])
        if (!Number.isFinite(count)) {
          out += `{${node.name}}`
          break
        }
        const category = rulesFor(locale).select(count)
        const chosen = branchFor(node.branches, [`=${count}`, category, 'other'])
        out += renderNodes(chosen, locale, params, formatNumber(locale, count))
        break
      }

      case 'select': {
        const raw = params[node.name]
        const key = raw === null || raw === undefined ? 'other' : String(raw)
        const chosen = branchFor(node.branches, [key, 'other'])
        out += renderNodes(chosen, locale, params, hashValue)
        break
      }
    }
  }
  return out
}

/** Render a compiled message for `locale` with `params`. */
export function renderMessage(
  compiled: CompiledMessage,
  locale: string,
  params: MessageParams = {},
): string {
  return renderNodes(compiled, locale, params, null)
}
