import React from 'react'

/**
 * One translated sentence, with the value inside it picked out.
 *
 * THE PROBLEM THIS SOLVES. Three sentences on the auth screens put a value in the middle of
 * themselves and emphasise it: the fixture the visitor was saving, and the address a reset link
 * was sent to. In JSX that is normally written as a prefix, a `<span>` and a suffix — three
 * pieces, each translated on its own. Every one of those pieces is then frozen in English word
 * order, which is the exact failure src/i18n/format.ts exists to prevent: the catalogue can no
 * longer decide where in the sentence the value goes, and a language that puts it elsewhere
 * cannot say so.
 *
 * So the catalogue keeps the WHOLE sentence with a hole in it, `t()` renders it, and this finds
 * the rendered value inside the rendered sentence and wraps that one run. The hole may sit
 * anywhere the language needs it, including at the very start or the very end, and the emphasis
 * follows it.
 *
 * WHAT IT DOES WHEN IT CANNOT FIND THE VALUE. It renders the sentence, plainly and in full.
 * That happens if a translation drops the hole, or if the value is the empty string. Losing a
 * font weight is not worth losing a sentence over, and it is never worth throwing during a
 * render.
 *
 * ONLY THE FIRST OCCURRENCE is wrapped. A value that appears twice is emphasised once, which is
 * what every sentence here wants and is stable rather than surprising.
 */
export interface EmphasisedProps {
  /** The rendered message, value already interpolated. */
  sentence: string
  /** The value to pick out, exactly as it appears in `sentence`. */
  value: string
  /** Classes for the emphasised run. */
  className?: string
  /**
   * The element the run is wrapped in. `strong` where the emphasis carries MEANING — the
   * address a reset link was sent to is the whole point of that sentence — and the default
   * `span` where it is only weight. A screen reader announces the two differently, so this is
   * not a styling choice.
   */
  as?: 'span' | 'strong'
}

const Emphasised: React.FC<EmphasisedProps> = ({ sentence, value, className, as = 'span' }) => {
  const at = value ? sentence.indexOf(value) : -1
  if (at < 0) return <>{sentence}</>
  const Tag = as
  return (
    <>
      {sentence.slice(0, at)}
      <Tag className={className}>{value}</Tag>
      {sentence.slice(at + value.length)}
    </>
  )
}

export default Emphasised
