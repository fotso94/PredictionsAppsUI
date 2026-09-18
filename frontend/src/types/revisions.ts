/**
 * Preserved earlier versions of a published expert prediction.
 *
 * Editing a published prediction rewrites the live row, so without these the numbers a reader saw
 * before the correction would be gone. Revisions are APPEND-ONLY: revision 1 is always the
 * original, and a second correction adds a second row rather than replacing the first. Everything
 * here is a record of what was published and when, never a re-computation of it.
 *
 * Carried on GET /api/v1/matches/{id} as `expert_prediction_revisions` (the list payload does not
 * carry them). An empty list means the prediction has never been edited — it does NOT mean the
 * history is unknown.
 */

/**
 * One earlier published version, in full.
 *
 * `values` is the whole published view as it stood before the edit, not a diff, so it can be read
 * back without reconstructing it from `changes_summary`.
 */
export interface ExpertPredictionRevisionValues {
  home_win_prob: number | null;
  draw_prob: number | null;
  away_win_prob: number | null;
  confidence_score: number | null;
  btts_yes_prob: number | null;
  btts_no_prob: number | null;
  btts_confidence: number | null;
  total_goals_over_25_prob: number | null;
  total_goals_under_25_prob: number | null;
  total_goals_over_35_prob: number | null;
  total_goals_under_35_prob: number | null;
  total_goals_confidence: number | null;
  reasoning: string | null;
  key_factors: unknown;
  status: string | null;
  /** The publication time THIS version carried, not the current one. */
  published_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface ExpertPredictionRevision {
  id: string;
  prediction_id: string;
  /** 1-based, oldest first. Revision 1 is the original published version. */
  revision: number;
  /** When this version stopped being the published one (UTC ISO-8601). */
  replaced_at: string | null;
  edited_by: string | null;
  /**
   * The backend's own description of what changed, e.g.
   * "home_win_prob 0.33 -> 0.51; reasoning changed". Empty string when nothing of substance did.
   */
  changes_summary: string | null;
  /**
   * NULL when the kickoff time is unknown — a `false` would assert "edited before kickoff", which
   * is a claim we cannot make without a kickoff to compare against.
   */
  edited_after_kickoff: boolean | null;
  /** Convenience copy of `values.published_at`. */
  published_at: string | null;
  values: ExpertPredictionRevisionValues;
}
