/**
 * E2E tests for event teams: a team decides who may book a task.
 *
 * The flow spans three people's screens, so it lives with the multi-user
 * specs:
 *
 * 1. An organiser creates a team with a requirement on the Teams page and
 *    reserves a task for it in the task form.
 * 2. A volunteer outside the team sees the task locked and cannot book it.
 * 3. They ask to join from the Teams page, attaching a file for the
 *    requirement.
 * 4. The organiser reviews the request: Approve stays disabled until the check
 *    is ticked and its issue date entered. Approving deletes the file.
 * 5. The volunteer can now book the shift.
 *
 * Each test gets its own event, so the teams never leak into the worker event
 * (a team there would add a Teams entry to every later test's sidebar). The
 * volunteer is a disposable user: they join things, and the shared member must
 * not.
 */
import type { Page } from '@playwright/test'

import type { EventTeamMemberRead, EventTeamRead } from '../../../src/client/types.gen.js'
import { expect, test } from '../../fixtures.js'
import {
  API,
  type EventRead,
  type ShiftRead,
  type TaskRead,
  addMember,
  api,
  apiStatus,
  createEvent,
  createTaskWithShifts,
  deleteEvent,
  deleteTask,
  futureDate,
  listShifts,
  uniqueName,
} from '../../helpers/api.js'
import { pickDate } from '../../helpers/ui.js'

/** The smallest file the server recognises as a PDF (it reads the magic bytes). */
const SAMPLE_PDF = {
  name: 'first-aid-certificate.pdf',
  mimeType: 'application/pdf',
  buffer: Buffer.from('%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n'),
}

/** A first-aid style requirement: issue date asked, valid two years, file allowed. */
const FIRST_AID = {
  label: 'First aid course',
  ask_issue_date: true,
  valid_for_years: 2,
  accepts_document: true,
}

function teamsUrl(eventId: string): string {
  return `/app/teams/${eventId}`
}

async function listTeams(page: Page, eventId: string): Promise<EventTeamRead[]> {
  return api<EventTeamRead[]>(page, 'GET', `/events/${eventId}/teams`)
}

/**
 * Attach a file to the caller's own waiting request (multipart, field `file`).
 * Sent from inside the page so the fixture's header names the caller.
 */
async function attachDocument(
  page: Page,
  eventId: string,
  teamId: string,
  requirementId: string,
): Promise<number> {
  return page.evaluate(
    async ({ url, text, name, type }) => {
      const form = new FormData()
      form.append('file', new Blob([text], { type }), name)
      const res = await fetch(url, { method: 'PUT', body: form })
      return res.status
    },
    {
      url: `${API}/events/${eventId}/teams/${teamId}/join/documents/${requirementId}`,
      text: SAMPLE_PDF.buffer.toString('latin1'),
      name: SAMPLE_PDF.name,
      type: SAMPLE_PDF.mimeType,
    },
  )
}

async function createTeam(
  page: Page,
  eventId: string,
  body: { name: string; requires_approval?: boolean; requirements?: object[] },
): Promise<EventTeamRead> {
  return api<EventTeamRead>(page, 'POST', `/events/${eventId}/teams`, body)
}

let event: EventRead
let task: TaskRead
let shift: ShiftRead

test.beforeEach(async ({ adminPage }) => {
  event = await createEvent(adminPage, uniqueName('E2E Teams'), 'published', 'private', {
    start: futureDate(1),
    end: futureDate(3),
  })
  const created = await createTaskWithShifts(adminPage, {
    name: uniqueName('E2E Ticket Booth'),
    eventId: event.id,
    status: 'published',
    startDate: futureDate(1),
    endDate: futureDate(1),
    startTime: '10:00',
    endTime: '11:00',
    slotDuration: 60,
    peoplePerShift: 2,
  })
  task = created.task
  ;[shift] = await listShifts(adminPage, task.id)
})

test.afterEach(async ({ adminPage }) => {
  // Tasks outlive their event, so they go first; the event takes its teams,
  // requests, checks and files with it.
  await deleteTask(adminPage, task.id).catch(() => {})
  await deleteEvent(adminPage, event.id).catch(() => {})
})

// ── Organiser: setting a team up ────────────────────────────────────────────

