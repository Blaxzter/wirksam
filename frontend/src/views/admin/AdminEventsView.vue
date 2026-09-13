<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import { ChevronDown, ChevronRight, Copy, Plus, Search } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { toast } from 'vue-sonner'

import { useAuthStore } from '@/stores/auth'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { useDialog } from '@/composables/useDialog'

import Badge from '@/components/ui/badge/Badge.vue'
import Button from '@/components/ui/button/Button.vue'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { DateRangePicker } from '@/components/ui/date-range-picker'
import Input from '@/components/ui/input/Input.vue'
import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationFirst,
  PaginationItem,
  PaginationLast,
  PaginationNext,
  PaginationPrevious,
} from '@/components/ui/pagination'

import AdminEventRow from '@/components/admin/AdminEventRow.vue'
import AdminEventRowSkeleton from '@/components/admin/AdminEventRowSkeleton.vue'

import type { EventListResponse, EventRead } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'

const PAGE_SIZE = 20
const SEARCH_DEBOUNCE_MS = 300

const { t } = useI18n()
const router = useRouter()
const authStore = useAuthStore()
const { get, patch, delete: del } = useAuthenticatedClient()
const { confirmDestructive } = useDialog()

const selectedEventId = computed(() => authStore.selectedEventId)

// === Filters ===
const searchInput = ref('')
const searchQuery = ref('')
const dateFrom = ref<string | null>(null)
const dateTo = ref<string | null>(null)
const markedDays = ref<Set<string>>(new Set())

// === Active section state ===
const activeItems = ref<EventRead[]>([])
const activeTotal = ref(0)
const activePage = ref(1)
const loadingActive = ref(false)
const activePages = computed(() => Math.max(1, Math.ceil(activeTotal.value / PAGE_SIZE)))

// === Expired section state (lazy-loaded on first expand) ===
const expiredItems = ref<EventRead[]>([])
const expiredTotal = ref(0)
const expiredPage = ref(1)
const loadingExpired = ref(false)
const expiredOpen = ref(false)
const expiredLoaded = ref(false)
const expiredPages = computed(() => Math.max(1, Math.ceil(expiredTotal.value / PAGE_SIZE)))

async function handleVisibleMonth(range: { from: string; to: string }) {
  try {
    const res = await get<{ data: string[] }>({
      url: '/tasks/active-dates',
      query: { date_from: range.from, date_to: range.to, all_events: true },
    })
    markedDays.value = new Set(res.data)
  } catch {
    // non-critical
  }
}

const canFeature = computed(() => authStore.isAdmin)
const featuringId = ref<string | null>(null)

function buildBaseQuery(): Record<string, unknown> {
  const q: Record<string, unknown> = { limit: PAGE_SIZE }
  // The superadmin curates the whole catalogue; everyone else manages the
  // events they actually belong to.
  q.scope = authStore.isAdmin ? 'all' : 'mine'
  if (searchQuery.value) q.search = searchQuery.value
  if (dateFrom.value) q.date_from = dateFrom.value
  if (dateTo.value) q.date_to = dateTo.value
  return q
}

/** Put an event on (or take it off) the home screen. Superadmin only. */
async function handleToggleFeatured(event: EventRead) {
  featuringId.value = event.id
  try {
    const res = await patch<{ data: EventRead }>({
      url: `/events/${event.id}/featured`,
      body: { is_featured: !event.is_featured },
    })
    const apply = (list: EventRead[]) =>
      list.map((e) => (e.id === event.id ? { ...e, is_featured: res.data.is_featured } : e))
    activeItems.value = apply(activeItems.value)
    expiredItems.value = apply(expiredItems.value)
    toast.success(
      res.data.is_featured
        ? t('duties.events.featured.featured')
        : t('duties.events.featured.unfeatured'),
    )
  } catch (error) {
    toastApiError(error)
  } finally {
    featuringId.value = null
  }
}

