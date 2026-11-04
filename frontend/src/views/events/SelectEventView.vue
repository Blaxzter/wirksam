<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import { AlertTriangle, FlaskConicalIcon } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { toast } from 'vue-sonner'

import { useAuthStore } from '@/stores/auth'
import { useSandboxStore } from '@/stores/sandbox'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import Badge from '@/components/ui/badge/Badge.vue'
import { Button } from '@/components/ui/button'

import SandboxStartDialog from '@/components/sandbox/SandboxStartDialog.vue'
import EventPickerList, { type PickerTab } from '@/components/select-event/EventPickerList.vue'
import NotificationSetupStep from '@/components/select-event/NotificationSetupStep.vue'
import SelectEventHeroPane, {
  type SelectEventMode,
} from '@/components/select-event/SelectEventHeroPane.vue'
import SelectEventTopBar from '@/components/select-event/SelectEventTopBar.vue'
import type { EventStats } from '@/components/select-event/SelectableEventCard.vue'

import type { EventListResponse, EventRead, TaskFeedResponse } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const sandboxStore = useSandboxStore()
const { get, post, patch } = useAuthenticatedClient()

// Offered here as well as on the landing page: the picker is where a brand-new
// account lands with nothing in it, and "look at a finished one first" answers
// that better than an empty list does. The dialog says out loud that starting a
// demo signs them out of the account they just made.
const demoDialogOpen = ref(false)

const selectMode = computed<SelectEventMode>(() => {
  const raw = route.query.mode
  if (raw === 'switch' || raw === 'expired') return raw
  return 'onboarding'
})

const onboarding = computed(() => selectMode.value === 'onboarding')

/** The expired event, when it gave out vouchers: "did I get mine?" still has an answer. */
const expiredVoucherEventId = computed(() => {
  const event = authStore.selectedEvent
  if (selectMode.value !== 'expired' || !event?.is_expired) return null
  return (event.voucher_task_count ?? 0) > 0 ? event.id : null
})

const step = ref<1 | 2>(1)
const phase = ref<'intro' | 'main'>('intro')

// Mobile strip layout: 4 panels [H1, M1, H2, M2] for onboarding (forward = always slide left)
// or 2 panels [Hero, Main] for switch/expired (hero offscreen, main shown).
const stripWidthClass = computed(() => (onboarding.value ? 'w-[400%]' : 'w-[200%]'))
const panelWidthClass = computed(() => (onboarding.value ? 'w-1/4' : 'w-1/2'))
const stripTranslateClass = computed(() => {
  if (!onboarding.value) return '-translate-x-1/2'
  if (step.value === 1) return phase.value === 'intro' ? 'translate-x-0' : '-translate-x-1/4'
  return phase.value === 'intro' ? '-translate-x-1/2' : '-translate-x-3/4'
})

const events = ref<EventRead[]>([])
const discoverEvents = ref<EventRead[]>([])
const featuredEvents = ref<EventRead[]>([])
const eventStats = ref<Record<string, EventStats>>({})
const loading = ref(true)
const discoverLoading = ref(false)
const discoverLoaded = ref(false)
const submitting = ref(false)
const requestingId = ref<string | null>(null)
const tab = ref<PickerTab>('mine')
// Radio-style selection: clicking a card stages it; Continue commits it.
const pendingSelectionId = ref<string | null>(authStore.selectedEventId ?? null)

const phoneNumber = ref('')
const savingPhone = ref(false)

const today = () => new Date().toISOString().slice(0, 10)

