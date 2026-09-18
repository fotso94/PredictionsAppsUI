/**
 * The measured record: `GET /api/v1/performance/sources`.
 *
 * Read-only, stored-data-only. The endpoint scores nothing and calls no provider — it reads score
 * rows that settlement already wrote — so this costs no request allowance and is safe to call on
 * a public page.
 *
 * WHY THE RETURN TYPE DISTINGUISHES THREE OUTCOMES. "We could not reach the endpoint", "the
 * endpoint answered and nothing has been scored" and "the endpoint answered with figures" are
 * three different statements, and an interface that collapses the first two shows "nothing has
 * been measured" whenever the network hiccups — which is a claim about the data made out of a
 * failed request. So a failure returns `{ state: 'failed', error }` and the caller says so.
 *
 * Nothing here computes, rounds up, renormalises or fills in a figure. The percentages the UI
 * prints are the endpoint's own ratios multiplied by 100 for display; every one of them is
 * refused by the backend below its minimum sample and arrives as null with a reason instead.
 */

import apiClient from './api-client';
import type { MeasuredPerformance } from '@/types';
import { describeError } from './backend-match-data.service';

const API = '/api/v1';

/**
 * How long a fetched measurement is reused for.
 *
 * Settlement runs far less often than a page is opened and the endpoint touches only stored rows,
 * so a short cache exists purely to stop one navigation session issuing the same query repeatedly.
 */
const CACHE_TTL_MS = 60 * 1000;

/** The endpoint answered. `data` may legitimately contain no measured source at all. */
export interface PerformanceLoaded {
  state: 'loaded';
  data: MeasuredPerformance;
}

/** The endpoint could not be reached. This is NOT "nothing has been measured". */
export interface PerformanceFailed {
  state: 'failed';
  /** The backend's own message where it gave one, for the reader. */
  error: string;
}

export type PerformanceResult = PerformanceLoaded | PerformanceFailed;

export interface PerformanceQuery {
  /** First kickoff date to include, `YYYY-MM-DD`. Backend default: 90 days back. */
  start?: string;
  /** Last kickoff date to include, `YYYY-MM-DD`. Backend default: today. */
  end?: string;
}

class PerformanceService {
  private cache = new Map<string, { value: PerformanceLoaded; at: number }>();

  /**
   * The measured record over a window of kickoffs.
   *
   * Only a successful answer is cached: a failure must be retried rather than remembered, or a
   * single blip would keep the page saying "unavailable" for the rest of the minute.
   */
  async getMeasuredPerformance(query: PerformanceQuery = {}): Promise<PerformanceResult> {
    const params = new URLSearchParams();
    if (query.start) params.set('start', query.start);
    if (query.end) params.set('end', query.end);
    const suffix = params.toString();
    const key = suffix || 'default';

    const cached = this.cache.get(key);
    if (cached && Date.now() - cached.at < CACHE_TTL_MS) return cached.value;

    try {
      const { data } = await apiClient.get<MeasuredPerformance>(
        `${API}/performance/sources${suffix ? `?${suffix}` : ''}`,
      );
      const value: PerformanceLoaded = { state: 'loaded', data };
      this.cache.set(key, { value, at: Date.now() });
      return value;
    } catch (error) {
      return { state: 'failed', error: describeError(error) };
    }
  }

  /** Drop everything remembered, so the next read goes to the backend. */
  clearCache(): void {
    this.cache.clear();
  }
}

export const performanceService = new PerformanceService();
export default performanceService;
