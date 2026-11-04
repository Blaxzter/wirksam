/**
 * The same authenticated page, scanned in both locales.
 *
 * A missing or empty translation can produce an empty `aria-label`, an
 * unlabelled button or a link with no discernible text. The i18n key-parity
 * check compares en/de key sets — it cannot see what the rendered DOM does with
 * a blank value, and the English scan will not catch it either.
 *
 * Forcing German takes both halves. The app boots its locale from
 * `localStorage.locale` (see `src/locales/i18n.ts`), which a page-level init
 * script can set because it runs after the context-level one the fixtures use
 * to seed `en`. But `/users/me` is a plain read now, and `stores/auth.ts`
 * applies the account's own `preferred_language` over the top as soon as the
 * profile arrives — so the stored preference has to agree, or the page flips
 * back to English a moment after it renders.
 */
import { expect, test } from '../../fixtures.js'
import { expectNoA11yViolations } from '../../helpers/a11y.js'
import { api } from '../../helpers/api.js'

test.describe('a11y – locales', () => {
  test.afterEach(async ({ adminPage: page }) => {
    // Worker users are reused by later tests; put the language back.
    await api(page, 'PATCH', '/users/me', { preferred_language: 'en' }).catch(() => {})
  })

  test('dashboard in English', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await expect(page.getByTestId('sidebar-link-my-bookings')).toContainText('My Bookings')
    await expect(page.getByTestId('dashboard-next-shift')).toBeVisible()
    await expectNoA11yViolations(page, { label: 'admin dashboard, locale=en' })
  })

  test('dashboard in German', async ({ adminPage: page }) => {
    await api(page, 'PATCH', '/users/me', { preferred_language: 'de' })
    await page.addInitScript(() => localStorage.setItem('locale', 'de'))
    await page.goto('/app/home')

    // Prove the page really switched — otherwise this is a duplicate English scan.
    await expect(page.getByTestId('sidebar-link-my-bookings')).toContainText('Meine Buchungen')
    await expect(page.getByTestId('dashboard-next-shift')).toBeVisible()
    await expectNoA11yViolations(page, { label: 'admin dashboard, locale=de' })
  })
})
