/**
 * Error narrowing helpers.
 *
 * `catch (err: any)` hides the shape of what was thrown and lets `err.response.data.detail`
 * blow up at runtime. These helpers take `unknown` and read an axios error safely, so callers
 * never have to widen the catch binding.
 */

import axios from 'axios';
import { t } from '@/i18n';

/** FastAPI's validation errors arrive as a list of objects; its HTTPExceptions as a string or object. */
interface ApiErrorDetail {
  message?: unknown;
  errors?: unknown;
  msg?: unknown;
}

function detailToMessage(detail: unknown): string | null {
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const parts = detail
      .map(entry => (typeof entry === 'string' ? entry : ((entry as ApiErrorDetail)?.msg ?? (entry as ApiErrorDetail)?.message)))
      .filter((part): part is string => typeof part === 'string' && part.trim().length > 0);
    return parts.length > 0 ? parts.join(' — ') : null;
  }
  if (detail && typeof detail === 'object') {
    const obj = detail as ApiErrorDetail;
    const message = typeof obj.message === 'string' ? obj.message : null;
    const errors = Array.isArray(obj.errors)
      ? obj.errors.filter((e): e is string => typeof e === 'string')
      : [];
    const joined = [message, ...errors].filter(Boolean).join(' — ');
    return joined || null;
  }
  return null;
}

/**
 * Best human-readable message for anything a request can throw.
 *
 * Order: the API's own `detail`, then the API's `message`, then the transport error message,
 * then the caller's fallback. Never invents a reason the server did not give.
 */
export function getErrorMessage(err: unknown, fallback: string): string {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data as { detail?: unknown; message?: unknown } | undefined;
    const fromDetail = detailToMessage(data?.detail);
    if (fromDetail) return fromDetail;
    if (typeof data?.message === 'string' && data.message.trim()) return data.message;
    // Only OUR two sentences are translated. `data.detail`, `data.message` and `err.message`
    // above are the server's own words and the transport's, and are passed through unchanged in
    // every language — a paraphrase of somebody else's error is a different error.
    if (err.response?.status === 503) return t('error.serviceUnavailable');
    if (err.code === 'ECONNABORTED') return t('error.timedOut');
    if (err.message) return err.message;
    return fallback;
  }
  if (err instanceof Error && err.message) return err.message;
  if (typeof err === 'string' && err.trim()) return err;
  return fallback;
}

/** HTTP status of a failed request, when the failure reached a response at all. */
export function getErrorStatus(err: unknown): number | null {
  if (axios.isAxiosError(err)) return err.response?.status ?? null;
  return null;
}
