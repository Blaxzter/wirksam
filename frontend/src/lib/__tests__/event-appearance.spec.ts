import { describe, expect, it } from 'vitest'

import {
  EVENT_BASE_COLORS,
  EVENT_PRIMARY_COLORS,
  EVENT_SECONDARY_COLORS,
  eventColourAttr,
  eventInitial,
  eventLogoUrl,
  hasDarkTile,
  isEventBaseColor,
  isEventPrimaryColor,
  isEventSecondaryColor,
  isWordmark,
} from '@/lib/event-appearance'

describe('isEventPrimaryColor', () => {
  it('accepts every preset and nothing else', () => {
    for (const colour of EVENT_PRIMARY_COLORS) expect(isEventPrimaryColor(colour)).toBe(true)
    // Too light to read as text: a secondary colour only.
    expect(isEventPrimaryColor('yellow')).toBe(false)
    expect(isEventPrimaryColor('#ff0000')).toBe(false)
    expect(isEventPrimaryColor(null)).toBe(false)
    expect(isEventPrimaryColor(undefined)).toBe(false)
  })
})

describe('isEventSecondaryColor', () => {
  it('accepts every preset, yellow and green included, and nothing else', () => {
    for (const colour of EVENT_SECONDARY_COLORS) expect(isEventSecondaryColor(colour)).toBe(true)
    expect(isEventSecondaryColor('yellow')).toBe(true)
    expect(isEventSecondaryColor('chartreuse')).toBe(false)
    expect(isEventSecondaryColor(null)).toBe(false)
  })
})

describe('isEventBaseColor', () => {
  it('accepts every base tone and nothing else', () => {
    for (const name of EVENT_BASE_COLORS) expect(isEventBaseColor(name)).toBe(true)
    expect(EVENT_BASE_COLORS).toContain('primary')
    expect(EVENT_BASE_COLORS).toContain('neutral')
    for (const value of ['cream', 'yellow', '', null, undefined, 3]) {
      expect(isEventBaseColor(value)).toBe(false)
    }
  })
})

describe('eventColourAttr', () => {
  it('passes a preset of the kind on', () => {
    expect(eventColourAttr('primary', 'teal')).toBe('teal')
    expect(eventColourAttr('secondary', 'yellow')).toBe('yellow')
    expect(eventColourAttr('base', 'primary')).toBe('primary')
  })

  it('takes an own colour, in lower case', () => {
    expect(eventColourAttr('primary', '#1E6BB8')).toBe('#1e6bb8')
    expect(eventColourAttr('base', '#2e7d32')).toBe('#2e7d32')
  })

  it('has nothing for no colour, a preset of another kind, or something unknown', () => {
    expect(eventColourAttr('primary', null)).toBeUndefined()
    expect(eventColourAttr('primary', undefined)).toBeUndefined()
    expect(eventColourAttr('primary', 'yellow')).toBeUndefined()
    expect(eventColourAttr('base', 'chartreuse')).toBeUndefined()
    expect(eventColourAttr('secondary', 42)).toBeUndefined()
  })
})

describe('isWordmark', () => {
  it('is a logo at least twice as wide as tall', () => {
    expect(isWordmark({ logo_width: 512, logo_height: 128 })).toBe(true)
    expect(isWordmark({ logo_width: 200, logo_height: 100 })).toBe(true)
    expect(isWordmark({ logo_width: 190, logo_height: 100 })).toBe(false)
    expect(isWordmark({ logo_width: 64, logo_height: 64 })).toBe(false)
  })

  it('is not one without a size', () => {
    expect(isWordmark({ logo_width: null, logo_height: 64 })).toBe(false)
    expect(isWordmark({ logo_width: 64, logo_height: 0 })).toBe(false)
    expect(isWordmark({})).toBe(false)
    expect(isWordmark(null)).toBe(false)
  })
})

describe('eventLogoUrl', () => {
  it('points at the logo with its version, so a new logo is a new URL', () => {
    expect(eventLogoUrl({ id: 'e1', logo_etag: 'abc' })).toBe(
      `${import.meta.env.VITE_API_URL}/events/e1/logo?v=abc`,
    )
  })

  it('is null without a logo', () => {
    expect(eventLogoUrl({ id: 'e1', logo_etag: null })).toBeNull()
    expect(eventLogoUrl({ id: 'e1' })).toBeNull()
    expect(eventLogoUrl(null)).toBeNull()
    expect(eventLogoUrl(undefined)).toBeNull()
  })

  it('points at the version for dark mode, which only counts beside the logo', () => {
    const api = import.meta.env.VITE_API_URL
    expect(eventLogoUrl({ id: 'e1', logo_etag: 'abc', logo_dark_etag: 'def' }, 'dark')).toBe(
      `${api}/events/e1/logo/dark?v=def`,
    )
    expect(eventLogoUrl({ id: 'e1', logo_etag: 'abc' }, 'dark')).toBeNull()
    expect(eventLogoUrl({ id: 'e1', logo_etag: null, logo_dark_etag: 'def' }, 'dark')).toBeNull()
  })
})

describe('hasDarkTile', () => {
  it('is on unless switched off', () => {
    expect(hasDarkTile({ id: 'e1', logo_dark_tile: true })).toBe(true)
    expect(hasDarkTile({ id: 'e1' })).toBe(true)
    expect(hasDarkTile(null)).toBe(true)
    expect(hasDarkTile({ id: 'e1', logo_dark_tile: false })).toBe(false)
  })
})

describe('eventInitial', () => {
  it('takes the first letter, upper-cased', () => {
    expect(eventInitial('summer fair')).toBe('S')
    expect(eventInitial('  über uns')).toBe('Ü')
  })

  it('keeps a character that is more than one code unit whole', () => {
    expect(eventInitial('🎪 Zirkus')).toBe('🎪')
  })

  it('has a stand-in for an empty name', () => {
    expect(eventInitial('')).toBe('?')
    expect(eventInitial('   ')).toBe('?')
    expect(eventInitial(null)).toBe('?')
  })
})
