import React, { createContext, useCallback, useContext, useId, useMemo, useState } from 'react'
import clsx from 'clsx'

/**
 * Text-only reading mode: a choice the reader makes, not a guess we make about them.
 *
 * WHY THIS EXISTS, WITH THE NUMBER THAT JUSTIFIES IT. The matchday route was measured at 360x740
 * against a production build served the way a production host serves it — gzip, immutable
 * `/assets/*`, `no-cache` index.html — summing transferred bytes including response headers. A
 * cold visit on 2026-09-19 came to 2,440.5 kB across 56 requests, and 2,164.1 kB of that, 48
 * requests, was club crests from cdn.live-score-api.com drawn at 16-24px. The JavaScript everyone
 * worries about was 199.2 kB of the same load. On this route the imagery is the data cost, by a
 * factor of ten, and nothing in the bundle work touches it.
 *
 * Those figures are one measurement of one day's fixtures, re-measured independently before they
 * were written here. A different day carries a different set of clubs, so treat them as the
 * order of magnitude they establish and re-measure rather than quoting them forward.
 *
 * WHAT IT IS NOT. It is not a badge, it is not a claim, and it is not switched on for anybody by
 * inference. `navigator.connection.saveData` and `prefers-reduced-data` are guesses about a
 * reader's circumstances made from the wrong side of the connection; a reader on an expensive
 * megabyte in Douala and a reader on office fibre can both want this, and only they know which.
 * So it is off until somebody turns it on, and it is remembered after that.
 *
 * WHY IT PATCHES `HTMLImageElement`, WHICH DESERVES AN EXPLANATION.
 * `display: none` does not stop a browser fetching an image, and a MutationObserver cannot stop
 * one either: React sets `src` on an element it has created but not yet inserted, so the fetch has
 * already started by the time the node is observable. The only place left to stand between the
 * reader and 2 MB of crests is the assignment itself. So while the mode is on — and only while it
 * is on — `src` assignment on `<img>` is redirected into a data attribute instead of the network.
 * The original property descriptor is restored when the mode is turned off, and the withheld URLs
 * are put back, so the mode is genuinely reversible without a reload.
 *
 * The patch is scoped to `HTMLImageElement.prototype`, never to `Element.prototype`: nothing but
 * an `<img>` is affected. An image that must survive the mode can opt out with
 * `data-lowdata-keep`; nothing in the application needs to today, because every image on the
 * matchday route is a decorative crest already marked `aria-hidden="true"` with an empty `alt`.
 *
 * WHAT IT DOES NOT CLAIM. Nothing here caches anything, and turning it on does not make the site
 * work offline. Every page still reads over the network, and the freshness block keeps saying
 * exactly what it said before about how old the stored data behind it is. A reading mode that
 * quietly changed how current the numbers looked would be a worse defect than the bytes it saved.
 */

/** Where the reader's choice is kept. Versioned so a future change of meaning cannot be misread. */
const STORAGE_KEY = 'sp.lowData.v1'

/** Set on <html> so tests and stylesheets can see the mode without reaching into React. */
const ROOT_ATTRIBUTE = 'data-low-data'

/** Marks an image whose src this mode is holding back, and where it was put. */
const WITHHELD_ATTRIBUTE = 'data-lowdata-withheld'
const STASHED_ATTRIBUTE = 'data-lowdata-src'

/** An image that must load even in text-only mode. Nothing uses it yet; the escape hatch is real. */
const KEEP_ATTRIBUTE = 'data-lowdata-keep'

// --------------------------------------------------------------------------- stored preference

function readStoredPreference(): boolean {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === 'on'
  } catch {
    // Private mode, disabled storage, a locked-down browser: the mode is simply off.
    return false
  }
}

function writeStoredPreference(on: boolean): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, on ? 'on' : 'off')
  } catch {
    // The choice still applies to this page; it just will not survive a reload. Better than
    // throwing inside a click handler.
  }
}

// --------------------------------------------------------------------------- the image guard

