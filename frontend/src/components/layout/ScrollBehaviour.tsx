import React, { useEffect, useLayoutEffect, useRef } from 'react'
import { useLocation, useNavigationType } from 'react-router-dom'

/**
 * Where a page starts when you open it, and where Back puts you back.
 *
 * THE BUG THIS EXISTS TO FIX. Nothing in this application ever touched the scroll position, so a
 * single-page navigation left the document exactly where the previous page had been scrolled to.
 * Opening a team from the two links at the BOTTOM of a match page therefore landed on the team
 * page at its footer — Quick Links and the copyright block — with the team's own heading a full
 * screen above. Every deep page in the app has the same failure; the match page just makes it
 * easiest to hit, because its outgoing links are the last thing on it.
 *
 * WHY THIS IS NOT ONE LINE OF scrollTo(0, 0). Two requirements pull in opposite directions:
 * a forward move must start at the top of the new page, and Back must return the reader to the
 * list exactly where they left it — same filters, same fixture under the thumb. React Router tells
 * us which of the two happened, so each gets its own rule:
 *
 *   POP (Back or Forward)            restore the offset saved for that history entry
 *   a move to a different path       top of the new page
 *   the same path, new query string  leave the reader alone
 *
 * That third rule is the one worth spelling out. The matchday workspace writes every filter and
 * every date into the URL with `replace: true` (see MatchdayWorkspace.apply), and a replace mints
 * a fresh location key, so a reader toggling competitions generates a stream of navigations
 * without ever asking to go anywhere. Treating those as forward moves would fire the reader back
 * to the top of the list on every chip they tap, and — worse — a canonicalising replace arriving
 * just after a Back would throw away the position we had only just restored. A URL rewrite that
 * stays on the same path is the page describing itself, not the reader moving.
 *
 * WHEN THE RESTORE CAN ACTUALLY HAPPEN. Applying a saved offset once, at the instant Back fires,
 * does nothing useful: the fixtures arrive a frame or several later, and until they do the
 * document is a heading and a spinner with nothing to scroll. A restore is therefore not a single
 * jump but a short convergence. Every frame for up to RESTORE_WINDOW_MS the reader is put as close
 * to the saved offset as the page can currently reach, and it is applied exactly as soon as the
 * page is tall enough to hold it — but that is where the restore LANDS, not where it ends. See
 * A PAGE CAN BE TALL ENOUGH BEFORE IT IS FINISHED below for why those are two different moments.
 *
 * That is deliberately not "wait for the exact height or give up". A page that comes back five
 * pixels shorter than it went away — one fewer fixture on the day, a notice that has settled —
 * would strand the reader at the top under that rule, and the bottom of a page they were reading
 * the bottom of is not an arbitrary place to be. What IS arbitrary is a position picked while the
 * page is still a spinner, and converging rather than guessing once is exactly what avoids it.
 * The whole thing is abandoned the instant the reader takes over: once they have chosen a position
 * of their own, moving them is never right. HOW WE KNOW THEY HAVE, below, is the part that took
 * two goes to get right.
 *
 * A PAGE CAN BE TALL ENOUGH BEFORE IT IS FINISHED, and stopping at the first layout that could
 * hold the offset is what this component used to do. Measured on the mocked journey's filtered
 * list, walking into the last fixture and pressing Back — a list that is not held back at all,
 * answering from the stub as fast as the network layer can:
 *
 *   360x740   the reader left at 2059. Back: 1371 tall, nothing to scroll; one frame later 3404
 *             tall, which reaches 2059, so the offset was applied and the watch stopped. NINETEEN
 *             MILLISECONDS after that the document finished at 3515 — the matchday controls above
 *             the list growing from 559 to 670 as their own content arrived — and the browser's
 *             scroll anchoring, handed straight back by a restore that thought it was done,
 *             carried the reader down with the growth to 2170.
 *   390x844   the same, 1961 to 2072: the same 111px, the same one frame late.
 *   1440x900  the same growth (2271 to 2366) but the last converge happened to fall on the far
 *             side of it, so the reader landed on 1376 and stayed. The defect was not absent at
 *             1440, it was invisible there.
 *
 * 111px is a fixture and a half at 360. The reader asked for the row they were reading and got
 * the row below it, on every Back, on both phones. What makes it worse than a miss is that the
 * anchoring kept the WRONG content still: it preserved what sat at 2059 in a layout that existed
 * for one frame, which is not the layout the reader's offset was recorded against.
 *
 * So a restore is over when the offset has been applied AND the page has stopped moving under it:
 * `landed` and then RESTORE_SETTLE_MS of unchanged height. Until both hold, the watch keeps the
 * browser's anchoring held off and re-applies the offset on every frame the page changes shape.
 * This is also why the watch now starts even when the very first converge succeeds: a page that
 * is already tall enough at the instant Back fires can still be one paint from finished, and the
 * old code's early return left exactly that case with no correction and no anchoring hold.
 *
 * AND THE LIST THAT ARRIVES AFTER THE WINDOW HAS CLOSED. Measured on a Galaxy S8 (360x740) with
 * `GET /api/v1/matches` held back 4 s, walking into a fixture from the filtered list of
 * e2e/mocked/navigation-continuity.spec.ts and pressing Back: the reader left the list at 2043,
 * came back to a skeleton that could reach only 654, and was converged onto that bottom — as close
 * as that page could then reach — after which the window expired with nothing else to converge
 * onto. The rows landed a couple of seconds later, the document grew until it could reach 2691,
 * and the browser's own scroll anchoring carried the reader down with the growth to 2691: the very
 * bottom of a list they had been in the middle of, 648px — nearly a whole viewport — past where
 * they were. Giving up on the restore did not leave them where they were; it left them somewhere
 * neither they nor this component chose. The same run on WebKit at 390 ends at 2699 with the
 * reader's offset at 2037; at 1440 it ends near the top of the list instead — the same abandoned
 * restore landing in a different arbitrary place.
 *
 * So the watch has two phases, and RESTORE_WINDOW_MS now separates them rather than ending the
 * restore:
 *
 *   0 .. RESTORE_WINDOW_MS      converge every frame, as above.
 *   .. RESTORE_MAX_MS           stop moving the page. Measure it, and move the reader ONLY on the
 *                               frame the document's height actually changes — which is content
 *                               arriving, the one event that can make the saved offset reachable.
 *
 * The second phase never nudges a page that is sitting still, so a reader left looking at the
 * bottom of a short page stays there; it costs one height read every RESTORE_POLL_MS rather than
 * one per frame; and it is hard-stopped by RESTORE_MAX_MS, which is what keeps a restore from
 * outliving the navigation that started it. Neither phase writes an intermediate position back.
 *
 * HOW WE KNOW THE READER HAS TAKEN OVER. Watching for `wheel`, `touchstart` and `keydown` was not
 * enough, and the longer watch made that hole four times worse than it used to be. Dragging the
 * scrollbar fires none of those, and neither does middle-click autoscroll, so for up to six
 * seconds a reader scrolling with the one control that is always on screen had their own scrolling
 * undone every frame. `mousedown` is now watched too, which is the first event both of those send.
 *
 * But an event list is a list of the ways we thought of. Find-in-page scrolls the document with no
 * DOM input event at all, and what every case has in common is the thing actually worth testing
 * for: the page is at an offset this component did not put it at. So each frame of the watch
 * begins by comparing where the page is against where we last left it, and hands the page over the
 * moment those disagree.
 *
 * The one thing that also moves a page nobody touched is the browser's own scroll anchoring, which
 * is exactly what this component is fighting — so the position check is only trusted while the
 * document's height is unchanged since we last placed the reader. A height that moved is content
 * arriving, not a reader. The cost of that exception is one frame: a reader who moves the page in
 * the same frame the page grows is put back once, and the event list above is what catches them.
 *
 * WHAT HAPPENS WHEN THE CAP EXPIRES, which is a decision and not an accident. Measured with
 * `GET /api/v1/matches` held back 7 s — past RESTORE_MAX_MS — and the restore therefore abandoned
 * before the rows existed: on a Galaxy S8 the reader converged onto the skeleton's bottom at 765,
 * and when the rows landed a second later the browser's scroll anchoring carried them to 2691, the
 * very bottom of the list. WebKit at 390 did the same thing, 751 to 2699. Chromium at 1440 left
 * them at 19. Three engines, three different arbitrary answers, none of them chosen by anybody.
 *
 * So for as long as a restore is owed, the browser's anchoring is held off — `overflow-anchor:
 * none` on <html> AND on <body>, because on Chromium the root element alone does not suppress it
 * (measured: with it set on <html> only, that same reader still went 765 -> 2691). An expired cap
 * is the one outcome that keeps it held, and that is the fallback: this component stops trying to
 * reach the saved offset, and in exchange the page growing underneath the reader does not move
 * them either. They stay exactly where the convergence left them — as close to where they were as
 * the page could reach while they were waiting — which is a place this component chose and can
 * state, rather than wherever the growth happens to throw them on the engine they are using.
 *
 * The hold is given back at the reader's next scroll (see `record`) or when they navigate away,
 * whichever comes first: once they are moving the page themselves, anchoring is theirs again.
 *
 * The phase of a pending restore is published on <html> as RESTORE_PHASE. It is the only handle a
 * browser test has on a boundary that is otherwise invisible from outside — e2e/mocked/
 * navigation-continuity.spec.ts releases its held fixture list on it rather than on a stopwatch —
 * and it says out loud, in the inspector, why anchoring is off on this page.
 *
 * MOTION. Every jump here passes `behavior: 'instant'`. index.css sets `scroll-behavior: smooth`
 * on <html>, and both `scrollTo(x, y)` and `behavior: 'auto'` defer to that — which would turn
 * each of these into an animated slide down a page the reader has not seen yet. 'instant' opts out
 * for everyone, so there is no animation to suppress for a reader who has asked for reduced
 * motion, and no branch here that could drift from the one in index.css.
 *
 * IN-PAGE ANCHORS. A location carrying a hash is left entirely alone, so the skip link in
 * Layout.tsx and any future anchor keep whatever behaviour the browser gives them.
 */

