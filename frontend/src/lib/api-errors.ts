import type { AxiosError } from 'axios'
import { toast } from 'vue-sonner'

import type { ProblemDetails, ValidationErrorItem } from '@/client/types.gen'
import i18n from '@/locales/i18n'

type ProblemDetailsWithCode = ProblemDetails & { code?: string }

export type NormalizedApiError = {
  message: string
  status?: number
  code?: string
  title?: string
  detail?: string
  errors?: ValidationErrorItem[]
  isNetworkError?: boolean
}

const t = (key: string, params?: Record<string, unknown>) =>
  params ? (i18n.global.t(key, params) as string) : (i18n.global.t(key) as string)
const te = (key: string) => i18n.global.te(key)

const DEFAULT_MESSAGE_KEY = 'common.errors.api.default'
const TYPE_PREFIX = 'urn:problem:'

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null

const isAxiosError = (error: unknown): error is AxiosError =>
  isRecord(error) && 'isAxiosError' in error && error.isAxiosError === true

const isProblemDetails = (data: unknown): data is ProblemDetailsWithCode => {
  if (!isRecord(data)) return false
  return 'title' in data || 'status' in data || 'type' in data
}

const formatValidationErrors = (errors: ValidationErrorItem[]): string => {
  return errors
    .map((item) => {
      const loc = item.loc
        .map((part) => String(part))
        .filter((part, index) => !(index === 0 && ['body', 'query', 'path'].includes(part)))
        .join('.')
      return loc ? `${loc}: ${item.msg}` : item.msg
    })
    .join(', ')
}

const statusMessage = (status?: number): string | null => {
  switch (status) {
    case 401:
      return t('common.errors.api.unauthorized')
    case 403:
      return t('common.errors.api.forbidden')
    case 404:
      return t('common.errors.api.notFoundResource')
    case 429:
      return t('common.errors.api.rateLimited')
    case 500:
      return t('common.errors.api.server')
    default:
      return null
  }
}

const codeFromType = (type?: string): string | undefined => {
  if (!type || !type.startsWith(TYPE_PREFIX)) return undefined
  const code = type.slice(TYPE_PREFIX.length)
  return code || undefined
}

const messageFromCode = (code?: string | null): string | null => {
  if (!code) return null
  const key = `errorCodes.${code}`
  return te(key) ? t(key) : null
}

const clockTime = (value: unknown): string => (typeof value === 'string' ? value.slice(0, 5) : '')

/**
 * `booking.time_conflict` carries the shift it clashes with, so the message can
 * name it instead of leaving the volunteer to hunt through their bookings.
 */
const timeConflictMessage = (problem: ProblemDetailsWithCode): string | null => {
  const shift = (problem as Record<string, unknown>).conflicting_shift
  if (!isRecord(shift) || typeof shift.date !== 'string') return null
  const name =
    typeof shift.task_name === 'string' && shift.task_name
      ? shift.task_name
      : typeof shift.title === 'string'
        ? shift.title
        : ''
  if (!name) return null
  const date = new Date(`${shift.date}T00:00:00`).toLocaleDateString(i18n.global.locale.value, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  })
  const start = clockTime(shift.start_time)
  const end = clockTime(shift.end_time)
  const when = start && end ? `${date}, ${start} – ${end}` : date
  return t('errorCodes.booking.time_conflict_with', { name, when })
}

const messageFromProblemDetails = (problem: ProblemDetailsWithCode): string => {
  if (Array.isArray(problem.errors) && problem.errors.length > 0) {
    return t('common.errors.api.validation', {
      message: formatValidationErrors(problem.errors),
    })
  }
  const code = problem.code ?? codeFromType(problem.type)
  if (code === 'booking.time_conflict') {
    const conflict = timeConflictMessage(problem)
    if (conflict) return conflict
  }
  const codeMessage = messageFromCode(code)
  if (codeMessage) return codeMessage
  if (problem.detail) return problem.detail
  const statusFallback = statusMessage(problem.status)
  if (statusFallback) return statusFallback
  if (problem.title) return problem.title
  return t(DEFAULT_MESSAGE_KEY)
}

const messageFromLegacyDetail = (detail: unknown): string | null => {
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (!isRecord(item)) return null
        const loc = Array.isArray(item.loc) ? item.loc.join('.') : undefined
        const msg = typeof item.msg === 'string' ? item.msg : undefined
        return loc && msg ? `${loc}: ${msg}` : msg
      })
      .filter(Boolean)
      .join(', ')
    return messages ? t('common.errors.api.validation', { message: messages }) : null
  }
  if (typeof detail === 'string') return detail
  return null
}

export const normalizeApiError = (error: unknown, fallbackMessage?: string): NormalizedApiError => {
  const fallback = fallbackMessage ?? t(DEFAULT_MESSAGE_KEY)
  const useFallback = fallbackMessage !== undefined
  if (isAxiosError(error)) {
    const response = error.response
    const status = response?.status
    const data = response?.data

    if (isProblemDetails(data)) {
      const code = data.code ?? codeFromType(data.type)
      return {
        message: messageFromProblemDetails(data),
        status: typeof data.status === 'number' ? data.status : status,
        code,
        title: data.title,
        detail: data.detail,
        errors: data.errors,
      }
    }

    if (data && isRecord(data)) {
      const legacyDetail = messageFromLegacyDetail(data.detail)
      if (legacyDetail) {
        return {
          message: legacyDetail,
          status,
        }
      }

      if (typeof data.message === 'string') {
        return { message: data.message, status }
      }
    }

    if (status) {
      const statusFallback = statusMessage(status)
      if (statusFallback) {
        return {
          message: statusFallback,
          status,
        }
      }
      return {
        message: useFallback ? fallback : t('common.errors.api.statusFallback', { status }),
        status,
      }
    }
  }

  if (error instanceof Error) {
    const message = error.message
    if (message.includes('Network Error') || (isRecord(error) && error.code === 'NETWORK_ERROR')) {
      return {
        message: t('common.errors.api.network'),
        isNetworkError: true,
      }
    }
    if (message.toLowerCase().includes('timeout')) {
      return {
        message: t('common.errors.api.timeout'),
        isNetworkError: true,
      }
    }
    return { message: message || fallback }
  }

  return { message: fallback }
}

export const getApiErrorMessage = (error: unknown, fallbackMessage?: string): string =>
  normalizeApiError(error, fallbackMessage).message

export const toastApiError = (error: unknown, fallbackMessage?: string): NormalizedApiError => {
  const normalized = normalizeApiError(error, fallbackMessage)
  toast.error(normalized.message)
  return normalized
}
