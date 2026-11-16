<script setup lang="ts">
/**
 * "Which tasks?": the tasks the viewer may put on a list, searched and paged
 * by the server, with the chosen ones as removable chips above.
 *
 * Tasks only a team may book never go on a list. Without a search the server
 * leaves them out and one line names them; while searching they show up,
 * disabled, saying which team they belong to, so nobody hunts for a task that
 * is missing for a reason.
 *
 * A task that gives vouchers says that people signing up through the list earn
 * them too.
 */
import { computed, onMounted, ref, watch } from 'vue'

import { Lock, Ticket, TriangleAlert, X } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { useSharedListFormat } from '@/composables/useSharedListFormat'
import { useSharedListWizardApi } from '@/composables/useSharedListWizardApi'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'

import SearchField from '@/components/data-table/SearchField.vue'
import WizardTaskShifts from '@/components/shared-lists/wizard/WizardTaskShifts.vue'

import type { SharedListCandidate } from '@/client/types.gen'
import { getApiErrorMessage } from '@/lib/api-errors'
import { type PickedTask, type WizardShift, taskProblem } from '@/lib/shared-list-selection'

const props = defineProps<{
  eventId: string
  /** The chosen tasks, in list order. */
  picked: readonly PickedTask[]
  /** The loaded shifts per task; a chosen task's problem shows once its shifts are in. */
  shiftsByTask: ReadonlyMap<string, readonly WizardShift[]>
}>()

const excluded = defineModel<Set<string>>('excluded', { required: true })

const emit = defineEmits<{
  pick: [task: SharedListCandidate]
  unpick: [taskId: string]
}>()

const { t } = useI18n()
const { daysText, list } = useSharedListFormat()
const { fetchCandidates } = useSharedListWizardApi()

const q = ref('')
const items = ref<SharedListCandidate[]>([])
const total = ref(0)
const lockedCount = ref(0)
const lockedNames = ref<string[]>([])
const loading = ref(false)
const loadError = ref<unknown>(null)
// Guards against an older search answering after a newer one.
let generation = 0

const pickedIds = computed(() => new Set(props.picked.map((task) => task.id)))

async function load(append = false) {
  const gen = ++generation
  loading.value = true
  loadError.value = null
  try {
    const page = await fetchCandidates(props.eventId, {
      q: q.value,
      skip: append ? items.value.length : 0,
    })
    if (gen !== generation) return
    items.value = append ? [...items.value, ...page.items] : page.items
    total.value = page.total
    lockedCount.value = page.locked_count
    lockedNames.value = page.locked_names
  } catch (error) {
    if (gen === generation) loadError.value = error
  } finally {
    if (gen === generation) loading.value = false
  }
}

onMounted(() => load())
watch(q, () => load())

function onCheck(task: SharedListCandidate, value: boolean | 'indeterminate') {
  if (value === true) emit('pick', task)
  else emit('unpick', task.id)
}

function problemOf(taskId: string) {
  const shifts = props.shiftsByTask.get(taskId)
  return shifts ? taskProblem(shifts, excluded.value) : 'none'
}

/** "„A“, „B“, „C“ und 2 weitere sind nur für Teams da …" */
const lockedHint = computed(() => {
  if (q.value || lockedCount.value === 0) return ''
  const names = lockedNames.value.map((name) => t('sharedLists.text.quoted', { name }))
  const rest = lockedCount.value - lockedNames.value.length
  if (rest > 0) names.push(t('sharedListWizard.picker.lockedMore', { count: rest }))
  return t('sharedListWizard.picker.lockedHint', { names: list(names) }, lockedCount.value)
})
</script>