/** Scroll offsets in CSS pixels, keyed by the history entry they belong to (see slotFor()). */
const positions = new Map<string, number>()

/**
 * How many entries we keep. A reader who has walked through fifty fixtures is not going to press
 * Back fifty-one times, and an unbounded map mirrored into sessionStorage is a leak that only ever
 * shows up on the machines of the people who use the site most.
 */
const MAX_ENTRIES = 50

const STORAGE_KEY = 'sp.scroll-positions'

/**
 * How long a restore keeps CONVERGING — putting the reader as close to the saved offset as the
 * page can currently reach, every frame. Long enough for a cached react-query list to paint and
 * for a quick local request to answer; short enough that a reader who has given up and started
 * reading the top of the page is not dragged along by it frame after frame.
 */
const RESTORE_WINDOW_MS = 1500

/**
 * The absolute ceiling on a restore, convergence and the quiet watch that follows it together.
 * Nothing here can outlive it.
 *
 * Six seconds. The failure this bounds was measured with the fixtures delayed by 4 s, arriving at
 * about 4.5 s, and a cap has to sit clear of the case it exists to catch or it fixes nothing. It
 * is also a fifth of the API client's own 30 s request timeout (src/services/api-client.ts): past
 * six seconds of skeleton the reader is no longer waiting to be put back where they were, and a
 * component that moved them then would be acting on a decision they made half a minute ago.
 *
 * The cost of being wrong in the other direction is bounded too, but NOT by handing the reader
 * back to the browser: that was measured, and the browser's own anchoring put them at the bottom
 * of the list on two engines out of three. See WHAT HAPPENS WHEN THE CAP EXPIRES above. What the
 * cap costs a reader whose rows arrive a second after it is the distance between where the page
 * could reach while they waited and where they actually were — no further, because nothing is
 * allowed to move them after it.
 */
