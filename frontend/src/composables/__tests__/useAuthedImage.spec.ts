// @vitest-environment jsdom
import { effectScope, nextTick, ref } from 'vue'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useAuthedImage } from '@/composables/useAuthedImage'

const auth = vi.hoisted(() => ({ getAuthToken: vi.fn() }))

vi.mock('@/composables/useAuthenticatedClient', () => ({
  useAuthenticatedClient: () => ({ getAuthToken: auth.getAuthToken }),
}))

const fetchMock = vi.fn()
const createObjectURL = vi.fn()
const revokeObjectURL = vi.fn()

function okResponse(body = 'img') {
  return { ok: true, status: 200, blob: async () => new Blob([body]) }
}

let urlCounter = 0

beforeEach(() => {
  vi.resetAllMocks()
  urlCounter = 0
  auth.getAuthToken.mockResolvedValue('tok')
  createObjectURL.mockImplementation(() => `blob:${++urlCounter}`)
  vi.stubGlobal('fetch', fetchMock)
  vi.stubGlobal('URL', Object.assign(URL, { createObjectURL, revokeObjectURL }))
})

afterEach(() => {
  vi.unstubAllGlobals()
})

/** Run the composable inside an effect scope so disposal can be observed. */
function setup(url: Parameters<typeof useAuthedImage>[0]) {
  const scope = effectScope()
  const image = scope.run(() => useAuthedImage(url))!
  return { scope, image }
}

describe('useAuthedImage', () => {
  it('fetches with the bearer token and exposes an object URL', async () => {
    fetchMock.mockResolvedValue(okResponse())
    const { image } = setup('https://api.test/venue-plans/p1/image?v=e1')

    expect(image.loading.value).toBe(true)
    await image.ready()

    expect(fetchMock).toHaveBeenCalledWith('https://api.test/venue-plans/p1/image?v=e1', {
      headers: { Authorization: 'Bearer tok' },
    })
    expect(image.src.value).toBe('blob:1')
    expect(image.loading.value).toBe(false)
    expect(image.error.value).toBeNull()
  })

  it('stays empty and settled without a URL', async () => {
    const { image } = setup(null)
    await image.ready()

    expect(fetchMock).not.toHaveBeenCalled()
    expect(image.src.value).toBeNull()
    expect(image.loading.value).toBe(false)
  })

  it('records an error for a failed response and still resolves ready', async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 404, blob: vi.fn() })
    const { image } = setup('https://api.test/x')

    await image.ready()

    expect(image.src.value).toBeNull()
    expect(image.error.value).toBeInstanceOf(Error)
    expect(image.loading.value).toBe(false)
  })

  it('records an error when there is no session', async () => {
    auth.getAuthToken.mockRejectedValue(new Error('User is not authenticated'))
    const { image } = setup('https://api.test/x')

    await image.ready()

    expect(fetchMock).not.toHaveBeenCalled()
    expect(image.error.value).toBeInstanceOf(Error)
  })

  it('revokes the old object URL when the source changes, and on dispose', async () => {
    fetchMock.mockResolvedValue(okResponse())
    const url = ref<string | null>('https://api.test/a')
    const { scope, image } = setup(url)
    await image.ready()
    expect(image.src.value).toBe('blob:1')

    url.value = 'https://api.test/b'
    await nextTick()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:1')
    await image.ready()
    expect(image.src.value).toBe('blob:2')

    url.value = null
    await nextTick()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:2')
    expect(image.src.value).toBeNull()

    url.value = 'https://api.test/c'
    await nextTick()
    await image.ready()
    scope.stop()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:3')
  })

  it('ignores a slow response for a URL that has since changed', async () => {
    let resolveFirst!: (value: unknown) => void
    fetchMock
      .mockImplementationOnce(() => new Promise((resolve) => (resolveFirst = resolve)))
      .mockResolvedValueOnce(okResponse('second'))
    const url = ref('https://api.test/slow')
    const { image } = setup(url)
    await Promise.resolve()
    await Promise.resolve()

    url.value = 'https://api.test/fast'
    await nextTick()
    await image.ready()
    expect(image.src.value).toBe('blob:1')

    resolveFirst(okResponse('first'))
    await new Promise((r) => setTimeout(r, 0))
    // The stale response produced no new URL and did not flip loading.
    expect(createObjectURL).toHaveBeenCalledTimes(1)
    expect(image.src.value).toBe('blob:1')
    expect(image.loading.value).toBe(false)
  })

  it('ignores a stale failure as well', async () => {
    let rejectFirst!: (reason: unknown) => void
    fetchMock
      .mockImplementationOnce(() => new Promise((_resolve, reject) => (rejectFirst = reject)))
      .mockResolvedValueOnce(okResponse())
    const url = ref('https://api.test/slow')
    const { image } = setup(url)
    await Promise.resolve()
    await Promise.resolve()

    url.value = 'https://api.test/fast'
    await nextTick()
    await image.ready()

    rejectFirst(new Error('boom'))
    await new Promise((r) => setTimeout(r, 0))
    expect(image.error.value).toBeNull()
    expect(image.src.value).toBe('blob:1')
  })

  it('works outside an effect scope (no dispose hook)', async () => {
    fetchMock.mockResolvedValue(okResponse())
    const image = useAuthedImage('https://api.test/x')
    await image.ready()
    expect(image.src.value).toBe('blob:1')
  })
})
