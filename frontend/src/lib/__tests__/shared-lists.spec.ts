import { afterEach, describe, expect, it } from 'vitest'

import {
  JUST_NOW_MINUTES,
  askedFieldKeys,
  canUseSharedLists,
  effectiveStatusBadge,
  endsSummary,
  fillLevel,
  lockedForManager,
  pooledBeyond,
  relativeSignupTime,
  sharedListUrl,
} from '@/lib/shared-lists'

afterEach(() => {
  delete globalThis.__APP_CONFIG__
})

describe('canUseSharedLists', () => {
  const event = { can_manage: false, managed_task_count: 0 }

  it('is offered to whoever runs the event', () => {
    expect(canUseSharedLists({ ...event, can_manage: true })).toBe(true)
  })

  it('is offered to someone in charge of one of its tasks', () => {
    expect(canUseSharedLists({ ...event, managed_task_count: 2 })).toBe(true)
  })

  it('is not offered to a plain member, or without an event', () => {
    expect(canUseSharedLists(event)).toBe(false)
    expect(canUseSharedLists({ ...event, managed_task_count: undefined })).toBe(false)
    expect(canUseSharedLists(null)).toBe(false)
    expect(canUseSharedLists(undefined)).toBe(false)
  })

  it('is offered in a demo event too, whose lists mail nobody', () => {
    const demo = { ...event, can_manage: true, is_sandbox: true }
    expect(canUseSharedLists(demo)).toBe(true)
  })

  it('follows the deployment switch', () => {
    globalThis.__APP_CONFIG__ = { SHARED_LISTS_ENABLED: 'false' }
    expect(canUseSharedLists({ ...event, can_manage: true })).toBe(false)
    globalThis.__APP_CONFIG__ = { SHARED_LISTS_ENABLED: 'true' }
    expect(canUseSharedLists({ ...event, can_manage: true })).toBe(true)
  })
})

describe('lockedForManager', () => {
  it('locks a person in charge out of fixes once the organisers turned sharing off', () => {
    const off = { managers_share_lists: false }
    expect(lockedForManager({ access: 'manager' }, off)).toBe(true)
    expect(lockedForManager({ access: 'manager' }, { managers_share_lists: true })).toBe(false)
    expect(lockedForManager({ access: 'manager' }, null)).toBe(false)
    expect(lockedForManager({ access: 'admin' }, off)).toBe(false)
    expect(lockedForManager({ access: 'viewer' }, off)).toBe(false)
  })
})

describe('sharedListUrl', () => {
  it('puts the code under /l/ on the given origin', () => {
    expect(sharedListUrl('Ab3xYz', 'https://wirksam.app')).toBe('https://wirksam.app/l/Ab3xYz')
  })

  it('does not double a trailing slash, and escapes the code', () => {
    expect(sharedListUrl('a b', 'https://example.org/')).toBe('https://example.org/l/a%20b')
  })

  it('defaults to this deployment’s origin', () => {
    const original = globalThis.window
    globalThis.window = { location: { origin: 'http://localhost:5555' } } as Window &
      typeof globalThis
    try {
      expect(sharedListUrl('code')).toBe('http://localhost:5555/l/code')
    } finally {
      globalThis.window = original
    }
  })
})

describe('effectiveStatusBadge', () => {
  it('pulses only for a live list', () => {
    expect(effectiveStatusBadge('live')).toEqual({
      variant: 'default',
      labelKey: 'sharedLists.status.live',
      pulse: true,
    })
  })

  it('warns about a paused list and quietens closed ones', () => {
    expect(effectiveStatusBadge('paused')).toMatchObject({ variant: 'warning', pulse: false })
    expect(effectiveStatusBadge('expired')).toMatchObject({
      variant: 'outline',
      labelKey: 'sharedLists.status.expired',
    })
    expect(effectiveStatusBadge('ended')).toMatchObject({ variant: 'outline', pulse: false })
  })
})

describe('fillLevel', () => {
  it('is full once no place is free', () => {
    expect(fillLevel(0, 12)).toBe('full')
  })

  it('is partial from half the places taken, short below', () => {
    expect(fillLevel(6, 12)).toBe('partial')
    expect(fillLevel(7, 12)).toBe('short')
    expect(fillLevel(12, 12)).toBe('short')
  })

  it('has no level without places', () => {
    expect(fillLevel(0, 0)).toBe('none')
  })

  it('reads a negative free count as none free', () => {
    expect(fillLevel(-1, 4)).toBe('full')
  })
})