const RESTORE_MAX_MS = 6000

/**
 * How often the second phase measures the page. Ten times a second is far finer than a reader can
 * notice and coarse enough that a five-second watch forces fifty layouts rather than three hundred.
 */
const RESTORE_POLL_MS = 100

/**
 * How long the document's height must hold still, AFTER the offset has been applied, before the
 * restore is called finished and the browser's scroll anchoring is handed back.
 *
 * This is the number that closes A PAGE CAN BE TALL ENOUGH BEFORE IT IS FINISHED above. It has to
 * clear the gap between the paint that makes the offset reachable and the paint that finishes the
 * page — measured at 15 to 19 milliseconds, one frame, on all three widths — with enough room
 * that a single slow frame on a loaded machine does not end the watch early. A quarter of a
 * second is roughly fifteen frames at 60Hz.
 *
 * It is bounded from above by two things. e2e/mocked/navigation-continuity.spec.ts requires a
 * landed restore to have given the page's anchoring back 600ms after the rows arrive, so this has
 * to be comfortably inside that; and RESTORE_MAX_MS still hard-stops everything, so the settle
 * can extend a restore but can never prolong one past the cap.
 *
 * What it costs: on an ordinary Back the page is watched for a quarter of a second longer than it
 * used to be, and a reader who scrolls in that quarter second is handed the page by the check in
 * the watch — the same check that has always covered them — rather than being fought for it.
 */
