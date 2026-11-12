// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { h } from 'vue'

import { Lock, ShieldCheck } from '@lucide/vue'
import { beforeEach, describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import { SidebarProvider } from '@/components/ui/sidebar'

import NavMain, { type NavItem, type NavSubItem } from '@/components/navigation/NavMain.vue'

import i18n from '@/locales/i18n'

/**
 * The badges on an event's task links. A badge's tooltip only opens on hover,
 * so whatever the icon means has to reach a screen reader some other way:
 * "3" next to a shield says nothing about being in charge.
 */

// An open tooltip measures itself; jsdom has no ResizeObserver.
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver

const page = { template: '<div />' }

async function mountNav(tasks: NavSubItem[], { collapsed = false } = {}) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { name: 'home', path: '/', component: page },
      { name: 'tasks', path: '/tasks', component: page },
      { name: 'task-detail', path: '/tasks/:taskId', component: page },
    ],
  })
  await router.push('/')
  await router.isReady()
  const items: NavItem[] = [
    { title: 'Sommerfest', routeName: 'tasks', isActive: true, items: tasks },
  ]
  return mount(
    {
      render: () =>
        h(SidebarProvider, { defaultOpen: !collapsed }, () =>
          h(NavMain, { open: !collapsed, items }),
        ),
    },
    { global: { plugins: [i18n, router] } },
  )
}

const task = (id: string, badge: NavSubItem['badge']): NavSubItem => ({
  title: id,
  routeName: 'task-detail',
  routeParams: { taskId: id },
  badge,
})

/** The link's text as a screen reader gets it: everything not aria-hidden. */
function spoken(node: Node): string {
  if (node.nodeType === Node.TEXT_NODE) return node.textContent ?? ''
  if (node instanceof Element && node.getAttribute('aria-hidden') === 'true') return ''
  return Array.from(node.childNodes).map(spoken).join(' ')
}

function spokenLink(w: Awaited<ReturnType<typeof mountNav>>, taskId: string): string {
  const link = w.find(`a[href="/tasks/${taskId}"]`)
  expect(link.exists()).toBe(true)
  return spoken(link.element).replace(/\s+/g, ' ').trim()
}

beforeEach(() => {
  i18n.global.locale.value = 'en'
})

describe('NavMain: task badges', () => {
  it('reads the label in place of a count beside an icon', async () => {
    const w = await mountNav([
      task('cafe', {
        text: '3',
        icon: ShieldCheck,
        tooltip: "You're in charge · 3 open shifts",
        label: "You're in charge · 3 open shifts",
      }),
    ])

    expect(w.find('a[href="/tasks/cafe"]').text()).toContain('3')
    expect(spokenLink(w, 'cafe')).toBe("cafe You're in charge · 3 open shifts")
  })

  it('reads the label in place of a status beside an icon', async () => {
    const w = await mountNav([
      task('setup', {
        text: 'Draft',
        icon: ShieldCheck,
        tooltip: "You're in charge",
        label: "Draft · You're in charge",
      }),
    ])

    expect(spokenLink(w, 'setup')).toBe("setup Draft · You're in charge")
  })

  it('reads the tooltip when the badge is only an icon', async () => {
    const w = await mountNav([
      task('bar', { text: '', icon: Lock, tooltip: 'Only for the Bar team' }),
    ])

    expect(spokenLink(w, 'bar')).toBe('bar Only for the Bar team')
  })

  it('reads the text alone when there is no label', async () => {
    const w = await mountNav([
      task('stage', { text: '2', tooltip: '2 open shifts', variant: 'outline' }),
    ])

    expect(spokenLink(w, 'stage')).toBe('stage 2')
  })
})

