<script setup lang="ts">
import { computed, ref } from 'vue'

import { Lock, Search, ShieldCheck, UserRound } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import Button from '@/components/ui/button/Button.vue'
import Input from '@/components/ui/input/Input.vue'

import { joinNames } from '@/components/events/teams/teamHelpers'

import type { EventTeamRead } from '@/client/types.gen'

/**
 * "More teams": the ones the viewer could join.
 *
 * A handful get a full row each — what the team does, what it unlocks, who to
 * ask. Past {@link COMPACT_FROM} the list switches to one line per team with
 * a filter and a search, and shows {@link PAGE} at a time: at a Kirchentag
 * with 25 teams the full rows would bury the one you came for.
 */
const props = defineProps<{
  teams: EventTeamRead[]
  busyTeamId?: string | null
  highlightId?: string | null
}>()

const emit = defineEmits<{ join: [team: EventTeamRead] }>()

const { t, locale } = useI18n()

const COMPACT_FROM = 7
const PAGE = 10

type Filter = 'all' | 'open' | 'approval'
const filter = ref<Filter>('all')
const search = ref('')
const showAll = ref(false)

const compact = computed(() => props.teams.length >= COMPACT_FROM)

const filtered = computed(() => {
  const q = search.value.trim().toLocaleLowerCase()
  return props.teams.filter(
    (team) =>
      (filter.value === 'all' ||
        (filter.value === 'open' ? !team.requires_approval : team.requires_approval)) &&
      (!q ||
        team.name.toLocaleLowerCase().includes(q) ||
        (team.description ?? '').toLocaleLowerCase().includes(q)),
  )
})

const shown = computed(() => {
  if (!compact.value || showAll.value) return filtered.value
  const first = filtered.value.slice(0, PAGE)
  // A deep link to a team further down still lands on it.
  const target = filtered.value.find((team) => team.id === props.highlightId)
  return target && !first.includes(target) ? [...first, target] : first
})
const rest = computed(() => filtered.value.length - shown.value.length)

const filters: { value: Filter; key: string }[] = [
  { value: 'all', key: 'teams.more.filterAll' },
  { value: 'open', key: 'teams.summary.open' },
  { value: 'approval', key: 'teams.summary.approval' },
]

function openShifts(team: EventTeamRead): string {
  if (!team.task_count) return t('teams.summary.noTasks')
  return team.open_shift_count
    ? t('teams.summary.openShifts', { count: team.open_shift_count }, team.open_shift_count)
    : t('teams.summary.allTakenCap')
}

function summary(team: EventTeamRead): string {
  return [
    team.requires_approval ? t('teams.summary.approval') : t('teams.summary.open'),
    t('teams.summary.tasks', { count: team.task_count ?? 0 }, team.task_count ?? 0),
    ...(team.task_count ? [openShifts(team)] : []),
  ].join(' · ')
}

function details(team: EventTeamRead): string {
  const parts: string[] = []
  if (team.tasks?.length)
    parts.push(
      t('teams.summary.unlocks', {
        tasks: joinNames(
          team.tasks.map((task) => task.name),
          locale.value,
        ),
      }),
    )
  if (team.contact) parts.push(t('teams.summary.questions', { contact: team.contact }))
  parts.push(t('teams.summary.members', { count: team.member_count ?? 0 }, team.member_count ?? 0))
  return parts.join(' · ')
}

function joinLabel(team: EventTeamRead): string {
  if (!team.requires_approval) return t('teams.more.join')
  return team.my_status === 'declined' ? t('teams.more.askAgain') : t('teams.more.askToJoin')
}

/** The same, with the team's name, for a list of 25 otherwise identical buttons. */
function joinLabelNamed(team: EventTeamRead): string {
  const name = team.name
  if (!team.requires_approval) return t('teams.more.joinNamed', { name })
  return team.my_status === 'declined'
    ? t('teams.more.askAgainNamed', { name })
    : t('teams.more.askToJoinNamed', { name })
}
</script>

