/**
 * English, composed — the source catalogue and the fallback, assembled from its areas.
 *
 * NOTHING IS DECLARED HERE. Every key lives in the area it belongs to (./core.en.ts,
 * ./auth.en.ts, ./expert.en.ts, ./reader.en.ts); this file exists so that the rest of the
 * application, `MessageKey` and the browser suite all keep importing one catalogue from one
 * path. See ./types.ts for why the areas exist and where to add a key.
 *
 * ORDER IS NOT MEANING. A later spread would silently win a key an earlier one already defined,
 * which is exactly the collision three concurrent authors could produce without noticing — so
 * `the four catalogue areas claim no key twice` in frontend/e2e/mocked/localisation.spec.ts
 * fails on a duplicate rather than letting spread order decide it.
 */

import core from './core.en'
import auth from './auth.en'
import expert from './expert.en'
import reader from './reader.en'

const en = { ...core, ...auth, ...expert, ...reader }

export default en
