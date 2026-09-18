/**
 * Match Filtering Utilities
 * 
 * Provides reusable functions for filtering matches based on status
 * and detecting live matches across the application.
 */

import { Match, MatchStatus } from '@/types';
import { localDateString } from '@/services/match-data-source';

/**
 * Check if a match is currently live
 * Live statuses: 'live', 'halftime'
 */
export function isMatchLive(match: Match): boolean {
  return match.status === 'live' || match.status === 'halftime';
}

/**
 * Check if a match is scheduled (not started yet)
 * Scheduled statuses: 'scheduled'
 */
export function isMatchScheduled(match: Match): boolean {
  return match.status === 'scheduled';
}

/**
 * Check if a match is finished
 * Finished statuses: 'finished'
 */
export function isMatchFinished(match: Match): boolean {
  return match.status === 'finished';
}

/**
 * Check if a match is postponed or cancelled
 */
export function isMatchPostponedOrCancelled(match: Match): boolean {
  return match.status === 'postponed' || match.status === 'cancelled';
}

/**
 * Filter matches to show only live and scheduled matches
 * Excludes: finished, postponed, cancelled
 * 
 * Use this for:
 * - Expert Match Selection Page
 * - Today Predictions Page
 * - Home Page "Today's Matches" section
 */
export function filterLiveAndScheduledMatches(matches: Match[]): Match[] {
  return matches.filter(match => 
    isMatchLive(match) || isMatchScheduled(match)
  );
}

/**
 * Filter matches to show only live, scheduled today, and scheduled tomorrow
 * Excludes: finished, postponed, cancelled
 * 
 * Use this for:
 * - Home Page "Featured Predictions" section
 */
export function filterLiveAndUpcomingMatches(matches: Match[], includeTomorrow: boolean = false): Match[] {
  const today = localDateString(0);
  const tomorrowStr = localDateString(1);

  return matches.filter(match => {
    // Exclude finished, postponed, cancelled
    if (isMatchFinished(match) || isMatchPostponedOrCancelled(match)) {
      return false;
    }

    // Include live matches
    if (isMatchLive(match)) {
      return true;
    }

    // Include scheduled matches for today
    if (match.date === today && isMatchScheduled(match)) {
      return true;
    }

    // Include scheduled matches for tomorrow if requested
    if (includeTomorrow && match.date === tomorrowStr && isMatchScheduled(match)) {
      return true;
    }

    return false;
  });
}

/**
 * Get live score display text for a match
 * Returns null if match is not live or doesn't have scores
 */
export function getLiveScoreText(match: Match): string | null {
  if (!isMatchLive(match) || !match.result) {
    return null;
  }

  const homeScore = match.result.homeScore ?? 0;
  const awayScore = match.result.awayScore ?? 0;

  return `${homeScore} - ${awayScore}`;
}

/**
 * Get match status display text
 * Returns user-friendly status text
 */
export function getMatchStatusText(match: Match): string {
  switch (match.status) {
    case 'live':
      return 'LIVE';
    case 'halftime':
      return 'HT';
    case 'scheduled':
      return 'Scheduled';
    case 'finished':
      return 'Finished';
    case 'postponed':
      return 'Postponed';
    case 'cancelled':
      return 'Cancelled';
    default:
      return 'Unknown';
  }
}

/**
 * Get CSS classes for match status badge
 */
export function getMatchStatusBadgeClasses(match: Match): string {
  const baseClasses = 'text-xs px-2 py-1 rounded font-medium';
  
  if (isMatchLive(match)) {
    return `${baseClasses} bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200 animate-pulse`;
  }
  
  if (isMatchScheduled(match)) {
    return `${baseClasses} bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200`;
  }
  
  if (isMatchFinished(match)) {
    return `${baseClasses} bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-300`;
  }
  
  if (match.status === 'postponed') {
    return `${baseClasses} bg-yellow-100 dark:bg-yellow-900 text-yellow-800 dark:text-yellow-200`;
  }
  
  if (match.status === 'cancelled') {
    return `${baseClasses} bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-200`;
  }
  
  return `${baseClasses} bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-300`;
}

/**
 * Sort matches by status priority (live first, then scheduled, then finished)
 */
export function sortMatchesByStatus(matches: Match[]): Match[] {
  return [...matches].sort((a, b) => {
    // Priority: live > halftime > scheduled > finished > postponed > cancelled
    const statusPriority: Record<MatchStatus, number> = {
      'live': 1,
      'halftime': 2,
      'scheduled': 3,
      'finished': 4,
      'postponed': 5,
      'cancelled': 6,
    };

    const aPriority = statusPriority[a.status] || 999;
    const bPriority = statusPriority[b.status] || 999;

    return aPriority - bPriority;
  });
}

