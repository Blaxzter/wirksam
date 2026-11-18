// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { h } from 'vue'

import { Pause } from '@lucide/vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import SelectionBar, { type SelectionAction } from '@/components/data-table/SelectionBar.vue'

import i18n from '@/locales/i18n'

/**
 * The bar for the ticked rows of a table: how many, what can be done with
 * them, and a way out. On a phone the actions fold into one menu so the bar
 * stays one line; a confirmation takes the bar over and hands focus back to
 * whatever started it.
 */

let wide = true
function stubMatchMedia() {
  window.matchMedia = vi.fn((media: string) => ({
    matches: wide,
    media,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia
}

const ACTIONS: SelectionAction[] = [
  { id: 'pause', label: 'Pause', icon: Pause },
  { id: 'resume', label: 'Resume', disabled: true },
  { id: 'end', label: 'End', destructive: true },
]

type Props = {
  count: number
  actions?: SelectionAction[]
  confirming?: boolean
  label?: string
  placement?: 'page' | 'dialog'
  focusOnLeave?: () => HTMLElement | null | undefined
}

function mountBar(props: Props, slots: Record<string, () => unknown> = {}) {
  return mount(SelectionBar, {
    props,
    slots,
    attachTo: document.body,
    global: { plugins: [i18n] },
  })
}

let mounted: ReturnType<typeof mountBar>[] = []
function track(w: ReturnType<typeof mountBar>) {
  mounted.push(w)
  return w
}

const byTestId = (w: ReturnType<typeof mountBar>, id: string) => w.find(`[data-testid="${id}"]`)

beforeEach(() => {
  wide = true
  stubMatchMedia()
  i18n.global.locale.value = 'en'
})

afterEach(() => {
  for (const w of mounted) w.unmount()
  mounted = []
  document.body.innerHTML = ''
})

describe('SelectionBar', () => {
  it('renders nothing while nothing is selected', () => {
    const w = track(mountBar({ count: 0, actions: ACTIONS }))
    expect(byTestId(w, 'selection-bar').exists()).toBe(false)
  })

  it('is a named region that says how many rows are selected', () => {
    i18n.global.locale.value = 'de'
    const w = track(mountBar({ count: 3, actions: ACTIONS }))
    const bar = byTestId(w, 'selection-bar')
    expect(bar.attributes('role')).toBe('region')
    expect(bar.attributes('aria-label')).toBe('Auswahl')
    expect(byTestId(w, 'selection-message').text()).toBe('3 ausgewählt')
  })

  it('takes its own name and message when given', () => {
    const w = track(
      mountBar(
        { count: 2, actions: ACTIONS, label: 'Selected tasks' },
        { message: () => '2 tasks · 5 places free' },
      ),
    )
    expect(byTestId(w, 'selection-bar').attributes('aria-label')).toBe('Selected tasks')
    expect(byTestId(w, 'selection-message').text()).toBe('2 tasks · 5 places free')
  })

  it('offers every action as a button on a wide screen', async () => {
    const w = track(mountBar({ count: 2, actions: ACTIONS }))
    await byTestId(w, 'selection-action-pause').trigger('click')
    await byTestId(w, 'selection-action-resume').trigger('click')
    await byTestId(w, 'selection-action-end').trigger('click')
    expect(w.emitted('action')).toEqual([['pause'], ['end']])
    // Unusable but still focusable: a disabled button would drop focus to <body>.
    const resume = byTestId(w, 'selection-action-resume')
    expect(resume.attributes('aria-disabled')).toBe('true')
    expect(resume.attributes()).not.toHaveProperty('disabled')
    expect(byTestId(w, 'selection-action-end').attributes('data-variant')).toBe('destructive')
    expect(byTestId(w, 'selection-actions').exists()).toBe(false)
  })

  it('clears the selection with words on a wide screen', async () => {
    const w = track(mountBar({ count: 2, actions: ACTIONS }))
    const clear = byTestId(w, 'selection-clear')
    expect(clear.text()).toBe('Clear selection')
    await clear.trigger('click')
    expect(w.emitted('clear')).toHaveLength(1)
  })

  it('keeps one action as a button on a phone, and clearing as a named icon', async () => {
    wide = false
    stubMatchMedia()
    const w = track(mountBar({ count: 1, actions: [ACTIONS[0]] }))
    await byTestId(w, 'selection-action-pause').trigger('click')
    expect(w.emitted('action')).toEqual([['pause']])
    const clear = byTestId(w, 'selection-clear')
    expect(clear.text()).toBe('')
    expect(clear.attributes('aria-label')).toBe('Clear selection')
  })

  it('folds several actions into one menu on a phone', async () => {
    wide = false
    stubMatchMedia()
    const w = track(mountBar({ count: 2, actions: ACTIONS }))
    const trigger = byTestId(w, 'selection-actions')
    expect(trigger.text()).toBe('Actions')
    expect(byTestId(w, 'selection-action-pause').exists()).toBe(false)

    await trigger.trigger('keydown', { key: 'Enter' })
    await flushPromises()
    const item = document.querySelector<HTMLElement>('[data-testid="selection-action-end"]')
    expect(item?.getAttribute('role')).toBe('menuitem')
    item!.click()
    await flushPromises()
    expect(w.emitted('action')).toEqual([['end']])
    expect(document.activeElement).toBe(trigger.element)
  })

  it('swaps its content for an announced confirmation, and hands focus back after it', async () => {
    const w = track(
      mountBar({ count: 2, actions: ACTIONS }, { confirm: () => h('span', 'End 2 lists?') }),
    )
    await byTestId(w, 'selection-action-end').trigger('click')
    await w.setProps({ confirming: true })
    await flushPromises()
    const confirm = byTestId(w, 'selection-confirm')
    expect(confirm.attributes('role')).toBe('alert')
    expect(confirm.text()).toBe('End 2 lists?')
    expect(byTestId(w, 'selection-message').exists()).toBe(false)
    expect(document.activeElement).toBe(confirm.element)

    await w.setProps({ confirming: false })
    await flushPromises()
    expect(document.activeElement).toBe(byTestId(w, 'selection-action-end').element)
  })

  it('gives focus to the first live button when the starter is gone', async () => {
    const w = track(mountBar({ count: 2, actions: ACTIONS, confirming: true }))
    await w.setProps({ confirming: false })
    await flushPromises()
    expect(document.activeElement).toBe(byTestId(w, 'selection-action-pause').element)
  })

  it('hands focus on when the selection empties while focus is in the bar', async () => {
    const table = document.createElement('button')
    document.body.append(table)
    const w = track(mountBar({ count: 2, actions: ACTIONS, focusOnLeave: () => table }))
    ;(byTestId(w, 'selection-clear').element as HTMLElement).focus()

    await w.setProps({ count: 0 })
    await flushPromises()

    expect(byTestId(w, 'selection-bar').exists()).toBe(false)
    expect(document.activeElement).toBe(table)
  })

  it('leaves focus alone when it is elsewhere as the bar goes', async () => {
    const table = document.createElement('button')
    const other = document.createElement('input')
    document.body.append(table, other)
    const w = track(mountBar({ count: 2, actions: ACTIONS, focusOnLeave: () => table }))
    other.focus()

    await w.setProps({ count: 0 })
    await flushPromises()

    expect(document.activeElement).toBe(other)
  })

  it('sticks to the bottom of a dialog instead of above the phone’s navigation', () => {
    const page = track(mountBar({ count: 1 }))
    expect(byTestId(page, 'selection-bar').classes()).toContain('md:bottom-4')
    const dialog = track(mountBar({ count: 1, placement: 'dialog' }))
    expect(byTestId(dialog, 'selection-bar').classes()).toContain('bottom-0')
  })
})
