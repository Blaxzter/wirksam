// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'

import { useFocusReturn } from '@/composables/useFocusReturn'

/**
 * reka's Drawer only ever hands focus back to a `DrawerTrigger`, and our
 * sheets open through `v-model`. These tests pin what the sheet does instead:
 * remember who had focus on open, give it back on close, and stay out of the
 * way when focus went elsewhere or a handler of the sheet decided already.
 */

function renderPage() {
  document.body.innerHTML = `
    <button id="opener">⋯</button>
    <div id="sheet" role="dialog"><button id="row">Row</button></div>
    <div id="other" role="dialog"><input id="field" /></div>
  `
  const el = (id: string) => document.getElementById(id) as HTMLElement
  return { opener: el('opener'), sheet: el('sheet'), row: el('row'), field: el('field') }
}

/** FocusScope dispatches its close event on the sheet itself. */
function closeEvent(sheet: HTMLElement, prevented = false): Event {
  const event = new CustomEvent('focusScope.autoFocusOnUnmount', { cancelable: true })
  if (prevented) event.preventDefault()
  sheet.dispatchEvent(event)
  return event
}

afterEach(() => {
  document.body.innerHTML = ''
})

describe('useFocusReturn', () => {
  it('gives focus back to the button that opened the sheet', () => {
    const { opener, sheet, row } = renderPage()
    const focus = useFocusReturn()

    opener.focus()
    focus.remember()
    row.focus()

    const event = closeEvent(sheet)
    focus.restore(event)

    expect(document.activeElement).toBe(opener)
    expect(event.defaultPrevented).toBe(true)
  })

  it('also when focus had already dropped to the page', () => {
    const { opener, sheet } = renderPage()
    const focus = useFocusReturn()

    opener.focus()
    focus.remember()
    opener.blur()

    focus.restore(closeEvent(sheet))

    expect(document.activeElement).toBe(opener)
  })

  it('leaves focus where another dialog put it, and keeps reka from moving it', () => {
    const { opener, sheet, field } = renderPage()
    const focus = useFocusReturn()

    opener.focus()
    focus.remember()
    field.focus()

    const event = closeEvent(sheet)
    focus.restore(event)

    expect(document.activeElement).toBe(field)
    expect(event.defaultPrevented).toBe(true)
  })

  it('does nothing when a handler of the sheet has decided already', () => {
    const { opener, sheet, row } = renderPage()
    const focus = useFocusReturn()

    opener.focus()
    focus.remember()
    row.focus()

    focus.restore(closeEvent(sheet, true))

    expect(document.activeElement).toBe(row)
  })

  it('leaves it to reka when the opener is gone or nobody had focus', () => {
    const { opener, sheet, row } = renderPage()
    const focus = useFocusReturn()

    opener.focus()
    focus.remember()
    opener.remove()
    row.focus()
    const gone = closeEvent(sheet)
    focus.restore(gone)
    expect(gone.defaultPrevented).toBe(false)

    // Opened with nothing focused: there is nobody to give it back to.
    row.blur()
    focus.remember()
    const nobody = closeEvent(sheet)
    focus.restore(nobody)
    expect(nobody.defaultPrevented).toBe(false)
  })

  it('forgets the opener once it has been used', () => {
    const { opener, sheet, row } = renderPage()
    const focus = useFocusReturn()

    opener.focus()
    focus.remember()
    focus.restore(closeEvent(sheet))

    row.focus()
    const again = closeEvent(sheet)
    focus.restore(again)

    expect(document.activeElement).toBe(row)
    expect(again.defaultPrevented).toBe(false)
  })
})
