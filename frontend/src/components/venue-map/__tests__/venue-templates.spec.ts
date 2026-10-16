// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'

import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { forgetTemplateShapes } from '@/composables/useVenueTemplates'

import VenuePlanCreateDialog from '@/components/venue-map/editor/VenuePlanCreateDialog.vue'
import VenueTemplateNameDialog from '@/components/venue-map/editor/VenueTemplateNameDialog.vue'
import VenueTemplateThumb from '@/components/venue-map/editor/VenueTemplateThumb.vue'

import type { VenueTemplateRead, VenueTemplateSummary } from '@/client/types.gen'
import i18n from '@/locales/i18n'

/**
 * Venue plan templates in the editor's dialogs: picking one in "New map",
 * the empty state, renaming and deleting from a card, and the thumbnail.
 */

// The template menus' tooltips (reka-ui) measure themselves when they open on
// focus or hover; jsdom has no ResizeObserver.
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
}

const api = {
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
  getAuthToken: async () => 'tok',
}

vi.mock('@/composables/useAuthenticatedClient', () => ({
  useAuthenticatedClient: () => api,
}))

const confirmDestructive = vi.fn(async () => true)
vi.mock('@/composables/useDialog', () => ({
  useDialog: () => ({ confirmDestructive }),
}))

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }))
vi.mock('vue-sonner', () => ({ toast }))

const fetchMock = vi.fn()
const stamp = '2026-10-16T00:00:00Z'

function template(id: string, overrides: Partial<VenueTemplateRead> = {}): VenueTemplateRead {
  return {
    id,
    name: `Gelände ${id}`,
    canvas_width: 1600,
    canvas_height: 1000,
    image_etag: null,
    image_width: null,
    image_height: null,
    shape_count: 1,
    created_at: stamp,
    updated_at: stamp,
    width: 1600,
    height: 1000,
    ...overrides,
  }
}

let templates: VenueTemplateSummary[]

beforeEach(() => {
  setActivePinia(createPinia())
  i18n.global.locale.value = 'en'
  forgetTemplateShapes()
  templates = [template('t1'), template('t2', { name: 'Halle', image_etag: 'img1' })]
  api.get.mockImplementation(async ({ url }: { url: string }) => {
    if (url === '/venue-templates') return { data: templates }
    const id = url.split('/').pop()!
    return {
      data: {
        ...template(id),
        shapes: [
          {
            id: 's1',
            kind: 'rect',
            style: 'stage',
            points: [
              [0.1, 0.1],
              [0.4, 0.4],
            ],
            label: 'Bühne',
          },
        ],
      },
    }
  })
  fetchMock.mockResolvedValue({ ok: true, status: 200, blob: async () => new Blob(['x']) })
  vi.stubGlobal('fetch', fetchMock)
  vi.stubGlobal(
    'URL',
    Object.assign(URL, { createObjectURL: () => 'blob:tpl', revokeObjectURL: () => {} }),
  )
})

const mounted: { unmount: () => void }[] = []

afterEach(() => {
  for (const w of mounted.splice(0)) w.unmount()
  vi.unstubAllGlobals()
  vi.clearAllMocks()
  document.body.innerHTML = ''
})

function q<T extends Element = HTMLElement>(testid: string, root: ParentNode = document): T {
  const el = root.querySelector<T>(`[data-testid="${testid}"]`)
  if (!el) throw new Error(`missing ${testid}`)
  return el
}

async function typeInto(testid: string, value: string) {
  const input = q<HTMLInputElement>(testid)
  input.value = value
  input.dispatchEvent(new Event('input', { bubbles: true }))
  await flushPromises()
}

/** Open a reka dropdown menu by its trigger (jsdom: by keyboard), then pick an item. */
async function pickMenuItem(trigger: HTMLElement, item: string) {
  trigger.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true, key: 'Enter' }))
  await flushPromises()
  q(item).click()
  await flushPromises()
}

async function openCreate(props: { sandbox?: boolean } = {}) {
  const wrapper = mount(VenuePlanCreateDialog, {
    props: { open: false, ...props },
    global: { plugins: [i18n] },
    attachTo: document.body,
  })
  mounted.push(wrapper)
  await wrapper.setProps({ open: true })
  await flushPromises()
  q('plan-create-template').querySelector('input')!.click()
  await flushPromises()
  return wrapper
}

