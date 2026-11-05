import { describe, expect, it } from 'vitest'

import { normalizeApiError } from '@/lib/api-errors'
import deDuties from '@/locales/de/duties.json'
import deErrors from '@/locales/de/errorCodes.json'
import deNotifications from '@/locales/de/notifications.json'
import deTeams from '@/locales/de/teams.json'
import enDuties from '@/locales/en/duties.json'
import enErrors from '@/locales/en/errorCodes.json'
import enNotifications from '@/locales/en/notifications.json'
import enTeams from '@/locales/en/teams.json'

/**
 * Sentences that once promised something the app doesn't do, or named a role by
 * a word used nowhere else. Nothing else would notice them coming back.
 */

const LOCALES = [
  { lang: 'en', duties: enDuties, teams: enTeams, errors: enErrors, notices: enNotifications },
  { lang: 'de', duties: deDuties, teams: deTeams, errors: deErrors, notices: deNotifications },
]

describe('the error for an archived place', () => {
  it('says what happened instead of something generic', () => {
    const { message } = normalizeApiError({
      isAxiosError: true,
      response: { status: 409, data: { status: 409, code: 'voucher.point_archived' } },
    })
    expect(message).toBe(enErrors.voucher.point_archived)
  })
})

describe.each(LOCALES)('wording ($lang)', ({ lang, duties, teams, errors, notices }) => {
  const organisers = lang === 'en' ? /organiser/i : /Organisator:in/

  it('calls the people who run an event organisers in the team texts', () => {
    const texts = [
      teams.form.requiresApprovalOn,
      teams.join.description,
      teams.join.attachHint,
      teams.mine.deciderAdmins,
      errors.team.forbidden,
    ]
    for (const text of texts) {
      expect(text).toMatch(organisers)
      expect(text).not.toMatch(/admin/i)
    }
  })

  it('counts organisers among those who can book a reserved task', () => {
    expect(teams.page.subtitleAdmin).toMatch(organisers)
  })

  it('leaves room for voucher tasks when promising shifts to people in charge', () => {
    expect(duties.events.invite.tasksHint).toMatch(lang === 'en' ? /voucher/i : /Marken/)
  })

  it('sends people to the task page to publish, not to the task list', () => {
    expect(duties.events.clone.adjust.status.draft.hint).not.toMatch(
      lang === 'en' ? /task list/i : /Aufgabenliste/,
    )
  })

  it('points overnight events at single shifts, since the pattern cannot cross midnight', () => {
    const hint = duties.events.fields.defaultTimesHint
    expect(hint).not.toMatch(lang === 'en' ? /on each task/i : /bei den einzelnen Aufgaben/)
    expect(hint).toContain(duties.tasks.detail.addSingleShift)
  })

  it('does not promise a reminder on a channel that may be off, and names the inbox', () => {
    const hint = notices.reminders.channelActiveHint
    expect(hint).toMatch(lang === 'en' ? /inbox/i : /Postfach/)
    expect(hint).not.toMatch(lang === 'en' ? /You'll be notified/ : /Du wirst/)
  })

  it('has nothing left about the availability reminder, which is gone', () => {
    expect(notices.categories).not.toHaveProperty('availability')
    expect(notices.types).not.toHaveProperty('availability')
  })

  it('does not say someone else can put you on a shift', () => {
    expect(duties.availability.fullyAvailableHint).not.toMatch(
      lang === 'en' ? /scheduled/i : /eingeplant/,
    )
  })
})