async function loadEvents() {
  loading.value = true
  try {
    const res = await get<{ data: EventListResponse }>({
      url: '/events/',
      query: { limit: 100, date_from: today(), scope: 'mine' },
    })
    events.value = res.data.items.filter((e) => !e.is_expired)

    const statsById: Record<string, EventStats> = {}
    await Promise.all(
      events.value.map(async (event) => {
        try {
          const feedRes = await get<{ data: TaskFeedResponse }>({
            url: '/tasks/feed',
            query: { view: 'cards', event_id: event.id, all_events: true, limit: 200 },
          })
          const items = feedRes.data.items
          statsById[event.id] = {
            taskCount: feedRes.data.total ?? items.length,
            totalShifts: items.reduce((s, t) => s + (t.total_shifts ?? 0), 0),
            openShifts: items.reduce((s, t) => s + (t.available_shifts ?? 0), 0),
          }
        } catch {
          statsById[event.id] = { taskCount: 0, totalShifts: 0, openShifts: 0 }
        }
      }),
    )
    eventStats.value = statsById
  } catch (error) {
    toastApiError(error)
  } finally {
    loading.value = false
  }
}

/**
 * Public events the user is not in yet, plus the curated selection.
 *
 * Both are fetched together and loaded lazily on the first visit to Discover.
 * `featured` is the superadmin's pick; those events are pulled out of the
 * general list so they are not offered twice.
 */
async function loadDiscover() {
  discoverLoading.value = true
  try {
    const [discoverRes, featuredRes] = await Promise.all([
      get<{ data: EventListResponse }>({
        url: '/events/',
        query: { limit: 100, date_from: today(), scope: 'discover' },
      }),
      get<{ data: EventListResponse }>({
        url: '/events/',
        query: { limit: 100, date_from: today(), scope: 'featured' },
      }),
    ])

    const open = discoverRes.data.items.filter((e) => !e.is_expired)
    // The featured scope does not exclude events you already belong to, so
    // drop those here — Discover is only about what you could still join.
    const featured = featuredRes.data.items.filter((e) => !e.is_expired && !e.my_role)
    const featuredIds = new Set(featured.map((e) => e.id))

    featuredEvents.value = featured
    discoverEvents.value = open.filter((e) => !featuredIds.has(e.id))
    discoverLoaded.value = true
  } catch (error) {
    toastApiError(error)
  } finally {
    discoverLoading.value = false
  }
}

watch(tab, (next) => {
  if (next === 'discover' && !discoverLoaded.value) void loadDiscover()
})

async function handleRequestJoin(event: EventRead) {
  requestingId.value = event.id
  try {
    await post({ url: `/events/${event.id}/join-request`, body: {} })
    // Reflect the pending state in place rather than refetching the list.
    discoverEvents.value = discoverEvents.value.map((e) =>
      e.id === event.id ? { ...e, join_request_status: 'pending' } : e,
    )
    toast.success(t('duties.events.join.requestSent'))
  } catch (error) {
    toastApiError(error)
  } finally {
    requestingId.value = null
  }
}

function handleStageSelection(event: EventRead) {
  pendingSelectionId.value = event.id
}

async function handleCommitSelection() {
  if (!pendingSelectionId.value) return
  submitting.value = true
  try {
    if (pendingSelectionId.value !== authStore.selectedEventId) {
      await authStore.setSelectedEvent(pendingSelectionId.value)
    }
    if (selectMode.value === 'onboarding') {
      step.value = 2
      phase.value = 'intro'
    } else {
      toast.success(t('duties.selectEvent.success'))
      router.push({ name: 'home' })
    }
  } catch (error) {
    toastApiError(error)
  } finally {
    submitting.value = false
  }
}

function handleCancel() {
  router.push({ name: 'home' })
}

function handleHeroBackFromStep2() {
  step.value = 1
  phase.value = 'main'
}

function handleNotifBack() {
  step.value = 1
  phase.value = 'main'
}

/**
 * Creating an event is its own page, not a dialog: the form is too tall to
 * fit a phone screen. The mode travels with it so cancelling comes back to
 * the picker in the state it was left in.
 */
function openCreate() {
  router.push({
    name: 'event-create',
    query: { returnTo: 'select-event', mode: selectMode.value },
  })
}