async function loadActive() {
  loadingActive.value = true
  try {
    const response = await get<{ data: EventListResponse }>({
      url: '/events/',
      query: {
        ...buildBaseQuery(),
        skip: (activePage.value - 1) * PAGE_SIZE,
        is_expired: false,
      },
    })
    activeItems.value = response.data.items
    activeTotal.value = response.data.total
  } catch (error) {
    toastApiError(error)
  } finally {
    loadingActive.value = false
  }
}

async function loadExpired() {
  loadingExpired.value = true
  try {
    const response = await get<{ data: EventListResponse }>({
      url: '/events/',
      query: {
        ...buildBaseQuery(),
        skip: (expiredPage.value - 1) * PAGE_SIZE,
        is_expired: true,
      },
    })
    expiredItems.value = response.data.items
    expiredTotal.value = response.data.total
    expiredLoaded.value = true
  } catch (error) {
    toastApiError(error)
  } finally {
    loadingExpired.value = false
  }
}

// Debounced search
let searchDebounceTimer: ReturnType<typeof setTimeout> | null = null
watch(searchInput, (value) => {
  if (searchDebounceTimer) clearTimeout(searchDebounceTimer)
  searchDebounceTimer = setTimeout(() => {
    searchQuery.value = value.trim()
  }, SEARCH_DEBOUNCE_MS)
})

// On filter change, reset paging and reload (expired only when section is open)
watch([searchQuery, dateFrom, dateTo], () => {
  activePage.value = 1
  loadActive()
  expiredPage.value = 1
  if (expiredOpen.value) {
    loadExpired()
  } else {
    // Mark stale so a subsequent open re-fetches with new filters
    expiredLoaded.value = false
  }
})

// Lazy-load expired the first time the section is expanded (or after filters change)
watch(expiredOpen, (open) => {
  if (open && !expiredLoaded.value) loadExpired()
})

watch(activePage, loadActive)
watch(expiredPage, () => {
  if (expiredOpen.value) loadExpired()
})

const handleDelete = async (event: EventRead) => {
  const confirmed = await confirmDestructive(t('duties.events.deleteConfirm'))
  if (!confirmed) return
  try {
    await del({ url: `/events/${event.id}` })
    toast.success(t('duties.events.delete'))
    // Reload whichever section the deleted item belonged to
    if (event.is_expired) {
      if (expiredOpen.value) await loadExpired()
      else expiredLoaded.value = false
    } else {
      await loadActive()
    }
  } catch (error) {
    toastApiError(error)
  }
}

const handleEdit = (event: EventRead) => {
  router.push({ name: 'event-settings', params: { eventId: event.id } })
}

// Running an event again: same tasks, same shift grid, new dates. The row
// action reaches any event in either table; the header button is a shortcut to
// the one currently selected.
const handleClone = (event: EventRead) => {
  router.push({ name: 'event-clone', params: { sourceId: event.id } })
}

const cloneSourceId = computed(() =>
  selectedEventId.value && authStore.canManageEvent(selectedEventId.value)
    ? selectedEventId.value
    : null,
)

const goToCloneSelected = () => {
  if (!cloneSourceId.value) return
  router.push({ name: 'event-clone', params: { sourceId: cloneSourceId.value } })
}

// Creating an event is a page of its own — the form never fitted a dialog on
// a phone. It comes back here once the event exists.
const goToCreate = () => {
  router.push({ name: 'event-create' })
}

onMounted(loadActive)
</script>

