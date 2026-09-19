import React, { useCallback, useEffect, useId, useMemo, useState } from 'react'
import clsx from 'clsx'
import {
  type Language, type ZoneId, LANGUAGES, LANGUAGE_ENDONYM, currentLanguage, currentZone,
  languageFellBack, onLocaleChange, preferencesAreDurable, setLanguage as applyLanguage,
  setZone as applyZone, t as translate, zoneLabel,
} from './index'
import { LocaleContext, type LocaleValue, useLocale } from './react'
import { OFFERED_ZONES, deviceZone, offsetLabel, zoneCity, zoneOption } from './zones'

/**
 * The provider, and the two controls that set what it holds.
 *
 * Components only, because `react-refresh/only-export-components` and `--max-warnings 0` between
 * them make a mixed module a build failure. The state, the storage and the formatting live in
 * ./index.ts and the context object in ./react.ts.
 */

/**
 * The module's language and zone, snapshotted so a change actually repaints.
 *
 * `t` is a stable function reading a module-level catalogue, so nothing about its identity
 * changes when the catalogue does, and React would happily leave the old text on screen. Copying
 * the state into `useState` and rebuilding the context value is what makes the change visible —
 * including inside the plain `.ts` helpers that produce half the sentences on this site, because
 * they are called again during the same render.
 */
const snapshot = () => ({
  language: currentLanguage(),
  zone: currentZone(),
  fellBack: languageFellBack(),
})

export const LocaleProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [state, setState] = useState(snapshot)

  useEffect(() => onLocaleChange(() => setState(snapshot())), [])

  const setLanguage = useCallback((next: Language) => applyLanguage(next), [])
  const setZone = useCallback((next: ZoneId) => applyZone(next), [])

  const value = useMemo<LocaleValue>(() => ({
    ...state,
    setLanguage,
    setZone,
    // Stable by design: `t` reads the module-level catalogue, so there is one lookup function for
    // components and for the plain `.ts` helpers that produce half the sentences on the page. The
    // state change above is what re-runs both.
    t: translate,
  }), [state, setLanguage, setZone])

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>
}

/**
 * The language control.
 *
 * TWO BUTTONS, NOT A DROPDOWN. There are two languages, both are named in their own language, and
 * a reader who cannot read the interface can still see "Français" and press it — which is the one
 * job this control has. A `<select>` hides the choice behind an interaction and, on a phone,
 * behind a native picker whose own labels are in the device's language, not the page's.
 *
 * Each button is a radio in a group rather than a toggle, so a screen reader announces "1 of 2"
 * and which one is set, and arrow keys move between them.
 */
const LanguageChoice: React.FC<{ compact?: boolean }> = ({ compact = false }) => {
  const { language, setLanguage, t } = useLocale()
  const labelId = useId()

  return (
    <div>
      <p id={labelId} className="text-sm font-medium text-white">{t('settings.language')}</p>
      <div role="radiogroup" aria-labelledby={labelId} className="mt-1.5 flex flex-wrap gap-1.5">
        {LANGUAGES.map(code => {
          const selected = language === code
          return (
            <button
              key={code}
              type="button"
              role="radio"
              aria-checked={selected}
              // `lang` on the button itself: "Français" is French text sitting inside an English
              // page, and without this a screen reader reads it with an English voice.
              lang={code}
              onClick={() => { void setLanguage(code) }}
              data-testid={`language-choice-${code}`}
              className={clsx(
                'tap-target-row focus-ring rounded-lg border px-3 py-2 text-sm font-medium transition-colors',
                selected
                  ? 'border-primary-500 bg-primary-900 text-primary-100'
                  : 'border-dark-600 bg-dark-800 text-secondary-200 hover:bg-dark-700 hover:text-white',
              )}
            >
              {LANGUAGE_ENDONYM[code]}
            </button>
          )
        })}
      </div>
      {!compact && (
        <p className="mt-1.5 text-xs text-secondary-400">{t('settings.languageHelp')}</p>
      )}
    </div>
  )
}

/**
 * The time-zone control.
 *
 * A native `<select>`, so the platform's own keyboard handling and phone picker apply, and so a
 * list of seventeen entries costs one tap instead of seventeen tap targets on a 360px screen.
 *
 * THE DEVICE'S ZONE IS ALWAYS THE FIRST OPTION, whether or not it is on the offered list. A
 * reader in a city this list does not name must still be able to get back to a zone that is right
 * for them, and the one zone we can be sure is a candidate is the one their clock is already set
 * to. It is labelled as the device's, not as theirs, because those are different claims.
 *
 * EVERY OPTION CARRIES TODAY'S OFFSET, and the ones whose clocks move say so. "UTC+01:00" beside
 * Douala is a fact all year; beside Paris it is a fact about today, and a reader choosing a zone
 * in March deserves to know which of the two they are looking at.
 */
