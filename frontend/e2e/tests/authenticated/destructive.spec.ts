/**
 * E2E tests for the destructive account flows (issue #136).
 *
 * Every test here mutates or removes the account it runs as, so they all use
 * the test-scoped `disposableUser` / `disposablePage` fixtures. The
 * worker-scoped `adminUser` / `memberUser` / `workerEvent` are shared by every
 * test the worker runs and must never be the target of a destructive action.
 */
import type { Locator, Page } from '@playwright/test'

import { expect, serverApiRaw, test } from '../../fixtures.js'

/**
 * The fixtures pin the UI locale to English (localStorage `locale` plus the
 * seeded `preferred_language`), so matching the row menu and the status badge
 * by their English label is deterministic. Keys live in
 * `src/locales/en/admin.json` under `users.*`.
 */
const MENU = {
  activate: 'Activate',
  deactivate: 'Deactivate',
  makeAdmin: 'Make Admin',
  removeAdmin: 'Remove Admin',
} as const

const STATUS = {
  active: 'Active',
  suspended: 'Suspended',
} as const

/** `src/locales/en/user.json` → `settings.deleteAccount.*` */
const DELETE_ACCOUNT = {
  trigger: 'Delete My Account',
  confirm: 'Yes, delete my account',
} as const

/** Open the admin users page and narrow the table down to one user's row. */
async function findUserRow(page: Page, email: string): Promise<Locator> {
  await page.goto('/app/admin/users')
  const table = page.getByTestId('users-table')
  await expect(table).toBeVisible()
  await page.getByTestId('users-search').fill(email)
  const row = table.getByRole('row').filter({ hasText: email })
  await expect(row).toBeVisible()
  return row
}

/** Click one entry of the ⋮ actions menu on a users-table row. */
async function runRowAction(page: Page, row: Locator, item: string): Promise<void> {
  // The row's only button is the dropdown trigger; the menu itself is portalled
  // to the document body, so it is looked up from the page rather than the row.
  await row.getByRole('button').click()
  await page.getByRole('menuitem', { name: item, exact: true }).click()
}

test.describe('Destructive – account self-deletion', () => {
  test('a user deletes their own account and loses access', async ({
    adminUser,
    disposablePage,
    disposableUser,
  }) => {
    await disposablePage.goto('/app/settings/dataPrivacy')
    const section = disposablePage.getByTestId('section-dataPrivacy')
    await expect(section).toBeVisible()

    await section.getByRole('button', { name: DELETE_ACCOUNT.trigger }).click()
    const dialog = disposablePage.getByRole('dialog')
    await expect(dialog).toBeVisible()

    // The confirmation word is translated, and the input's placeholder *is*
    // that word — read it back instead of hard-coding "DELETE".
    const confirmInput = dialog.getByRole('textbox')
    const confirmWord = (await confirmInput.getAttribute('placeholder')) ?? ''
    await confirmInput.fill(confirmWord)
    await dialog.getByRole('button', { name: DELETE_ACCOUNT.confirm }).click()

    // The record is gone: an admin lookup 404s.
    await expect
      .poll(
        async () => {
          const res = await serverApiRaw('GET', `/users/${disposableUser.id}`, adminUser.email)
          return res.status
        },
        { message: 'admin lookup of the deleted account should 404' },
      )
      .toBe(404)

    // The identity is dead too — it no longer resolves to a user. `/users/me`
    // is a plain read now; the account that used to be created on first sight
    // of an unknown caller no longer is.
    const profile = await serverApiRaw('GET', '/users/me', disposableUser.email)
    expect(profile.status).toBe(401)

    // And the SPA can no longer reach an authenticated page.
    await disposablePage.goto('/app/home')
    await expect(disposablePage).not.toHaveURL(/\/app\/home/)
  })
})

test.describe('Destructive – deactivate and reactivate', () => {
  test('deactivating blocks a user and reactivating restores access', async ({
    adminPage,
    disposablePage,
    disposableUser,
  }) => {
    // Baseline: the account works.
    await expect(disposablePage).toHaveURL(/\/app\/home/)

    const row = await findUserRow(adminPage, disposableUser.email)
    await expect(row).toContainText(STATUS.active)
    await runRowAction(adminPage, row, MENU.deactivate)
    await expect(row).toContainText(STATUS.suspended)

    // The blocked user is bounced to the suspended-account screen…
    await disposablePage.goto('/app/home')
    await expect(disposablePage).toHaveURL(/\/account-suspended/)

    // …and endpoints that require an active account reject them.
    const blocked = await serverApiRaw('GET', '/users/me/export', disposableUser.email)
    expect(blocked.status).toBe(403)

    const rowAgain = await findUserRow(adminPage, disposableUser.email)
    await runRowAction(adminPage, rowAgain, MENU.activate)
    await expect(rowAgain).toContainText(STATUS.active)

    await disposablePage.goto('/app/home')
    await expect(disposablePage).toHaveURL(/\/app\/home/)
    await expect(disposablePage.getByTestId('page-heading')).toBeVisible()

    const restored = await serverApiRaw('GET', '/users/me/export', disposableUser.email)
    expect(restored.status).toBe(200)
  })
})

test.describe('Destructive – grant and revoke admin', () => {
  test('the admin role opens and closes the admin area for that user', async ({
    adminPage,
    disposablePage,
    disposableUser,
  }) => {
    const adminNavLink = disposablePage.getByTestId('sidebar-link-admin-users')

    // Baseline: a plain member has neither the nav entry nor the route.
    await expect(adminNavLink).toBeHidden()
    await disposablePage.goto('/app/admin/users')
    await expect(disposablePage).toHaveURL(/\/app\/home/)

    const row = await findUserRow(adminPage, disposableUser.email)
    await runRowAction(adminPage, row, MENU.makeAdmin)
    await expect(row).toContainText('admin')

    // A fresh load re-fetches the profile, so the sidebar picks the role up.
    await disposablePage.goto('/app/home')
    await expect(adminNavLink).toBeVisible()
    await adminNavLink.click()
    await expect(disposablePage).toHaveURL(/\/app\/admin\/users/)
    await expect(disposablePage.getByTestId('users-table')).toBeVisible()

    const rowAgain = await findUserRow(adminPage, disposableUser.email)
    await runRowAction(adminPage, rowAgain, MENU.removeAdmin)
    await expect(rowAgain).not.toContainText('admin')

    await disposablePage.goto('/app/admin/users')
    await expect(disposablePage).toHaveURL(/\/app\/home/)
    await expect(adminNavLink).toBeHidden()
  })
})
