// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'

import { registerCustomColour } from '@/lib/custom-colour'

/** An own colour, put on the page as a preset the first time it is needed. */

describe('registerCustomColour', () => {
  it('writes the rules into one style element, once per colour and kind', () => {
    expect(registerCustomColour('primary', '#1E6BB8')).toBe('#1e6bb8')
    registerCustomColour('primary', '#1e6bb8')
    registerCustomColour('secondary', '#1e6bb8')

    const styles = document.querySelectorAll('style#event-custom-colours')
    expect(styles).toHaveLength(1)
    const text = styles[0]!.textContent!
    expect(text.match(/^\[data-event-primary='#1e6bb8'\] \{/gm)).toHaveLength(1)
    expect(text).toMatch(/^\[data-event-secondary='#1e6bb8'\] \{/m)
  })
})
