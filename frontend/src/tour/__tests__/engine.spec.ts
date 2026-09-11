// @vitest-environment jsdom
/**
 * The engine's DOM-bound half: what a tour leaves behind when it ends, and what
 * it writes into the popover while it runs.
 *
 * `tracks.spec.ts` walks the step data; nothing else stands the engine up
 * against a real dialog, which is where the two halves disagreed — a step that
 * opens a modal to reach its anchor left that modal open, and a reka-ui modal
 * takes `pointer-events` away from the whole document while it is up.
 *
 * The later cases pin the three things the redesign moved out of TypeScript and
 * into copy: the per-step Next label and its silent fallback, the chapter name
 * on the progress line, and the machine-readable attributes the e2e suite reads
 * now that the button text is arbitrary prose.
 */
import { mount } from '@vue/test-utils'
import { defineComponent, h, nextTick, ref } from 'vue'

import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import { TOUR_TRACKS, useTourStore } from '@/stores/tour'

import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'

import i18n from '@/locales/i18n'
import { openAccordionSection } from '@/tour/dom'
import { createTourController } from '@/tour/engine'
import { acquireStageProxy, releaseStageProxy } from '@/tour/placement'

const Blank = defineComponent({ render: () => h('div') })

/**
 * The helper track's first `inOverlay` step — the one that reaches its anchor
 * by opening `ShiftDetailDialog`.
 *
 * Derived rather than written down. A literal index pins the whole track's
 * ordering to a number that has nothing to do with what this file tests, and it
 * makes `expect(currentStep?.inOverlay).toBe(true)` below tautological: the
 * assertion would only ever be checking that somebody kept the constant up to
 * date. Looking the step up by the property under test keeps both honest.
 */
const OVERLAY_STEP_INDEX = TOUR_TRACKS.helper.steps.findIndex((step) => step.inOverlay)

/** The step a helper tour opens on, which is what most of these cases render. */
const FIRST_STEP = TOUR_TRACKS.helper.steps[0]

/**
 * An adjacent pair — one step that carries its own Next label, followed by one
 * that does not — so a single press across the two exercises both halves of
 * `stepLabel()`.
 *
 * Probed out of the copy rather than written down, for the same reason as
 * `OVERLAY_STEP_INDEX` above: which steps opt into a verb-shaped button is a
 * translator's decision, made by adding a string to `tour.json` and nothing
 * else, so a literal index here would pin a choice this file has no say in.
 */
const LABELLED_INDEX = TOUR_TRACKS.helper.steps.findIndex(
  (step, index, steps) =>
    i18n.global.te(step.nextKey) &&
    steps[index + 1] !== undefined &&
    !i18n.global.te(steps[index + 1].nextKey),
)
const LABELLED_STEP = TOUR_TRACKS.helper.steps[LABELLED_INDEX]
const FALLBACK_STEP = TOUR_TRACKS.helper.steps[LABELLED_INDEX + 1]

/**
 * The dashboard, as much of it as the first step needs.
 *
 * Both anchors, because `main-content`/`page-heading` is what the engine waits
 * out a route flush against and `dashboard-next-shift` is what step one
 * actually highlights — an absent anchor is not an error, it is a six-second
 * wait, which is longer than every `settle()` in this file put together.
 */
const DASHBOARD_DOM = `
  <div data-testid="main-content"><h1 data-testid="page-heading">Dashboard</h1></div>
  <div data-testid="dashboard-next-shift">Saturday, 09:00</div>`

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'home', component: Blank },
      { path: '/tasks', name: 'tasks', component: Blank },
      { path: '/availability', name: 'availability', component: Blank },
      { path: '/my-bookings', name: 'my-bookings', component: Blank },
    ],
  })
}

/** A modal dialog, mounted open, the way `ShiftDetailDialog` renders one. */
function mountOpenDialog() {
  return mount(
    defineComponent({
      // Registered under a different name because `Dialog` is a reserved HTML
      // element name, which `vue/no-reserved-component-names` rejects.
      components: { DialogRoot: Dialog, DialogContent, DialogDescription, DialogTitle },
      setup: () => ({ open: ref(true) }),
      template: `
        <DialogRoot v-model:open="open">
          <DialogContent data-testid="dialog-shift-detail">
            <DialogTitle>Shift</DialogTitle>
            <DialogDescription>Details</DialogDescription>
          </DialogContent>
        </DialogRoot>
      `,
    }),
    { attachTo: document.body },
  )
}