const RESTORE_SETTLE_MS = 250

/**
 * A reader doing any of these has chosen their own position, and a pending restore must yield.
 *
 * These are the inputs that announce themselves BEFORE the scroll they cause, which is what makes
 * them worth keeping: they abandon the restore without even one frame of fighting. `mousedown` is
 * here for the two this list used to miss — a scrollbar drag and a middle-click autoscroll both
 * start with one, and neither fires a wheel, a touch or a key.
 *
 * They are still not the whole story. Find-in-page scrolls the document with no DOM input event
 * of any kind, and a reader can reach the scrollbar of a page this list has already seen a
 * mousedown on. So these sit on top of the position check in the watch, which catches a reader
 * however they moved the page.
 */
const READER_TOOK_OVER = ['wheel', 'touchstart', 'keydown', 'mousedown'] as const

/**
 * How far the page may be from where we last put it before that counts as the reader having moved
 * it. Two pixels: a scroll offset comes back fractional on a non-integer device pixel ratio, and
 * nothing a reader does to a page moves it by less than that.
 */
const READER_SLOP = 2

/**
 * Where the phase of a pending restore is published, on <html>: `converging`, then `holding`,
 * then gone. See WHAT HAPPENS WHEN THE CAP EXPIRES above.
 */
const RESTORE_PHASE = 'data-scroll-restore'

/** How a watch ended. Only `expired` keeps the browser's scroll anchoring held off. */
type RestoreOutcome = 'restored' | 'reader' | 'expired' | 'unmounted'

let hydrated = false

/**
 * Seed the map from sessionStorage once per document.
 *
 * The map alone would be enough for Back inside the app, because a client-side navigation never
 * tears down the module. sessionStorage is what covers leaving to another site and coming back:
 * that reloads the document, and we have already told the browser not to restore the scroll
 * itself, so without this the reader would land at the top of a page they had read half of.
 */
function hydrate(): void {
  if (hydrated) return
  hydrated = true
  try {
    const stored = window.sessionStorage.getItem(STORAGE_KEY)
    if (!stored) return
    for (const [key, value] of Object.entries(JSON.parse(stored) as Record<string, unknown>)) {
      if (typeof value === 'number' && Number.isFinite(value)) positions.set(key, value)
    }
  } catch {
    // sessionStorage throws outright in a storage-blocked or partitioned context, and a corrupted
    // entry throws in JSON.parse. Remembering a scroll offset is a convenience; it must never be
    // able to take the page down with it.
  }
}

/**
 * Which slot of the map this location owns.
 *
 * `location.key` is normally unique per history entry, with one exception that matters here:
 * React Router names a document's INITIAL location with the literal string `default`. A tab that
 * loads /matches, walks off to another site and comes back to /match/123 therefore has two
 * different initial locations both asking for the slot called `default` — and because the map is
 * mirrored into sessionStorage, which survives exactly that round trip, the second one would be
 * handed the first one's offset and drop the reader at an arbitrary point in an unrelated page.
 *
 * Qualifying that one key with the URL is enough to separate them, and is not a behaviour change
 * for the case the key is shared *legitimately*: a reload keeps both the key and the URL, so the
 * page still comes back where the reader left it. Every other key is already unique per entry and
 * is used verbatim, so two visits to the same URL keep the distinct positions they had.
 */
function slotFor(key: string, pathname: string, search: string): string {
  return key === 'default' ? `default@${pathname}${search}` : key
}

/** Record `y` for `key`, re-inserting so the map stays in least-recently-used order. */
function remember(key: string, y: number): void {
  positions.delete(key)
  positions.set(key, y)
  while (positions.size > MAX_ENTRIES) {
    const oldest = positions.keys().next().value
    if (oldest === undefined) break
    positions.delete(oldest)
  }
}

function persist(): void {
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(Object.fromEntries(positions)))
  } catch {
    // See hydrate().
  }
}