let guardInstalled = false
let modeIsOn = false
let originalSrcDescriptor: PropertyDescriptor | undefined

function shouldWithhold(image: HTMLImageElement): boolean {
  return modeIsOn && !image.hasAttribute(KEEP_ATTRIBUTE)
}

/** Park a URL where the mode can give it back, and make sure the element is not asking for it. */
function stash(image: HTMLImageElement, url: string): void {
  Element.prototype.setAttribute.call(image, STASHED_ATTRIBUTE, url)
  Element.prototype.setAttribute.call(image, WITHHELD_ATTRIBUTE, '')
  if (image.hasAttribute('src')) image.removeAttribute('src')
}

function installGuard(): void {
  if (guardInstalled || typeof HTMLImageElement === 'undefined') return
  const prototype = HTMLImageElement.prototype
  const descriptor = Object.getOwnPropertyDescriptor(prototype, 'src')
  const read = descriptor?.get
  const write = descriptor?.set
  if (!descriptor || !read || !write) return

  originalSrcDescriptor = descriptor
  Object.defineProperty(prototype, 'src', {
    configurable: true,
    enumerable: descriptor.enumerable,
    get(this: HTMLImageElement): string {
      return read.call(this) as string
    },
    set(this: HTMLImageElement, value: string) {
      if (shouldWithhold(this)) {
        stash(this, value)
        return
      }
      write.call(this, value)
    },
  })

  // React assigns `src` with setAttribute, not with the property, so both doors need the same
  // guard. Shadowing it here leaves every other element type untouched.
  prototype.setAttribute = function (this: HTMLImageElement, name: string, value: string): void {
    if (name.toLowerCase() === 'src' && shouldWithhold(this)) {
      stash(this, value)
      return
    }
    Element.prototype.setAttribute.call(this, name, value)
  }

  guardInstalled = true
}

function removeGuard(): void {
  if (!guardInstalled) return
  if (originalSrcDescriptor) {
    Object.defineProperty(HTMLImageElement.prototype, 'src', originalSrcDescriptor)
  }
  // Deleting the shadow restores Element.prototype.setAttribute by inheritance.
  Reflect.deleteProperty(HTMLImageElement.prototype, 'setAttribute')
  guardInstalled = false
}

/** Bring images already on the page into line with the mode, in both directions. */
function reconcileExistingImages(on: boolean): void {
  if (typeof document === 'undefined') return
  if (on) {
    for (const image of Array.from(document.images)) {
      if (image.hasAttribute(KEEP_ATTRIBUTE) || image.hasAttribute(WITHHELD_ATTRIBUTE)) continue
      const current = image.getAttribute('src')
      if (current) stash(image, current)
    }
    return
  }
  const held = document.querySelectorAll<HTMLImageElement>(`img[${WITHHELD_ATTRIBUTE}]`)
  for (const image of Array.from(held)) {
    const url = image.getAttribute(STASHED_ATTRIBUTE)
    image.removeAttribute(WITHHELD_ATTRIBUTE)
    image.removeAttribute(STASHED_ATTRIBUTE)
    if (url) image.setAttribute('src', url)
  }
}

function applyMode(on: boolean): void {
  modeIsOn = on
  if (on) installGuard()
  if (typeof document !== 'undefined') {
    document.documentElement.setAttribute(ROOT_ATTRIBUTE, on ? 'on' : 'off')
  }
  reconcileExistingImages(on)
  if (!on) removeGuard()
}

/**
 * Applied as this module is evaluated, which is before `ReactDOM.createRoot(...).render()` runs in
 * main.tsx. That timing is the whole point: a reader who turned the mode on last week must not pay
 * for a screen of crests before a React effect gets a chance to stop them.
 */
const initiallyOn = typeof window === 'undefined' ? false : readStoredPreference()
if (typeof window !== 'undefined') applyMode(initiallyOn)

/** Withheld images collapse rather than leave a gap where a crest used to be. */
const LOW_DATA_CSS = `
img[${WITHHELD_ATTRIBUTE}] { display: none !important; }
`