test.describe('Event teams – setting up', () => {
  test('an organiser creates a team with a requirement from the Teams page', async ({
    adminPage,
  }) => {
    const name = uniqueName('Kasse')
    await adminPage.goto(teamsUrl(event.id))
    await expect(adminPage.getByTestId('teams-empty')).toBeVisible()

    await adminPage.getByTestId('btn-create-team').click()
    const form = adminPage.getByTestId('team-form-dialog')
    await expect(form).toBeVisible()
    await form.getByTestId('team-name').fill(name)
    await form.getByTestId('btn-add-preset-firstAid').click()
    await expect(form.getByTestId('team-requirement-0')).toBeVisible()
    await form.getByTestId('btn-save-team').click()
    await expect(form).toBeHidden()

    await expect(adminPage.getByTestId('teams-manage-list')).toContainText(name)

    // The preset's rules reached the server, not just its label.
    const [team] = await listTeams(adminPage, event.id)
    expect(team.name).toBe(name)
    expect(team.requires_approval).toBe(true)
    expect(team.requirements).toHaveLength(1)
    expect(team.requirements?.[0]).toMatchObject({
      ask_issue_date: true,
      valid_for_years: 2,
      accepts_document: true,
    })
  })

  test('the task form reserves a task for one team', async ({ adminPage }) => {
    const team = await createTeam(adminPage, event.id, { name: uniqueName('Kasse') })

    await adminPage.goto(`/app/tasks/${task.id}/edit`)
    const section = adminPage.getByTestId('section-who-can-book')
    await expect(section).toBeVisible()
    await section.getByTestId('task-team-mode-team').click()
    await section.getByTestId('task-team').click()
    await adminPage.getByTestId(`team-option-${team.id}`).click()
    await expect(section.getByTestId('task-team')).toContainText(team.name)
    await adminPage.getByTestId('btn-submit').click()

    await expect
      .poll(async () => (await api<TaskRead>(adminPage, 'GET', `/tasks/${task.id}`)).team_id)
      .toBe(team.id)
  })

  test('a volunteer sees the Teams page without the organiser controls', async ({
    adminPage,
    disposablePage,
    disposableUser,
  }) => {
    const team = await createTeam(adminPage, event.id, { name: uniqueName('Aufbau') })
    await addMember(adminPage, disposablePage, event.id, disposableUser.email)

    await disposablePage.goto(teamsUrl(event.id))
    await expect(disposablePage.getByTestId(`btn-join-team-${team.id}`)).toBeVisible()
    await expect(disposablePage.getByTestId('btn-create-team')).toHaveCount(0)
    await expect(disposablePage.getByTestId('teams-manage-list')).toHaveCount(0)
  })
})

// ── The whole way: locked, asked, reviewed, booked ──────────────────────────

