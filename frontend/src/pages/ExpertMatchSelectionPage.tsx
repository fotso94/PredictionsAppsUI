/**
 * Choose the fixture to write about.
 *
 * This page used to render two long lists — "Today's Matches" and "Tomorrow's Matches" — of tall
 * three-column cards. Each card repeated the venue, the round, the internal UUID and the provider's
 * fixture id, and the three-column team grid did not collapse: a 23-fixture day pushed the page 11
 * CSS pixels wider than a 390px phone, so the whole thing scrolled sideways.
 *
 * It is now one list with filters, and the football context an expert actually chooses on — when it
 * kicks off, which competition, who is playing, and whether anybody has published on it yet. The
 * identifiers are gone from the card body; the composer keeps them behind an advanced disclosure
 * for the rare case where somebody has one to paste.
 *
 * Reads are stored-data-only, so filtering and paging between days spends no provider allowance.
 */

import React from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowLeftIcon } from '@heroicons/react/24/outline'
import { Match } from '@/types'
import FixturePicker from '@/components/expert/FixturePicker'

const ExpertMatchSelectionPage: React.FC = () => {
  const navigate = useNavigate()

  const openComposer = (match: Match) => {
    navigate(`/expert/predictions/create?matchId=${encodeURIComponent(match.id)}`)
  }

  return (
    <div className="container mx-auto max-w-4xl px-4 py-8">
      <Link to="/expert/dashboard" className="focus-ring mb-4 inline-flex items-center gap-1 text-sm text-primary-300 hover:text-primary-200">
        <ArrowLeftIcon className="h-4 w-4" aria-hidden="true" />
        Back to dashboard
      </Link>

      <h1 className="text-2xl font-bold text-white sm:text-3xl">Choose a match</h1>
      <p className="mt-1 text-sm text-secondary-300">
        Pick the fixture you want to publish a view on. Your prediction goes live as soon as you press publish —
        there is no approval step and nothing to wait for.
      </p>

      <FixturePicker
        className="mt-6"
        onChoose={openComposer}
        actionLabel="Write a prediction"
        heading={<>
          <h2 className="text-sm font-semibold text-white">Fixtures</h2>
          <p className="mt-1 text-xs text-secondary-400">
            Filter by day, competition or team. Finished, postponed and cancelled fixtures are left out.
          </p>
        </>}
      />

      <div className="card mt-6 p-4">
        <h2 className="text-sm font-semibold text-white">How a prediction reaches readers</h2>
        <ol className="mt-2 list-inside list-decimal space-y-1 text-xs text-secondary-300">
          <li>Choose the fixture here.</li>
          <li>Enter your percentages — type 55 for 55%, not 0.55 — and tick only the markets you want to publish.</li>
          <li>Preview what readers will see, then publish.</li>
        </ol>
        <p className="mt-3 text-xs text-secondary-400">
          Expert predictions are shown separately from model forecasts and are never merged with them. A market you
          leave out is shown as unavailable rather than as 0%. The fixture list covers the configured competitions only.
        </p>
      </div>
    </div>
  )
}

export default ExpertMatchSelectionPage
