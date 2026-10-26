<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { ClipboardCheck, Crown, EllipsisVertical, TriangleAlert, UserMinus } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { avatarUrlFor } from '@/composables/useAvatarUrl'
import { useDialog } from '@/composables/useDialog'

import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import Button from '@/components/ui/button/Button.vue'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Skeleton } from '@/components/ui/skeleton'

import EventMemberPicker from '@/components/events/EventMemberPicker.vue'
import TeamReviewDialog from '@/components/events/teams/TeamReviewDialog.vue'
import {
  type ReviewPerson,
  displayName,
  initials,
  needsReview,
} from '@/components/events/teams/teamHelpers'

import type {
  EventMemberRead,
  EventTeamMemberRead,
  EventTeamRead,
  TeamCheckRead,
} from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'

/**
 * A team's members, for its leads and the event admins: add someone from the
 * event, appoint or remove a lead (admins only), record a new check, remove
 * someone. Waiting requests are decided in the request list at the top of the
 * Teams page, not here.
 */
const props = defineProps<{
  eventId: string
  team: EventTeamRead
  /** The event roster, to pick people from. */
  eventMembers: EventMemberRead[]
  /** Event admins may appoint leads and remove them; a lead may not. */
  isEventAdmin: boolean
  currentUserId?: string | null
  /** Bumped by the page after a change made elsewhere (a decided request). */
  version?: number
}>()

const emit = defineEmits<{ updated: [] }>()

const { t, locale } = useI18n()
const { get, post, patch, delete: del } = useAuthenticatedClient()
const { confirmDestructive } = useDialog()

const rows = ref<EventTeamMemberRead[]>([])
const loading = ref(false)
const error = ref(false)
const busyUserId = ref<string | null>(null)

const reviewOpen = ref(false)
const reviewMode = ref<'add' | 'recheck'>('add')
const reviewPerson = ref<ReviewPerson | null>(null)
const reviewRow = ref<EventTeamMemberRead | null>(null)
const reviewReusable = ref<TeamCheckRead[] | null>(null)

const approved = computed(() =>
  rows.value
    .filter((r) => r.status === 'approved')
    // Leads first, then by name: the people to ask stand at the top.
    .sort(
      (a, b) =>
        Number(b.role === 'lead') - Number(a.role === 'lead') ||
        displayName(a).localeCompare(displayName(b), locale.value),
    ),
)

/** Approved members cannot be added again; the picker says why. */
const unavailable = computed(() =>
  Object.fromEntries(approved.value.map((r) => [r.user_id, t('teams.roster.alreadyIn')])),
)

const base = computed(() => `/events/${props.eventId}/teams/${props.team.id}/members`)

// Bumped per load, so a slow answer for a team switched away from cannot land.
let generation = 0

async function load() {
  const gen = ++generation
  loading.value = true
  error.value = false
  try {
    const res = await get<{ data: EventTeamMemberRead[] }>({
      url: base.value,
      query: { status: 'approved' },
    })
    if (gen === generation) rows.value = res.data
  } catch {
    if (gen === generation) error.value = true
  } finally {
    if (gen === generation) loading.value = false
  }
}

watch(
  () => props.team.id,
  () => {
    rows.value = []
    void load()
  },
  { immediate: true },
)

// Reload in place, without the skeleton: the rows on screen stay until the new
// ones arrive.
watch(
  () => props.version,
  () => void load(),
)

async function act(userId: string, run: () => Promise<unknown>, message: string) {
  busyUserId.value = userId
  try {
    await run()
    toast.success(message)
    await load()
    emit('updated')
  } catch (err) {
    toastApiError(err)
  } finally {
    busyUserId.value = null
  }
}

function personOf(member: EventMemberRead): ReviewPerson {
  return {
    user_id: member.user_id,
    name: member.name || member.email || '?',
    email: member.email,
    avatar_etag: member.avatar_etag,
  }
}

