// @vitest-environment jsdom
import { mount } from '@vue/test-utils'

import { beforeEach, describe, expect, it } from 'vitest'

import FillBar from '@/components/data-table/FillBar.vue'

import i18n from '@/locales/i18n'

/**
 * How full a list or task is: a progress bar a screen reader hears as one
 * sentence ("3 of 10 free"), with the same sentence on screen for everyone
 * else, and the venue map's staffing colours.
 */

function mountBar(props: { free: number; cap: number; label?: string }) {
  return mount(FillBar, { props, global: { plugins: [i18n] } })
}

const bar = (w: ReturnType<typeof mountBar>) => w.find('[role="progressbar"]')

beforeEach(() => {
  i18n.global.locale.value = 'en'
})

describe('FillBar', () => {
  it('counts the places taken, and says how many are free', () => {
    const w = mountBar({ free: 3, cap: 10 })
    expect(bar(w).attributes()).toMatchObject({
      'aria-label': 'Places',
      'aria-valuemin': '0',
      'aria-valuemax': '10',
      'aria-valuenow': '7',
      'aria-valuetext': '3 of 10 free',
    })
    expect(w.text()).toBe('3 of 10 free')
    expect(bar(w).find('div').attributes('style')).toContain('width: 70%')
  })

  it('says the sentence once to a screen reader', () => {
    const w = mountBar({ free: 3, cap: 10 })
    expect(w.find('span[aria-hidden="true"]').text()).toBe('3 of 10 free')
  })

  it('speaks German and takes its own name', () => {
    i18n.global.locale.value = 'de'
    const w = mountBar({ free: 0, cap: 4, label: 'Schichten' })
    expect(bar(w).attributes('aria-label')).toBe('Schichten')
    expect(bar(w).attributes('aria-valuetext')).toBe('0 von 4 frei')
  })

  it('takes the staffing colour of how full it is', () => {
    const fill = (free: number) =>
      bar(mountBar({ free, cap: 4 }))
        .find('div')
        .classes()
    expect(fill(0)).toContain('bg-staff-full')
    expect(fill(2)).toContain('bg-staff-partial')
    expect(fill(4)).toContain('bg-staff-short')
  })

  it('keeps nonsense in range', () => {
    const over = mountBar({ free: 12, cap: 10 })
    expect(bar(over).attributes('aria-valuenow')).toBe('0')
    expect(bar(over).attributes('aria-valuetext')).toBe('10 of 10 free')
    const empty = mountBar({ free: 0, cap: 0 })
    expect(bar(empty).attributes('aria-valuemax')).toBe('0')
    expect(bar(empty).find('div').attributes('style')).toContain('width: 0%')
  })
})