/**
 * One accordion section, in reka-ui's shape.
 *
 * Only the parts `openAccordionSection` reads: `data-state` on the item and the
 * trigger, and a content panel that is only *measurable* once it is open. The
 * click handler is what a real trigger does — it flips all three — and the spy
 * on it is the whole point of the second call.
 */
function mountAccordionSection(testId: string, state: 'open' | 'closed') {
  document.body.innerHTML = `
    <div data-testid="${testId}" data-state="${state}">
      <button data-slot="accordion-trigger" data-state="${state}"></button>
      <div data-slot="accordion-content" data-state="${state}"></div>
    </div>`

  const item = document.querySelector<HTMLElement>(`[data-testid="${testId}"]`)!
  const trigger = item.querySelector<HTMLElement>('[data-slot="accordion-trigger"]')!
  const content = item.querySelector<HTMLElement>('[data-slot="accordion-content"]')!

  const clicks = vi.fn(() => {
    const next = item.getAttribute('data-state') === 'open' ? 'closed' : 'open'
    for (const node of [item, trigger, content]) node.setAttribute('data-state', next)
  })
  trigger.addEventListener('click', clicks)

  return { item, trigger, content, clicks }
}

/** The rendered Next button, and the label driver wrote into it. */
function nextButton() {
  return document.querySelector<HTMLButtonElement>('.driver-popover-next-btn')
}

/**
 * Long enough for driver's own animation frame, for the engine's pre-scroll to
 * hand back, and for reka-ui to unmount a dismissed dialog — the
 * `pointer-events` it took off `<body>` comes back in a watcher cleanup,
 * several ticks after the key lands.
 *
 * Two hundred rather than the hundred it was: the pre-scroll puts another
 * `await` between `start()` and the first `render()`, and although
 * `scrollAnchorIntoView` short-circuits under the `matchMedia` stub below, the
 * microtasks it costs are real.
 */
const settle = () => new Promise((resolve) => setTimeout(resolve, 200))

