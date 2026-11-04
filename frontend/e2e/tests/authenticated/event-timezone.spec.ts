/**
 * An event's time zone, from the create form to the settings and the quiet hint.
 *
 * What the zone does to reminders, cut-offs and vouchers is the backend's and is
 * tested there (`tests/api/routes/test_event_timezone.py`). This is the part only
 * a browser can show: the picker, what is said before a change is saved, and
 * that someone in the event's own zone sees nothing new at all.
 */
import { expect, test } from '../../fixtures.js'
import {
  type EventRead,
  api,
  createEvent,
  createTaskWithShifts,
  deleteEvent,
  futureDate,
  uniqueName,
} from '../../helpers/api.js'
import { pickDate } from '../../helpers/ui.js'

test.describe('Event time zone', () => {
  test('an event created with a chosen zone shows it again in the settings', async ({
    adminPage: page,
  }) => {
    await page.goto('/app/events/create')

    // New events start in the device's own zone.
    const own = await page.evaluate(() => Intl.DateTimeFormat().resolvedOptions().timeZone)
    await expect(page.getByTestId('timezone-picker-value')).toHaveText(own.replaceAll('_', ' '))

    await page.getByTestId('input-event-name').fill(uniqueName('E2E Time Zone'))
    await pickDate(page.getByTestId('picker-start-date').getByRole('button'), futureDate(30))
    await pickDate(page.getByTestId('picker-end-date').getByRole('button'), futureDate(34))

    await page.getByTestId('timezone-picker').click()
    await page.getByTestId('timezone-picker-input').fill('tokyo')
    await page.getByTestId('timezone-option-Asia/Tokyo').click()
    await expect(page.getByTestId('timezone-picker-value')).toHaveText('Asia/Tokyo')

    const [response] = await Promise.all([
      page.waitForResponse((r) => r.url().includes('/events/') && r.request().method() === 'POST'),
      page.getByTestId('btn-submit-create-event').click(),
    ])
    const created = (await response.json()) as EventRead
    expect(created.timezone).toBe('Asia/Tokyo')
    await expect(page).toHaveURL(/\/app\/events$/)

    await page.goto(`/app/event-settings/${created.id}`)
    await expect(page.getByTestId('timezone-picker-value')).toHaveText('Asia/Tokyo')

    await deleteEvent(page, created.id).catch(() => {})
  })

  test('changing the zone says what happens before it is saved', async ({ adminPage: page }) => {
    const event = await createEvent(page, uniqueName('E2E Time Zone Change'))
    await page.goto(`/app/event-settings/${event.id}`)
    await expect(page.getByTestId('timezone-picker-value')).toBeVisible()
    await expect(page.getByTestId('timezone-change-note')).toBeHidden()

    await page.getByTestId('timezone-picker').click()
    await page.getByTestId('timezone-picker-input').fill('new york')
    await page.getByTestId('timezone-option-America/New_York').click()

    await expect(page.getByTestId('timezone-change-note')).toContainText('America/New York')

    const [saved] = await Promise.all([
      page.waitForResponse(
        (r) => r.url().includes(`/events/${event.id}`) && r.request().method() === 'PATCH',
      ),
      page.getByRole('button', { name: /save/i }).first().click(),
    ])
    expect(((await saved.json()) as EventRead).timezone).toBe('America/New_York')

    await deleteEvent(page, event.id).catch(() => {})
  })

  test.describe('on a device in Lisbon', () => {
    test.use({ contextOptions: { timezoneId: 'Europe/Lisbon' } })

    test('the task page mentions the zone only when the event is elsewhere', async ({
      adminPage: page,
    }) => {
      const event = await createEvent(page, uniqueName('E2E Time Zone Hint'))
      const task = await createTaskWithShifts(page, {
        name: uniqueName('E2E Time Zone Task'),
        eventId: event.id,
        status: 'published',
        startDate: futureDate(31),
        endDate: futureDate(31),
      })

      await api(page, 'PATCH', `/events/${event.id}`, { timezone: 'Europe/Lisbon' })
      await page.goto(`/app/tasks/${task.task.id}`)
      await expect(page.getByTestId('page-heading')).toBeVisible()
      await expect(page.getByTestId('event-zone-hint')).toBeHidden()

      await api(page, 'PATCH', `/events/${event.id}`, { timezone: 'Asia/Tokyo' })
      await page.goto(`/app/tasks/${task.task.id}`)
      await expect(page.getByTestId('event-zone-hint')).toContainText('Asia/Tokyo')

      await deleteEvent(page, event.id).catch(() => {})
    })
  })
})
