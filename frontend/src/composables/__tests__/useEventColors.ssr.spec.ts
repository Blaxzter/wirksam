// Deliberately NOT jsdom: the prerender runs without a DOM.
import { effectScope } from 'vue'

import { describe, expect, it } from 'vitest'

import { useEventColors } from '../useEventColors'

describe('useEventColors without a DOM', () => {
  it('does nothing rather than reach for document', () => {
    expect(typeof document).toBe('undefined')
    const scope = effectScope()
    expect(() =>
      scope.run(() => useEventColors({ primary_color: 'blue', secondary_color: 'yellow' })),
    ).not.toThrow()
    expect(() => scope.stop()).not.toThrow()
  })
})
