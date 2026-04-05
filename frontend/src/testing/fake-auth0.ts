/**
 * Fake Auth0 plugin for E2E tests.
 *
 * When the app detects E2E bypass mode, this module provides a mock Auth0
 * client so the app thinks the user is authenticated without any real Auth0
 * interaction. Identity is established server-side via the X-Test-User-Email
 * header. The user object is read from the localStorage cache seeded by the
 * Playwright fixture so that the email matches the seeded test user.
 */

import { ref } from 'vue'
import type { App } from 'vue'
import { AUTH0_INJECTION_KEY } from '@auth0/auth0-vue'

function getUserFromCache() {
  const key = Object.keys(localStorage).find((k) => k.startsWith('@@auth0spajs@@'))
  if (key) {
    try {
      const raw = JSON.parse(localStorage.getItem(key) ?? '{}')
      const user = raw?.body?.decodedToken?.user
      if (user) return user
    } catch { /* fall through to default */ }
  }
  return {
    sub: 'test|default@test.example.com',
    email: 'default@test.example.com',
    name: 'Test User',
    email_verified: true,
    picture: '',
  }
}

const fakeUser = getUserFromCache()

const fakeAuth0: any = {
  isAuthenticated: ref(true),
  isLoading: ref(false),
  user: ref(fakeUser),
  loginWithRedirect: async () => {},
  loginWithPopup: async () => {},
  logout: () => {},
  getAccessTokenSilently: async () => 'fake-test-token',
  getAccessTokenWithPopup: async () => 'fake-test-token',
  checkSession: async () => {},
  handleRedirectCallback: async () => ({ appState: {} }),
  idTokenClaims: ref(null),
  error: ref(null),
}

export function installFakeAuth0(app: App) {
  app.provide(AUTH0_INJECTION_KEY, fakeAuth0)
  app.config.globalProperties.$auth0 = fakeAuth0
}
