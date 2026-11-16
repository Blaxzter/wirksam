// @vitest-environment jsdom
import { mount } from '@vue/test-utils'

import { describe, expect, it, vi } from 'vitest'

import SharedListSignupPerson from '@/components/shared-lists/SharedListSignupPerson.vue'

import i18n from '@/locales/i18n'

import { signup } from './fixtures'

/**
 * The contact line under a name: address and number as one line, which a
 * narrow column may wrap before the address's @ but never inside it.
 */

vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ profile: { time_format: 'h24' } }) }))

function contactOf(patch: Parameters<typeof signup>[1]) {
  const wrapper = mount(SharedListSignupPerson, {
    props: { signup: signup('s1', patch) },
    global: { plugins: [i18n] },
  })
  return wrapper.find('[data-testid="shared-list-signup-contact"]')
}

describe('SharedListSignupPerson', () => {
  it('may wrap an address before its @ only', () => {
    const contact = contactOf({ email: 'p.neumann@example.org', phone: '0170 1234567' })
    expect(contact.text()).toBe('p.neumann@example.org · 0170 1234567')
    expect(contact.html()).toContain('p.neumann<wbr>@example.org')
    expect(contact.classes()).not.toContain('break-all')
  })

  it('shows a number on its own', () => {
    expect(contactOf({ email: null, phone: '0170 1234567' }).text()).toBe('0170 1234567')
  })

  it('shows no contact line without address or number', () => {
    expect(contactOf({ email: null, phone: null }).exists()).toBe(false)
  })
})