async function savePhone() {
  savingPhone.value = true
  try {
    await patch({
      url: '/users/me',
      body: { phone_number: phoneNumber.value || null },
    })
  } catch (error) {
    toastApiError(error)
  } finally {
    savingPhone.value = false
  }
}

async function finishOnboarding() {
  if (phoneNumber.value && phoneNumber.value !== (authStore.profile?.phone_number ?? '')) {
    await savePhone()
  }
  toast.success(t('duties.selectEvent.success'))
  router.push({ name: 'home' })
}

watch(
  () => authStore.profile?.phone_number,
  (value) => {
    phoneNumber.value = value ?? ''
  },
  { immediate: true },
)

/**
 * Open on Discover when the user belongs to no event yet.
 *
 * "My events" is empty for a brand-new account, and an empty list is a dead
 * end. Discover is where the curated selection lives, so that is the useful
 * first screen. `?tab=discover` asks for the same, from the QR code of an event
 * they aren't in. Only applied on the initial load — once someone picks a tab
 * themselves, their choice stands.
 */
onMounted(async () => {
  const createdId = typeof route.query.created === 'string' ? route.query.created : null
  await loadEvents()
  if (createdId) {
    // Back from the create page: stage what was just made so it comes up
    // already highlighted, then drop the marker so a reload does not repeat it.
    pendingSelectionId.value = createdId
    const query = { ...route.query }
    delete query.created
    void router.replace({ query })
  } else if (events.value.length === 0 || route.query.tab === 'discover') {
    tab.value = 'discover'
  }
})
</script>

