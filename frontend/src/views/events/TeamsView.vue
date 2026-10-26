<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'

import { Plus, UsersRound } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { toast } from 'vue-sonner'

import { useAuthStore } from '@/stores/auth'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { useDialog } from '@/composables/useDialog'

import Button from '@/components/ui/button/Button.vue'
import { Skeleton } from '@/components/ui/skeleton'

import TeamFormDialog from '@/components/events/teams/TeamFormDialog.vue'
import TeamJoinDialog from '@/components/events/teams/TeamJoinDialog.vue'
import TeamListMine from '@/components/events/teams/TeamListMine.vue'
import TeamListMore from '@/components/events/teams/TeamListMore.vue'
import TeamManageBoard from '@/components/events/teams/TeamManageBoard.vue'
import TeamRequestList from '@/components/events/teams/TeamRequestList.vue'

import type {
  EventMemberRead,
  EventRead,
  EventTeamMemberRead,
  EventTeamRead,
} from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'

/**
 * The Teams page of one event (`/app/teams/:eventId?`, falling back to the
 * selected event like the map).
 *
 * - Everyone in the event sees their own teams and the ones they could join,
 *   and joins in place: an open team at once, one that needs approval through
 *   a short request with an optional note and files.
 * - Whoever can decide something — a team lead, an event admin — gets the
 *   waiting requests at the top.
 * - Event admins get every team as a list with the chosen team's roster
 *   beside it, and create, edit and delete teams here.
 */
const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const { get, post, delete: del } = useAuthenticatedClient()
const { confirmDestructive } = useDialog()

const eventId = computed<string | null>(() => {
  const p = route.params.eventId
  if (typeof p === 'string' && p) return p
  return authStore.selectedEventId ?? null
})
/** `?team=<id>`: the team to open and scroll to (links from tasks, notifications). */
const focusTeamId = computed(() => (typeof route.query.team === 'string' ? route.query.team : null))

const event = ref<EventRead | null>(null)
const teams = ref<EventTeamRead[]>([])
const requests = ref<EventTeamMemberRead[]>([])
const members = ref<EventMemberRead[]>([])
const loading = ref(false)
const loadError = ref(false)
const busyTeamId = ref<string | null>(null)
/** Bumped when a request is decided above, so open rosters reload. */
const rosterVersion = ref(0)

const isMember = computed(() => authStore.isEventMember(eventId.value))
const canEdit = computed(() => authStore.canManageEvent(eventId.value))
/** A lead of at least one team, or an event admin: sees requests and rosters. */
const canDecide = computed(() => canEdit.value || teams.value.some((team) => team.can_manage))
const currentUserId = computed(() => authStore.user?.id ?? null)
/** Roles come with the profile; until then nobody is "not a member" yet. */
const profileReady = computed(() => !!authStore.profile)

const mine = computed(() =>
  teams.value.filter((team) => team.my_status === 'approved' || team.my_status === 'pending'),
)
const others = computed(() =>
  teams.value.filter((team) => team.my_status !== 'approved' && team.my_status !== 'pending'),
)

// Bumped per load: switching events mid-request must not show the old event's teams.
let generation = 0

async function loadDecisionData(id: string, gen: number) {
  if (!canDecide.value) {
    requests.value = []
    members.value = []
    return
  }
  const [reqRes, memRes] = await Promise.all([
    get<{ data: EventTeamMemberRead[] }>({ url: `/events/${id}/teams/requests` }),
    get<{ data: EventMemberRead[] }>({ url: `/events/${id}/members` }),
  ])
  if (gen !== generation) return
  requests.value = reqRes.data
  members.value = memRes.data
}

async function load({ quiet = false } = {}) {
  const id = eventId.value
  const gen = ++generation
  if (!id || !isMember.value) {
    loading.value = false
    return
  }
  if (!quiet) loading.value = true
  loadError.value = false
  try {
    const [eventRes, teamsRes] = await Promise.all([
      get<{ data: EventRead }>({ url: `/events/${id}` }),
      get<{ data: EventTeamRead[] }>({ url: `/events/${id}/teams` }),
    ])
    if (gen !== generation) return
    event.value = eventRes.data
    teams.value = teamsRes.data
    await loadDecisionData(id, gen)
  } catch (error) {
    if (gen !== generation) return
    // A failed reload keeps what is on screen and says so; a failed first
    // load is an error state, never "no teams" (the admin would create them
    // again).
    if (quiet) toastApiError(error)
    else loadError.value = true
  } finally {
    if (gen === generation) loading.value = false
  }
}