describe('askedFieldKeys', () => {
  it('always asks for the name, then what the list asks for', () => {
    expect(askedFieldKeys('required', 'optional')).toEqual([
      'sharedLists.settings.ask.name',
      'sharedLists.settings.ask.email.required',
      'sharedLists.settings.ask.phone.optional',
    ])
  })

  it('leaves out what is switched off', () => {
    expect(askedFieldKeys('off', 'off')).toEqual(['sharedLists.settings.ask.name'])
    expect(askedFieldKeys('optional', 'required')).toEqual([
      'sharedLists.settings.ask.name',
      'sharedLists.settings.ask.email.optional',
      'sharedLists.settings.ask.phone.required',
    ])
  })
})

describe('endsSummary', () => {
  const format = { date: (d: string) => `D(${d})`, time: (t: string) => `T(${t})` }

  it('names the start of the last shift, as written on the event’s clock', () => {
    expect(
      endsSummary(
        { ends_mode: 'last_shift', ends_on: null, closes_at: '2026-12-06T18:30:00' },
        format,
      ),
    ).toEqual({
      key: 'sharedLists.settings.ends.lastShift',
      params: { date: 'D(2026-12-06)', time: 'T(18:30)' },
    })
  })

  it('says so when no shift is ahead to close with', () => {
    expect(
      endsSummary({ ends_mode: 'last_shift', ends_on: null, closes_at: null }, format),
    ).toEqual({ key: 'sharedLists.settings.ends.lastShiftNone', params: {} })
  })

  it('names the closing day', () => {
    expect(
      endsSummary(
        { ends_mode: 'date', ends_on: '2026-12-01', closes_at: '2026-12-01T23:59:59.999999' },
        format,
      ),
    ).toEqual({ key: 'sharedLists.settings.ends.date', params: { date: 'D(2026-12-01)' } })
  })

  it('closes by hand', () => {
    expect(endsSummary({ ends_mode: 'manual', ends_on: null, closes_at: null }, format)).toEqual({
      key: 'sharedLists.settings.ends.manual',
      params: {},
    })
  })
})

describe('relativeSignupTime', () => {
  // Local noon, so the calendar-day arithmetic cannot straddle midnight in any zone.
  const now = new Date(2026, 10, 12, 12, 0, 0)
  /** `now` minus `ms`, written the way the API sends it: naive UTC. */
  const ago = (ms: number) => new Date(now.getTime() - ms).toISOString().replace('Z', '')

  it('says "just now" for the first few minutes', () => {
    expect(relativeSignupTime(ago(60_000), now)).toEqual({
      key: 'sharedLists.signups.when.justNow',
      count: 0,
    })
  })

  it('says "just now" for a clock that runs a little ahead', () => {
    expect(relativeSignupTime(ago(-60_000), now)?.key).toBe('sharedLists.signups.when.justNow')
  })

  it('says "today" later the same day', () => {
    expect(relativeSignupTime(ago((JUST_NOW_MINUTES + 1) * 60_000), now)).toEqual({
      key: 'sharedLists.signups.when.today',
      count: 0,
    })
  })

  it('says "yesterday" for the day before, whatever the hour', () => {
    expect(relativeSignupTime(ago(13 * 3_600_000), now)).toEqual({
      key: 'sharedLists.signups.when.yesterday',
      count: 1,
    })
  })

  it('counts whole days after that', () => {
    expect(relativeSignupTime(ago(3 * 86_400_000), now)).toEqual({
      key: 'sharedLists.signups.when.daysAgo',
      count: 3,
    })
  })

  it('reads the value as UTC whether or not it says so', () => {
    const iso = new Date(now.getTime() - 2 * 86_400_000).toISOString()
    expect(relativeSignupTime(iso, now)?.count).toBe(2)
  })

  it('gives nothing for a value it cannot read', () => {
    expect(relativeSignupTime('not a date', now)).toBeNull()
  })
})

describe('pooledBeyond', () => {
  const row = (email: string | null, pooled: number) => ({ email, pooled_signups: pooled })

  it('counts the other sign-ups of a confirmed address', () => {
    expect(pooledBeyond([row('fam@example.org', 2)])).toBe(2)
  })

  it('leaves out the ones that are selected too, and counts each address once', () => {
    const family = [row('fam@example.org', 2), row('fam@example.org', 2)]
    expect(pooledBeyond(family)).toBe(1)
    expect(pooledBeyond([...family, row('fam@example.org', 2)])).toBe(0)
    expect(pooledBeyond([...family, row('other@example.org', 1)])).toBe(2)
  })

  it('counts nothing for sign-ups no confirmed address pools', () => {
    expect(pooledBeyond([])).toBe(0)
    expect(pooledBeyond([row('anna@example.org', 0), row(null, 0)])).toBe(0)
  })

  it('counts a row on its own when its address is not there to go by', () => {
    expect(pooledBeyond([row(null, 1), row(null, 1)])).toBe(2)
  })
})