<template>
  <div class="relative h-screen overflow-hidden">
    <div
      :class="[
        'flex h-full transition-transform duration-300 ease-out motion-reduce:transition-none',
        stripWidthClass,
        stripTranslateClass,
        'lg:grid lg:w-full lg:grid-cols-2 lg:translate-x-0 lg:transition-none',
      ]"
    >
      <!-- Hero step 1 -->
      <SelectEventHeroPane
        :class="[panelWidthClass, 'shrink-0 lg:w-auto', step === 1 ? '' : 'lg:hidden']"
        :step="1"
        :mode="selectMode"
        :show-mobile-continue="onboarding && step === 1 && phase === 'intro'"
        @mobile-continue="phase = 'main'"
      />

      <!-- Main step 1: picker -->
      <main
        :class="[
          'flex flex-col h-full overflow-hidden',
          panelWidthClass,
          'shrink-0 lg:w-auto',
          step === 1 ? '' : 'lg:hidden',
        ]"
      >
        <SelectEventTopBar />
        <div class="flex-1 overflow-y-auto">
          <div
            class="mx-auto flex min-h-full w-full max-w-3xl flex-col justify-center space-y-6 px-4 py-6 sm:px-8"
          >
            <div
              v-if="selectMode === 'expired'"
              class="rounded-lg border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive"
            >
              <div class="flex items-start gap-2">
                <AlertTriangle class="mt-0.5 h-4 w-4 shrink-0" />
                <div>
                  <p class="font-semibold">{{ t('duties.selectEvent.expired.title') }}</p>
                  <p>{{ t('duties.selectEvent.expired.body') }}</p>
                  <RouterLink
                    v-if="expiredVoucherEventId"
                    :to="{ name: 'my-vouchers', params: { eventId: expiredVoucherEventId } }"
                    class="mt-1 inline-block font-medium underline underline-offset-4"
                    data-testid="link-expired-vouchers"
                  >
                    {{ t('vouchers.afterEventLink') }}
                  </RouterLink>
                </div>
              </div>
            </div>

            <div class="space-y-2">
              <h1 data-testid="page-heading" class="text-2xl sm:text-3xl font-bold tracking-tight">
                {{ t('duties.selectEvent.pick.title') }}
              </h1>
              <p class="text-muted-foreground">{{ t('duties.selectEvent.pick.subtitle') }}</p>
              <Button
                v-if="sandboxStore.enabled"
                data-testid="btn-sandbox-start-picker"
                variant="link"
                class="h-auto gap-1.5 p-0 text-muted-foreground"
                @click="demoDialogOpen = true"
              >
                <FlaskConicalIcon class="size-4" />
                {{ t('sandbox.cta.picker') }}
              </Button>
              <div
                v-if="onboarding"
                class="flex flex-wrap items-center gap-x-2 gap-y-1 pt-2 text-xs text-muted-foreground"
              >
                <div class="flex items-center gap-2">
                  <Badge variant="default">1</Badge>
                  <span>{{ t('duties.selectEvent.pick.title') }}</span>
                </div>
                <span aria-hidden="true">/</span>
                <div class="flex items-center gap-2">
                  <Badge variant="secondary">2</Badge>
                  <span>{{ t('duties.selectEvent.notifications.title') }}</span>
                </div>
              </div>
            </div>

            <EventPickerList
              v-model:tab="tab"
              :events="events"
              :discover-events="discoverEvents"
              :featured-events="featuredEvents"
              :stats="eventStats"
              :loading="loading"
              :discover-loading="discoverLoading"
              :pending-selection-id="pendingSelectionId"
              :current-selected-id="authStore.selectedEventId"
              :submitting="submitting"
              :mode="selectMode"
              :requesting-id="requestingId"
              @stage="handleStageSelection"
              @commit="handleCommitSelection"
              @cancel="handleCancel"
              @back="phase = 'intro'"
              @open-create="openCreate"
              @request-join="handleRequestJoin"
            />
          </div>
        </div>
      </main>

      <!-- Hero step 2 (onboarding only) -->
      <SelectEventHeroPane
        v-if="onboarding"
        :class="[panelWidthClass, 'shrink-0 lg:w-auto', step === 2 ? '' : 'lg:hidden']"
        :step="2"
        :mode="selectMode"
        :show-mobile-continue="step === 2 && phase === 'intro'"
        @mobile-continue="phase = 'main'"
        @mobile-back="handleHeroBackFromStep2"
      />

      <!-- Main step 2: notifications (onboarding only) -->
      <main
        v-if="onboarding"
        :class="[
          'flex flex-col h-full overflow-hidden',
          panelWidthClass,
          'shrink-0 lg:w-auto',
          step === 2 ? '' : 'lg:hidden',
        ]"
      >
        <SelectEventTopBar />
        <div class="flex-1 overflow-y-auto">
          <div
            class="mx-auto flex min-h-full w-full max-w-3xl flex-col justify-center space-y-6 px-4 py-6 sm:px-8"
          >
            <div class="space-y-2">
              <h1 class="text-2xl sm:text-3xl font-bold tracking-tight">
                {{ t('duties.selectEvent.notifications.title') }}
              </h1>
              <p class="text-muted-foreground">
                {{ t('duties.selectEvent.notifications.subtitle') }}
              </p>
              <div
                class="flex flex-wrap items-center gap-x-2 gap-y-1 pt-2 text-xs text-muted-foreground"
              >
                <div class="flex items-center gap-2">
                  <Badge variant="secondary">1</Badge>
                  <span>{{ t('duties.selectEvent.pick.title') }}</span>
                </div>
                <span aria-hidden="true">/</span>
                <div class="flex items-center gap-2">
                  <Badge variant="default">2</Badge>
                  <span>{{ t('duties.selectEvent.notifications.title') }}</span>
                </div>
              </div>
            </div>

            <NotificationSetupStep
              v-model:phone-number="phoneNumber"
              :saving-phone="savingPhone"
              @back="handleNotifBack"
              @finish="finishOnboarding"
            />
          </div>
        </div>
      </main>
    </div>

    <SandboxStartDialog v-model:open="demoDialogOpen" />
  </div>
</template>