describe('New map: start from a template', () => {
  it('lists my templates with a preview and names the map after the pick', async () => {
    const wrapper = await openCreate()
    expect(api.get).toHaveBeenCalledWith({ url: '/venue-templates' })
    const cards = document.querySelectorAll('[data-testid^="template-card-"]')
    expect(cards).toHaveLength(2)
    expect(q('template-card-t2').textContent).toContain('Halle')
    expect(document.querySelectorAll('[data-testid="template-thumb"]')).toHaveLength(2)
    // The drawing is drawn in the preview; the picture is fetched with the token.
    expect(q('template-card-t1').querySelector('.vs-stage')).not.toBeNull()
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/venue-templates/t2/image?v=img1'),
      expect.anything(),
    )

    // Nothing picked yet: nothing to create.
    expect(q<HTMLButtonElement>('plan-name-save').disabled).toBe(true)

    q('template-pick', q('template-card-t2')).click()
    await flushPromises()
    expect(q<HTMLInputElement>('plan-name-input').value).toBe('Halle')
    // Another pick replaces the name it filled in itself.
    q('template-pick', q('template-card-t1')).click()
    await flushPromises()
    expect(q<HTMLInputElement>('plan-name-input').value).toBe('Gelände t1')

    q('plan-name-save').click()
    await flushPromises()
    expect(wrapper.emitted('submit')?.[0]).toEqual([
      { name: 'Gelände t1', mode: 'template', canvas: 'landscape', templateId: 't1' },
    ])
  })

  it('keeps a name the organiser typed', async () => {
    const wrapper = await openCreate()
    await typeInto('plan-name-input', 'Sommerfest')
    q('template-pick', q('template-card-t2')).click()
    await flushPromises()
    expect(q<HTMLInputElement>('plan-name-input').value).toBe('Sommerfest')
    q('plan-name-save').click()
    await flushPromises()
    expect(wrapper.emitted('submit')?.[0]?.[0]).toMatchObject({
      name: 'Sommerfest',
      templateId: 't2',
    })
  })

  it('is open in the demo too', async () => {
    const wrapper = await openCreate({ sandbox: true })
    q('template-pick', q('template-card-t1')).click()
    await flushPromises()
    q('plan-name-save').click()
    await flushPromises()
    expect(wrapper.emitted('submit')?.[0]?.[0]).toMatchObject({ mode: 'template' })
  })

  it('explains how to make a template when there are none', async () => {
    templates = []
    await openCreate()
    expect(q('template-list-empty').textContent).toContain('Save as template')
    expect(q<HTMLButtonElement>('plan-name-save').disabled).toBe(true)
  })

  it('says when the templates could not be loaded and retries', async () => {
    api.get.mockRejectedValueOnce(new Error('offline'))
    await openCreate()
    expect(q('template-list-error').textContent).toContain('could not be loaded')
    // Retry sits inside the form: it must not also submit it.
    expect(q('template-list-retry').getAttribute('type')).toBe('button')
    q('template-list-retry').click()
    await flushPromises()
    expect(document.querySelectorAll('[data-testid^="template-card-"]')).toHaveLength(2)
  })

  it('drops a pick that turned out to be deleted and reloads the list', async () => {
    const wrapper = await openCreate()
    q('template-pick', q('template-card-t2')).click()
    await flushPromises()
    expect(q<HTMLButtonElement>('plan-name-save').disabled).toBe(false)

    templates = templates.filter((tpl) => tpl.id !== 't2')
    api.get.mockClear()
    ;(wrapper.vm as unknown as { templateGone: (id: string) => void }).templateGone('t2')
    await flushPromises()
    expect(api.get).toHaveBeenCalledWith({ url: '/venue-templates' })
    expect(document.querySelector('[data-testid="template-card-t2"]')).toBeNull()
    expect(q<HTMLButtonElement>('plan-name-save').disabled).toBe(true)
  })

  it('still submits a blank map without a template', async () => {
    const wrapper = await openCreate()
    q('plan-create-blank').querySelector('input')!.click()
    await typeInto('plan-name-input', 'Leer')
    q('plan-name-save').click()
    await flushPromises()
    expect(wrapper.emitted('submit')?.[0]?.[0]).toEqual({
      name: 'Leer',
      mode: 'blank',
      canvas: 'landscape',
      templateId: null,
    })
  })
})

