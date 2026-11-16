<script setup lang="ts">
/**
 * Shared lists of one event (`/app/shared-lists/:eventId?`, the selected
 * event without one): public links through which people without an account
 * sign up for shifts.
 *
 * Three tabs: the lists themselves, the tasks and which of their places no
 * open list offers, and the page a list's link opens. A list's details open
 * over the page. The tab, each table's view and the open list live in the
 * address (`components/shared-lists/pageQuery.ts`), which is why the route
 * keeps this page mounted while the query changes.
 *
 * Event admins and the people in charge of tasks use it; the server decides
 * per request, and this page says so when it refuses.
 */
import { computed, ref, watch } from 'vue'

import { Plus } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { type LocationQueryRaw, RouterLink, useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import { useSharedListsStore } from '@/stores/sharedLists'

import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

import SharedListDetailDialog from '@/components/shared-lists/SharedListDetailDialog.vue'
import SharedListsLinksTab from '@/components/shared-lists/SharedListsLinksTab.vue'
import SharedListsPreviewTab from '@/components/shared-lists/SharedListsPreviewTab.vue'
import SharedListsTasksTab from '@/components/shared-lists/SharedListsTasksTab.vue'
import {
  LIST_KEY,
  PREVIEW_KEY,
  SIGNUPS_PREFIX,
  type SharedListsTab,
  TABS,
  TAB_KEY,
  TASKS_PREFIX,
} from '@/components/shared-lists/pageQuery'
import HintTooltip from '@/components/utils/HintTooltip.vue'

import { type NormalizedApiError, normalizeApiError } from '@/lib/api-errors'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const store = useSharedListsStore()

const eventId = computed<string | null>(() => {
  const param = route.params.eventId
  if (typeof param === 'string' && param) return param
  return authStore.selectedEventId ?? null
})

const eventName = computed(() =>
  authStore.selectedEvent && authStore.selectedEvent.id === eventId.value
    ? authStore.selectedEvent.name
    : null,
)

const loadError = ref<NormalizedApiError | null>(null)

async function loadOverview() {
  loadError.value = null
  if (!eventId.value) return
  try {
    await store.fetchOverview()
  } catch (error) {
    loadError.value = normalizeApiError(error)
  }
}

watch(
  eventId,
  (id) => {
    store.setEvent(id)
    void loadOverview()
  },
  { immediate: true },
)

/** Refused outright (not allowed, or no such event for this viewer): retrying will not help. */
const refused = computed(() => loadError.value?.status === 403 || loadError.value?.status === 404)

// --- The address ---

function replaceQuery(query: LocationQueryRaw) {
  void router.replace({ query, hash: route.hash })
}

function withQuery(patch: Record<string, string | undefined>): LocationQueryRaw {
  const query: LocationQueryRaw = { ...route.query }
  for (const [key, value] of Object.entries(patch)) {
    if (value === undefined) delete query[key]
    else query[key] = value
  }
  return query
}

/** The query without the open list and its sign-ups table. */
function withoutDetail(): LocationQueryRaw {
  return Object.fromEntries(
    Object.entries(route.query).filter(
      ([key]) => key !== LIST_KEY && !key.startsWith(`${SIGNUPS_PREFIX}_`),
    ),
  )
}

const tab = computed<SharedListsTab>(
  () => TABS.find((name) => name === route.query[TAB_KEY]) ?? 'links',
)

function setTab(value: string | number) {
  const next = TABS.find((name) => name === value)
  if (next) replaceQuery(withQuery({ [TAB_KEY]: next === 'links' ? undefined : next }))
}

const openListId = computed(() => {
  const id = route.query[LIST_KEY]
  return typeof id === 'string' && id ? id : null
})

function openList(id: string) {
  replaceQuery(withQuery({ [LIST_KEY]: id }))
}

function closeList() {
  replaceQuery(withoutDetail())
}

function previewList(id: string) {
  replaceQuery({ ...withoutDetail(), [TAB_KEY]: 'preview', [PREVIEW_KEY]: id })
}

/** The notice's way to the tasks whose free places no open list offers. */
function showTodoTasks() {
  replaceQuery(
    withQuery({
      [TAB_KEY]: 'tasks',
      [`${TASKS_PREFIX}_filter`]: 'todo',
      [`${TASKS_PREFIX}_q`]: undefined,
      [`${TASKS_PREFIX}_page`]: undefined,
    }),
  )
}

function create() {
  if (!eventId.value) return
  void router.push({ name: 'shared-list-create', params: { eventId: eventId.value } })
}

const TRIGGER_CLASS =
  'h-auto flex-none gap-2 rounded-none border-0 border-b-2 border-transparent px-0.5 pt-1 pb-2.5 text-[15px] font-semibold text-muted-foreground shadow-none data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:text-foreground data-[state=active]:shadow-none dark:data-[state=active]:border-primary dark:data-[state=active]:bg-transparent'
</script>

<template>
  <div class="mx-auto max-w-6xl space-y-6" data-testid="shared-lists-page">
    <div class="flex flex-wrap items-end justify-between gap-4">
      <div class="min-w-0 max-w-3xl space-y-1.5">
        <p v-if="eventName" class="text-sm text-muted-foreground">{{ eventName }}</p>
        <h1 data-testid="page-heading" class="text-2xl font-bold sm:text-3xl">
          {{ t('sharedLists.page.title') }}
        </h1>
        <p class="text-muted-foreground">{{ t('sharedLists.page.lede') }}</p>
      </div>
      <template v-if="store.overview && !loadError">
        <p
          v-if="store.reshareLocked"
          class="max-w-sm rounded-xl bg-muted px-3 py-2.5 text-[13px]"
          data-testid="shared-lists-managers-off"
        >
          {{ t('sharedLists.page.managersOff') }}
        </p>
        <HintTooltip
          v-else
          :label="store.overview.can_create ? null : t('sharedLists.page.createDisabled')"
        >
          <span class="inline-flex max-sm:w-full">
            <Button
              class="max-sm:h-11 max-sm:w-full"
              :disabled="!store.overview.can_create"
              data-testid="btn-share-list"
              @click="create"
            >
              <Plus aria-hidden="true" />
              {{ t('sharedLists.page.create') }}
            </Button>
          </span>
        </HintTooltip>
      </template>
    </div>

    <!-- Until the profile is in, the selected event is not known yet. -->
    <div
      v-if="!eventId && authStore.profile"
      class="flex flex-col items-center gap-3 rounded-xl border border-dashed px-4 py-10 text-center text-sm"
      data-testid="shared-lists-no-event"
    >
      <p class="text-muted-foreground">{{ t('sharedLists.page.noEvent') }}</p>
      <Button as-child variant="outline">
        <RouterLink :to="{ name: 'select-event', query: { mode: 'switch' } }">
          {{ t('sharedLists.page.chooseEvent') }}
        </RouterLink>
      </Button>
    </div>

    <div
      v-else-if="loadError"
      class="flex flex-col items-center gap-3 rounded-xl border border-dashed px-4 py-10 text-center text-sm"
      role="alert"
      data-testid="shared-lists-error"
    >
      <p class="max-w-md text-muted-foreground">
        {{ loadError.status === 403 ? t('sharedLists.page.forbidden') : loadError.message }}
      </p>
      <Button v-if="refused" as-child variant="outline">
        <RouterLink :to="{ name: 'home' }">{{ t('sharedLists.page.backHome') }}</RouterLink>
      </Button>
      <Button v-else variant="outline" data-testid="shared-lists-retry" @click="loadOverview">
        {{ t('sharedLists.page.retry') }}
      </Button>
    </div>

    <div v-else-if="!store.overview || !eventId" class="space-y-3" aria-busy="true">
      <Skeleton class="h-20 w-full rounded-xl" />
      <Skeleton v-for="i in 3" :key="i" class="h-24 w-full rounded-xl" />
    </div>

    <Tabs v-else :model-value="tab" class="gap-5" @update:model-value="setTab">
      <!-- Scrolls sideways on a narrow phone rather than wrapping the tabs. -->
      <div class="overflow-x-auto shadow-[inset_0_-1px_0_var(--border)] [scrollbar-width:none]">
        <TabsList
          class="h-auto w-max gap-6 rounded-none bg-transparent p-0"
          :aria-label="t('sharedLists.tabs.label')"
        >
          <TabsTrigger value="links" :class="TRIGGER_CLASS" data-testid="tab-links">
            {{ t('sharedLists.tabs.links') }}
            <!-- From the overview, which every visit loads, whichever tab it opens on. -->
            <span
              class="rounded-full bg-muted px-1.5 text-xs font-semibold tabular-nums"
              data-testid="tab-links-count"
            >
              {{ store.overview.summary.active_lists }}
            </span>
          </TabsTrigger>
          <TabsTrigger value="tasks" :class="TRIGGER_CLASS" data-testid="tab-tasks">
            {{ t('sharedLists.tabs.tasks') }}
          </TabsTrigger>
          <TabsTrigger value="preview" :class="TRIGGER_CLASS" data-testid="tab-preview">
            {{ t('sharedLists.tabs.preview') }}
          </TabsTrigger>
        </TabsList>
      </div>

      <TabsContent value="links">
        <SharedListsLinksTab :key="eventId" @open="openList" @show-todo-tasks="showTodoTasks" />
      </TabsContent>
      <TabsContent value="tasks">
        <SharedListsTasksTab :key="eventId" :event-id="eventId" @open="openList" />
      </TabsContent>
      <TabsContent value="preview">
        <SharedListsPreviewTab :key="eventId" />
      </TabsContent>
    </Tabs>

    <SharedListDetailDialog
      v-if="eventId && store.overview"
      :list-id="openListId"
      @close="closeList"
      @preview="previewList"
    />
  </div>
</template>
