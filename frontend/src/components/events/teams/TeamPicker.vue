<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { Lock, Plus, UsersRound } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

import { invalidateTeams, teamsPageLocation, useTeams } from '@/composables/useTeams'

import Button from '@/components/ui/button/Button.vue'
import Label from '@/components/ui/label/Label.vue'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'

import TeamFormDialog from '@/components/events/teams/TeamFormDialog.vue'

import type { EventTeamRead } from '@/client/types.gen'

/**
 * "Who can book" for a task: everyone in the event, or the approved members
 * of one of its teams.
 *
 * Two radio cards pick the mode; the team itself is a Select of the event's
 * teams, with "New team…" for someone who manages the event. `null` on the
 * model is "everyone". `inputId` lands on the team trigger, so a
 * `<Label :for>` outside works.
 */
const teamId = defineModel<string | null>({ required: true })

const props = defineProps<{
  eventId: string | null | undefined
  inputId?: string
}>()

const { t } = useI18n()
const authStore = useAuthStore()

const { teams, loading, error, reload } = useTeams(() => props.eventId ?? null)

// Reka's Select refuses '' as a value; "nothing chosen" is a value no item
// carries, so the trigger shows its placeholder.
const NONE = '__none'
const CREATE = '__new'

type Mode = 'everyone' | 'team'
const mode = ref<Mode>(teamId.value ? 'team' : 'everyone')
// The team chosen before switching to "everyone", restored on the way back.
let lastTeamId: string | null = teamId.value

// An edit form fills the model in once its task has loaded.
watch(teamId, (id) => {
  if (id) {
    mode.value = 'team'
    lastTeamId = id
  }
})

// A team of the previous event is no answer for this one.
watch(
  () => props.eventId,
  () => (lastTeamId = null),
)

function onModeChange(value: unknown) {
  const next: Mode = value === 'team' ? 'team' : 'everyone'
  mode.value = next
  if (next === 'everyone') {
    teamId.value = null
    return
  }
  // A single team is the obvious choice.
  teamId.value = lastTeamId ?? (teams.value.length === 1 ? (teams.value[0]?.id ?? null) : null)
}

const canCreate = computed(() => !!props.eventId && authStore.canManageEvent(props.eventId))

const selected = computed(() => teams.value.find((team) => team.id === teamId.value) ?? null)

// A team not (yet) in the list — still loading, or just created — keeps an
// option, so the trigger is not blank.
const orphanId = computed(() =>
  teamId.value && !loading.value && !selected.value ? teamId.value : null,
)

const showNoTeams = computed(
  () => !!props.eventId && !loading.value && !error.value && teams.value.length === 0,
)

const formOpen = ref(false)
// Ids before a "New team…" save, to recognise the new one when the list reloads.
let pickNewAfter: Set<string> | null = null

function onSelect(value: unknown) {
  const v = String(value ?? NONE)
  if (v === CREATE) {
    // Not a real choice: keep the current one until the dialog saves.
    formOpen.value = true
    return
  }
  teamId.value = v === NONE ? null : v
  if (teamId.value) lastTeamId = teamId.value
}

function onCreated(team?: EventTeamRead) {
  if (team?.id) {
    teamId.value = team.id
  } else {
    pickNewAfter = new Set(teams.value.map((t) => t.id))
  }
  invalidateTeams(props.eventId)
}

watch(teams, (list) => {
  if (!pickNewAfter) return
  const added = list.find((team) => !pickNewAfter!.has(team.id))
  if (added) {
    teamId.value = added.id
    pickNewAfter = null
  }
})

const teamsPage = computed(() => teamsPageLocation(props.eventId))
</script>