/** After any change: the lists, and the sidebar's team count and badge. */
async function refresh() {
  await load({ quiet: true })
  if (eventId.value) void authStore.refreshSelectedEvent(eventId.value)
}

function onRequestsUpdated() {
  rosterVersion.value += 1
  void refresh()
}

watch(
  [eventId, isMember],
  () => {
    event.value = null
    teams.value = []
    requests.value = []
    members.value = []
    void load()
  },
  { immediate: true },
)

// Land on the team a link pointed at once it is on the page.
watch(
  [focusTeamId, loading],
  async ([id, isLoading]) => {
    if (!id || isLoading) return
    await nextTick()
    document.getElementById(`team-${id}`)?.scrollIntoView?.({ block: 'center', behavior: 'smooth' })
  },
  { immediate: true },
)

/**
 * Picking a team is a step of its own, so the phone's back button returns to
 * the list (below `lg` the team replaces it). Clearing the choice — the back
 * button in the panel, a deleted team — replaces instead, so going back never
 * lands on a team that was just closed or no longer exists.
 */
function selectTeam(id: string | null) {
  if (id === focusTeamId.value) return
  const location = { query: { ...route.query, team: id ?? undefined } }
  if (id === null) router.replace(location)
  else router.push(location)
}

// --- Joining -------------------------------------------------------------

const joinOpen = ref(false)
const joining = ref<EventTeamRead | null>(null)

async function join(team: EventTeamRead) {
  if (team.requires_approval) {
    joining.value = team
    joinOpen.value = true
    return
  }
  busyTeamId.value = team.id
  try {
    await post({ url: `/events/${eventId.value}/teams/${team.id}/join`, body: {} })
    toast.success(t('teams.join.joined', { name: team.name }))
    await refresh()
  } catch (error) {
    toastApiError(error)
  } finally {
    busyTeamId.value = null
  }
}

async function leave(team: EventTeamRead) {
  const pending = team.my_status === 'pending'
  if (!pending) {
    const ok = await confirmDestructive({
      title: t('teams.mine.leaveConfirm', { name: team.name }),
      text: team.requires_approval ? t('teams.mine.leaveHintApproval') : t('teams.mine.leaveHint'),
      confirmText: t('teams.mine.leave'),
    })
    if (!ok) return
  }
  busyTeamId.value = team.id
  try {
    await del({ url: `/events/${eventId.value}/teams/${team.id}/join` })
    toast.success(pending ? t('teams.mine.withdrawn') : t('teams.mine.left', { name: team.name }))
    await refresh()
  } catch (error) {
    toastApiError(error)
  } finally {
    busyTeamId.value = null
  }
}

// --- Admin: create, edit, delete ----------------------------------------

const formOpen = ref(false)
const editing = ref<EventTeamRead | null>(null)

function openCreate() {
  editing.value = null
  formOpen.value = true
}

function openEdit(team: EventTeamRead) {
  editing.value = team
  formOpen.value = true
}

async function onSaved(team: EventTeamRead) {
  await refresh()
  selectTeam(team.id)
}

async function remove(team: EventTeamRead) {
  const count = team.task_count ?? 0
  const ok = await confirmDestructive({
    title: t('teams.manage.deleteConfirm', { name: team.name }),
    text: count
      ? t('teams.manage.deleteHintWithTasks', { count }, count)
      : t('teams.manage.deleteHint'),
    confirmText: t('teams.manage.delete'),
  })
  if (!ok) return
  busyTeamId.value = team.id
  try {
    await del({ url: `/events/${eventId.value}/teams/${team.id}` })
    toast.success(t('teams.manage.deleted'))
    if (focusTeamId.value === team.id) selectTeam(null)
    await refresh()
  } catch (error) {
    toastApiError(error)
  } finally {
    busyTeamId.value = null
  }
}
</script>

