// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { getApiErrorMessage, normalizeApiError, toastApiError } from '@/lib/api-errors'
import i18n from '@/locales/i18n'

const { toastError } = vi.hoisted(() => ({ toastError: vi.fn() }))

vi.mock('vue-sonner', () => ({
  toast: { error: toastError },
}))

/**
 * These tests drive the real i18n instance so the assertions are the literal
 * strings a user sees, taken from `src/locales/{en,de}/*.json`. If a message is
 * reworded the test fails, which is the point: this module decides what the UI
 * shows when the API fails.
 */
const EN = {
  default: 'Something went wrong. Please try again.',
  unauthorized: 'Your sign-in is no longer valid. Please log in again.',
  forbidden: 'You do not have permission to see this.',
  notFound: 'We could not find what you were looking for.',
  rateLimited: 'Too many requests. Please try again later.',
  server: 'Something went wrong on our end.',
  network: 'No connection. Please check your internet connection.',
  timeout: 'The server is taking too long to respond.',
}

type AxiosLikeResponse = { status?: number; data?: unknown }

/** A plain axios-shaped object: what interceptors usually hand around. */
const axiosError = (
  response?: AxiosLikeResponse,
  extra: Record<string, unknown> = {},
): unknown => ({
  isAxiosError: true,
  name: 'AxiosError',
  message: 'Request failed',
  response,
  ...extra,
})

/** A real `AxiosError`-alike: an `Error` instance that is also flagged axios. */
const axiosErrorInstance = (message: string, extra: Record<string, unknown> = {}): unknown =>
  Object.assign(new Error(message), { isAxiosError: true, name: 'AxiosError' }, extra)