function personOfRow(row: EventTeamMemberRead): ReviewPerson {
  return {
    user_id: row.user_id,
    name: displayName(row),
    email: row.user_email,
    avatar_etag: row.user_avatar_etag,
  }
}

async function pick(member: EventMemberRead) {
  // A team with requirements needs its checks ticked before anyone is in.
  if (needsReview(props.team)) {
    busyUserId.value = member.user_id
    try {
      // A valid check from another team of this event shows as "already
      // checked" and fills in the issue date, as it does for a request.
      const res = await get<{ data: TeamCheckRead[] }>({
        url: `${base.value}/${member.user_id}/reusable-checks`,
      })
      reviewReusable.value = res.data
    } catch {
      // Not worth stopping for: the dialog simply starts empty.
      reviewReusable.value = []
    } finally {
      busyUserId.value = null
    }
    reviewMode.value = 'add'
    reviewPerson.value = personOf(member)
    reviewRow.value = null
    reviewOpen.value = true
    return
  }
  void act(
    member.user_id,
    () => post({ url: base.value, body: { user_id: member.user_id, role: 'member' } }),
    t('teams.roster.added', { name: personOf(member).name }),
  )
}

function recheck(row: EventTeamMemberRead) {
  reviewReusable.value = null
  reviewMode.value = 'recheck'
  reviewPerson.value = personOfRow(row)
  reviewRow.value = row
  reviewOpen.value = true
}

function toggleLead(row: EventTeamMemberRead) {
  const role = row.role === 'lead' ? 'member' : 'lead'
  return act(
    row.user_id,
    () => patch({ url: `${base.value}/${row.user_id}`, body: { role } }),
    t('teams.roster.roleChanged'),
  )
}

async function remove(row: EventTeamMemberRead) {
  const ok = await confirmDestructive({
    title: t('teams.roster.removeConfirm', { name: displayName(row), team: props.team.name }),
    text: t('teams.roster.removeHint'),
    confirmText: t('teams.roster.remove'),
  })
  if (!ok) return
  await act(
    row.user_id,
    () => del({ url: `${base.value}/${row.user_id}` }),
    t('teams.roster.removed'),
  )
}

/** Leads are removed by admins only, except that a lead may step out. */
function canRemove(row: EventTeamMemberRead): boolean {
  return props.isEventAdmin || row.role !== 'lead' || row.user_id === props.currentUserId
}

function hasActions(row: EventTeamMemberRead): boolean {
  return props.isEventAdmin || canRemove(row) || needsReview(props.team)
}

function formatDay(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString(locale.value, {
    month: 'short',
    year: 'numeric',
  })
}

function checkSummary(row: EventTeamMemberRead): string {
  return (row.checks ?? [])
    .map((c) =>
      c.expires_on
        ? t(c.expired ? 'teams.roster.checkExpired' : 'teams.roster.checkUntil', {
            label: c.label,
            date: formatDay(c.expires_on),
          })
        : t('teams.roster.checkDone', { label: c.label }),
    )
    .join(' · ')
}

function onReviewed() {
  void load()
  emit('updated')
}
</script>