describe('tour engine', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    document.body.innerHTML = ''
    document.body.style.pointerEvents = ''
    // The stage proxy is appended to `<body>` by `tour/placement.ts` and is the
    // one node a torn-down tour can leave behind, so a case that ends badly
    // must not hand the next one a stale rectangle to highlight.
    releaseStageProxy()
    sessionStorage.clear()
    // jsdom measures everything at 0×0, and `firstVisible` rejects that.
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
      width: 120,
      height: 40,
      top: 0,
      left: 0,
      right: 120,
      bottom: 40,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    } as DOMRect)
    window.matchMedia = ((query: string) => ({
      matches: true,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia
  })

  it('hands the document back when a tour is dismissed inside a dialog', async () => {
    expect(OVERLAY_STEP_INDEX).toBeGreaterThan(-1)

    const dialog = mountOpenDialog()
    await nextTick()
    // The premise: a reka-ui modal takes pointer events off the whole body, so
    // everything outside it — the demo banner's "restart the tour" included —
    // stops receiving clicks.
    expect(document.body.style.pointerEvents).toBe('none')

    const router = makeRouter()
    await router.push('/tasks')
    await router.isReady()
    const controller = createTourController(router)

    const store = useTourStore()
    store.start('helper')
    store.goTo(OVERLAY_STEP_INDEX)
    expect(store.currentStep?.inOverlay).toBe(true)

    // Stood up by hand rather than by an oversized anchor: jsdom measures every
    // element at the same 120×40, so nothing here is ever big enough for
    // `computeStageBox` to clamp. The leak being guarded against is the same
    // one either way — teardown owns the node, and nothing else removes it.
    const proxy = acquireStageProxy({ top: 0, left: 0, width: 10, height: 10 })
    expect(proxy.isConnected).toBe(true)

    controller.stop()
    await settle()

    expect(document.body.style.pointerEvents).not.toBe('none')
    expect(proxy.isConnected).toBe(false)
    dialog.unmount()
  })

  it('draws a popover again after the visitor closes the tour', async () => {
    const router = makeRouter()
    await router.push('/')
    await router.isReady()
    const controller = createTourController(router)
    router.afterEach((to) => controller.handleRouteChange(to))

    document.body.innerHTML = DASHBOARD_DOM

    controller.start('helper')
    await settle()
    expect(document.querySelector('.driver-popover')).not.toBeNull()

    document.querySelector<HTMLElement>('.driver-popover-close-btn')!.click()
    await settle()
    expect(document.querySelector('.driver-popover')).toBeNull()
    expect(useTourStore().status).toBe('idle')

    controller.start('helper')
    await settle()
    expect(useTourStore().status).toBe('running')
    expect(document.querySelector('.driver-popover')).not.toBeNull()
  })

  it('labels Next from the step when it has copy, and generically when it has none', async () => {
    // Asserted against `i18n` rather than against the English strings: the
    // wording is the copy agents' to change, and what this pins is the
    // resolution — that `nextKey` is consulted, and that a step without the copy
    // silently gets `tour.common.next` instead of the raw dotted path vue-i18n
    // renders for a key it cannot find.
    expect(LABELLED_INDEX).toBeGreaterThan(-1)
    const generic = i18n.global.t('tour.common.next')
    const owned = i18n.global.t(LABELLED_STEP.nextKey)
    expect(owned).not.toBe(generic)

    const router = makeRouter()
    await router.push('/')
    await router.isReady()
    const controller = createTourController(router)
    router.afterEach((to) => controller.handleRouteChange(to))

    // Both screens the walk crosses, since the pair is not promised to sit on
    // one route: `waitFor` on a selector that never turns up is a six-second
    // stall, and a missing anchor is another.
    document.body.innerHTML = `${DASHBOARD_DOM}
      <div data-testid="task-list"><div data-testid="task-row">Welcome desk</div></div>`

    const store = useTourStore()
    store.start('helper')
    store.goTo(LABELLED_INDEX)
    // Rendered through the route handler rather than `start()`, which always
    // opens at step one — the pair this is about is wherever the copy puts it.
    controller.handleRouteChange(router.currentRoute.value)
    await settle()
    expect(nextButton()?.textContent).toBe(owned)

    nextButton()!.click()
    await settle()
    expect(store.currentStep?.id).toBe(FALLBACK_STEP.id)
    expect(nextButton()?.textContent).toBe(generic)
  })

  it('stamps the step and the end of the track onto the Next button', async () => {
    // The label is arbitrary prose now, so `e2e/tests/public/sandbox-tour.spec.ts`
    // can no longer read "is this the last step?" off the button text — and
    // driver's own `driver-popover-done-btn` is not an alternative, since it
    // only appears under `drive()` and this app uses `highlight()`. These two
    // attributes are the replacement, which makes them a contract.
    const router = makeRouter()
    await router.push('/')
    await router.isReady()
    const controller = createTourController(router)

    document.body.innerHTML = DASHBOARD_DOM

    controller.start('helper')
    await settle()

    expect(nextButton()?.dataset.tourStep).toBe(FIRST_STEP.id)
    expect(nextButton()?.dataset.tourLast).toBe('false')
  })

  it('puts the chapter, and only the step number, on the progress line', async () => {
    const router = makeRouter()
    await router.push('/')
    await router.isReady()
    const controller = createTourController(router)

    document.body.innerHTML = DASHBOARD_DOM

    controller.start('helper')
    await settle()

    const progress = document.querySelector('.driver-popover-progress-text')?.textContent ?? ''
    expect(progress).toContain(i18n.global.t(FIRST_STEP.chapterKey))
    // The e2e suite reads the current step out of this line with the first
    // `\d+` it finds, so a chapter name that arrived before the number — or
    // one carrying a digit of its own — would break it silently.
    expect(/\d+/.exec(progress)?.[0]).toBe('1')
  })

  it('leaves an accordion section alone when it is already open', async () => {
    // `openSection` is handed to every `before()` hook, and the engine re-runs
    // those whenever the view remounts under a step — which `TaskCreateView`'s
    // own filters do. A hook that clicked unconditionally would therefore
    // *collapse* the section its copy is describing on the second run.
    const closed = mountAccordionSection('section-schedule', 'closed')
    await expect(openAccordionSection('section-schedule')).resolves.toBe(closed.item)
    expect(closed.clicks).toHaveBeenCalledTimes(1)
    expect(closed.item.getAttribute('data-state')).toBe('open')

    const open = mountAccordionSection('section-schedule', 'open')
    await expect(openAccordionSection('section-schedule')).resolves.toBe(open.item)
    expect(open.clicks).not.toHaveBeenCalled()
    expect(open.item.getAttribute('data-state')).toBe('open')
  })

  it('reports a section that is not on this screen rather than throwing', async () => {
    // A track treats `null` as "carry on with a centred popover"; a rejection
    // would be caught by the engine and read as the same thing, but only after
    // the hook had already given up on whatever came after it.
    await expect(openAccordionSection('section-preview')).resolves.toBeNull()
  })
})
