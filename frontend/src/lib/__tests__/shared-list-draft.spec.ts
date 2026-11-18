import { describe, expect, it } from 'vitest'

import type { SharedListDetail } from '@/client/types.gen'
import {
  blankDraft,
  changedFields,
  draftFromDetail,
  draftSignature,
  settingsBlockers,
  toPayload,
} from '@/lib/shared-list-draft'

/**
 * The draft the wizard edits: its defaults (correction (b): no limit per
 * person), how a list loads into it, what blocks saving, and that an edit
 * sends only what changed.
 */

function detail(overrides: Partial<SharedListDetail> = {}): SharedListDetail {
  return {
    id: 'l1',
    code: 'abc',
    title: 'Glühwein: Wer hilft mit?',
    share_note: 'Eltern 3b',
    status: 'live',
    effective_status: 'live',
    ends_mode: 'date',
    ends_on: '2026-12-06',
    closes_at: null,
    expires_soon: false,
    is_full: false,
    created_at: '2026-11-01T10:00:00',
    created_by_name: 'Anna',
    tasks: [{ id: 'k', name: 'Kitchen' }],
    only_days: null,
    excluded_shift_ids: ['s2', 's1'],
    excluded_shift_count: 2,
    capacity: 4,
    free: 2,
    signup_count: 1,
    guest_count: 1,
    view_count: 3,
    issue: null,
    access: 'admin',
    intro: null,
    ask_email: 'optional',
    ask_phone: 'required',
    show_names: 'first',
    max_per_person: 2,
    rotated_at: null,
    paused_at: null,
    ended_at: null,
    task_ids: ['k', 'tent'],
    detail_tasks: [
      {
        id: 'k',
        name: 'Kitchen',
        offered: true,
        not_offered_reason: null,
        shift_count: 2,
        capacity: 4,
        free: 2,
        only_days: null,
      },
      {
        id: 'tent',
        name: 'Tent',
        offered: false,
        not_offered_reason: 'team_locked',
        shift_count: 0,
        capacity: 0,
        free: 0,
        only_days: null,
      },
    ],
    event: {
      id: 'e1',
      name: 'Fair',
      start_date: '2026-12-05',
      end_date: '2026-12-06',
      timezone: 'Europe/Berlin',
    },
    ...overrides,
  }
}

describe('blankDraft', () => {
  it('asks for an email, not a phone, shows no names and sets no limit per person', () => {
    const draft = blankDraft()
    expect(draft).toMatchObject({
      tasks: [],
      title: '',
      titleTouched: false,
      askEmail: 'required',
      askPhone: 'off',
      showNames: 'none',
      maxPerPerson: null,
      endsMode: 'last_shift',
      endsOn: null,
    })
    expect(draft.excluded.size).toBe(0)
  })

  it('starts with the tasks given, as a copy', () => {
    const tasks = [{ id: 'k', name: 'Kitchen', unavailable: null }]
    const draft = blankDraft(tasks)
    expect(draft.tasks).toEqual(tasks)
    expect(draft.tasks).not.toBe(tasks)
  })
})

describe('draftFromDetail', () => {
  it('holds what the list has, its title counted as typed', () => {
    const draft = draftFromDetail(detail())
    expect(draft).toMatchObject({
      title: 'Glühwein: Wer hilft mit?',
      titleTouched: true,
      intro: '',
      shareNote: 'Eltern 3b',
      askEmail: 'optional',
      askPhone: 'required',
      showNames: 'first',
      maxPerPerson: 2,
      endsMode: 'date',
      endsOn: '2026-12-06',
    })
    expect([...draft.excluded]).toEqual(['s2', 's1'])
  })

  it('marks a task the list can no longer offer', () => {
    expect(draftFromDetail(detail()).tasks).toEqual([
      { id: 'k', name: 'Kitchen', unavailable: null },
      { id: 'tent', name: 'Tent', unavailable: 'team_locked' },
    ])
  })

  it('reads a missing share note as empty', () => {
    expect(draftFromDetail(detail({ share_note: null, intro: 'Hi' }))).toMatchObject({
      shareNote: '',
      intro: 'Hi',
    })
  })
})

