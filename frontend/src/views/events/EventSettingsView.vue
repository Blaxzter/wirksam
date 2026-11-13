<script setup lang="ts">
import { type Ref, computed, nextTick, onMounted, ref, watch } from 'vue'

import { Info, Map as MapIcon, MapPin, Pencil, Ticket, Users } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import Button from '@/components/ui/button/Button.vue'

import EventDetailsSummary from '@/components/events/EventDetailsSummary.vue'
import EventEditForm from '@/components/events/EventEditForm.vue'
import EventHours from '@/components/events/EventHours.vue'
import EventVoucherSettings from '@/components/events/EventVoucherSettings.vue'
import EventVouchers from '@/components/events/EventVouchers.vue'
import EventInvitations from '@/components/events/EventInvitations.vue'
import EventJoinRequests from '@/components/events/EventJoinRequests.vue'
import EventMembers from '@/components/events/EventMembers.vue'
import EventLocations from '@/components/locations/EventLocations.vue'
import VenueMapEditor from '@/components/venue-map/VenueMapEditor.vue'

import type {
  EventInvitationRead,
  EventJoinRequestRead,
  EventMemberRead,
  EventRead,
  TaskListResponse,
  TaskRead,
  VolunteerHours,
} from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const { get } = useAuthenticatedClient()

const targetEventId = computed<string | null>(() => {
  const p = route.params.eventId
  if (typeof p === 'string' && p) return p
  return authStore.selectedEventId ?? null
})

type Tab = 'details' | 'people' | 'vouchers' | 'locations' | 'map'
const activeTab = ref<Tab>('details')

function readTabFromQuery() {
  // The route also changes on the way out; another page's `?tab=` is not ours.
  if (route.name !== 'event-settings') return
  const qTab = route.query.tab
  // Teams moved to a page of their own; old `?tab=teams` links land there.
  if (qTab === 'teams') {
    router.replace({
      name: 'teams',
      params: { eventId: targetEventId.value ?? undefined },
      query: typeof route.query.team === 'string' ? { team: route.query.team } : {},
    })
    return
  }
  // "managers" is the old name for this tab; keep old links working.
  if (qTab === 'people' || qTab === 'managers') activeTab.value = 'people'
  else if (qTab === 'vouchers' || qTab === 'locations' || qTab === 'map') activeTab.value = qTab
  else activeTab.value = 'details'
}
readTabFromQuery()
watch(() => route.query.tab, readTabFromQuery)

function setTab(tab: Tab) {
  activeTab.value = tab
  router.replace({
    query: {
      ...route.query,
      tab: tab === 'details' ? undefined : tab,
    },
  })
}

const event = ref<EventRead | null>(null)
const tasks = ref<TaskRead[]>([])
const members = ref<EventMemberRead[]>([])
const invitations = ref<EventInvitationRead[]>([])
const joinRequests = ref<EventJoinRequestRead[]>([])
const hours = ref<VolunteerHours[]>([])
const loading = ref(false)

const canManage = computed(() =>
  targetEventId.value ? authStore.canManageEvent(targetEventId.value) : false,
)
const isOwner = computed(() =>
  targetEventId.value ? authStore.isEventOwner(targetEventId.value) : false,
)
/** Anyone in the event can see the roster; only admins get the rest. */
const isMember = computed(() =>
  targetEventId.value ? authStore.isEventMember(targetEventId.value) : false,
)

/**
 * Once a task earns vouchers (published or archived) or takes them, the
 * organisers get the Vouchers tab: its rules and who has how many. A draft
 * counts here too, although not in the event's counts, so the rules can be
 * set before the task goes out (its people in charge are already bound by
 * them).
 */
const usesVouchers = computed(
  () =>
    (event.value?.voucher_task_count ?? 0) > 0 ||
    (event.value?.voucher_point_count ?? 0) > 0 ||
    tasks.value.some((task) => (task.vouchers_per_shift ?? 0) > 0 || task.is_voucher_point),
)

/**
 * The tab actually shown: "vouchers", "locations" and "map" are for event
 * admins (vouchers only once the event uses them), so a shared `?tab=map` link
 * falls back to the details for everyone else.
 */
