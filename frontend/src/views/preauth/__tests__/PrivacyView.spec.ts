// @vitest-environment jsdom
import { mount } from '@vue/test-utils'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import i18n from '@/locales/i18n'
import PrivacyView from '@/views/preauth/PrivacyView.vue'

/**
 * The privacy policy's section on signing up through a shared list names the
 * number of days a guest's details are kept. The page belongs to no list, so
 * no API answer carries the number: it comes from the deployment's runtime
 * config, the hosted 30 unless the deployed `config.js` says otherwise.
 */

vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))

const retention = () =>
  mount(PrivacyView, { global: { plugins: [i18n] } })
    .find('[data-testid="privacy-guests-retention"]')
    .text()

beforeEach(() => {
  i18n.global.locale.value = 'en'
})

afterEach(() => {
  delete globalThis.__APP_CONFIG__
})

describe('PrivacyView: guests', () => {
  it('names the hosted 30 days, and that unredeemed vouchers expire', () => {
    expect(retention()).toMatch(/^30 days after your last shift we anonymise your details/)
    expect(retention()).toContain('Vouchers you have not redeemed by then expire.')
  })

  it('names the deployment’s own number of days', () => {
    globalThis.__APP_CONFIG__ = { GUEST_DATA_RETENTION_DAYS: '14' }
    expect(retention()).toMatch(/^14 days after/)
  })

  it('says one day in German, with Sie', () => {
    i18n.global.locale.value = 'de'
    globalThis.__APP_CONFIG__ = { GUEST_DATA_RETENTION_DAYS: '1' }
    expect(retention()).toMatch(/^Einen Tag nach Ihrer letzten Schicht anonymisieren wir/)
  })
})