<template>
  <div class="mx-auto max-w-7xl space-y-6">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div class="space-y-2">
        <h1 data-testid="page-heading" class="text-2xl sm:text-3xl font-bold">
          {{ t('admin.events.title') }}
        </h1>
        <p class="text-muted-foreground">{{ t('admin.events.subtitle') }}</p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <!-- Visible at every width on purpose: "Create event" has a phone-sized
             FAB to fall back on, this has none, and a second round button in
             the same corner would sit on top of it. Without this the feature
             has no reachable entry point on a phone at all. -->
        <Button
          v-if="cloneSourceId"
          data-testid="btn-clone-event"
          variant="outline"
          @click="goToCloneSelected"
        >
          <Copy class="mr-2 h-4 w-4" />
          {{ t('duties.events.clone.action') }}
        </Button>
        <Button data-testid="btn-create-event" class="max-xl:hidden" @click="goToCreate">
          <Plus class="mr-2 h-4 w-4" />
          {{ t('duties.events.create') }}
        </Button>
      </div>
    </div>

    <div class="flex flex-wrap items-center gap-4">
      <div class="relative flex-1">
        <Search class="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          v-model="searchInput"
          data-testid="input-search"
          :placeholder="t('common.actions.search')"
          class="pl-10"
        />
      </div>
      <DateRangePicker
        :date-from="dateFrom"
        :date-to="dateTo"
        :marked-days="markedDays"
        :default-label="t('admin.events.filters.allDates')"
        :reset-label="t('admin.events.filters.showAll')"
        @update:date-from="dateFrom = $event"
        @update:date-to="dateTo = $event"
        @update:visible-month="handleVisibleMonth"
      />
    </div>

    <!-- Active / upcoming events -->
    <div
      v-if="!loadingActive && activeItems.length === 0"
      class="py-12 text-center text-muted-foreground"
    >
      {{ t('duties.events.empty') }}
    </div>
    <div v-else class="overflow-x-auto rounded-lg border bg-card">
      <table class="w-full min-w-[53rem] table-fixed text-sm">
        <colgroup>
          <col />
          <col class="w-28" />
          <col class="w-28" />
          <col class="w-40" />
          <col class="w-20" />
          <col class="w-44" />
        </colgroup>
        <thead class="bg-muted/50">
          <tr>
            <th class="px-4 py-2 text-left font-medium">{{ t('duties.events.fields.name') }}</th>
            <th class="px-4 py-2 text-left font-medium">
              {{ t('duties.events.fields.startDate') }}
            </th>
            <th class="px-4 py-2 text-left font-medium">{{ t('duties.events.fields.endDate') }}</th>
            <th class="px-4 py-2 text-left font-medium">{{ t('duties.events.fields.status') }}</th>
            <th class="px-4 py-2 text-left font-medium">
              {{ t('duties.events.members.columnHeader') }}
            </th>
            <th class="px-4 py-2 text-right font-medium"></th>
          </tr>
        </thead>
        <tbody class="divide-y">
          <template v-if="loadingActive && activeItems.length === 0">
            <AdminEventRowSkeleton v-for="i in 5" :key="`skeleton-active-${i}`" />
          </template>
          <AdminEventRow
            v-for="event in activeItems"
            v-else
            :key="event.id"
            :event="event"
            :selected-event-id="selectedEventId"
            :can-feature="canFeature"
            :featuring-id="featuringId"
            @edit="handleEdit"
            @clone="handleClone"
            @delete="handleDelete"
            @toggle-featured="handleToggleFeatured"
          />
        </tbody>
      </table>
    </div>

    <div v-if="activePages > 1" class="flex justify-center">
      <Pagination
        v-model:page="activePage"
        :total="activeTotal"
        :items-per-page="PAGE_SIZE"
        :sibling-count="1"
      >
        <PaginationContent>
          <PaginationFirst />
          <PaginationPrevious />
          <template v-for="(item, index) in activePages" :key="index">
            <PaginationItem
              v-if="Math.abs(item - activePage) <= 1 || item === 1 || item === activePages"
              :value="item"
              :is-active="activePage === item"
              as-child
            >
              <Button
                variant="outline"
                size="icon"
                class="h-9 w-9"
                :class="
                  activePage === item ? '!bg-primary !text-primary-foreground !border-primary' : ''
                "
              >
                {{ item }}
              </Button>
            </PaginationItem>
            <PaginationEllipsis v-else-if="Math.abs(item - activePage) === 2" />
          </template>
          <PaginationNext />
          <PaginationLast />
        </PaginationContent>
      </Pagination>
    </div>

    <!-- Expired events (collapsible, lazy-loaded on first expand) -->
    <Collapsible v-model:open="expiredOpen">
      <CollapsibleTrigger
        class="flex w-full items-center gap-2 rounded-md border bg-muted/30 px-3 py-2 text-left text-sm font-medium hover:bg-muted/50"
        data-testid="btn-toggle-expired"
      >
        <component :is="expiredOpen ? ChevronDown : ChevronRight" class="size-4" />
        <span>{{ t('admin.events.expiredSection') }}</span>
        <Badge v-if="expiredLoaded" variant="outline" class="ml-1">
          {{ expiredTotal }}
        </Badge>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div
          v-if="expiredLoaded && expiredItems.length === 0 && !loadingExpired"
          class="py-8 text-center text-muted-foreground text-sm"
        >
          {{ t('admin.events.noExpired') }}
        </div>
        <template v-else>
          <div class="mt-2 overflow-x-auto rounded-lg border bg-card">
            <table class="w-full min-w-[53rem] table-fixed text-sm">
              <colgroup>
                <col />
                <col class="w-28" />
                <col class="w-28" />
                <col class="w-40" />
                <col class="w-20" />
                <col class="w-44" />
              </colgroup>
              <thead class="bg-muted/50">
                <tr>
                  <th class="px-4 py-2 text-left font-medium">
                    {{ t('duties.events.fields.name') }}
                  </th>
                  <th class="px-4 py-2 text-left font-medium">
                    {{ t('duties.events.fields.startDate') }}
                  </th>
                  <th class="px-4 py-2 text-left font-medium">
                    {{ t('duties.events.fields.endDate') }}
                  </th>
                  <th class="px-4 py-2 text-left font-medium">
                    {{ t('duties.events.fields.status') }}
                  </th>
                  <th class="px-4 py-2 text-left font-medium">
                    {{ t('duties.events.members.columnHeader') }}
                  </th>
                  <th class="px-4 py-2 text-right font-medium"></th>
                </tr>
              </thead>
              <tbody class="divide-y">
                <template v-if="loadingExpired && expiredItems.length === 0">
                  <AdminEventRowSkeleton v-for="i in 3" :key="`skeleton-expired-${i}`" />
                </template>
                <AdminEventRow
                  v-for="event in expiredItems"
                  v-else
                  :key="event.id"
                  :event="event"
                  :selected-event-id="selectedEventId"
                  :can-feature="canFeature"
                  :featuring-id="featuringId"
                  muted
                  @edit="handleEdit"
                  @clone="handleClone"
                  @delete="handleDelete"
                  @toggle-featured="handleToggleFeatured"
                />
              </tbody>
            </table>
          </div>

          <div v-if="expiredPages > 1" class="mt-3 flex justify-center">
            <Pagination
              v-model:page="expiredPage"
              :total="expiredTotal"
              :items-per-page="PAGE_SIZE"
              :sibling-count="1"
            >
              <PaginationContent>
                <PaginationFirst />
                <PaginationPrevious />
                <template v-for="(item, index) in expiredPages" :key="index">
                  <PaginationItem
                    v-if="Math.abs(item - expiredPage) <= 1 || item === 1 || item === expiredPages"
                    :value="item"
                    :is-active="expiredPage === item"
                    as-child
                  >
                    <Button
                      variant="outline"
                      size="icon"
                      class="h-9 w-9"
                      :class="
                        expiredPage === item
                          ? '!bg-primary !text-primary-foreground !border-primary'
                          : ''
                      "
                    >
                      {{ item }}
                    </Button>
                  </PaginationItem>
                  <PaginationEllipsis v-else-if="Math.abs(item - expiredPage) === 2" />
                </template>
                <PaginationNext />
                <PaginationLast />
              </PaginationContent>
            </Pagination>
          </div>
        </template>
      </CollapsibleContent>
    </Collapsible>

    <Button
      size="icon"
      class="xl:hidden fixed bottom-24 md:bottom-6 right-6 z-40 h-14 w-14 rounded-full shadow-lg"
      data-testid="fab-create-event"
      :aria-label="t('duties.events.create')"
      @click="goToCreate"
    >
      <Plus class="size-7" :stroke-width="2.5" />
    </Button>
  </div>
</template>