const shownTab = computed<Tab>(() => {
  if ((activeTab.value === 'locations' || activeTab.value === 'map') && !canManage.value)
    return 'details'
  if (activeTab.value === 'vouchers' && !(canManage.value && usesVouchers.value)) return 'details'
  return activeTab.value
})

// On a phone the tab row scrolls sideways: keep the chosen tab in view, so a
// `?tab=map` link does not open with its tab cut off at the edge.
const tabRow = ref<HTMLElement | null>(null)
watch(
  shownTab,
  async (tab) => {
    await nextTick()
    tabRow.value
      ?.querySelector<HTMLElement>(`[data-testid="tab-${tab}"]`)
      ?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' })
  },
  { immediate: true },
)

/**
 * Read one list of the event into `target`. The page outlives a switch to
 * another event (tabs no longer remount it), so an answer that arrives after
 * the switch is dropped rather than shown under the new event's name.
 */
async function loadList<T>(
  target: Ref<T[]>,
  url: string,
  query?: Record<string, string>,
): Promise<void> {
  const id = targetEventId.value
  if (!id) return
  let data: T[] = []
  try {
    data = (await get<{ data: T[] }>({ url: `/events/${id}/${url}`, query })).data
  } catch {
    // An empty list, as before: the section shows its empty state.
  }
  if (id === targetEventId.value) target.value = data
}

function loadMembers() {
  return loadList(members, 'members')
}

function loadInvitations() {
  return canManage.value ? loadList(invitations, 'invitations') : Promise.resolve()
}

function loadJoinRequests() {
  return canManage.value
    ? loadList(joinRequests, 'join-requests', { status: 'pending' })
    : Promise.resolve()
}

function loadHours() {
  return canManage.value ? loadList(hours, 'hours') : Promise.resolve()
}

/** Total minutes per member, for the badge on each roster row. */
const hoursByUser = computed(() =>
  canManage.value
    ? Object.fromEntries(hours.value.map((h) => [h.user_id, h.total_minutes]))
    : undefined,
)

async function loadPeople() {
  await Promise.all([loadMembers(), loadInvitations(), loadJoinRequests(), loadHours()])
}

/** A request was decided: the sidebar's count of waiting requests goes down with it. */
async function handleJoinRequestsUpdated() {
  await loadPeople()
  if (targetEventId.value) void authStore.refreshSelectedEvent(targetEventId.value)
}

/** After leaving an event the user no longer belongs here — send them home. */
async function handleLeft() {
  await authStore.loadProfile()
  router.push({ name: 'select-event', query: { mode: 'switch' } })
}

async function loadEvent() {
  const id = targetEventId.value
  if (!id) return
  loading.value = true
  try {
    const [eventRes, tasksRes] = await Promise.all([
      get<{ data: EventRead }>({ url: `/events/${id}` }),
      get<{ data: TaskListResponse }>({
        url: '/tasks/',
        query: { limit: 200, event_id: id, all_events: true },
      }),
    ])
    if (id !== targetEventId.value) return
    event.value = eventRes.data
    tasks.value = tasksRes.data.items
    if (isMember.value) await loadPeople()
  } catch (error) {
    if (id === targetEventId.value) toastApiError(error)
  } finally {
    if (id === targetEventId.value) loading.value = false
  }
}

function handleUpdated(updated: EventRead) {
  event.value = updated
}

watch(targetEventId, () => {
  event.value = null
  members.value = []
  invitations.value = []
  joinRequests.value = []
  hours.value = []
  tasks.value = []
  loadEvent()
})

onMounted(loadEvent)
</script>

