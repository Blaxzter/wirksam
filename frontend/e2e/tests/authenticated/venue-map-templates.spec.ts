/**
 * E2E tests for venue plan templates: save a drawn plan as a template from
 * the plan menu, start a new plan from it in "New map", and manage (rename,
 * delete) the template from the same dialog.
 *
 * Runs as a disposable organiser in an event of their own (see e2e/CLAUDE.md);
 * templates belong to that account and go with it at teardown.
 *
 * Every step is checked through the API: a template is a copy of the drawing
 * only, so the new plan must have the shapes but neither the place link nor
 * the pin of the original.
 */
import { expect, test } from '../../fixtures.js'
import {
  type EventRead,
  api,
  batchShapes,
  createEvent,
  createLocation,
  createMarker,
  createVenuePlan,
  deleteEvent,
  futureDate,
  getPlanShapes,
  setSelectedEvent,
  uniqueName,
} from '../../helpers/api.js'

type TemplateSummary = { id: string; name: string; shape_count: number }

let event: EventRead

test.beforeEach(async ({ disposablePage: page }) => {
  event = await createEvent(page, uniqueName('E2E Map Templates'), 'published', 'private', {
    start: futureDate(1),
    end: futureDate(3),
  })
  await setSelectedEvent(page, event.id)
})

test.afterEach(async ({ disposablePage: page }) => {
  await deleteEvent(page, event.id).catch(() => {})
})

test.describe('Venue plan templates', () => {
  test('save a plan as a template, start a new plan from it, rename and delete it', async ({
    disposablePage: page,
  }) => {
    const location = await createLocation(page, event.id, { name: 'Bühne' })
    const plan = await createVenuePlan(page, event.id, 'Festwiese')
    await batchShapes(page, plan.id, [
      {
        op: 'create',
        shape: {
          id: crypto.randomUUID(),
          kind: 'rect',
          style: 'stage',
          points: [
            [0.1, 0.1],
            [0.4, 0.4],
          ],
          label: 'Bühne',
          location_id: location.id,
        },
      },
    ])
    await createMarker(page, plan.id, { kind: 'entrance', x: 0.6, y: 0.6 })

    await page.goto(`/app/event-settings/${event.id}?tab=map`)
    const editor = page.getByTestId('venue-map-editor')
    await expect(editor.getByTestId('editor-canvas')).toBeVisible()

    // ── Save as template ──
    await editor.getByTestId('plan-actions').click()
    await page.getByTestId('plan-save-template').click()
    const nameInput = page.getByTestId('template-name-input')
    await expect(nameInput).toHaveValue('Festwiese')
    await nameInput.fill('Wiese mit Bühne')
    await page.getByTestId('template-name-save').click()
    await expect(page.getByTestId('template-name-dialog')).toHaveCount(0)

    let templates = await api<TemplateSummary[]>(page, 'GET', '/venue-templates')
    expect(templates).toHaveLength(1)
    expect(templates[0]).toMatchObject({ name: 'Wiese mit Bühne', shape_count: 1 })
    const templateId = templates[0]!.id

    // ── A new plan from the template ──
    await editor.getByTestId('plan-add').click()
    await page.getByTestId('plan-create-template').click()
    const card = page.getByTestId(`template-card-${templateId}`)
    await expect(card).toBeVisible()
    await expect(card.getByTestId('template-thumb')).toBeVisible()
    await card.locator('label').click()
    await expect(page.getByTestId('plan-name-input')).toHaveValue('Wiese mit Bühne')
    await page.getByTestId('plan-name-input').fill('Zweite Wiese')
    await page.getByTestId('plan-name-save').click()
    await expect(page.getByRole('dialog')).toHaveCount(0)

    const map = await api<{ plans: { id: string; name: string; markers?: unknown[] }[] }>(
      page,
      'GET',
      `/events/${event.id}/venue-map`,
    )
    const copy = map.plans.find((p) => p.name === 'Zweite Wiese')
    expect(copy).toBeTruthy()
    expect(copy!.markers ?? []).toHaveLength(0)
    const { shapes } = await getPlanShapes(page, copy!.id)
    expect(shapes).toHaveLength(1)
    expect(shapes[0]).toMatchObject({ kind: 'rect', style: 'stage', label: 'Bühne' })
    expect(shapes[0]!.location_id ?? null).toBeNull()

    // ── Rename and delete from "New map" ──
    await editor.getByTestId('plan-add').click()
    await page.getByTestId('plan-create-template').click()
    await card.getByTestId('template-actions').click()
    await page.getByTestId('template-rename').click()
    await page.getByTestId('template-name-input').fill('Sommerwiese')
    await page.getByTestId('template-name-save').click()
    await expect(card).toContainText('Sommerwiese')

    await card.getByTestId('template-actions').click()
    await page.getByTestId('template-delete').click()
    await page.getByTestId('btn-dialog-confirm').click()
    await expect(card).toHaveCount(0)
    await expect(page.getByTestId('template-list-empty')).toBeVisible()

    templates = await api<TemplateSummary[]>(page, 'GET', '/venue-templates')
    expect(templates).toHaveLength(0)
  })
})
