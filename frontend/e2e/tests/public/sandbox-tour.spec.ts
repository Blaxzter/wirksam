import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

/**
 * The guided tour, end to end.
 *
 * The single thing worth testing here is that the tour **survives navigation**.
 * Every step lives in a fresh view: `PostAuthLayout` keys its `RouterView` on
 * the route, so crossing from the dashboard to the task list destroys the
 * element the popover was anchored to. The tour keeps its place in a Pinia
 * store mirrored to `sessionStorage`, destroys the driver before each push and
 * re-queries the anchor on the other side — and if any of that regresses, the
 * symptom is a popover that silently stops appearing partway through, which no
 * unit test would catch.
 *
 * Two more things are only observable from out here, and both have been broken
 * once already: the helper track's book step has to reach a *live* Book button
 * (the seeder used to hand the guest the only bookable shift and then point the
 * tour at it), and the demo banner has to stay clickable underneath driver's
 * overlay.
 */

/**
 * The class `tour/dom.ts` writes on whatever the current step is pointing at.
 *
 * Asserted instead of driver's own `driver-active-element` because that one
 * moves: an anchor taller than the viewport is highlighted through the stage
 * proxy in `tour/placement.ts`, and driver's class goes to the stand-in. This
 * one is always on the real element.
 */
const ANCHOR_CLASS = /wirksam-tour-anchor/

/**
 * Get into a demo and stop at the greeting.
 *
 * A demo session opens on `SandboxWelcomeDialog`, which *offers* the tour
 * rather than starting one — so every case here has to answer it, and the two
 * that are about the offer itself answer it themselves.
 */