<template>
  <!-- One width for every tab, so the heading and the tab row stay put. The map
       editor uses all of it; the other tabs keep the narrower column. -->
  <div class="mx-auto max-w-6xl space-y-6">
    <div class="space-y-2">
      <h1 data-testid="page-heading" class="text-2xl sm:text-3xl font-bold">
        {{ t('duties.events.detail.title') }}
      </h1>
      <p v-if="event" class="text-muted-foreground">{{ event.name }}</p>
    </div>

    <!-- Scrolls sideways on a phone rather than wrapping onto a second row.
         The rule is an inset shadow, not a border: a scroll container would
         clip tabs pulled over a border with a negative margin. -->
    <div
      ref="tabRow"
      class="flex items-center gap-2 overflow-x-auto shadow-[inset_0_-1px_0_var(--border)]"
    >
      <Button
        variant="ghost"
        :class="[
          'shrink-0 rounded-none border-b-2',
          shownTab === 'details' ? 'border-primary text-primary' : 'border-transparent',
        ]"
        data-testid="tab-details"
        @click="setTab('details')"
      >
        <component :is="canManage ? Pencil : Info" class="mr-2 h-4 w-4" />
        {{ t('duties.events.detail.nav.details') }}
      </Button>
      <Button
        v-if="isMember"
        variant="ghost"
        :class="[
          'shrink-0 rounded-none border-b-2',
          shownTab === 'people' ? 'border-primary text-primary' : 'border-transparent',
        ]"
        data-testid="tab-people"
        @click="setTab('people')"
      >
        <Users class="mr-2 h-4 w-4" />
        {{ t('duties.events.detail.nav.people') }}
        <span
          v-if="joinRequests.length > 0"
          class="ml-2 rounded-full bg-primary px-1.5 py-0.5 text-[10px] font-semibold text-primary-foreground"
          data-testid="people-tab-badge"
        >
          {{ joinRequests.length }}
        </span>
      </Button>
      <template v-if="canManage">
        <Button
          v-if="usesVouchers"
          variant="ghost"
          :class="[
            'shrink-0 rounded-none border-b-2',
            shownTab === 'vouchers' ? 'border-primary text-primary' : 'border-transparent',
          ]"
          data-testid="tab-vouchers"
          @click="setTab('vouchers')"
        >
          <Ticket class="mr-2 h-4 w-4" />
          {{ t('vouchers.eventSettings.tab') }}
        </Button>
        <Button
          variant="ghost"
          :class="[
            'shrink-0 rounded-none border-b-2',
            shownTab === 'locations' ? 'border-primary text-primary' : 'border-transparent',
          ]"
          data-testid="tab-locations"
          @click="setTab('locations')"
        >
          <MapPin class="mr-2 h-4 w-4" />
          {{ t('locations.settings.tab') }}
        </Button>
        <Button
          variant="ghost"
          :class="[
            'shrink-0 rounded-none border-b-2',
            shownTab === 'map' ? 'border-primary text-primary' : 'border-transparent',
          ]"
          data-testid="tab-map"
          @click="setTab('map')"
        >
          <MapIcon class="mr-2 h-4 w-4" />
          {{ t('mapEditor.settings.tab') }}
        </Button>
      </template>
    </div>

    <div v-if="loading" class="py-12 text-center text-muted-foreground">
      {{ t('common.states.loading') }}
    </div>

    <VenueMapEditor
      v-else-if="event && targetEventId && shownTab === 'map'"
      :event-id="targetEventId"
      :sandbox="!!event.is_sandbox"
    />

    <div v-else-if="event && targetEventId" class="max-w-4xl">
      <template v-if="shownTab === 'details'">
        <EventEditForm
          v-if="canManage"
          :event="event"
          :event-id="targetEventId"
          :tasks="tasks"
          @updated="handleUpdated"
          @cancel="router.back()"
        />
        <EventDetailsSummary v-else :event="event" />
      </template>
      <div v-else-if="shownTab === 'people'" class="space-y-6">
        <EventJoinRequests
          v-if="canManage"
          :event-id="targetEventId"
          :requests="joinRequests"
          @updated="handleJoinRequestsUpdated"
        />
        <EventMembers
          :event-id="targetEventId"
          :members="members"
          :can-edit="canManage"
          :is-owner="isOwner"
          :hours-by-user="hoursByUser"
          @updated="loadPeople"
          @left="handleLeft"
        />
        <EventHours
          v-if="canManage"
          :event-id="targetEventId"
          :hours="hours"
          :members="members"
          @updated="loadHours"
        />
        <EventInvitations
          v-if="canManage"
          :event-id="targetEventId"
          :invitations="invitations"
          @updated="loadInvitations"
        />
      </div>
      <div v-else-if="shownTab === 'vouchers'" class="space-y-6">
        <EventVoucherSettings :event="event" :tasks="tasks" @updated="handleUpdated" />
        <EventVouchers :event-id="targetEventId" :members="members" />
      </div>
      <EventLocations v-else-if="shownTab === 'locations'" :event-id="targetEventId" />
    </div>
  </div>
</template>
