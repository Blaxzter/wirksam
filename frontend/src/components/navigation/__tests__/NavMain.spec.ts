// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { h } from 'vue'

import { Lock, ShieldCheck } from '@lucide/vue'
import { beforeEach, describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import { TooltipProvider } from '@/components/ui/tooltip'

import NavMain, { type NavItem, type NavSubItem } from '@/components/navigation/NavMain.vue'

import i18n from '@/locales/i18n'

/**
 * The badges on an event's task links. A badge's tooltip only opens on hover,
 * so whatever the icon means has to reach a screen reader some other way:
 * "3" next to a shield says nothing about being in charge.
 */

const page = { template: '<div />' }

async function mountNav(tasks: NavSubItem[]) {
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
    { render: () => h(TooltipProvider, () => h(NavMain, { open: true, items })) },
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
    // A group with sub-items, which needs no surrounding sidebar.
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
        render: () => h(TooltipProvider, () => h(NavMain, { open: true, items, groupLabelKey })),
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