// --------------------------------------------------------------------------- context

export interface LowDataValue {
  /** True when the reader has asked for text only. */
  enabled: boolean
  /** Turn the mode on or off. Takes effect immediately and is remembered. */
  setEnabled: (on: boolean) => void
}

const LowDataContext = createContext<LowDataValue>({ enabled: false, setEnabled: () => undefined })

export const LowDataProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [enabled, setEnabledState] = useState<boolean>(initiallyOn)

  const setEnabled = useCallback((on: boolean) => {
    applyMode(on)
    writeStoredPreference(on)
    setEnabledState(on)
  }, [])

  const value = useMemo<LowDataValue>(() => ({ enabled, setEnabled }), [enabled, setEnabled])

  return (
    <LowDataContext.Provider value={value}>
      <style>{LOW_DATA_CSS}</style>
      {children}
    </LowDataContext.Provider>
  )
}

export interface LowDataToggleProps {
  /**
   * `menu` is the full row, with the sentence that says what the mode does and what it does not.
   * `bar` is the compact form for the wide header, where the sentence is the accessible name.
   */
  variant?: 'menu' | 'bar'
  className?: string
}

/**
 * The control itself.
 *
 * It is a switch, it says which way it is set, and it never says anything about how much a reader
 * will save: that number depends on the day's fixtures and on their connection, and this
 * application is in no position to state it. What it can state truthfully is what it stops doing.
 */
export const LowDataToggle: React.FC<LowDataToggleProps> = ({ variant = 'menu', className }) => {
  const { enabled, setEnabled } = useContext(LowDataContext)
  const explanationId = useId()
  const state = enabled ? 'On' : 'Off'

  if (variant === 'bar') {
    return (
      <button
        type="button"
        role="switch"
        aria-checked={enabled}
        aria-label={`Text-only mode, ${state}. Crests and other images are not downloaded.`}
        data-testid="low-data-toggle-bar"
        onClick={() => setEnabled(!enabled)}
        className={clsx(
          // `hidden xl:flex` lives here rather than at the call site because it is a fact about
          // this variant: it is 126px wide, and the header row it belongs to was measured with
          // 32px to spare at 1024. See the breakpoint note in components/layout/Header.tsx.
          'focus-ring hidden shrink-0 items-center gap-2 whitespace-nowrap rounded-lg px-3 py-2 text-sm font-medium transition-colors xl:flex',
          enabled
            ? 'bg-primary-900 text-primary-200 hover:bg-primary-800'
            : 'text-secondary-300 hover:bg-dark-800 hover:text-white',
          className,
        )}
      >
        <span aria-hidden="true">Text-only</span>
        <span
          aria-hidden="true"
          className={clsx(
            'rounded px-1.5 py-0.5 text-xs font-semibold',
            enabled ? 'bg-primary-700 text-white' : 'bg-dark-700 text-secondary-300',
          )}
        >
          {state}
        </span>
      </button>
    )
  }

  return (
    <div className={clsx('px-3 py-2', className)}>
      <button
        type="button"
        role="switch"
        aria-checked={enabled}
        aria-describedby={explanationId}
        data-testid="low-data-toggle-menu"
        onClick={() => setEnabled(!enabled)}
        className="focus-ring tap-target-row flex w-full items-center justify-between gap-3 rounded-lg text-base font-medium text-secondary-300 transition-colors hover:text-white"
      >
        <span>Text-only mode</span>
        <span
          aria-hidden="true"
          className={clsx(
            'rounded px-2 py-0.5 text-xs font-semibold',
            enabled ? 'bg-primary-700 text-white' : 'bg-dark-700 text-secondary-300',
          )}
        >
          {state}
        </span>
      </button>
      <p id={explanationId} className="mt-1 text-xs text-secondary-400">
        Crests and other images are not downloaded. Pages still load over the network; nothing is
        stored for reading offline, and how old the data is does not change.
      </p>
    </div>
  )
}

export default LowDataContext