describe('normalizeApiError', () => {
  const originalLocale = i18n.global.locale.value

  beforeEach(() => {
    i18n.global.locale.value = 'en'
    toastError.mockClear()
  })

  afterEach(() => {
    i18n.global.locale.value = originalLocale
  })

  describe('RFC 7807 problem details bodies', () => {
    it('renders validation errors and strips the leading body/query/path segment', () => {
      const result = normalizeApiError(
        axiosError({
          status: 422,
          data: {
            type: 'urn:problem:validation_error',
            title: 'Validation Error',
            status: 422,
            errors: [
              { loc: ['body', 'name'], msg: 'Field required', type: 'missing' },
              { loc: ['query', 'page'], msg: 'must be >= 1', type: 'value_error' },
            ],
          },
        }),
      )

      expect(result.message).toBe('Please check your entry: name: Field required, page: must be >= 1')
      expect(result.status).toBe(422)
      expect(result.code).toBe('validation_error')
      expect(result.title).toBe('Validation Error')
      expect(result.errors).toHaveLength(2)
    })

    it('keeps a leading segment that is not body/query/path and joins nested locations', () => {
      const result = normalizeApiError(
        axiosError({
          status: 422,
          data: {
            title: 'Validation Error',
            status: 422,
            errors: [
              { loc: ['body', 'items', 0, 'name'], msg: 'too short', type: 'value_error' },
              { loc: ['header'], msg: 'missing header', type: 'missing' },
            ],
          },
        }),
      )

      expect(result.message).toBe(
        'Please check your entry: items.0.name: too short, header: missing header',
      )
    })

    it('falls back to the bare message when the location is only "body"', () => {
      const result = normalizeApiError(
        axiosError({
          status: 422,
          data: {
            title: 'Validation Error',
            status: 422,
            errors: [{ loc: ['body'], msg: 'Invalid payload', type: 'value_error' }],
          },
        }),
      )

      expect(result.message).toBe('Please check your entry: Invalid payload')
    })

    it('prefers an explicit error code over the detail text', () => {
      const result = normalizeApiError(
        axiosError({
          status: 404,
          data: {
            type: 'about:blank',
            title: 'Not Found',
            status: 404,
            code: 'user.not_found',
            detail: 'User 42 does not exist',
          },
        }),
      )

      expect(result.message).toBe('That user could not be found.')
      expect(result.code).toBe('user.not_found')
      expect(result.detail).toBe('User 42 does not exist')
      expect(result.status).toBe(404)
    })

    it('derives the error code from a urn:problem: type', () => {
      const result = normalizeApiError(
        axiosError({
          status: 409,
          data: { type: 'urn:problem:booking.slot_full', title: 'Conflict', status: 409 },
        }),
      )

      expect(result.message).toBe('This duty shift is fully booked')
      expect(result.code).toBe('booking.slot_full')
    })

    it('ignores a type that does not use the urn:problem: prefix', () => {
      const result = normalizeApiError(
        axiosError({
          status: 409,
          data: { type: 'https://example.com/errors/booking.slot_full', title: 'Conflict' },
        }),
      )

      expect(result.code).toBeUndefined()
      expect(result.message).toBe('Conflict')
    })

    it('ignores an empty code left behind by a bare urn:problem: type', () => {
      const result = normalizeApiError(
        axiosError({ status: 400, data: { type: 'urn:problem:', title: 'Bare', status: 400 } }),
      )

      expect(result.code).toBeUndefined()
      expect(result.message).toBe('Bare')
    })

    it('falls back to the detail when the code has no translation', () => {
      const result = normalizeApiError(
        axiosError({
          status: 400,
          data: {
            type: 'urn:problem:some.unmapped_code',
            title: 'Bad Request',
            status: 400,
            detail: 'The start date must be before the end date.',
          },
        }),
      )

      expect(result.message).toBe('The start date must be before the end date.')
      expect(result.code).toBe('some.unmapped_code')
    })

    it('skips the validation branch when the errors array is empty', () => {
      const result = normalizeApiError(
        axiosError({
          status: 400,
          data: { title: 'Bad Request', status: 400, errors: [], detail: 'Nothing to see' },
        }),
      )

      expect(result.message).toBe('Nothing to see')
    })

    it('falls back to the status message when there is no code and no detail', () => {
      const result = normalizeApiError(
        axiosError({ status: 403, data: { type: 'about:blank', title: 'Forbidden', status: 403 } }),
      )

      expect(result.message).toBe(EN.forbidden)
      expect(result.code).toBeUndefined()
    })

    it('falls back to the title when the status has no dedicated message', () => {
      const result = normalizeApiError(
        axiosError({ status: 409, data: { type: 'about:blank', title: 'Conflict', status: 409 } }),
      )

      expect(result.message).toBe('Conflict')
    })

    it('falls back to the generic message when nothing else is usable', () => {
      const result = normalizeApiError(axiosError({ status: 418, data: { status: 418 } }))

      expect(result.message).toBe(EN.default)
      expect(result.title).toBeUndefined()
    })

    it('ignores the caller fallback for a problem details body', () => {
      const result = normalizeApiError(
        axiosError({ status: 418, data: { status: 418 } }),
        'Could not load duties',
      )

      expect(result.message).toBe(EN.default)
    })

    it('prefers the status from the body over the transport status', () => {
      const result = normalizeApiError(
        axiosError({ status: 500, data: { title: 'Conflict', status: 409 } }),
      )

      expect(result.status).toBe(409)
    })

    it('uses the transport status when the body status is not a number', () => {
      const result = normalizeApiError(
        axiosError({ status: 418, data: { title: 'Teapot', status: 'nope' } }),
      )

      expect(result.status).toBe(418)
      expect(result.message).toBe('Teapot')
    })
  })

  describe('legacy FastAPI detail bodies', () => {
    it('formats a list of legacy validation items (keeping the body prefix)', () => {
      const result = normalizeApiError(
        axiosError({
          status: 422,
          data: {
            detail: [{ loc: ['body', 'email'], msg: 'invalid email address', type: 'value_error' }],
          },
        }),
      )

      expect(result.message).toBe('Please check your entry: body.email: invalid email address')
      expect(result.status).toBe(422)
    })

    it('drops legacy items that are not usable objects', () => {
      const result = normalizeApiError(
        axiosError({
          status: 422,
          data: { detail: ['oops', { loc: ['body', 'x'] }, { msg: 'only msg' }] },
        }),
      )

      expect(result.message).toBe('Please check your entry: only msg')
    })

    it('falls through to a top-level message when the legacy list yields nothing', () => {
      const result = normalizeApiError(
        axiosError({ status: 400, data: { detail: [], message: 'Legacy message' } }),
      )

      expect(result.message).toBe('Legacy message')
      expect(result.status).toBe(400)
    })

    it('returns a plain string detail verbatim', () => {
      const result = normalizeApiError(
        axiosError({ status: 400, data: { detail: 'Something specific went wrong' } }),
      )

      expect(result.message).toBe('Something specific went wrong')
    })

    it('uses a top-level message even when the status has its own text', () => {
      const result = normalizeApiError(
        axiosError({ status: 500, data: { message: 'Boom from the server' } }),
      )

      expect(result.message).toBe('Boom from the server')
      expect(result.status).toBe(500)
    })

    it('falls through to the status message when the body has nothing usable', () => {
      const result = normalizeApiError(axiosError({ status: 401, data: { foo: 'bar' } }))

      expect(result.message).toBe(EN.unauthorized)
    })

    it('handles an array body', () => {
      const result = normalizeApiError(axiosError({ status: 404, data: [] }))

      expect(result.message).toBe(EN.notFound)
    })

    it('handles a non-object body such as an HTML error page', () => {
      const result = normalizeApiError(axiosError({ status: 500, data: '<html>oops</html>' }))

      expect(result.message).toBe(EN.server)
    })
  })

  describe('status-only responses', () => {
    it.each([
      [401, EN.unauthorized],
      [403, EN.forbidden],
      [404, EN.notFound],
      [429, EN.rateLimited],
      [500, EN.server],
    ])('maps status %i to its dedicated message', (status, expected) => {
      const result = normalizeApiError(axiosError({ status }))

      expect(result.message).toBe(expected)
      expect(result.status).toBe(status)
    })

    it('keeps the mapped status message even when a fallback was supplied', () => {
      const result = normalizeApiError(axiosError({ status: 404 }), 'Could not load duties')

      expect(result.message).toBe(EN.notFound)
    })

    it('interpolates the status for an unmapped code without a fallback', () => {
      const result = normalizeApiError(axiosError({ status: 418 }))

      expect(result.message).toBe('Request failed with status 418')
      expect(result.status).toBe(418)
    })

    it('uses the caller fallback for an unmapped status code', () => {
      const result = normalizeApiError(axiosError({ status: 502 }), 'Could not load duties')

      expect(result.message).toBe('Could not load duties')
      expect(result.status).toBe(502)
    })

    it('treats status 0 as no status at all', () => {
      const result = normalizeApiError(axiosError({ status: 0 }))

      expect(result.message).toBe(EN.default)
      expect(result.status).toBeUndefined()
    })
  })

  describe('transport failures', () => {
    it('reports a network error for an Error-shaped axios failure with no response', () => {
      const result = normalizeApiError(axiosErrorInstance('Network Error'))

      expect(result.message).toBe(EN.network)
      expect(result.isNetworkError).toBe(true)
      expect(result.status).toBeUndefined()
    })

    it('reports a network error from the axios error code', () => {
      const result = normalizeApiError(
        axiosErrorInstance('connect ECONNREFUSED', { code: 'NETWORK_ERROR' }),
      )

      expect(result.message).toBe(EN.network)
      expect(result.isNetworkError).toBe(true)
    })

    it('reports a timeout for an axios timeout message', () => {
      const result = normalizeApiError(axiosErrorInstance('timeout of 5000ms exceeded'))

      expect(result.message).toBe(EN.timeout)
      expect(result.isNetworkError).toBe(true)
    })

    it('falls back to the generic message for a plain axios object with no response', () => {
      // Not an `Error` instance, so the network/timeout sniffing never runs.
      const result = normalizeApiError(axiosError(undefined, { message: 'Network Error' }))

      expect(result.message).toBe(EN.default)
      expect(result.isNetworkError).toBeUndefined()
    })

    it('uses the caller fallback for a plain axios object with no response', () => {
      const result = normalizeApiError(axiosError(), 'Could not load duties')

      expect(result.message).toBe('Could not load duties')
    })
  })

  describe('plain errors', () => {
    it('detects a network error from the message', () => {
      const result = normalizeApiError(new Error('Network Error while fetching'))

      expect(result.message).toBe(EN.network)
      expect(result.isNetworkError).toBe(true)
    })

    it('detects a network error from a NETWORK_ERROR code', () => {
      const error = Object.assign(new Error('socket hang up'), { code: 'NETWORK_ERROR' })

      expect(normalizeApiError(error).message).toBe(EN.network)
    })

    it.each(['Request Timeout', 'TIMEOUT after 30s', 'the request timed out — timeout'])(
      'detects a timeout case-insensitively in %s',
      (message) => {
        const result = normalizeApiError(new Error(message))

        expect(result.message).toBe(EN.timeout)
        expect(result.isNetworkError).toBe(true)
      },
    )

    it('surfaces any other error message verbatim', () => {
      const result = normalizeApiError(new Error('Could not parse the schedule'))

      expect(result.message).toBe('Could not parse the schedule')
      expect(result.isNetworkError).toBeUndefined()
      expect(result.status).toBeUndefined()
    })

    it('surfaces the message of an Error subclass', () => {
      expect(normalizeApiError(new TypeError('x is not a function')).message).toBe(
        'x is not a function',
      )
    })

    it('falls back when the error message is empty', () => {
      expect(normalizeApiError(new Error('')).message).toBe(EN.default)
      expect(normalizeApiError(new Error(''), 'Could not load duties').message).toBe(
        'Could not load duties',
      )
    })
  })

  describe('non-error values', () => {
    it.each([
      ['a string', 'boom'],
      ['null', null],
      ['undefined', undefined],
      ['a number', 42],
      ['a bare object', { oops: true }],
    ])('falls back to the generic message for %s', (_label, value) => {
      const result = normalizeApiError(value)

      expect(result.message).toBe(EN.default)
      expect(result.status).toBeUndefined()
      expect(result.code).toBeUndefined()
    })

    it('uses the caller fallback instead of the generic message', () => {
      expect(normalizeApiError(null, 'Could not load duties').message).toBe('Could not load duties')
      expect(normalizeApiError('boom', 'Could not load duties').message).toBe(
        'Could not load duties',
      )
    })
  })

  describe('german locale', () => {
    beforeEach(() => {
      i18n.global.locale.value = 'de'
    })

    it('translates the generic fallback', () => {
      expect(normalizeApiError(null).message).toBe(
        'Etwas ist schiefgelaufen. Bitte versuchen Sie es erneut.',
      )
    })

    it('translates status messages', () => {
      expect(normalizeApiError(axiosError({ status: 401 })).message).toBe(
        'Ihre Anmeldung ist nicht mehr gültig. Bitte melden Sie sich erneut an.',
      )
      expect(normalizeApiError(axiosError({ status: 418 })).message).toBe(
        'Anfrage fehlgeschlagen mit Status 418',
      )
    })

    it('translates error codes', () => {
      const result = normalizeApiError(
        axiosError({
          status: 404,
          data: { type: 'urn:problem:user.not_found', title: 'Not Found', status: 404 },
        }),
      )

      expect(result.message).toBe('Dieser Benutzer wurde nicht gefunden.')
    })

    it('translates the validation wrapper', () => {
      const result = normalizeApiError(
        axiosError({
          status: 422,
          data: {
            title: 'Validation Error',
            status: 422,
            errors: [{ loc: ['body', 'name'], msg: 'Field required', type: 'missing' }],
          },
        }),
      )

      expect(result.message).toBe('Bitte prüfen Sie Ihre Eingabe: name: Field required')
    })

    it('translates network errors', () => {
      expect(normalizeApiError(new Error('Network Error')).message).toBe(
        'Keine Verbindung. Bitte überprüfen Sie Ihre Internetverbindung.',
      )
    })
  })
})

