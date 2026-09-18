/**
 * Whether the viewer has asked their system to reduce motion.
 *
 * index.css already neutralises CSS animations and transitions under
 * `@media (prefers-reduced-motion: reduce)`. This hook is for the cases CSS cannot reach: a
 * JavaScript-driven animation, an auto-scrolling strip, a `scrollIntoView` that should jump rather
 * than glide. Reach for the CSS first; use this only when there is nothing for CSS to switch off.
 *
 * Returns false during server-side or test environments with no `matchMedia`, which is the safe
 * default: it means "no preference expressed", not "motion is wanted".
 */

import { useEffect, useState } from 'react';

const QUERY = '(prefers-reduced-motion: reduce)';

function currentPreference(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false;
  return window.matchMedia(QUERY).matches;
}

export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState<boolean>(currentPreference);

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;
    const media = window.matchMedia(QUERY);
    const onChange = (event: MediaQueryListEvent) => setReduced(event.matches);
    // The preference can change while the page is open (a system setting, not a page setting).
    media.addEventListener('change', onChange);
    setReduced(media.matches);
    return () => media.removeEventListener('change', onChange);
  }, []);

  return reduced;
}

export default useReducedMotion;