const TimeZoneChoice: React.FC = () => {
  const { zone, setZone, t } = useLocale()
  const selectId = useId()
  const device = deviceZone()
  const now = new Date()

  const options = useMemo(() => {
    const listed = OFFERED_ZONES.map(option => option.id)
    return listed.includes(device) ? OFFERED_ZONES : [
      { id: device, city: zoneCity(device), observesDaylightSaving: false },
      ...OFFERED_ZONES,
    ]
  }, [device])

  return (
    /*
     * `min-w-0` is load-bearing on both of these, and it was a measurement that put it there.
     *
     * A <select> sizes itself to its LONGEST OPTION, and "Use this device's zone (New York,
     * Toronto) · UTC-04:00 · clocks change during the year" is a long option. Inside a grid item,
     * whose default `min-width: auto` refuses to shrink below content, that min-content width
     * becomes the footer's, and the footer's becomes the document's: measured at 200% text zoom,
     * 121px of sideways page scroll at every width, in both languages. `min-w-0` lets the box
     * shrink and `truncate` on the control keeps the chosen option readable rather than clipped.
     */
    <div className="min-w-0">
      <label htmlFor={selectId} className="text-sm font-medium text-white">
        {t('settings.timeZone')}
      </label>
      <select
        id={selectId}
        value={zone}
        onChange={event => setZone(event.target.value)}
        data-testid="time-zone-choice"
        className="focus-ring mt-1.5 block w-full min-w-0 max-w-sm truncate rounded-lg border border-dark-600 bg-dark-800 px-3 py-2 text-sm text-secondary-100"
      >
        {options.map(option => (
          <option key={option.id} value={option.id}>
            {option.id === device
              ? t('settings.useDeviceZone', { zone: option.city })
              : option.city}
            {' · '}
            {offsetLabel(option.id, now)}
            {option.observesDaylightSaving ? ` · ${t('settings.zoneObservesDst')}` : ''}
          </option>
        ))}
      </select>
      <p className="mt-1.5 text-xs text-secondary-400" data-testid="time-zone-current">
        {t('settings.timeZoneNow', { zone: zoneLabel(now) })}
      </p>
      <p className="mt-1 text-xs text-secondary-400">{t('settings.timeZoneHelp')}</p>
    </div>
  )
}

export interface RegionSettingsProps {
  /** `menu` is the compact form inside the header panel; `panel` is the footer block. */
  variant?: 'menu' | 'panel'
  className?: string
}

/**
 * Language and time zone together, wherever the reader finds them.
 *
 * THEY SIT SIDE BY SIDE AND THE COPY SAYS THEY ARE SEPARATE. Putting them in one block is
 * convenient; leaving the reader to infer that picking French moves them to Paris is not. The
 * sentence under them states outright that the two choices are independent of one another and
 * that no country is stored or guessed, because that is the assumption this arrangement would
 * otherwise invite.
 *
 * It is NOT in the header bar. The bar's widths were measured control by control by the package
 * before this one — a 126px switch at `xl`, with 32px of slack at 1024 — and a language control
 * on it would spend that measurement without re-doing it. So the full block lives in the footer,
 * which every page in the shell renders and which has room at every width, and the header's menu
 * panel carries the same block for the widths where the panel is reachable.
 */
export const RegionSettings: React.FC<RegionSettingsProps> = ({ variant = 'panel', className }) => {
  const { t, fellBack } = useLocale()
  const [durable, setDurable] = useState(true)

  // Read in an effect, not during render: it writes to localStorage to find out, and a render
  // must not have side effects.
  useEffect(() => { setDurable(preferencesAreDurable()) }, [])

  return (
    <section
      className={clsx('min-w-0', variant === 'menu' ? 'space-y-3 px-3 py-2' : 'space-y-3', className)}
      aria-label={t('settings.openLabel')}
      data-testid="region-settings"
    >
      {variant === 'panel' && (
        <h3 className="font-semibold text-white">{t('settings.title')}</h3>
      )}
      <LanguageChoice compact={variant === 'menu'} />
      <TimeZoneChoice />
      {fellBack && (
        <p role="status" className="text-xs text-warning-200" data-testid="language-fell-back">
          {t('settings.languageFellBack')}
        </p>
      )}
      {!durable && (
        <p className="text-xs text-warning-200" data-testid="settings-not-durable">
          {t('settings.notDurable')}
        </p>
      )}
      <p className="text-xs text-secondary-400" data-testid="settings-independent">
        {t('settings.independent')}
      </p>
    </section>
  )
}

/** The zone as the interface names it, for a caller that wants only the string. */
export const ZoneName: React.FC<{ className?: string }> = ({ className }) => {
  const { zone } = useLocale()
  const option = zoneOption(zone)
  return <span className={className}>{option ? option.city : zoneCity(zone)}</span>
}

export default LocaleProvider