<template>
  <div class="mx-auto max-w-5xl space-y-6" data-testid="teams-page">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div class="min-w-0 space-y-1">
        <p v-if="event" class="text-sm text-muted-foreground">{{ event.name }}</p>
        <h1 data-testid="page-heading" class="text-2xl font-bold sm:text-3xl">
          {{ t('teams.page.title') }}
        </h1>
        <p class="max-w-2xl text-muted-foreground">
          {{ canEdit ? t('teams.page.subtitleAdmin') : t('teams.page.subtitle') }}
        </p>
      </div>
      <Button
        v-if="canEdit && eventId"
        class="max-sm:w-full"
        data-testid="btn-create-team"
        @click="openCreate"
      >
        <Plus class="mr-1.5 size-4" />
        {{ t('teams.page.create') }}
      </Button>
    </div>

    <div v-if="!profileReady" class="space-y-3" aria-busy="true">
      <Skeleton class="h-6 w-40" />
      <Skeleton v-for="i in 3" :key="i" class="h-16 w-full rounded-xl" />
    </div>

    <!-- No event to show teams of. -->
    <div
      v-else-if="!eventId"
      class="flex flex-col items-center gap-3 rounded-xl border border-dashed px-4 py-10 text-center text-sm"
      data-testid="teams-no-event"
    >
      <p class="text-muted-foreground">{{ t('teams.page.noEvent') }}</p>
      <Button as-child variant="outline">
        <RouterLink :to="{ name: 'select-event', query: { mode: 'switch' } }">
          {{ t('teams.page.chooseEvent') }}
        </RouterLink>
      </Button>
    </div>

    <p
      v-else-if="!isMember"
      class="rounded-xl border border-dashed px-4 py-10 text-center text-sm text-muted-foreground"
      data-testid="teams-not-member"
    >
      {{ t('teams.page.notMember') }}
    </p>

    <div v-else-if="loading && teams.length === 0" class="space-y-3" aria-busy="true">
      <Skeleton class="h-6 w-40" />
      <Skeleton v-for="i in 3" :key="i" class="h-16 w-full rounded-xl" />
    </div>

    <div
      v-else-if="loadError && teams.length === 0"
      class="flex flex-col items-center gap-3 rounded-xl border border-dashed px-4 py-10 text-center text-sm"
      role="alert"
      data-testid="teams-error"
    >
      <p class="max-w-sm text-muted-foreground">{{ t('teams.page.loadError') }}</p>
      <Button variant="outline" data-testid="teams-retry" @click="load()">
        {{ t('teams.page.retry') }}
      </Button>
    </div>

    <div
      v-else-if="teams.length === 0"
      class="flex flex-col items-center gap-3 rounded-xl border border-dashed px-4 py-10 text-center text-sm text-muted-foreground"
      data-testid="teams-empty"
    >
      <UsersRound class="size-6" />
      <p class="max-w-sm">{{ canEdit ? t('teams.page.emptyAdmin') : t('teams.page.empty') }}</p>
    </div>

    <template v-else-if="eventId">
      <TeamRequestList
        v-if="canDecide && requests.length > 0"
        :event-id="eventId"
        :requests="requests"
        :teams="teams"
        @updated="onRequestsUpdated"
      />

      <TeamManageBoard
        v-if="canEdit"
        :event-id="eventId"
        :teams="teams"
        :event-members="members"
        :is-event-admin="canEdit"
        :current-user-id="currentUserId"
        :selected-id="focusTeamId"
        :busy-team-id="busyTeamId"
        :version="rosterVersion"
        @select="selectTeam"
        @edit="openEdit"
        @delete="remove"
        @updated="refresh"
      />

      <template v-else>
        <TeamListMine
          v-if="mine.length > 0"
          :event-id="eventId"
          :teams="mine"
          :event-members="members"
          :current-user-id="currentUserId"
          :sandbox="!!event?.is_sandbox"
          :highlight-id="focusTeamId"
          :busy-team-id="busyTeamId"
          :version="rosterVersion"
          @leave="leave"
          @updated="refresh"
        />
        <TeamListMore
          v-if="others.length > 0"
          :teams="others"
          :busy-team-id="busyTeamId"
          :highlight-id="focusTeamId"
          @join="join"
        />
      </template>
    </template>

    <TeamFormDialog
      v-if="eventId && canEdit"
      v-model:open="formOpen"
      :event-id="eventId"
      :team="editing"
      @saved="onSaved"
    />
    <TeamJoinDialog
      v-if="eventId && joining"
      v-model:open="joinOpen"
      :event-id="eventId"
      :team="joining"
      :sandbox="!!event?.is_sandbox"
      @done="refresh"
    />
  </div>
</template>
