import { describe, expect, it } from 'vitest'

import { dayGroup, groupByDay, noticeTime, notificationTarget } from '@/lib/notifications'

/** How the server writes a moment: naive UTC, no `Z`. */
const naive = (d: Date) => d.toISOString().slice(0, -1)

// Tuesday 3 November 2026, 14:00 in the reader's own zone.
const NOW = new Date(2026, 10, 3, 14, 0)
const at = (day: number, hour: number, minute = 0) => new Date(2026, 10, day, hour, minute)

const t = (key: string, named?: Record<string, unknown>) =>
  named ? `${key}${JSON.stringify(named)}` : key

describe('notificationTarget', () => {
  it('opens the invitation before its event', () => {
    expect(notificationTarget({ event_id: 'e1', token: 'tok' })).toEqual({
      kind: 'invitation',
      to: { name: 'invite-accept', params: { token: 'tok' } },
    })
  })

  it('opens the task for task and booking notices', () => {
    const task = { kind: 'task', to: { name: 'task-detail', params: { eventId: 't1' } } }
    expect(notificationTarget({ task_id: 't1', event_id: 'e1' })).toEqual(task)
    expect(notificationTarget({ booking_id: 'b1', slot_id: 's1', task_id: 't1' })).toEqual(task)
  })

  it('opens the team on the Teams page', () => {
    expect(notificationTarget({ team_id: 'tm1', event_id: 'e1', user_id: 'u1' })).toEqual({
      kind: 'team',
      to: { name: 'teams', params: { eventId: 'e1' }, query: { team: 'tm1' } },
    })
  })

  it('opens the event, or my bookings', () => {
    expect(notificationTarget({ event_id: 'e1' })).toEqual({
      kind: 'event',
      to: { name: 'event-settings', params: { eventId: 'e1' } },
    })
    expect(notificationTarget({ booking_id: 'b1' })).toEqual({
      kind: 'bookings',
      to: { name: 'my-bookings' },
    })
  })

  it('has nowhere to go without ids', () => {
    expect(notificationTarget(null)).toBeNull()
    expect(notificationTarget(undefined)).toBeNull()
    expect(notificationTarget({ user_id: 'u1' })).toBeNull()
    // A removed task leaves `task_id: null` behind; that is no target.
    expect(notificationTarget({ task_id: null, team_id: 'tm1' })).toBeNull()
    expect(notificationTarget({ token: '' })).toBeNull()
  })
})

describe('dayGroup', () => {
  it('goes by the calendar day, not by 24 hours', () => {
    expect(dayGroup(at(3, 0, 1), NOW)).toBe('today')
    expect(dayGroup(at(2, 23, 59), NOW)).toBe('yesterday')
    expect(dayGroup(at(2, 0, 0), NOW)).toBe('yesterday')
    expect(dayGroup(at(1, 23, 59), NOW)).toBe('earlier')
  })

  it('counts a moment a little ahead of the reader’s clock as today', () => {
    expect(dayGroup(at(3, 14, 2), NOW)).toBe('today')
  })

  it('knows yesterday across the start of a month', () => {
    const first = new Date(2026, 11, 1, 9, 0)
    expect(dayGroup(new Date(2026, 10, 30, 20, 0), first)).toBe('yesterday')
  })
})

describe('groupByDay', () => {
  it('keeps the order and leaves out empty groups', () => {
    const items = [
      { id: 'a', created_at: naive(at(3, 13, 55)) },
      { id: 'b', created_at: naive(at(3, 12, 0)) },
      { id: 'c', created_at: naive(at(1, 18, 40)) },
    ]
    expect(groupByDay(items, NOW)).toEqual([
      { key: 'today', items: [items[0], items[1]] },
      { key: 'earlier', items: [items[2]] },
    ])
  })

  it('puts a notice without a readable date under "earlier"', () => {
    const items = [
      { id: 'a', created_at: naive(at(2, 18, 40)) },
      { id: 'b', created_at: 'not a date' },
    ]
    expect(groupByDay(items, NOW).map((g) => [g.key, g.items.map((i) => i.id)])).toEqual([
      ['yesterday', ['a']],
      ['earlier', ['b']],
    ])
  })

  it('has no groups for no notices', () => {
    expect(groupByDay([], NOW)).toEqual([])
  })
})

describe('noticeTime', () => {
  it('reads minutes and hours today', () => {
    expect(noticeTime(naive(at(3, 13, 59)), NOW, t, 'en')).toBe(
      'notifications.timeAgo.minutes{"n":1}',
    )
    expect(noticeTime(naive(new Date(NOW.getTime() - 20_000)), NOW, t, 'en')).toBe(
      'notifications.timeAgo.justNow',
    )
    expect(noticeTime(naive(at(3, 13, 55)), NOW, t, 'en')).toBe(
      'notifications.timeAgo.minutes{"n":5}',
    )
    expect(noticeTime(naive(at(3, 11, 50)), NOW, t, 'en')).toBe(
      'notifications.timeAgo.hours{"n":2}',
    )
  })

  it('reads a moment just ahead of the clock as just now', () => {
    expect(noticeTime(naive(at(3, 14, 1)), NOW, t, 'en')).toBe('notifications.timeAgo.justNow')
  })

  it('says "yesterday" with the time', () => {
    expect(noticeTime(naive(at(2, 18, 40)), NOW, t, 'de')).toBe(
      'notifications.time.yesterday{"time":"18:40"}',
    )
  })

  it('gives the date and time further back, the year only from another one', () => {
    expect(noticeTime(naive(at(1, 9, 5)), NOW, t, 'de')).toBe('So., 1. Nov., 09:05')
    expect(noticeTime(naive(new Date(2025, 11, 30, 9, 5)), NOW, t, 'de')).toBe(
      'Di., 30. Dez. 2025, 09:05',
    )
  })

  it('is empty for an unreadable date', () => {
    expect(noticeTime('', NOW, t, 'en')).toBe('')
  })
})