describe('NavMain: group label', () => {
  async function mountGroup(groupLabelKey?: string) {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { name: 'home', path: '/', component: page },
        { name: 'tasks', path: '/tasks', component: page },
        { name: 'task-detail', path: '/tasks/:taskId', component: page },
      ],
    })
    await router.push('/')
    await router.isReady()
    // A group with sub-items; its tooltip asks the sidebar whether it is collapsed.
    const items: NavItem[] = [
      {
        title: 'Sommerfest',
        routeName: 'tasks',
        isActive: true,
        items: [task('stage', undefined)],
      },
    ]
    return mount(
      {
        render: () => h(SidebarProvider, () => h(NavMain, { open: true, items, groupLabelKey })),
      },
      { global: { plugins: [i18n, router] } },
    )
  }

  it('heads the group "Platform" when no label is given', async () => {
    const w = await mountGroup()

    expect(w.find('[data-sidebar$="-label"]').text()).toBe('Platform')
  })

  // The sidebar's management and admin groups pass their own; under a
  // misspelt prop name all three groups read "Platform".
  it('heads the group with the label it is given', async () => {
    const w = await mountGroup('admin.sidebar.section')

    expect(w.find('[data-sidebar$="-label"]').text()).toBe('Administration')
  })
})

describe('NavMain: the tabs of one page', () => {
  // The event's settings fold out to its tabs: one route, told apart by `?tab=`.
  async function mountTabs(path: string, badge?: number) {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ name: 'event-settings', path: '/settings/:eventId?', component: page }],
    })
    await router.push(path)
    await router.isReady()
    const tab = (title: string, name?: string): NavSubItem => ({
      title,
      routeName: 'event-settings',
      routeQuery: { tab: name },
    })
    const items: NavItem[] = [
      {
        title: 'Event',
        routeName: 'event-settings',
        isActive: true,
        badge,
        badgeLabel: badge ? `${badge} requests to decide` : undefined,
        items: [tab('Details'), tab('People', 'people'), tab('Map', 'map')],
      },
    ]
    return mount(
      { render: () => h(SidebarProvider, () => h(NavMain, { open: true, items })) },
      { global: { plugins: [i18n, router] } },
    )
  }

  const current = (w: Awaited<ReturnType<typeof mountTabs>>) =>
    w
      .findAll('[data-sidebar="menu-sub-button"]')
      .filter((link) => link.attributes('data-active') === 'true')
      .map((link) => link.text())

  it('lights only the tab that is open', async () => {
    expect(current(await mountTabs('/settings?tab=people'))).toEqual(['People'])
  })

  it('lights the first tab when the page has no tab in its address', async () => {
    expect(current(await mountTabs('/settings/e1'))).toEqual(['Details'])
  })

  it('links each tab by its query', async () => {
    const w = await mountTabs('/settings')
    const hrefs = w.findAll('[data-sidebar="menu-sub-button"]').map((a) => a.attributes('href'))
    expect(hrefs).toEqual(['/settings', '/settings?tab=people', '/settings?tab=map'])
  })

  it('shows what waits on the entry itself, for a screen reader too', async () => {
    const w = await mountTabs('/settings', 2)
    const badge = w.find('[data-testid="sidebar-badge-event-settings"]')
    expect(badge.exists()).toBe(true)
    expect(spoken(badge.element).replace(/\s+/g, ' ').trim()).toBe('2 requests to decide')
  })

  it('draws no badge when nothing waits', async () => {
    const w = await mountTabs('/settings', 0)
    expect(w.find('[data-testid="sidebar-badge-event-settings"]').exists()).toBe(false)
  })
})

describe('NavMain: the icon-only sidebar', () => {
  // Collapsed to icons, every other entry names itself in a tooltip
  // (SidebarMenuButton's); one with sub-items has to do the same.
  async function tooltipOfTasks(collapsed: boolean) {
    const w = await mountNav([task('stage', undefined)], { collapsed })
    await w.find('[data-testid="sidebar-link-tasks"]').trigger('focus')
    await flushPromises()
    const content = document.body.querySelector('[data-slot="tooltip-content"]')
    const result = { text: content?.textContent ?? '', hidden: content?.hasAttribute('hidden') }
    w.unmount()
    return result
  }

  it('names an entry with sub-items when collapsed', async () => {
    const tip = await tooltipOfTasks(true)
    expect(tip.text).toContain('Sommerfest')
    expect(tip.hidden).toBe(false)
  })

  it('keeps that tooltip hidden while the names are on show', async () => {
    const tip = await tooltipOfTasks(false)
    expect(tip.hidden).toBe(true)
  })
})
