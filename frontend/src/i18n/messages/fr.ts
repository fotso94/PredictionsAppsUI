/**
 * Français, composed — the chunk a French reader downloads, assembled from its areas.
 *
 * NOTHING IS DECLARED HERE. Every key lives in the area it belongs to (./core.fr.ts,
 * ./auth.fr.ts, ./expert.fr.ts, ./reader.fr.ts), and each of those is typed from its English
 * counterpart, so a missing translation is a compile error in the area file that is missing it.
 *
 * The `Catalog` annotation below is the second half of that guarantee: it catches an area that
 * exists in English and was never added to this composition, which per-area typing cannot see.
 *
 * This file and everything it imports are still one lazy chunk — src/i18n/index.ts reaches it
 * through `import('./messages/fr')` — so an English reader downloads none of it.
 */

import type { Catalog } from './types'
import core from './core.fr'
import auth from './auth.fr'
import expert from './expert.fr'
import reader from './reader.fr'

const fr: Catalog = { ...core, ...auth, ...expert, ...reader }

export default fr
