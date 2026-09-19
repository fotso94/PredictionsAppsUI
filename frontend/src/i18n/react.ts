/**
 * The React binding: the subscription that makes a language change repaint the page.
 *
 * Deliberately separate from the provider component. A module that exports both a component and a
 * hook trips this project's `react-refresh/only-export-components` rule, and `npm run lint` runs
 * with `--max-warnings 0`, so the split is a build requirement rather than a preference. The
 * components live in LocaleProvider.tsx and import the context from here.
 *
 * Nothing in here translates anything. `t` is the same function src/i18n/index.ts exports; what
 * this adds is only the guarantee that a component using it re-renders when the catalogue behind
 * it changes.
 */

import { createContext, useContext } from 'react'
import type { Language, TranslateFn, ZoneId } from './index'
import { currentLanguage, currentZone, setLanguage, setZone, t } from './index'

export interface LocaleValue {
  language: Language
  zone: ZoneId
  /** Loads the catalogue first, then switches: the page never renders half-translated. */
  setLanguage: (next: Language) => Promise<void>
  setZone: (next: ZoneId) => void
  t: TranslateFn
  /** True when the chosen catalogue failed to download and English is standing in. */
  fellBack: boolean
}

/**
 * The default value is the live module state rather than a stub.
 *
 * A component rendered outside the provider — a test mounting one component on its own, a future
 * portal — then gets correct English text instead of a blank page or a thrown error. What it does
 * not get is the re-render on change, which is exactly what the provider adds.
 */
export const LocaleContext = createContext<LocaleValue>({
  language: currentLanguage(),
  zone: currentZone(),
  setLanguage,
  setZone,
  t,
  fellBack: false,
})

/** Language, zone, both setters and `t`. */
export function useLocale(): LocaleValue {
  return useContext(LocaleContext)
}

/** Just the translator, for the many components that need nothing else. */
export function useT(): TranslateFn {
  return useContext(LocaleContext).t
}