<template>
  <section aria-labelledby="teams-more-title" class="space-y-2" data-testid="teams-more">
    <div class="flex flex-wrap items-center gap-2">
      <h2
        id="teams-more-title"
        class="mr-auto text-xs font-semibold tracking-wide text-muted-foreground uppercase"
      >
        {{ t('teams.more.title') }} · {{ teams.length }}
      </h2>
      <template v-if="compact">
        <div
          role="group"
          :aria-label="t('teams.more.filterLabel')"
          class="flex gap-1.5 overflow-x-auto"
        >
          <Button
            v-for="f in filters"
            :key="f.value"
            size="sm"
            :variant="filter === f.value ? 'default' : 'outline'"
            class="h-8 rounded-full"
            :aria-pressed="filter === f.value"
            :data-testid="`teams-filter-${f.value}`"
            @click="filter = f.value"
          >
            {{ t(f.key) }}
          </Button>
        </div>
        <div class="relative w-full sm:w-56">
          <Search
            class="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            v-model="search"
            type="search"
            class="h-8 pl-8"
            :placeholder="t('teams.more.search')"
            :aria-label="t('teams.more.search')"
            data-testid="teams-search"
          />
        </div>
      </template>
    </div>

    <ul class="divide-y overflow-hidden rounded-xl border bg-card">
      <li
        v-for="team in shown"
        :id="`team-${team.id}`"
        :key="team.id"
        class="scroll-mt-20 px-4 py-3 transition-colors"
        :class="team.id === highlightId ? 'bg-primary/5' : ''"
        :data-testid="`team-row-${team.id}`"
      >
        <!-- One line per team once there are many. -->
        <div
          v-if="compact"
          class="grid grid-cols-[1rem_1fr_auto] items-center gap-x-3 gap-y-0.5 md:grid-cols-[1rem_11rem_1fr_8rem_auto]"
        >
          <component
            :is="team.requires_approval ? Lock : 'span'"
            class="size-4 text-muted-foreground"
            :aria-label="team.requires_approval ? t('teams.summary.approval') : undefined"
          />
          <span class="truncate font-semibold">{{ team.name }}</span>
          <span
            class="col-start-2 row-start-2 truncate text-sm text-muted-foreground md:col-start-auto md:row-start-auto"
          >
            {{ team.description }}
          </span>
          <span
            class="hidden text-sm md:block"
            :class="team.open_shift_count ? 'font-medium' : 'text-muted-foreground'"
          >
            {{ openShifts(team) }}
          </span>
          <Button
            size="sm"
            class="col-start-3 row-span-2 row-start-1 w-28 md:col-start-auto md:row-span-1 md:row-start-auto"
            :variant="team.requires_approval ? 'default' : 'outline'"
            :disabled="busyTeamId === team.id"
            :aria-label="joinLabelNamed(team)"
            :data-testid="`btn-join-team-${team.id}`"
            @click="emit('join', team)"
          >
            {{ joinLabel(team) }}
          </Button>
        </div>

        <!-- A few teams: room to say what each one is. -->
        <div v-else class="flex items-start gap-3">
          <component
            :is="team.requires_approval ? Lock : UserRound"
            class="mt-1 size-4 shrink-0 text-muted-foreground"
            aria-hidden="true"
          />
          <div class="min-w-0 flex-1 space-y-1.5">
            <div class="flex flex-wrap items-start gap-x-3 gap-y-2">
              <div class="min-w-0 flex-1 sm:flex sm:items-baseline sm:gap-6">
                <p class="font-semibold sm:w-36 sm:shrink-0">{{ team.name }}</p>
                <p class="text-sm text-muted-foreground">{{ summary(team) }}</p>
              </div>
              <Button
                class="w-full sm:w-auto sm:min-w-28"
                :variant="team.requires_approval ? 'default' : 'outline'"
                :disabled="busyTeamId === team.id"
                :aria-label="joinLabelNamed(team)"
                :data-testid="`btn-join-team-${team.id}`"
                @click="emit('join', team)"
              >
                {{ joinLabel(team) }}
              </Button>
            </div>
            <p v-if="team.description" class="text-sm whitespace-pre-line">
              {{ team.description }}
            </p>
            <p
              v-if="team.requirements?.length"
              class="flex items-start gap-1.5 text-sm text-muted-foreground"
            >
              <ShieldCheck class="mt-0.5 size-4 shrink-0" />
              {{
                t('teams.summary.needs', {
                  list: joinNames(
                    team.requirements.map((r) => r.label),
                    locale,
                  ),
                })
              }}
            </p>
            <p class="text-xs text-muted-foreground">{{ details(team) }}</p>
            <p v-if="team.my_status === 'declined'" class="text-xs text-muted-foreground">
              {{ t('teams.more.declinedHint') }}
            </p>
          </div>
        </div>
      </li>
      <li
        v-if="shown.length === 0"
        class="px-4 py-6 text-center text-sm text-muted-foreground"
        data-testid="teams-no-match"
      >
        {{ t('teams.more.noMatch') }}
      </li>
      <li v-if="rest > 0" class="px-4 py-3">
        <Button
          variant="link"
          class="h-auto p-0"
          data-testid="btn-teams-more-show-all"
          @click="showAll = true"
        >
          {{ t('teams.more.showMore', { count: rest }, rest) }}
        </Button>
      </li>
    </ul>
  </section>
</template>