const ScrollBehaviour: React.FC = () => {
  const { key, pathname, search, hash } = useLocation()
  const navigationType = useNavigationType()
  /** This history entry's slot in the map. See slotFor(). */
  const slot = slotFor(key, pathname, search)
  /** The path of the previous location, so a query-only rewrite can be told from a real move. */
  const previousPath = useRef<string | null>(null)

  /**
   * The browser restores the scroll itself on a history traversal, and it does it against whatever
   * the page happened to contain at that instant — which in a single-page app is the *outgoing*
   * page. Taking ownership is the only way the rules above can hold.
   */
  useEffect(() => {
    if (!('scrollRestoration' in window.history)) return
    window.history.scrollRestoration = 'manual'
    return () => { window.history.scrollRestoration = 'auto' }
  }, [])

  // A layout effect, not an effect: this runs after the new page is in the DOM but before the
  // browser paints, so the reader never sees the old offset on the new page and then a jump.
  useLayoutEffect(() => {
    hydrate()
    const samePath = previousPath.current === pathname
    previousPath.current = pathname

    const root = document.documentElement

    let frame = 0
    let watching = false

    /**
     * Hold the browser's own scroll anchoring off while a restore is owed, so that this component
     * and the reader are the only two things that move the page.
     *
     * Both elements, not just <html>: measured on Chromium at 360, <html> alone did not suppress
     * it and the reader was still carried from 765 to 2691 when the rows landed.
     */
    let anchoringHeld = false
    let rootAnchorWas = ''
    let bodyAnchorWas = ''
    const holdAnchoring = () => {
      if (anchoringHeld) return
      anchoringHeld = true
      rootAnchorWas = root.style.overflowAnchor
      bodyAnchorWas = document.body.style.overflowAnchor
      root.style.overflowAnchor = 'none'
      document.body.style.overflowAnchor = 'none'
    }
    const releaseAnchoring = () => {
      if (!anchoringHeld) return
      anchoringHeld = false
      root.style.overflowAnchor = rootAnchorWas
      document.body.style.overflowAnchor = bodyAnchorWas
    }

    const stopWatching = (outcome: RestoreOutcome) => {
      watching = false
      if (frame) cancelAnimationFrame(frame)
      frame = 0
      for (const event of READER_TOOK_OVER) window.removeEventListener(event, abandonToReader)
      root.removeAttribute(RESTORE_PHASE)
      // An expired cap keeps the hold: see WHAT HAPPENS WHEN THE CAP EXPIRES. Every other ending
      // gives the page straight back — a restore that landed, or a reader who now owns the page.
      if (outcome !== 'expired') releaseAnchoring()
    }

    /** One function for every READER_TOOK_OVER event, so the add and the remove always match. */
    const abandonToReader = () => stopWatching('reader')

    const jumpTo = (top: number) => window.scrollTo({ top, left: 0, behavior: 'instant' })

    if (!hash) {
      if (navigationType === 'POP') {
        const target = positions.get(slot) ?? 0
        const documentHeight = () => document.documentElement.scrollHeight

        /** Where this component last left the page, and the height it had at that moment. */
        let placedAt = window.scrollY
        let placedHeight = documentHeight()

        /**
         * Put the reader as close to `target` as the page can currently reach, and report whether
         * that was the offset itself — which is the only state worth stopping on.
         */
        const converge = (): boolean => {
          const height = documentHeight()
          const furthest = Math.max(0, height - window.innerHeight)
          const reachable = Math.min(target, furthest)
          // Only move when there is somewhere to move to. Asking for the offset the page is
          // already at fires no scroll event, but skipping it keeps the per-frame work honest and
          // keeps this out of the way of anything else adjusting the scroll in the same frame.
          if (Math.abs(window.scrollY - reachable) > 0.5) jumpTo(reachable)
          // Read back rather than trusting `reachable`: a browser clamps and rounds, and the
          // reader check below is only as good as its idea of where we actually left the page.
          placedAt = window.scrollY
          placedHeight = height
          return furthest >= target
        }

        if (target <= 0) {
          jumpTo(0)
        } else {
          /**
           * Whether the offset ITSELF is currently applied, as opposed to the nearest position a
           * shorter page could reach. Re-read from every converge rather than latched: a page
           * that grows tall enough and then shrinks below the offset again has stopped holding
           * it, and a restore that called itself landed on the strength of a layout that no
           * longer exists would stop watching a page it has not finished with.
           */
          let landed = converge()
          watching = true
          holdAnchoring()
          root.setAttribute(RESTORE_PHASE, 'converging')
          const started = performance.now()
          const convergeUntil = started + RESTORE_WINDOW_MS
          const giveUpAt = started + RESTORE_MAX_MS
          let lastPoll = started
          /**
           * The last moment the document's height was seen to move. RESTORE_SETTLE_MS is measured
           * from here, so a page still being built keeps pushing the end of the restore out — as
           * far as the cap, and no further.
           */
          let heightMovedAt = started
          for (const event of READER_TOOK_OVER) {
            window.addEventListener(event, abandonToReader, { passive: true })
          }

          /**
           * The restore is finished: the reader is on the offset they asked for, and the page has
           * held still underneath them long enough to believe it is done arriving. Either half
           * alone is what the two measured failures were made of — the offset applied to a page
           * still growing (see A PAGE CAN BE TALL ENOUGH BEFORE IT IS FINISHED), and a page that
           * has stopped growing without ever reaching the offset, which is not a restore at all.
           */
          const finished = (now: number) => landed && now - heightMovedAt >= RESTORE_SETTLE_MS

          const tick = (now: number) => {
            if (!watching) return

            /** Read once a frame: the reader check and the settle must agree about the page. */
            const height = documentHeight()
            const grew = height !== placedHeight
            if (grew) heightMovedAt = now

            /*
             * The reader moved the page themselves, by any means at all. READER_TOOK_OVER names
             * the inputs we thought of; this notices the result, which is what covers the ones we
             * did not — find-in-page sends no DOM event whatsoever.
             *
             * Only while the height is what it was when we last placed them: a height that has
             * changed means content arrived, and the offset shifting with it is the browser's
             * scroll anchoring, which is the thing being corrected rather than a reader.
             */
            if (!grew && Math.abs(window.scrollY - placedAt) > READER_SLOP) {
              stopWatching('reader')
              return
            }

            if (now < convergeUntil) {
              landed = converge()
              if (finished(now)) {
                stopWatching('restored')
                return
              }
            } else if (now - lastPoll >= RESTORE_POLL_MS) {
              /*
               * Past the convergence window the page is left alone unless it is still being built.
               * A height that has changed is content arriving — the only thing that can make the
               * saved offset reachable, and the thing that drags the reader to the bottom through
               * the browser's scroll anchoring if nobody corrects it. A height that has not
               * changed means the page is finished and shorter than where the reader was, and
               * they stay at the bottom of it, which is where convergence already put them.
               *
               * A restore that lands out here settles on exactly the same terms as one that lands
               * inside the window: the rows arriving late can be followed by the rest of the page
               * arriving later still, and the reader is owed the offset against the finished
               * layout rather than against the first one that could hold it.
               */
              lastPoll = now
              if (root.getAttribute(RESTORE_PHASE) !== 'holding') {
                root.setAttribute(RESTORE_PHASE, 'holding')
              }
              if (grew) landed = converge()
              if (finished(now)) {
                stopWatching('restored')
                return
              }
            }
            if (now >= giveUpAt) {
              stopWatching('expired')
              return
            }
            frame = requestAnimationFrame(tick)
          }
          frame = requestAnimationFrame(tick)
        }
      } else if (!samePath) {
        jumpTo(0)
      }
    }

    // Not while a restore is converging: those intermediate offsets are this component moving the
    // page, not the reader choosing where to be, and writing them back would overwrite the very
    // offset the convergence is aiming for.
    //
    // A scroll once the watch is over is the reader's, and it is where an expired cap gives the
    // browser's anchoring back: they are moving the page now, so the page is theirs to anchor.
    const record = () => {
      if (watching) return
      releaseAnchoring()
      remember(slot, window.scrollY)
    }
    window.addEventListener('scroll', record, { passive: true })
    // A real unload gets no cleanup, so the last offset is written out here instead.
    window.addEventListener('pagehide', persist)

    return () => {
      const restoreUnfinished = watching
      stopWatching('unmounted')
      // Whatever ended the watch, the page being left keeps none of this: an expired cap holds
      // the browser's anchoring off for the reader who is still on that page, not for the next.
      releaseAnchoring()
      window.removeEventListener('scroll', record)
      window.removeEventListener('pagehide', persist)
      // Runs before the next location's setup, so the page being left is measured while it is
      // still the page on screen — this is what Back has to restore. A restore that never got
      // where it was going is the one case to leave alone: the offset it was aiming for is a
      // better answer than the half-loaded position it had reached.
      if (!restoreUnfinished) record()
      persist()
    }
  }, [hash, navigationType, pathname, slot])

  return null
}

export default ScrollBehaviour
