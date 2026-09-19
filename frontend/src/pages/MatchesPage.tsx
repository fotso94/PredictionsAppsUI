import React from 'react'
import { Helmet } from 'react-helmet-async'
import { useSearchParams } from 'react-router-dom'
import MatchdayWorkspace from '@/components/matches/MatchdayWorkspace'
import { readWorkspaceState } from '@/components/matches/workspaceState'
import { localDateString } from '@/services/match-data-source'
import { formatIsoDate } from '@/i18n'
import { useT } from '@/i18n/react'

/**
 * The matches-first workspace, on its own route and on the two date routes that predate it.
 *
 * ONE PAGE, THREE URLS. `/predictions/today` and `/predictions/tomorrow` are linked from all over
 * the site and asserted by the browser suite, so they keep working exactly as before — each simply
 * resolves to this workspace with its own day preselected. `/matches` is the general form and takes
 * `?date=`. All three are ordinary URLs: they can be bookmarked, shared and reached with the back
 * button, and no fixture is ever locked inside a modal.
 *
 * The heading here is the workspace's own, so a reader lands on "Today's matches" and the fixtures,
 * not on a hero they have to scroll past.
 */

export interface MatchesPageProps {
  /** The day this route names, if any. Absent on /matches, where the URL carries the date. */
  preset?: 'today' | 'tomorrow'
}

/*
 * The day in the document title and the meta description.
 *
 * This was `Intl.DateTimeFormat('en-GB', …)` — English, hard-coded, built once — over a date
 * parsed in the device's zone. Both are the reader's own now: `formatIsoDate` anchors the
 * calendar date at midday in their chosen zone and spells it out in their language.
 */
function formatDay(date: string): string {
  return formatIsoDate(date)
}

const MatchesPage: React.FC<MatchesPageProps> = ({ preset }) => {
  const t = useT()
  const [searchParams] = useSearchParams()
  const defaultDate = localDateString(preset === 'tomorrow' ? 1 : 0)
  // Read here only so the document title names the day actually on screen; the workspace reads the
  // same parameters for itself and stays the single owner of the state.
  const { date } = readWorkspaceState(searchParams, defaultDate)

  const title = t(preset === 'today' ? 'matchday.title.today'
    : preset === 'tomorrow' ? 'matchday.title.tomorrow'
      : 'matchday.title.generic')

  return (
    <>
      <Helmet>
        <title>{`${title} — ${formatDay(date)}`}</title>
        <meta
          name="description"
          content={t('matchday.documentDescription', { date: formatDay(date) })}
        />
      </Helmet>

      <div className="mx-auto max-w-5xl px-3 py-4 sm:px-6 sm:py-6 lg:px-8">
        <MatchdayWorkspace
          defaultDate={defaultDate}
          presetRoute={preset !== undefined}
          headingLevel={1}
          title={title}
          /*
            What the list IS. Three sentences, all of them facts about how this page renders
            things, which is why they can be written here as a constant.

            A fourth used to follow them: "Nothing on this page has been scored against a result,
            so no accuracy is claimed for any of it." That one is not a fact about the page, it is
            a fact about the data, and it kept being served on days when four provider forecasts
            had in fact been scored. The claim is still worth making — on a page of fixtures that
            have not kicked off it is the most useful thing the footnote says — so it has not been
            deleted. It has moved into the workspace, which is the only part of this that can see
            which fixtures were actually listed, and is computed there from them.
          */
          footnote={t('matchday.footnote')}
        />
      </div>
    </>
  )
}

export default MatchesPage