test.describe('Event teams – asking, reviewing and booking', () => {
  let team: EventTeamRead
  let requirementId: string

  test.beforeEach(async ({ adminPage, disposablePage, disposableUser }) => {
    team = await createTeam(adminPage, event.id, {
      name: uniqueName('Sanitätsdienst'),
      requires_approval: true,
      requirements: [FIRST_AID],
    })
    requirementId = team.requirements![0].id
    await api(adminPage, 'PATCH', `/tasks/${task.id}`, { team_id: team.id })
    await addMember(adminPage, disposablePage, event.id, disposableUser.email)
  })

  test('a non-member cannot book a reserved task', async ({ disposablePage }) => {
    await disposablePage.goto(`/app/tasks/${task.id}`)
    await expect(disposablePage.getByTestId('task-team-gate')).toContainText(team.name)
    await expect(disposablePage.getByTestId(`shift-team-locked-${shift.id}`)).toBeVisible()

    // The card opens the shift dialog, which offers the team instead of booking.
    await disposablePage.getByTestId(`shift-card-${shift.id}`).click()
    const dialog = disposablePage.getByTestId('dialog-shift-detail')
    await expect(dialog.getByTestId('shift-team-note')).toContainText(team.name)
    await expect(dialog.getByTestId('btn-book-shift')).toHaveCount(0)

    // And the server refuses it all the same.
    expect(await apiStatus(disposablePage, 'POST', '/bookings/', { shift_id: shift.id })).toBe(403)
  })

  test('asking with a file, approving after the check, then booking', async ({
    adminPage,
    disposablePage,
    disposableUser,
  }) => {
    // ── The volunteer asks to join and attaches their certificate ──
    await disposablePage.goto(teamsUrl(event.id))
    await disposablePage.getByTestId(`btn-join-team-${team.id}`).click()
    const join = disposablePage.getByTestId('team-join-dialog')
    await expect(join).toBeVisible()
    await join
      .getByTestId(`team-join-file-${requirementId}`)
      .locator('input[type="file"]')
      .setInputFiles(SAMPLE_PDF)
    await expect(join.getByTestId(`team-join-file-${requirementId}`)).toContainText(SAMPLE_PDF.name)
    await join.getByTestId('team-join-note').fill('I renewed my course this spring.')
    await join.getByTestId('btn-team-join-send').click()
    await expect(join).toBeHidden()

    await expect
      .poll(async () => {
        const mine = (await listTeams(disposablePage, event.id)).find((t) => t.id === team.id)
        return { status: mine?.my_status, files: mine?.my_documents?.length }
      })
      .toEqual({ status: 'pending', files: 1 })

    // ── The organiser reviews it ──
    await adminPage.goto(teamsUrl(event.id))
    const request = adminPage
      .getByTestId('team-requests')
      .locator('li')
      .filter({ hasText: disposableUser.name })
    await expect(request).toContainText(team.name)
    await expect(request).toContainText('I renewed my course this spring.')
    await request.locator('[data-testid^="btn-review-team-request-"]').click()

    const review = adminPage.getByTestId('team-review-dialog')
    await expect(review).toBeVisible()
    await expect(review.getByTestId('team-document-open')).toBeVisible()

    const approve = review.getByTestId('btn-team-review-approve')
    await expect(approve).toBeDisabled()
    await expect(review.getByTestId('team-review-hint')).toBeVisible()

    // Ticking alone is not enough: this requirement asks for the issue date.
    await review.getByTestId(`team-check-${requirementId}`).click()
    await expect(approve).toBeDisabled()
    const issued = new Date()
    issued.setMonth(issued.getMonth() - 6)
    await pickDate(
      review.getByTestId(`team-issued-${requirementId}`).getByRole('button'),
      issued.toISOString().slice(0, 10),
    )
    await expect(approve).toBeEnabled()
    await approve.click()
    await expect(review).toBeHidden()
    await expect(adminPage.getByTestId('team-requests')).toHaveCount(0)

    // The check is what remains; the file is gone with the decision.
    const members = await api<EventTeamMemberRead[]>(
      adminPage,
      'GET',
      `/events/${event.id}/teams/${team.id}/members`,
    )
    const row = members.find((m) => m.user_id === disposableUser.id)
    expect(row?.status).toBe('approved')
    expect(row?.checks?.map((c) => c.requirement_id)).toEqual([requirementId])
    expect(
      await apiStatus(
        adminPage,
        'GET',
        `/events/${event.id}/teams/${team.id}/members/${disposableUser.id}/documents/${requirementId}`,
      ),
    ).toBe(404)

    // ── Now the volunteer can book ──
    await disposablePage.goto(`/app/tasks/${task.id}`)
    await expect(disposablePage.getByTestId(`shift-card-${shift.id}`)).toBeVisible()
    await expect(disposablePage.getByTestId(`shift-team-locked-${shift.id}`)).toHaveCount(0)
    await disposablePage.getByTestId(`shift-card-${shift.id}`).click()
    await disposablePage.getByTestId('btn-dialog-confirm').click()
    await expect(disposablePage.getByTestId(`shift-card-${shift.id}`)).toContainText('1/2')
  })

  test('declining keeps the task locked and deletes the file', async ({
    adminPage,
    disposablePage,
    disposableUser,
  }) => {
    await api(disposablePage, 'POST', `/events/${event.id}/teams/${team.id}/join`, {
      message: null,
    })
    expect(await attachDocument(disposablePage, event.id, team.id, requirementId)).toBe(200)

    await adminPage.goto(teamsUrl(event.id))
    await adminPage
      .getByTestId('team-requests')
      .locator('li')
      .filter({ hasText: disposableUser.name })
      .locator('[data-testid^="btn-review-team-request-"]')
      .click()
    const review = adminPage.getByTestId('team-review-dialog')
    await review.getByTestId('btn-team-review-decline').click()
    await expect(review).toBeHidden()
    await expect(adminPage.getByTestId('team-requests')).toHaveCount(0)

    const mine = (await listTeams(disposablePage, event.id)).find((t) => t.id === team.id)
    expect(mine?.my_status).toBe('declined')
    expect(mine?.my_documents ?? []).toHaveLength(0)
    expect(
      await apiStatus(
        adminPage,
        'GET',
        `/events/${event.id}/teams/${team.id}/members/${disposableUser.id}/documents/${requirementId}`,
      ),
    ).toBe(404)
    expect(await apiStatus(disposablePage, 'POST', '/bookings/', { shift_id: shift.id })).toBe(403)
  })
})
