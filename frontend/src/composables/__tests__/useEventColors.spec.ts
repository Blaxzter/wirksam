// @vitest-environment jsdom
import { effectScope, nextTick, ref } from 'vue'

import { beforeEach, describe, expect, it } from 'vitest'

import { type EventColoursSource, useEventColors } from '../useEventColors'

/**
 * `useEventColors` mirrors an event's colours onto `<html data-event-primary
 * data-event-secondary>` for as long as the calling component (here: an
 * effect scope) lives.
 */

const primary = () => document.documentElement.dataset.eventPrimary
const secondary = () => document.documentElement.dataset.eventSecondary
const base = () => document.documentElement.dataset.eventBase

beforeEach(() => {
  delete document.documentElement.dataset.eventPrimary
  delete document.documentElement.dataset.eventSecondary
  delete document.documentElement.dataset.eventBase
})

describe('useEventColors', () => {
  it('puts an own colour on <html> as the preset it is made into', () => {
    const scope = effectScope()
    scope.run(() =>
      useEventColors({
        primary_color: '#1E6BB8',
        secondary_color: '#ffcc00',
        base_color: 'primary',
      }),
    )
    expect(primary()).toBe('#1e6bb8')
    expect(secondary()).toBe('#ffcc00')
    expect(base()).toBe('primary')
    expect(document.getElementById('event-custom-colours')?.textContent).toContain(
      "[data-event-primary='#1e6bb8']",
    )
    scope.stop()
  })

  it('puts the base tone on <html> too, and takes it off with its scope', () => {
    const scope = effectScope()
    scope.run(() => useEventColors({ base_color: 'blue' }))
    expect(base()).toBe('blue')
    scope.stop()
    expect(base()).toBeUndefined()
  })

  it('follows the main colour only when there is one', async () => {
    const event = ref<EventColoursSource>({ base_color: 'primary' })
    const scope = effectScope()
    scope.run(() => useEventColors(event))
    expect(base()).toBeUndefined()

    event.value = { base_color: 'primary', primary_color: 'teal' }
    await nextTick()
    expect(base()).toBe('primary')
    expect(primary()).toBe('teal')

    event.value = { base_color: 'sepia' }
    await nextTick()
    expect(base()).toBeUndefined()
    scope.stop()
  })

  it('puts both colours on <html> and takes them off with its scope', () => {
    const scope = effectScope()
    scope.run(() => useEventColors({ primary_color: 'teal', secondary_color: 'yellow' }))
    expect(primary()).toBe('teal')
    expect(secondary()).toBe('yellow')
    scope.stop()
    expect(primary()).toBeUndefined()
    expect(secondary()).toBeUndefined()
  })

  it('follows the source as it changes, one colour at a time', async () => {
    const event = ref<EventColoursSource | null>({ primary_color: 'red' })
    const scope = effectScope()
    scope.run(() => useEventColors(event))
    expect(primary()).toBe('red')
    expect(secondary()).toBeUndefined()

    event.value = { primary_color: 'red', secondary_color: 'green' }
    await nextTick()
    expect(secondary()).toBe('green')

    event.value = { primary_color: null, secondary_color: 'green' }
    await nextTick()
    expect(primary()).toBeUndefined()
    expect(secondary()).toBe('green')

    event.value = null
    await nextTick()
    expect(secondary()).toBeUndefined()
    scope.stop()
  })

  it('ignores a name it does not know, and yellow as a primary colour', () => {
    const scope = effectScope()
    scope.run(() => useEventColors({ primary_color: 'yellow', secondary_color: 'chartreuse' }))
    expect(primary()).toBeUndefined()
    expect(secondary()).toBeUndefined()
    scope.stop()
  })

  it('lets the newest caller decide, and an older one leaving does not strip it', () => {
    const leaving = effectScope()
    leaving.run(() => useEventColors({ primary_color: 'red', secondary_color: 'blue' }))
    const arriving = effectScope()
    arriving.run(() => useEventColors({ primary_color: 'violet' }))
    // The newest decides both: it has no secondary colour, so none shows.
    expect(primary()).toBe('violet')
    expect(secondary()).toBeUndefined()

    // The page that left cleans up after the next one has set its colours.
    leaving.stop()
    expect(primary()).toBe('violet')

    arriving.stop()
    expect(primary()).toBeUndefined()
  })

  it('falls back to the older caller when the newer one goes first', () => {
    const layout = effectScope()
    layout.run(() => useEventColors({ primary_color: 'orange', secondary_color: 'teal' }))
    const page = effectScope()
    page.run(() => useEventColors({ primary_color: 'pink' }))
    page.stop()
    expect(primary()).toBe('orange')
    expect(secondary()).toBe('teal')
    layout.stop()
    expect(primary()).toBeUndefined()
    expect(secondary()).toBeUndefined()
  })

  // Last on purpose: with no scope to stop, its caller stays on the stack.
  it('still applies outside a component, where nothing can take it off again', () => {
    useEventColors({ primary_color: 'slate', secondary_color: 'slate' })
    expect(primary()).toBe('slate')
    expect(secondary()).toBe('slate')
  })
})