<template>
  <div class="grid gap-3">
    <SearchField
      v-model="q"
      :label="t('sharedListWizard.picker.searchLabel')"
      :placeholder="t('sharedListWizard.picker.searchPlaceholder')"
    />

    <div
      v-if="picked.length"
      class="flex flex-wrap items-center gap-1.5"
      data-testid="wizard-picked"
    >
      <span class="mr-0.5 text-xs text-muted-foreground">
        {{ t('sharedListWizard.picker.picked', { count: picked.length }) }}
      </span>
      <button
        v-for="task in picked"
        :key="task.id"
        type="button"
        class="inline-flex min-h-8 max-w-full items-center gap-1 rounded-full border px-2.5 text-xs font-semibold outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
        :class="
          task.unavailable
            ? 'border-warning/50 bg-warning/10 text-warning'
            : 'border-primary/40 bg-primary/10 text-primary hover:border-primary'
        "
        :aria-label="t('sharedListWizard.picker.unpick', { name: task.name })"
        :data-testid="`wizard-picked-${task.id}`"
        @click="emit('unpick', task.id)"
      >
        <span class="truncate">{{ task.name }}</span>
        <X class="size-3 shrink-0" aria-hidden="true" />
      </button>
    </div>

    <p v-if="loadError" class="flex flex-wrap items-center gap-2 text-sm text-destructive">
      {{ getApiErrorMessage(loadError) }}
      <Button type="button" variant="outline" size="sm" @click="load()">
        {{ t('sharedListWizard.actions.retry') }}
      </Button>
    </p>

    <ul v-if="items.length" class="grid gap-2" data-testid="wizard-candidates">
      <li
        v-for="task in items"
        :key="task.id"
        class="grid gap-1 rounded-lg border px-3 py-2.5"
        :class="[
          task.team ? 'bg-transparent' : 'bg-card',
          pickedIds.has(task.id)
            ? problemOf(task.id) === 'none'
              ? 'border-primary/60'
              : 'border-warning/55'
            : '',
        ]"
        :data-testid="`wizard-candidate-${task.id}`"
      >
        <div class="flex items-start gap-3">
          <Checkbox
            :id="`wizard-task-${task.id}`"
            class="mt-0.5"
            :model-value="pickedIds.has(task.id)"
            :disabled="!!task.team"
            :aria-describedby="
              !task.team && task.earns_vouchers
                ? `wizard-task-meta-${task.id} wizard-task-vouchers-${task.id}`
                : `wizard-task-meta-${task.id}`
            "
            :data-testid="`wizard-task-check-${task.id}`"
            @update:model-value="(value) => onCheck(task, value)"
          />
          <div class="grid min-w-0 gap-0.5">
            <Label
              :for="`wizard-task-${task.id}`"
              class="block cursor-pointer leading-snug font-semibold break-words"
            >
              {{ task.name }}
            </Label>
            <p
              :id="`wizard-task-meta-${task.id}`"
              class="text-xs"
              :class="task.team ? 'text-warning' : 'text-muted-foreground'"
            >
              <template v-if="task.team">
                {{ t('sharedListWizard.picker.teamOnly', { team: task.team.name }) }}
              </template>
              <template v-else>
                {{
                  t('sharedListWizard.picker.fill', { free: task.free, capacity: task.capacity })
                }}
                · {{ daysText(task.dates) }}
              </template>
            </p>
            <p
              v-if="!task.team && task.earns_vouchers"
              :id="`wizard-task-vouchers-${task.id}`"
              class="flex items-start gap-1 text-xs text-muted-foreground"
              :data-testid="`wizard-task-vouchers-${task.id}`"
            >
              <Ticket class="mt-px size-3.5 shrink-0 text-primary" aria-hidden="true" />
              {{ t('sharedListWizard.picker.vouchers') }}
            </p>
            <p
              v-if="pickedIds.has(task.id) && problemOf(task.id) !== 'none'"
              class="flex items-start gap-1 text-xs font-semibold text-warning"
            >
              <TriangleAlert class="mt-px size-3.5 shrink-0" aria-hidden="true" />
              {{ t(`sharedListWizard.picker.problem.${problemOf(task.id)}`) }}
            </p>
          </div>
        </div>
        <WizardTaskShifts
          v-if="pickedIds.has(task.id) && (shiftsByTask.get(task.id)?.length ?? 0) > 1"
          v-model:excluded="excluded"
          class="ml-7"
          :task-id="task.id"
          :task-name="task.name"
          :shifts="shiftsByTask.get(task.id) ?? []"
        />
      </li>
    </ul>

    <p
      v-else-if="!loading && !loadError"
      class="text-sm text-muted-foreground"
      data-testid="wizard-candidates-empty"
    >
      {{ q ? t('sharedListWizard.picker.empty', { q }) : t('sharedListWizard.picker.none') }}
    </p>

    <Button
      v-if="items.length < total"
      type="button"
      variant="outline"
      size="sm"
      class="justify-self-start"
      :disabled="loading"
      data-testid="wizard-candidates-more"
      @click="load(true)"
    >
      {{ t('sharedListWizard.picker.loadMore') }}
    </Button>

    <p v-if="lockedHint" class="flex items-start gap-1.5 text-xs text-muted-foreground">
      <Lock class="mt-px size-3.5 shrink-0" aria-hidden="true" />
      {{ lockedHint }}
    </p>
  </div>
</template>
