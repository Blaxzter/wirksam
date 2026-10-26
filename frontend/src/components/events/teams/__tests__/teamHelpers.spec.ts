import { describe, expect, it } from 'vitest'

import {
  addYears,
  draftFromRequirement,
  draftToPayload,
  expiryFor,
  firstName,
  initials,
  issueDateProblem,
  joinNames,
  labelKey,
  needsReview,
  newDraft,
  reusableCheckFor,
  todayIso,
} from '@/components/events/teams/teamHelpers'

import type { TeamCheckRead, TeamRequirementRead } from '@/client/types.gen'

const police: TeamRequirementRead = {
  id: 'r1',
  label: 'Erweitertes Führungszeugnis',
  description: null,
  ask_issue_date: true,
  valid_for_years: 5,
  accepts_document: false,
}

function check(fields: Partial<TeamCheckRead>): TeamCheckRead {
  return {
    requirement_id: 'other',
    label: 'Erweitertes Führungszeugnis',
    checked_at: '2026-03-01T10:00:00',
    issued_on: '2026-02-20',
    expires_on: '2031-02-20',
    expired: false,
    source_team_name: 'Aufbau',
    ...fields,
  }
}

describe('addYears', () => {
  it('adds whole years', () => {
    expect(addYears('2026-03-12', 5)).toBe('2031-03-12')
  })

  it('moves 29 February to the 28th when the target year has none', () => {
    expect(addYears('2024-02-29', 2)).toBe('2026-02-28')
    expect(addYears('2024-02-29', 4)).toBe('2028-02-29')
  })
})

describe('expiryFor / issueDateProblem', () => {
  it('counts from the issue date', () => {
    expect(expiryFor(police, '2026-03-12', '2026-10-26')).toBe('2031-03-12')
  })

  it('counts from today without an issue date', () => {
    expect(expiryFor({ ...police, ask_issue_date: false }, null, '2026-10-26')).toBe('2031-10-26')
  })

  it('never expires without a validity', () => {
    expect(expiryFor({ ...police, valid_for_years: null }, '2026-03-12')).toBeNull()
  })

  it('refuses a date in the future and one already run out', () => {
    expect(issueDateProblem(police, '2026-10-27', '2026-10-26')).toBe('future')
    expect(issueDateProblem(police, '2021-10-25', '2026-10-26')).toBe('expired')
    expect(issueDateProblem(police, '2021-10-26', '2026-10-26')).toBeNull()
    expect(issueDateProblem(police, null, '2026-10-26')).toBeNull()
  })
})

describe('todayIso', () => {
  it('formats the local date', () => {
    expect(todayIso(new Date(2026, 0, 5, 23, 30))).toBe('2026-01-05')
  })
})

describe('reusableCheckFor', () => {
  it('finds a valid check with the same label, ignoring case and spaces', () => {
    const found = reusableCheckFor(police, [check({ label: '  erweitertes   führungszeugnis ' })])
    expect(found?.source_team_name).toBe('Aufbau')
  })

  it('skips expired checks and other labels', () => {
    expect(reusableCheckFor(police, [check({ expired: true })])).toBeUndefined()
    expect(reusableCheckFor(police, [check({ label: 'Erste-Hilfe-Kurs' })])).toBeUndefined()
    expect(reusableCheckFor(police, undefined)).toBeUndefined()
  })
})

describe('drafts', () => {
  it('round-trips an existing requirement and keeps its id', () => {
    const payload = draftToPayload(draftFromRequirement({ ...police, description: 'Note' }))
    expect(payload).toEqual({
      id: 'r1',
      label: 'Erweitertes Führungszeugnis',
      description: 'Note',
      ask_issue_date: true,
      valid_for_years: 5,
      accepts_document: false,
    })
  })

  it('sends a new one without an id, blank text as null, and no zero years', () => {
    const draft = newDraft({ label: '  Kurs ', description: '   ', valid_for_years: 0 })
    expect(draftToPayload(draft)).toEqual({
      label: 'Kurs',
      description: null,
      ask_issue_date: false,
      valid_for_years: null,
      accepts_document: false,
    })
  })

  it('gives every new draft its own key', () => {
    expect(newDraft().key).not.toBe(newDraft().key)
  })
})

describe('names', () => {
  it('builds initials without the demo prefix', () => {
    expect(initials('[DEMO] Carla Meier')).toBe('CM')
    expect(initials('vera@example.com')).toBe('VE')
    expect(initials('')).toBe('?')
    expect(initials('Anna')).toBe('AN')
  })

  it('takes the first name without the demo prefix', () => {
    expect(firstName('[DEMO] Carla Meier')).toBe('Carla')
    expect(firstName('Sven')).toBe('Sven')
  })

  it('normalises labels', () => {
    expect(labelKey('  First   AID ')).toBe('first aid')
  })

  it('joins names in the active language', () => {
    expect(joinNames(['A', 'B', 'C'], 'en')).toBe('A, B, and C')
    expect(joinNames(['A', 'B'], 'de')).toBe('A und B')
  })

  it('knows which teams need the review dialog', () => {
    expect(needsReview({ requirements: [police] })).toBe(true)
    expect(needsReview({ requirements: [] })).toBe(false)
    expect(needsReview(undefined)).toBe(false)
  })
})