<template>
  <div class="space-y-4" data-testid="team-picker">
    <RadioGroup
      :model-value="mode"
      :disabled="!eventId"
      :aria-label="t('teamLocks.picker.title')"
      class="grid gap-2.5 sm:grid-cols-2"
      @update:model-value="onModeChange"
    >
      <Label
        v-for="option in [
          {
            value: 'everyone',
            title: t('teamLocks.picker.everyone'),
            hint: t('teamLocks.picker.everyoneHint'),
          },
          {
            value: 'team',
            title: t('teamLocks.picker.team'),
            hint: t('teamLocks.picker.teamHint'),
          },
        ]"
        :key="option.value"
        :for="`${inputId ?? 'team-picker'}-${option.value}`"
        class="flex cursor-pointer items-start gap-3 rounded-lg border p-3.5 font-normal transition-colors has-[[data-state=checked]]:border-primary has-[[data-state=checked]]:bg-primary/5 has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-60"
      >
        <RadioGroupItem
          :id="`${inputId ?? 'team-picker'}-${option.value}`"
          :value="option.value"
          class="mt-0.5"
          :data-testid="`task-team-mode-${option.value}`"
        />
        <span class="space-y-0.5">
          <span class="block font-medium">{{ option.title }}</span>
          <span class="text-muted-foreground block text-xs">{{ option.hint }}</span>
        </span>
      </Label>
    </RadioGroup>

    <p v-if="!eventId" class="text-muted-foreground text-xs" data-testid="team-picker-no-event">
      {{ t('teamLocks.picker.noEvent') }}
    </p>

    <div v-else-if="mode === 'team'" class="space-y-2">
      <Label :for="inputId">{{ t('teamLocks.picker.teamLabel') }}</Label>

      <Skeleton v-if="loading && teams.length === 0" class="h-9 w-full sm:max-w-sm" />

      <Select v-else :model-value="teamId ?? NONE" @update:model-value="onSelect">
        <SelectTrigger :id="inputId" class="w-full sm:max-w-sm" data-testid="task-team">
          <SelectValue :placeholder="t('teamLocks.picker.choose')">
            <span v-if="selected" class="flex min-w-0 items-center gap-2">
              <Lock v-if="selected.requires_approval" aria-hidden="true" />
              <UsersRound v-else aria-hidden="true" />
              <span class="truncate">{{ selected.name }}</span>
            </span>
            <span v-else-if="orphanId">…</span>
            <span v-else class="text-muted-foreground">{{ t('teamLocks.picker.choose') }}</span>
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          <SelectItem
            v-for="team in teams"
            class="*:[span]:last:flex-1"
            :key="team.id"
            :value="team.id"
            :text-value="team.name"
            :data-testid="`team-option-${team.id}`"
          >
            <Lock v-if="team.requires_approval" aria-hidden="true" />
            <UsersRound v-else aria-hidden="true" />
            <span class="min-w-0 truncate">
              {{ team.name }}
              <span v-if="!team.requires_approval" class="text-muted-foreground text-xs">
                · {{ t('teamLocks.picker.openTeam') }}
              </span>
            </span>
            <span class="text-muted-foreground ml-auto pl-3 text-xs whitespace-nowrap">
              {{
                t(
                  'teamLocks.picker.members',
                  { count: team.member_count ?? 0 },
                  team.member_count ?? 0,
                )
              }}
            </span>
          </SelectItem>
          <SelectItem v-if="orphanId" :value="orphanId">…</SelectItem>
          <template v-if="canCreate">
            <SelectSeparator v-if="teams.length > 0 || orphanId" />
            <SelectItem
              :value="CREATE"
              class="text-primary font-medium"
              data-testid="team-option-create"
            >
              <Plus class="text-primary" aria-hidden="true" />
              {{ t('teamLocks.picker.createNew') }}
            </SelectItem>
          </template>
        </SelectContent>
      </Select>

      <div
        v-if="error"
        class="text-destructive flex flex-wrap items-center gap-2 text-xs"
        role="alert"
        data-testid="team-picker-error"
      >
        {{ t('teamLocks.picker.loadError') }}
        <Button variant="link" size="sm" class="h-auto p-0 text-xs" @click="reload()">
          {{ t('teamLocks.picker.retry') }}
        </Button>
      </div>
      <p
        v-else-if="showNoTeams"
        class="text-muted-foreground text-xs"
        data-testid="team-picker-no-teams"
      >
        {{ t('teamLocks.picker.noTeams') }}
        <RouterLink
          :to="teamsPage"
          target="_blank"
          class="text-primary underline-offset-4 hover:underline"
        >
          {{ t('teamLocks.picker.noTeamsLink') }}
        </RouterLink>
      </p>
      <p
        v-else-if="!teamId && !loading"
        class="text-xs text-amber-700 dark:text-amber-400"
        data-testid="team-picker-choose"
      >
        {{ t('teamLocks.picker.chooseTeam') }}
      </p>
    </div>

    <TeamFormDialog
      v-if="canCreate && eventId"
      v-model:open="formOpen"
      :event-id="eventId"
      @saved="onCreated"
    />
  </div>
</template>
