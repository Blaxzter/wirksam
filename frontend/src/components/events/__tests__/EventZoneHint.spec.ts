// @vitest-environment jsdom
import { mount } from '@vue/test-utils'

import { afterEach, describe, expect, it, vi } from 'vitest'

import EventZoneHint from '@/components/events/EventZoneHint.vue'

import * as timezones from '@/lib/timezones'
import i18n from '@/locales/i18n'

function mountHint(zone: string | null | undefined) {
  return mount(EventZoneHint, {
    props: { zone },
    global: { plugins: [i18n] },
  })
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('EventZoneHint', () => {
  it('says whose clock the times are on when the device is elsewhere', () => {
    vi.spyOn(timezones, 'browserTimeZone').mockReturnValue('Europe/Berlin')
    const wrapper = mountHint('America/New_York')
    expect(wrapper.get('[data-testid="event-zone-hint"]').text()).toContain('America/New York')
  })

  it('renders nothing in the same zone, which is what nearly everyone sees', () => {
    vi.spyOn(timezones, 'browserTimeZone').mockReturnValue('Europe/Lisbon')
    expect(mountHint('Europe/Lisbon').find('[data-testid="event-zone-hint"]').exists()).toBe(false)
  })

  it('renders nothing for the same zone under an old name', () => {
    vi.spyOn(timezones, 'browserTimeZone').mockReturnValue('Asia/Calcutta')
    expect(mountHint('Asia/Kolkata').find('[data-testid="event-zone-hint"]').exists()).toBe(false)
  })

  it.each([null, undefined])('renders nothing without a zone (%s)', (zone) => {
    expect(mountHint(zone).find('[data-testid="event-zone-hint"]').exists()).toBe(false)
  })
})