describe('New map: managing my templates', () => {
  it('renames a template from its card', async () => {
    api.patch.mockResolvedValue({ data: template('t1', { name: 'Wiese' }) })
    await openCreate()
    q('template-pick', q('template-card-t1')).click()
    await flushPromises()

    await pickMenuItem(q('template-actions', q('template-card-t1')), 'template-rename')
    expect(q<HTMLInputElement>('template-name-input').value).toBe('Gelände t1')
    await typeInto('template-name-input', '  Wiese ')
    q('template-name-save').click()
    await flushPromises()

    expect(api.patch).toHaveBeenCalledWith({
      url: '/venue-templates/t1',
      body: { name: 'Wiese' },
    })
    expect(q('template-card-t1').textContent).toContain('Wiese')
    // The name it filled in follows the rename.
    expect(q<HTMLInputElement>('plan-name-input').value).toBe('Wiese')
    expect(toast.success).toHaveBeenCalledWith('Template renamed')
  })

  it('keeps the rename dialog open when the server says no', async () => {
    api.patch.mockRejectedValue(new Error('nope'))
    await openCreate()
    await pickMenuItem(q('template-actions', q('template-card-t2')), 'template-rename')
    q('template-name-save').click()
    await flushPromises()
    expect(document.querySelector('[data-testid="template-name-dialog"]')).not.toBeNull()
    expect(toast.success).not.toHaveBeenCalled()
  })

  it('deletes a template after asking, and forgets the pick', async () => {
    api.delete.mockResolvedValue({})
    await openCreate()
    q('template-pick', q('template-card-t2')).click()
    await flushPromises()

    await pickMenuItem(q('template-actions', q('template-card-t2')), 'template-delete')
    expect(confirmDestructive).toHaveBeenCalledWith(
      expect.objectContaining({ text: expect.stringContaining('Halle') }),
    )
    expect(api.delete).toHaveBeenCalledWith({ url: '/venue-templates/t2' })
    expect(document.querySelector('[data-testid="template-card-t2"]')).toBeNull()
    expect(q<HTMLButtonElement>('plan-name-save').disabled).toBe(true)
  })

  it('keeps a template when the deletion is cancelled', async () => {
    confirmDestructive.mockResolvedValueOnce(false)
    await openCreate()
    await pickMenuItem(q('template-actions', q('template-card-t1')), 'template-delete')
    expect(api.delete).not.toHaveBeenCalled()
    expect(document.querySelector('[data-testid="template-card-t1"]')).not.toBeNull()
  })

  it('keeps the card when the deletion fails', async () => {
    api.delete.mockRejectedValue(new Error('nope'))
    await openCreate()
    await pickMenuItem(q('template-actions', q('template-card-t1')), 'template-delete')
    expect(document.querySelector('[data-testid="template-card-t1"]')).not.toBeNull()
  })
})

describe('VenueTemplateNameDialog', () => {
  it('starts from the given name and submits the trimmed one', async () => {
    const wrapper = mount(VenueTemplateNameDialog, {
      props: {
        open: false,
        title: 'Save as template',
        description: 'd',
        submitLabel: 'Save template',
        initialName: 'Gelände',
      },
      global: { plugins: [i18n] },
      attachTo: document.body,
    })
    mounted.push(wrapper)
    await wrapper.setProps({ open: true })
    await flushPromises()
    expect(q<HTMLInputElement>('template-name-input').value).toBe('Gelände')
    await typeInto('template-name-input', '   ')
    expect(q<HTMLButtonElement>('template-name-save').disabled).toBe(true)
    await typeInto('template-name-input', ' Park ')
    q('template-name-save').click()
    await flushPromises()
    expect(wrapper.emitted('submit')).toEqual([['Park']])
  })
})

describe('VenueTemplateThumb', () => {
  it('shows a map symbol for a template with nothing drawn', async () => {
    const wrapper = mount(VenueTemplateThumb, {
      props: { template: template('t3', { shape_count: 0 }) },
      global: { plugins: [i18n] },
    })
    mounted.push(wrapper)
    await flushPromises()
    expect(api.get).not.toHaveBeenCalled()
    expect(wrapper.find('svg.lucide-map, svg[class*="lucide"]').exists()).toBe(true)
  })

  it('keeps the light map colours for a picture', async () => {
    const wrapper = mount(VenueTemplateThumb, {
      props: { template: template('t4', { image_etag: 'e', image_width: 800, image_height: 600 }) },
      global: { plugins: [i18n] },
    })
    mounted.push(wrapper)
    await flushPromises()
    expect(wrapper.classes()).toContain('map-light')
    expect(wrapper.find('image').attributes('href')).toBe('blob:tpl')
  })
})