describe('settingsBlockers', () => {
  const context = { today: '2026-12-01', lastDate: '2026-12-06' }
  const draft = { title: 'Bar', endsMode: 'last_shift' as const, endsOn: null }

  it('has nothing to say about a titled list that closes with its last shift', () => {
    expect(settingsBlockers(draft, context)).toEqual([])
  })

  it('wants a title that is more than blanks', () => {
    expect(settingsBlockers({ ...draft, title: '   ' }, context)).toEqual([{ kind: 'no_title' }])
  })

  it('wants a closing day for a list that closes on a day', () => {
    expect(settingsBlockers({ ...draft, endsMode: 'date' }, context)).toEqual([
      { kind: 'ends_on_missing' },
    ])
  })

  it('refuses a closing day that is over', () => {
    expect(settingsBlockers({ ...draft, endsMode: 'date', endsOn: '2026-11-30' }, context)).toEqual(
      [{ kind: 'ends_on_past' }],
    )
  })

  it('refuses a closing day after the last shift, naming that shift’s day', () => {
    expect(settingsBlockers({ ...draft, endsMode: 'date', endsOn: '2026-12-07' }, context)).toEqual(
      [{ kind: 'ends_on_after_last', lastDate: '2026-12-06' }],
    )
  })

  it('takes today and the last shift’s day themselves', () => {
    for (const endsOn of ['2026-12-01', '2026-12-06']) {
      expect(settingsBlockers({ ...draft, endsMode: 'date', endsOn }, context)).toEqual([])
    }
  })

  it('leaves the closing day alone when asked to, but not the title', () => {
    const untouched = { ...context, checkClosing: false }
    expect(
      settingsBlockers({ ...draft, endsMode: 'date', endsOn: '2026-11-30' }, untouched),
    ).toEqual([])
    expect(settingsBlockers({ ...draft, title: '' }, untouched)).toEqual([{ kind: 'no_title' }])
  })

  it('does not check the closing day without a last shift to hold it against', () => {
    const open = { today: '2026-12-01', lastDate: null }
    expect(settingsBlockers({ ...draft, endsMode: 'date', endsOn: '2027-01-01' }, open)).toEqual([])
  })
})

describe('toPayload', () => {
  it('trims text, turns blank text into null and sorts the exclusions', () => {
    const draft = {
      ...blankDraft([{ id: 'k', name: 'Kitchen', unavailable: null }]),
      title: '  Bar  ',
      intro: '   ',
      shareNote: ' Eltern ',
    }
    expect(toPayload(draft, ['s2', 's1'])).toEqual({
      title: 'Bar',
      intro: null,
      share_note: 'Eltern',
      task_ids: ['k'],
      excluded_shift_ids: ['s1', 's2'],
      ask_email: 'required',
      ask_phone: 'off',
      show_names: 'none',
      max_per_person: null,
      ends_mode: 'last_shift',
      ends_on: null,
    })
  })

  it('sends a closing day only with a list that closes on a day', () => {
    const draft = { ...blankDraft(), endsOn: '2026-12-06' }
    expect(toPayload(draft, []).ends_on).toBeNull()
    expect(toPayload({ ...draft, endsMode: 'date' }, []).ends_on).toBe('2026-12-06')
  })
})

describe('changedFields', () => {
  const before = toPayload(draftFromDetail(detail()), ['s1'])

  it('is empty when nothing changed', () => {
    expect(changedFields(toPayload(draftFromDetail(detail()), ['s1']), before)).toEqual({})
  })

  it('names only what changed, so an untouched selection is not checked again', () => {
    const draft = { ...draftFromDetail(detail()), title: 'New', maxPerPerson: null }
    expect(changedFields(toPayload(draft, ['s1']), before)).toEqual({
      title: 'New',
      max_per_person: null,
    })
  })

  it('sends the whole selection once it changed', () => {
    expect(changedFields(toPayload(draftFromDetail(detail()), []), before)).toEqual({
      excluded_shift_ids: [],
    })
  })
})

describe('draftSignature', () => {
  it('is the same for the same choices, whatever order the exclusions came in', () => {
    const a = { ...blankDraft(), excluded: new Set(['s1', 's2']) }
    const b = { ...blankDraft(), excluded: new Set(['s2', 's1']) }
    expect(draftSignature(a)).toBe(draftSignature(b))
  })

  it('changes with any choice', () => {
    expect(draftSignature({ ...blankDraft(), title: 'Bar' })).not.toBe(draftSignature(blankDraft()))
  })
})