async function openDemo(page: Page, role: 'helper' | 'manager') {
  await page.goto('/')
  await page.getByTestId('btn-cta-demo').click()
  await expect(page.getByTestId('dialog-sandbox-start')).toBeVisible()
  await page.getByTestId(`btn-sandbox-role-${role}`).click()
  await page.getByTestId('btn-sandbox-start').click()
  await page.waitForURL(/\/app\//, { timeout: 30_000 })
  await expect(page.getByTestId('dialog-sandbox-welcome')).toBeVisible({ timeout: 20_000 })
}

/** Open a demo and say yes to the tour. */
async function startDemo(page: Page, role: 'helper' | 'manager') {
  await openDemo(page, role)
  await page.getByTestId('btn-tour-accept').click()
}

async function exitDemo(page: Page) {
  await page
    .locator('.driver-popover-close-btn')
    .click({ timeout: 3000 })
    .catch(() => {})
  await page.getByTestId('btn-sandbox-exit').click()
  await page.getByTestId('btn-dialog-confirm').click()
  await page.waitForURL(/\/$/, { timeout: 15_000 })
}

/**
 * `{ current, total }` out of `tour.common.progress`, whichever locale rendered
 * it and whatever chapter it was prefixed with.
 *
 * Parsed rather than compared to a literal because the counter is translated
 * ("Your event · Step 3 of 10" / "Deine Veranstaltung · Schritt 3 von 10") and
 * the tracks are still gaining and losing steps; the two numbers are the only
 * part of that string this file has any business knowing. The **last two**
 * matches, not the first two: the line opens with a chapter name, and while
 * `tracks.spec.ts` keeps digits out of those labels, a counter read from the
 * tail cannot be broken by a chapter called "Week 2" in the first place.
 */
async function progress(page: Page): Promise<{ current: number; total: number }> {
  const text = (await page.locator('.driver-popover-progress-text').textContent()) ?? ''
  const numbers = text.match(/\d+/g) ?? []
  const [current, total] = numbers.slice(-2).map(Number)
  return { current: current ?? NaN, total: total ?? NaN }
}

/** Just the step index, for the places that poll it. */
async function stepNumber(page: Page): Promise<number> {
  return (await progress(page)).current
}

/**
 * Click Next and wait for the step counter to actually change.
 *
 * A fixed timeout is not good enough: a step whose `before()` hook opens a
 * dialog takes noticeably longer than one that only moves the highlight, and
 * waiting a flat two seconds makes the walk race the slow ones.
 * Returns false once the tour has finished.
 *
 * "Have we finished?" is answered by `current === total`. The label is per-step
 * copy now — "Open this shift", "See my shifts" — so a regex over the button
 * text never sees the end coming, and driver's own `driver-popover-done-btn` is
 * not on offer either: driver only adds that under `drive()`, and this app
 * drives itself one `highlight()` at a time. The engine does stamp
 * `data-tour-last` for exactly this question, but the counter is already on
 * screen and is what the visitor is reading, so it is the better witness — and
 * it is the same string every other assertion here waits on.
 */
async function nextStep(page: Page): Promise<boolean> {
  const next = page.locator('.driver-popover-next-btn')
  if (!(await next.isVisible().catch(() => false))) return false

  const { current, total } = await progress(page)
  await next.click()
  if (!(current < total)) return false

  await page.waitForFunction(
    (previous) => {
      const text = document.querySelector('.driver-popover-progress-text')?.textContent ?? ''
      const numbers = text.match(/\d+/g)
      // Mid-navigation there is no popover at all. That is not the end of the
      // tour, it is the middle of the transition being waited for.
      if (!numbers || numbers.length < 2) return false
      return Number(numbers[numbers.length - 2]) !== previous
    },
    current,
    { timeout: 20_000 },
  )
  return true
}

/**
 * Press Next until the popover belongs to `stepId`, which the engine stamps on
 * the Next button as `data-tour-step`.
 *
 * By id rather than by counting presses, so a step added or removed upstream
 * moves this walk along rather than breaking it.
 */
async function walkTo(page: Page, stepId: string, maxSteps: number): Promise<boolean> {
  const next = page.locator('.driver-popover-next-btn')
  for (let i = 0; i < maxSteps; i++) {
    if ((await next.getAttribute('data-tour-step')) === stepId) return true
    if (!(await nextStep(page))) return false
  }
  return false
}

/**
 * Press Next, then press it twice more without waiting to be invited, and
 * report whether the tour had already refused by then.
 *
 * All three presses happen inside one `page.evaluate`, in a single task, and
 * that is the whole point. `show()` calls `setPreparing(true)` — and with it
 * `syncNavigationButtons()` — synchronously, before its first `await`, so the
 * button really is disabled by the time the click handler returns. Asking from
 * the Playwright side instead cost a round trip, during which a step whose
 * anchor was already on screen could finish and re-enable the button before the
 * question arrived; that made the observation a race, and the assertion below
 * could only ever be "at least one of them". Reading `disabled` in the same
 * task makes it a fact about every transition.
 *
 * The two extra presses are dispatched rather than `click()`ed because
 * `HTMLElement.click()` is specified to do nothing at all on a disabled
 * control, which would leave the greying-out testing itself. A dispatched event
 * still reaches driver's delegated listener, so what these two exercise is the
 * engine's own `if (preparing) return` — the guard that actually matters,
 * because Enter on a focused button never consults the styling either.
 *
 * Lives out here rather than inline because `playwright/no-conditional-in-test`
 * is right about branches in test bodies.
 */
async function pressNextImpatiently(page: Page): Promise<boolean> {
  return page.evaluate(() => {
    const next = document.querySelector<HTMLButtonElement>('.driver-popover-next-btn')
    if (!next) return false

    next.click()
    const busy = next.disabled

    next.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
    next.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
    return busy
  })
}

/** Walk a whole track, returning the route each step landed on. */
async function walk(page: Page, maxSteps: number): Promise<string[]> {
  await expect(page.locator('.driver-popover-title')).toBeVisible({ timeout: 20_000 })

  const routes: string[] = []
  for (let i = 0; i < maxSteps; i++) {
    // The popover must be present at every single step — this is the assertion
    // the whole spec exists for.
    await expect(page.locator('.driver-popover-title')).toBeVisible()
    routes.push(new URL(page.url()).pathname)
    if (!(await nextStep(page))) break
  }
  return routes
}

test.describe('guided tour', () => {
  // Walking a whole track means a dozen real navigations and page loads.
  test.slow()

  test('the helper track runs to the end across routes', async ({ page }) => {
    await startDemo(page, 'helper')

    const routes = await walk(page, 15)

    // It got somewhere, and it crossed route boundaries to do it.
    expect(routes.length).toBeGreaterThanOrEqual(5)
    expect(new Set(routes).size).toBeGreaterThan(1)
    expect(routes.some((r) => r.includes('/app/tasks'))).toBe(true)

    // Finishing closes the tour rather than leaving an overlay behind.
    await expect(page.locator('.driver-popover')).toBeHidden()

    await exitDemo(page)
  })

  test('the organiser track covers the management screens', async ({ page }) => {
    await startDemo(page, 'manager')

    const routes = await walk(page, 20)

    expect(routes.length).toBeGreaterThanOrEqual(8)
    expect(routes.some((r) => r.includes('/app/tasks'))).toBe(true)
    expect(routes.some((r) => r.includes('/app/reporting'))).toBe(true)

    await expect(page.locator('.driver-popover')).toBeHidden()

    await exitDemo(page)
  })

  test('the demo greets the visitor before it guides them', async ({ page }) => {
    await openDemo(page, 'helper')

    // Nothing is dimmed and nothing is highlighted while the question is on
    // screen: the greeting is a plain dialog, and the tour it offers does not
    // exist until somebody says yes.
    await expect(page.locator('.driver-popover')).toBeHidden()

    await page.getByTestId('btn-tour-decline').click()
    await expect(page.getByTestId('dialog-sandbox-welcome')).toBeHidden()
    await expect(page.locator('.driver-popover')).toBeHidden()

    // Declining is not a door closing: the banner offers the same tour for as
    // long as the demo lasts.
    await page.getByTestId('btn-sandbox-tour').click()
    await expect(page.locator('.driver-popover')).toBeVisible({ timeout: 20_000 })

    await exitDemo(page)
  })

  test('the first step highlights the screen it arrived on, not the one it left', async ({
    page,
  }) => {
    await startDemo(page, 'helper')
    await expect(page.locator('.driver-popover-title')).toBeVisible({ timeout: 20_000 })

    // `router.afterEach` fires one Vue flush before `RouterView` swaps its
    // component, so the landing page is still mounted and still measurable when
    // a tour resolves its first anchor — and the landing page carries a
    // `main-content` of its own, exactly like every screen the tour visits.
    // Resolving against it left driver drawing on a rectangle that was
    // unmounted a microsecond later, which puts the popover in the top-left
    // corner with nothing highlighted at all.
    await expect(page.getByTestId('dashboard-next-shift')).toHaveClass(ANCHOR_CLASS)

    await exitDemo(page)
  })

  test('the book step points at a shift the visitor can actually take', async ({ page }) => {
    await startDemo(page, 'helper')
    await expect(page.locator('.driver-popover-title')).toBeVisible({ timeout: 20_000 })

    // The defect the whole tour overhaul started from, and the only place it can
    // be caught. This step's copy says "press it now if you like" — and for a
    // long time it said that over a footer with no Book button in it, because
    // the chip the tour opened was the guest's own already-booked shift, where
    // `ShiftDetailDialog` renders *Cancel* instead. Two changes close it,
    // `data-tour-bookable` on the chip and a seeder that holds one upcoming
    // shift open, and neither is worth anything without the other, so the
    // assertion has to be made from out here where both are in play.
    expect(await walkTo(page, 'bookIt', 15)).toBe(true)

    const footer = page.getByTestId('shift-detail-footer')
    await expect(footer).toHaveClass(ANCHOR_CLASS)

    const book = page.getByTestId('btn-book-shift')
    await expect(book).toBeVisible()
    await expect(book).toBeEnabled()

    // Pressing it has to work, not merely look pressable: driver's overlay
    // covers the dialog, and the button is only reachable at all because the
    // anchor class hands its pointer events back. A refusal from the API — the
    // shift filled, the guest already on it — arrives as an error toast and
    // nothing else, so the success toast is the assertion and the absent error
    // toast is the check on the assertion.
    await book.click()
    await expect(page.locator('[data-sonner-toast][data-type="success"]')).toBeVisible()
    await expect(page.locator('[data-sonner-toast][data-type="error"]')).toHaveCount(0)

    // `handleBook` closes the dialog, which takes the anchored footer with it.
    // The step is meant to survive that as a centred popover rather than leave
    // driver staging a rectangle that has left the document.
    await expect(page.locator('.driver-popover-title')).toBeVisible()

    await exitDemo(page)
  })

  test('presses land one step at a time while a step is still opening', async ({ page }) => {
    await startDemo(page, 'helper')
    await expect(page.locator('.driver-popover-title')).toBeVisible({ timeout: 20_000 })

    // Five presses reach `shiftRoster`, whose `before()` hook has to click a
    // shift chip and wait for the dialog's footer — comfortably the slowest
    // transition in the track, and the one this is really about. The others are
    // here because a route push, and the scroll settle every step now waits on
    // before it highlights anything, are slow enough to click through as well.
    const busy: boolean[] = []
    for (let i = 0; i < 5; i++) {
      const before = await stepNumber(page)

      busy.push(await pressNextImpatiently(page))

      await expect.poll(() => stepNumber(page), { timeout: 25_000 }).toBe(before + 1)
      await expect(page.locator('.driver-popover-next-btn')).toBeEnabled()
    }

    // Every one of them, not merely one of them. The flag is read in the same
    // task as the click, so a transition that did not mark itself busy is a
    // transition in which a second press would have walked the store forward
    // unseen — which is the bug, whether or not the counter happened to recover.
    expect(busy).toEqual([true, true, true, true, true])

    await exitDemo(page)
  })

  test('the demo banner stays usable while the tour is running', async ({ page }) => {
    await startDemo(page, 'helper')
    await expect(page.locator('.driver-popover-title')).toBeVisible({ timeout: 20_000 })

    // Far enough in that a restart is visible in the counter.
    await nextStep(page)
    await nextStep(page)
    await expect.poll(() => stepNumber(page), { timeout: 25_000 }).toBeGreaterThan(1)

    // The banner is `fixed` at `z-50`, which puts it under driver's overlay, and
    // every element on the page is inside the reach of driver's own
    // `.driver-active * { pointer-events: none }`. So for the length of a tour
    // the two controls that can end the thing on screen — restart it, or leave
    // the demo — were dimmed and dead at once. Playwright's own actionability
    // check is the assertion here: it refuses to click through an overlay that
    // intercepts the press.
    const restart = page.getByTestId('btn-sandbox-tour')
    await expect(restart).toBeEnabled()
    await restart.click()

    await expect.poll(() => stepNumber(page), { timeout: 20_000 }).toBe(1)

    await exitDemo(page)
  })

  test('the banner can restart a tour that was closed', async ({ page }) => {
    await startDemo(page, 'helper')

    await expect(page.locator('.driver-popover')).toBeVisible({ timeout: 20_000 })
    await page.locator('.driver-popover-close-btn').click()
    await expect(page.locator('.driver-popover')).toBeHidden()

    await page.getByTestId('btn-sandbox-tour').click()
    await expect(page.locator('.driver-popover')).toBeVisible({ timeout: 20_000 })

    await exitDemo(page)
  })
})
