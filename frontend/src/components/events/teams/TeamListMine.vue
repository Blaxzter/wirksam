<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { Check, ChevronDown, ChevronRight, Clock, Crown, Phone, TriangleAlert } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import { toast } from 'vue-sonner'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import { Badge } from '@/components/ui/badge'
import Button from '@/components/ui/button/Button.vue'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'

import TeamFileField from '@/components/events/teams/TeamFileField.vue'
import TeamRoster from '@/components/events/teams/TeamRoster.vue'
import { deleteTeamDocument, uploadTeamDocument } from '@/components/events/teams/teamDocuments'
import { joinNames } from '@/components/events/teams/teamHelpers'

import type { EventMemberRead, EventTeamRead } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'

/**
 * "Your teams": the ones the viewer is in or waiting for.
 *
 * One row per team. With one or two teams the rows start open, showing what
 * the team unlocks and who to ask; with more they start closed and only the
 * first few show, so a long-serving volunteer is not handed a wall of cards.
 * A team the viewer leads opens onto its roster.
 */
const props = defineProps<{
  eventId: string
  teams: EventTeamRead[]
  eventMembers: EventMemberRead[]
  currentUserId?: string | null
  /** Demo events take no files. */
  sandbox?: boolean
  /** Open and scroll to this team (from `?team=`). */
  highlightId?: string | null
  busyTeamId?: string | null
  version?: number
}>()

const emit = defineEmits<{ leave: [team: EventTeamRead]; updated: [] }>()

const { t, locale } = useI18n()
const { getAuthToken } = useAuthenticatedClient()

/** Rows shown before "+ N more". */
const VISIBLE = 4
const showAll = ref(false)
const openIds = ref(new Set<string>())
const fileBusy = ref<string | null>(null)

const startOpen = computed(() => props.teams.length <= 2)
const visible = computed(() =>
  showAll.value || props.teams.length <= VISIBLE + 1 ? props.teams : props.teams.slice(0, VISIBLE),
)
const hidden = computed(() => props.teams.slice(visible.value.length))

// Teams already on screen once; one that turns up later was just joined or
// asked for, and opens so its files and status are in view.
const seen = new Set<string>()

watch(
  () => [props.teams.map((t) => t.id).join(), props.highlightId] as const,
  () => {
    const first = seen.size === 0
    const next = new Set<string>()
    for (const team of props.teams) {
      if (
        openIds.value.has(team.id) ||
        startOpen.value ||
        team.id === props.highlightId ||
        (!first && !seen.has(team.id))
      )
        next.add(team.id)
      seen.add(team.id)
    }
    openIds.value = next
    if (props.highlightId && hidden.value.some((t) => t.id === props.highlightId))
      showAll.value = true
  },
  { immediate: true },
)

function setOpen(id: string, value: boolean) {
  const next = new Set(openIds.value)
  if (value) next.add(id)
  else next.delete(id)
  openIds.value = next
}

function formatDay(iso: string | null | undefined): string {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString(locale.value, { day: 'numeric', month: 'short' })
}

function summary(team: EventTeamRead): string {
  const parts: string[] = []
  if (team.my_status === 'pending') return t('teams.mine.pending')
  if (team.my_role === 'lead') parts.push(t('teams.mine.youLead'))
  else parts.push(t('teams.mine.youAreIn'))
  // "0 tasks" says nothing worth a column; a team without tasks just says who you are.
  if (team.task_count)
    parts.push(
      t('teams.summary.tasks', { count: team.task_count }, team.task_count),
      team.open_shift_count
        ? t('teams.summary.openShifts', { count: team.open_shift_count }, team.open_shift_count)
        : t('teams.summary.allTaken'),
    )
  return parts.join(' · ')
}

function decider(team: EventTeamRead): string {
  const leads = team.lead_names ?? []
  return leads.length
    ? t('teams.mine.decider', { names: joinNames(leads, locale.value) }, leads.length)
    : t('teams.mine.deciderAdmins')
}

function footer(team: EventTeamRead): string {
  const parts: string[] = []
  const leads = team.lead_names ?? []
  // The contact line is the admin's own "who to ask"; the lead names are the
  // fallback when there is none, not an addition (it usually names them).
  if (team.contact) parts.push(team.contact)
  else if (leads.length)
    parts.push(t('teams.mine.leads', { names: joinNames(leads, locale.value) }, leads.length))
  parts.push(t('teams.summary.members', { count: team.member_count ?? 0 }, team.member_count ?? 0))
  return parts.join(' · ')
}