<template>
  <div class="space-y-4" data-testid="team-roster">
    <EventMemberPicker
      :members="eventMembers"
      :unavailable="unavailable"
      :label="t('teams.roster.add')"
      :placeholder="t('teams.roster.addPlaceholder')"
      :input-id="`team-add-person-${team.id}`"
      :disabled="busyUserId !== null"
      :empty-text="t('teams.roster.noMatch')"
      :action-hint="t('teams.roster.enterToAdd')"
      testid="team-add-member"
      @pick="pick"
    />

    <div class="space-y-2">
      <h3 class="text-sm font-semibold">
        {{ t('teams.roster.membersTitle') }}
        <span v-if="approved.length" class="text-muted-foreground font-normal">
          · {{ approved.length }}
        </span>
      </h3>

      <div v-if="loading && rows.length === 0" class="space-y-2">
        <Skeleton v-for="i in 3" :key="i" class="h-12 w-full" />
      </div>

      <div
        v-else-if="error && rows.length === 0"
        class="flex flex-col items-center gap-3 rounded-md border border-dashed px-4 py-6 text-center text-sm"
        role="alert"
        data-testid="team-roster-error"
      >
        <p class="text-muted-foreground">{{ t('teams.roster.loadError') }}</p>
        <Button variant="outline" size="sm" @click="load">{{ t('teams.page.retry') }}</Button>
      </div>

      <p
        v-else-if="approved.length === 0"
        class="text-muted-foreground rounded-md border border-dashed px-4 py-6 text-center text-sm"
      >
        {{ t('teams.roster.empty') }}
      </p>

      <ul v-else class="space-y-2">
        <li
          v-for="row in approved"
          :key="row.id"
          class="flex items-center gap-3 rounded-md border px-3 py-2"
          :data-testid="`team-member-row-${row.user_id}`"
        >
          <Avatar class="size-8 shrink-0">
            <AvatarImage
              v-if="avatarUrlFor({ id: row.user_id, avatar_etag: row.user_avatar_etag })"
              :src="avatarUrlFor({ id: row.user_id, avatar_etag: row.user_avatar_etag })!"
            />
            <AvatarFallback class="text-[10px]">{{ initials(displayName(row)) }}</AvatarFallback>
          </Avatar>
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
              <span class="truncate text-sm font-medium">{{ displayName(row) }}</span>
              <Badge v-if="row.role === 'lead'" variant="secondary" data-testid="team-member-lead">
                <Crown />
                {{ t('teams.roles.lead') }}
              </Badge>
              <Badge
                v-if="row.needs_recheck"
                variant="warning"
                class="rounded-full"
                data-testid="team-member-needs-recheck"
              >
                <TriangleAlert />
                {{ t('teams.roster.needsRecheck') }}
              </Badge>
            </div>
            <p v-if="row.checks?.length" class="text-muted-foreground truncate text-xs">
              {{ checkSummary(row) }}
            </p>
          </div>
          <DropdownMenu v-if="hasActions(row)">
            <DropdownMenuTrigger as-child>
              <Button
                variant="ghost"
                size="icon"
                class="size-8 shrink-0"
                :disabled="busyUserId === row.user_id"
                :aria-label="t('teams.roster.actionsFor', { name: displayName(row) })"
                :data-testid="`btn-team-member-actions-${row.user_id}`"
              >
                <EllipsisVertical class="size-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem
                v-if="isEventAdmin"
                data-testid="btn-toggle-team-lead"
                @select="toggleLead(row)"
              >
                <Crown class="mr-2 size-4" />
                {{
                  row.role === 'lead' ? t('teams.roster.unmakeLead') : t('teams.roster.makeLead')
                }}
              </DropdownMenuItem>
              <DropdownMenuItem
                v-if="needsReview(team)"
                data-testid="btn-team-record-check"
                @select="recheck(row)"
              >
                <ClipboardCheck class="mr-2 size-4" />
                {{ t('teams.roster.recordCheck') }}
              </DropdownMenuItem>
              <template v-if="canRemove(row)">
                <DropdownMenuSeparator v-if="isEventAdmin || needsReview(team)" />
                <DropdownMenuItem
                  variant="destructive"
                  data-testid="btn-remove-team-member"
                  @select="remove(row)"
                >
                  <UserMinus class="mr-2 size-4" />
                  {{ t('teams.roster.remove') }}
                </DropdownMenuItem>
              </template>
            </DropdownMenuContent>
          </DropdownMenu>
        </li>
      </ul>
    </div>

    <TeamReviewDialog
      v-if="reviewPerson"
      v-model:open="reviewOpen"
      :event-id="eventId"
      :team="team"
      :person="reviewPerson"
      :mode="reviewMode"
      :row="reviewRow"
      :reusable-checks="reviewReusable"
      @done="onReviewed"
    />
  </div>
</template>