describe('getApiErrorMessage', () => {
  const originalLocale = i18n.global.locale.value

  beforeEach(() => {
    i18n.global.locale.value = 'en'
  })

  afterEach(() => {
    i18n.global.locale.value = originalLocale
  })

  it('returns just the message of the normalized error', () => {
    expect(getApiErrorMessage(axiosError({ status: 403 }))).toBe(EN.forbidden)
  })

  it('forwards the caller fallback', () => {
    expect(getApiErrorMessage(null, 'Could not load duties')).toBe('Could not load duties')
  })

  it('returns the generic message with no fallback', () => {
    expect(getApiErrorMessage(undefined)).toBe(EN.default)
  })
})

describe('toastApiError', () => {
  const originalLocale = i18n.global.locale.value

  beforeEach(() => {
    i18n.global.locale.value = 'en'
    toastError.mockClear()
  })

  afterEach(() => {
    i18n.global.locale.value = originalLocale
  })

  it('shows the normalized message as an error toast and returns the normalized error', () => {
    const result = toastApiError(
      axiosError({
        status: 409,
        data: { type: 'urn:problem:booking.already_exists', title: 'Conflict', status: 409 },
      }),
    )

    expect(toastError).toHaveBeenCalledTimes(1)
    expect(toastError).toHaveBeenCalledWith('You already have a booking for this shift')
    expect(result).toEqual({
      message: 'You already have a booking for this shift',
      status: 409,
      code: 'booking.already_exists',
      title: 'Conflict',
      detail: undefined,
      errors: undefined,
    })
  })

  it('toasts the caller fallback for an unknown failure', () => {
    toastApiError('boom', 'Could not load duties')

    expect(toastError).toHaveBeenCalledWith('Could not load duties')
  })
})