function documentFor(team: EventTeamRead, requirementId: string) {
  return team.my_documents?.find((d) => d.requirement_id === requirementId)
}

async function attach(team: EventTeamRead, requirementId: string, file: File) {
  fileBusy.value = team.id
  try {
    const token = await getAuthToken()
    await uploadTeamDocument(token, props.eventId, team.id, requirementId, file)
    toast.success(t('teams.join.fileAttached'))
    emit('updated')
  } catch (error) {
    toastApiError(error)
  } finally {
    fileBusy.value = null
  }
}

async function detach(team: EventTeamRead, requirementId: string) {
  fileBusy.value = team.id
  try {
    const token = await getAuthToken()
    await deleteTeamDocument(token, props.eventId, team.id, requirementId)
    toast.success(t('teams.join.fileRemoved'))
    emit('updated')
  } catch (error) {
    toastApiError(error)
  } finally {
    fileBusy.value = null
  }
}
</script>

<template>
  <section aria-labelledby="teams-mine-title" class="space-y-2" data-testid="teams-mine">
    <h2
      id="teams-mine-title"
      class="text-xs font-semibold tracking-wide text-muted-foreground uppercase"
    >
      {{ t('teams.mine.title') }} · {{ teams.length }}
    </h2>
    <ul class="divide-y overflow-hidden rounded-xl border bg-card">
      <li
        v-for="team in visible"
        :key="team.id"
        :id="`team-${team.id}`"
        class="scroll-mt-20 transition-colors"
        :class="team.id === highlightId ? 'bg-primary/5' : ''"
        :data-testid="`team-row-${team.id}`"
      >
        <Collapsible
          :open="openIds.has(team.id)"
          @update:open="(value: boolean) => setOpen(team.id, value)"
        >
          <CollapsibleTrigger
            class="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-accent/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset"
            :data-testid="`btn-toggle-team-${team.id}`"
          >
            <component
              :is="team.my_status === 'pending' ? Clock : team.my_role === 'lead' ? Crown : Check"
              class="size-4 shrink-0 text-muted-foreground"
              aria-hidden="true"
            />
            <span class="min-w-0 flex-1 sm:flex sm:items-baseline sm:gap-6">
              <span class="block truncate font-semibold sm:w-40 sm:shrink-0">{{ team.name }}</span>
              <span class="block truncate text-sm text-muted-foreground">{{ summary(team) }}</span>
            </span>
            <Badge
              v-if="team.can_manage && team.pending_count"
              variant="warning"
              class="rounded-full"
              :data-testid="`team-pending-count-${team.id}`"
            >
              {{ t('teams.manage.waiting', { count: team.pending_count }, team.pending_count) }}
            </Badge>
            <Badge
              v-if="team.my_needs_recheck"
              variant="warning"
              class="hidden rounded-full sm:inline-flex"
            >
              <TriangleAlert />
              {{ t('teams.mine.needsRecheckShort') }}
            </Badge>
            <ChevronDown
              class="size-4 shrink-0 text-muted-foreground transition-transform"
              :class="openIds.has(team.id) ? 'rotate-180' : ''"
              aria-hidden="true"
            />
          </CollapsibleTrigger>

          <CollapsibleContent>
            <div class="space-y-3 px-4 pb-4 sm:pl-11">
              <p v-if="team.description" class="text-sm whitespace-pre-line">
                {{ team.description }}
              </p>
              <!-- What joining was for: straight on to the shifts it opened. -->
              <div v-if="team.tasks?.length" class="space-y-1.5">
                <p class="text-xs font-medium text-muted-foreground">
                  {{ t('teams.summary.unlocksLabel') }}
                </p>
                <ul class="divide-y rounded-md border" :data-testid="`team-tasks-${team.id}`">
                  <li v-for="task in team.tasks" :key="task.id">
                    <RouterLink
                      :to="{ name: 'task-detail', params: { eventId: task.id } }"
                      class="flex items-center gap-3 px-3 py-2 text-sm transition-colors hover:bg-muted/50 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                      :data-testid="`team-task-link-${task.id}`"
                    >
                      <span class="min-w-0 flex-1 truncate font-medium">{{ task.name }}</span>
                      <span
                        class="shrink-0 text-xs"
                        :class="task.open_shift_count ? '' : 'text-muted-foreground'"
                      >
                        {{
                          task.open_shift_count
                            ? t(
                                'teams.summary.openShifts',
                                { count: task.open_shift_count },
                                task.open_shift_count,
                              )
                            : t('teams.summary.allTakenCap')
                        }}
                      </span>
                      <ChevronRight
                        class="size-4 shrink-0 text-muted-foreground"
                        aria-hidden="true"
                      />
                    </RouterLink>
                  </li>
                </ul>
              </div>

              <p
                v-if="team.my_needs_recheck"
                class="flex items-start gap-1.5 rounded-md border border-amber-500/40 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:bg-amber-950/30 dark:text-amber-200"
                data-testid="team-my-needs-recheck"
              >
                <TriangleAlert class="mt-0.5 size-4 shrink-0" />
                {{ t('teams.mine.needsRecheck') }}
              </p>

              <template v-if="team.my_status === 'pending'">
                <p class="text-sm text-muted-foreground">
                  {{ t('teams.mine.askedOn', { date: formatDay(team.my_requested_at) }) }}
                  {{ decider(team) }}
                </p>
                <ul v-if="team.requirements?.length" class="space-y-2">
                  <li
                    v-for="req in team.requirements"
                    :key="req.id"
                    class="flex flex-col gap-2 rounded-md border px-3 py-2 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div class="min-w-0">
                      <p class="text-sm font-medium">{{ req.label }}</p>
                      <p v-if="req.description" class="text-xs text-muted-foreground">
                        {{ req.description }}
                      </p>
                    </div>
                    <TeamFileField
                      v-if="req.accepts_document && !sandbox"
                      :filename="documentFor(team, req.id)?.filename"
                      :label="req.label"
                      :busy="fileBusy === team.id"
                      :testid="`team-my-file-${req.id}`"
                      @choose="(file) => attach(team, req.id, file)"
                      @remove="detach(team, req.id)"
                    />
                    <span v-else class="text-xs text-muted-foreground">
                      {{ t('teams.mine.bringIt') }}
                    </span>
                  </li>
                </ul>
              </template>

              <TeamRoster
                v-if="team.can_manage && team.my_status === 'approved'"
                class="rounded-lg border p-3"
                :event-id="eventId"
                :team="team"
                :event-members="eventMembers"
                :is-event-admin="false"
                :current-user-id="currentUserId"
                :version="version"
                @updated="emit('updated')"
              />

              <div
                class="flex flex-wrap items-center justify-between gap-2 border-t pt-3 text-xs text-muted-foreground"
              >
                <span class="flex min-w-0 items-center gap-1.5">
                  <Phone v-if="team.contact" class="size-3.5 shrink-0" />
                  {{ t('teams.mine.questions') }} {{ footer(team) }}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  class="text-muted-foreground"
                  :disabled="busyTeamId === team.id"
                  :aria-label="
                    team.my_status === 'pending'
                      ? t('teams.mine.withdrawNamed', { name: team.name })
                      : t('teams.mine.leaveNamed', { name: team.name })
                  "
                  :data-testid="`btn-leave-team-${team.id}`"
                  @click="emit('leave', team)"
                >
                  {{
                    team.my_status === 'pending' ? t('teams.mine.withdraw') : t('teams.mine.leave')
                  }}
                </Button>
              </div>
            </div>
          </CollapsibleContent>
        </Collapsible>
      </li>
      <li v-if="hidden.length > 0">
        <button
          type="button"
          class="flex w-full items-center gap-3 px-4 py-3 text-left text-sm hover:bg-accent/50"
          data-testid="btn-teams-mine-more"
          @click="showAll = true"
        >
          <span class="font-medium">{{ t('teams.mine.showMore', { count: hidden.length }) }}</span>
          <span class="min-w-0 flex-1 truncate text-muted-foreground">
            {{ hidden.map((team) => team.name).join(', ') }}
          </span>
          <ChevronDown class="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        </button>
      </li>
    </ul>
  </section>
</template>
