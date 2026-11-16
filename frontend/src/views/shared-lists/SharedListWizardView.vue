<script setup lang="ts">
/**
 * Create, copy or edit a shared list, in steps: which tasks and shifts, how
 * the list looks, and (for a new list) how to share it.
 *
 * `shared-list-create` starts blank, from `?tasks=<id,id>` (picked on the
 * Tasks tab) or from `?from=<listId>` (a copy, its title counted as typed);
 * `shared-list-edit` loads the list and saves only what changed, so its link
 * stays the same. The selection is the tasks minus one set of excluded shifts
 * (`lib/shared-list-selection.ts`); days are only ever read off it.
 */
import { computed, nextTick, onMounted, ref, watch } from 'vue'

import { ArrowLeft, Check, ClipboardList, Eye, Settings2, Share2, TriangleAlert } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { type RouteLocationRaw, onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { toast } from 'vue-sonner'

import { useBreadcrumbStore } from '@/stores/breadcrumb'

import { useDialog } from '@/composables/useDialog'
import { useSharedListFormat } from '@/composables/useSharedListFormat'
import { useSharedListWizardApi } from '@/composables/useSharedListWizardApi'

import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Stepper,
  StepperIndicator,
  StepperItem,
  StepperSeparator,
  StepperTitle,
  StepperTrigger,
} from '@/components/ui/stepper'

import { LIST_KEY, PREVIEW_KEY, TAB_KEY } from '@/components/shared-lists/pageQuery'
import WizardSettingsStep from '@/components/shared-lists/wizard/WizardSettingsStep.vue'
import WizardShareStep from '@/components/shared-lists/wizard/WizardShareStep.vue'
import WizardTasksStep from '@/components/shared-lists/wizard/WizardTasksStep.vue'

import type { EventRead, SharedListCandidate, SharedListDetail } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'
import {
  SELECTION_FIELDS,
  type SettingsBlocker,
  blankDraft,
  changedFields,
  draftFromDetail,
  draftSignature,
  settingsBlockers,
  toPayload,
} from '@/lib/shared-list-draft'
import {
  MAX_TASKS,
  type Step1Blocker,
  type WizardShift,
  addTask,
  autoTitle,
  includedShifts,
  lastShift,
  maxPerOptions,
  pruneExcluded,
  step1Blockers,
} from '@/lib/shared-list-selection'
import { shareMessage } from '@/lib/shared-list-share-message'
import { canUseSharedLists, sharedListUrl } from '@/lib/shared-lists'
import { wallClockIn } from '@/lib/shift-time'

type Section = 'tasks' | 'settings' | 'share'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const breadcrumbStore = useBreadcrumbStore()
const { confirm } = useDialog()
const { shortDay, timeRange, daysText, formatDaySpan } = useSharedListFormat()
const api = useSharedListWizardApi()

// The wizard routes carry no `routerViewKey`, so any change of URL mounts a
// fresh view: reading the route once here is enough.
const isEdit = route.name === 'shared-list-edit'
const listId = isEdit ? String(route.params.listId) : null
const sections: readonly Section[] = isEdit ? ['tasks', 'settings'] : ['tasks', 'settings', 'share']
const stepIcons = { tasks: ClipboardList, settings: Settings2, share: Share2 }

const loading = ref(true)
const eventId = ref(String(route.params.eventId))
const event = ref<EventRead | null>(null)
/** The list as it was loaded for editing. */
const saved = ref<SharedListDetail | null>(null)
/** The list this wizard opened, once it exists. */
const created = ref<SharedListDetail | null>(null)
const draft = ref(blankDraft())
/** The draft as last loaded or saved; `null` until the load is done. */
const savedSignature = ref<string | null>(null)
const message = ref('')
const submitting = ref(false)

const activeSection = ref<Section>('tasks')
const visitedSections = ref(new Set<Section>(['tasks']))
/** Steps whose blocker shows although nothing changed: Next was pressed there. */
const revealed = ref(new Set<Section>())

// --- Selection ----------------------------------------------------------

const offeredTaskIds = computed(() =>
  draft.value.tasks.filter((task) => !task.unavailable).map((task) => task.id),
)

const shiftsReady = computed(() =>
  offeredTaskIds.value.every((id) => api.shiftsByTask.value.has(id)),
)

const loadedShifts = computed<WizardShift[]>(() =>
  offeredTaskIds.value.flatMap((id) => api.shiftsByTask.value.get(id) ?? []),
)

const included = computed(() =>
  includedShifts(loadedShifts.value, offeredTaskIds.value, draft.value.excluded),
)

const lastIncluded = computed(() => lastShift(included.value))

/** Today on the event's clock: the earliest day a list may close on. */
const today = computed(() => wallClockIn(event.value?.timezone).date)

const maxOptions = computed(() => maxPerOptions(included.value.length, draft.value.maxPerPerson))

/** Every loaded shift by id, of any task picked at some point. */
const knownShifts = computed(
  () => new Map([...api.shiftsByTask.value.values()].flat().map((shift) => [shift.id, shift])),
)

/** The request body as the draft stands, with only the exclusions that matter. */
const payload = computed(() =>
  toPayload(
    draft.value,
    pruneExcluded(draft.value.excluded, offeredTaskIds.value, knownShifts.value),
  ),
)

/**
 * For an edit, what differs from the list as loaded. Its exclusions are
 * pruned the same way, or shifts that have started since would read as a
 * change and make the API check the selection again.
 */
const changes = computed(() => {
  if (!saved.value) return null
  const before = draftFromDetail(saved.value)
  const beforeExcluded = pruneExcluded(
    before.excluded,
    before.tasks.map((task) => task.id),
    knownShifts.value,
  )
  return changedFields(payload.value, toPayload(before, beforeExcluded))
})

watch(offeredTaskIds, (ids) => {
  if (event.value) void api.loadShifts(event.value.id, ids)
})

// Until a title is typed, it follows the tasks.
watch(
  () => draft.value.tasks.map((task) => task.name),
  (names) => {
    if (!draft.value.titleTouched && event.value) {
      draft.value.title = autoTitle(names, event.value.name, t)
    }
  },
)

// Closing on a day starts out with the day of the last shift.
watch(
  () => draft.value.endsMode,
  (mode) => {
    if (mode === 'date' && !draft.value.endsOn && lastIncluded.value) {
      draft.value.endsOn = lastIncluded.value.date
    }
  },
)

function pickTask(task: SharedListCandidate) {
  if (draft.value.tasks.some((picked) => picked.id === task.id)) return
  draft.value.tasks = [...draft.value.tasks, { id: task.id, name: task.name, unavailable: null }]
  const known = api.shiftsByTask.value.get(task.id)
  if (known) {
    draft.value.excluded = addTask(
      draft.value.excluded,
      known.map((shift) => shift.id),
    )
  }
}

function unpickTask(taskId: string) {
  draft.value.tasks = draft.value.tasks.filter((task) => task.id !== taskId)
}

function retryShifts() {
  if (event.value) void api.loadShifts(event.value.id, offeredTaskIds.value)
}

/** Typing a title, and only that, stops it from following the tasks. */
const titleModel = computed({
  get: () => draft.value.title,
  set: (value: string) => {
    draft.value.title = value
    draft.value.titleTouched = true
  },
})

// --- Blockers -----------------------------------------------------------

function describeTasksBlocker(blocker: Step1Blocker): string {
  switch (blocker.kind) {
    case 'no_task':
      return t('sharedListWizard.blockers.noTask')
    case 'too_many_tasks':
      return t('sharedListWizard.blockers.tooManyTasks', { max: blocker.max })
    case 'task_unavailable':
      return t(`sharedListWizard.blockers.taskUnavailable.${blocker.reason}`, {
        name: blocker.name,
      })
    case 'no_included_shift':
      return t('sharedListWizard.blockers.noIncludedShift')
    case 'task_no_included':
      return t('sharedListWizard.blockers.taskNoIncluded', { name: blocker.name })
    case 'no_free_place':
      return t('sharedListWizard.blockers.noFreePlace')
  }
}

function describeSettingsBlocker(blocker: SettingsBlocker): string {
  switch (blocker.kind) {
    case 'no_title':
      return t('sharedListWizard.blockers.noTitle')
    case 'ends_on_missing':
      return t('sharedListWizard.blockers.endsOnMissing')
    case 'ends_on_past':
      return t('sharedListWizard.blockers.endsOnPast')
    case 'ends_on_after_last':
      return t('sharedListWizard.blockers.endsOnAfterLast', { date: shortDay(blocker.lastDate) })
  }
}

/**
 * Whether saving makes the API check the selection again: always for a new
 * list, and for an edit only when it changes the tasks, the shifts left out or
 * the closing (`SELECTION_FIELDS`). An edit that does not is not checked
 * against the shifts at all, so a full list can still have its text corrected.
 */
const checksSelection = computed(() => {
  const pending = changes.value
  return pending === null || SELECTION_FIELDS.some((field) => field in pending)
})

/**
 * What is wrong with the selection, as far as the API will check it. Nothing
 * is judged while shifts are still on their way: the days show that they are
 * loading, or that they failed.
 */
const tasksBlocker = computed(() => {
  if (!shiftsReady.value || !checksSelection.value) return ''
  // An edit that keeps the tasks is checked against those the list can still
  // offer, so a task that has become team-only does not block it.
  const keepsTasks = changes.value !== null && !('task_ids' in changes.value)
  const tasks = keepsTasks
    ? draft.value.tasks.filter((task) => !task.unavailable)
    : draft.value.tasks
  const [first] = step1Blockers(tasks, loadedShifts.value, draft.value.excluded)
  return first ? describeTasksBlocker(first) : ''
})

const tasksDone = computed(() => shiftsReady.value && tasksBlocker.value === '')

const settingsBlocker = computed(() => {
  const [first] = settingsBlockers(draft.value, {
    today: today.value,
    lastDate: lastIncluded.value?.date ?? null,
    checkClosing: checksSelection.value,
  })
  return first ? describeSettingsBlocker(first) : ''
})

function blockerOf(section: Section): string {
  if (section === 'tasks') return tasksBlocker.value
  if (section === 'settings') return settingsBlocker.value
  return ''
}

const isDirty = computed(
  () =>
    savedSignature.value !== null &&
    created.value === null &&
    draftSignature(draft.value) !== savedSignature.value,
)

/**
 * Why the step on screen cannot be left forwards, once that is worth saying:
 * after something was changed, or after Next was pressed here. A fresh wizard
 * does not greet anyone with an error.
 */
const stepBlockedReason = computed(() => {
  const section = activeSection.value
  if (!isDirty.value && !revealed.value.has(section)) return ''
  return blockerOf(section)
})

// --- Steps --------------------------------------------------------------

const currentStepNumber = computed(() => sections.indexOf(activeSection.value) + 1)

/** Back to the tasks at any time, on to the settings once the tasks are fine, and
 *  to sharing only once the list exists; after that, nowhere else. */
function isStepReachable(section: Section): boolean {
  if (created.value) return section === 'share'
  if (section === 'share') return false
  return section === 'tasks' || tasksDone.value
}

/** A tick claims the step is done, so it needs both halves of that. */
function isStepCompleted(section: Section): boolean {
  if (created.value) return section !== 'share'
  return (
    section !== activeSection.value && visitedSections.value.has(section) && !blockerOf(section)
  )
}

function stepHasProblem(section: Section): boolean {
  return !created.value && revealed.value.has(section) && blockerOf(section) !== ''
}

/**
 * Focus follows the wizard to the new step's heading, so a screen reader reads
 * what changed and the next Tab starts inside the step: the button that was
 * just pressed belonged to the step that is gone.
 */
function focusStepHeading() {
  document.querySelector<HTMLElement>('[data-testid="wizard-step-heading"]')?.focus()
}

function goToSection(section: Section) {
  if (section === activeSection.value || !isStepReachable(section)) return
  activeSection.value = section
  visitedSections.value = new Set(visitedSections.value).add(section)
  void nextTick().then(focusStepHeading)
}

/** The stepper hands back a 1-based step, or undefined while it settles. */
function onStepChange(step: number | undefined) {
  if (step === undefined) return
  const section = sections[step - 1]
  if (section) goToSection(section)
}

function reveal(section: Section) {
  revealed.value = new Set(revealed.value).add(section)
}

function goToSettings() {
  reveal('tasks')
  if (tasksDone.value) goToSection('settings')
}

// --- Load ---------------------------------------------------------------

function listsPage(query: Record<string, string> = {}): RouteLocationRaw {
  return { name: 'shared-lists', params: { eventId: eventId.value }, query }
}

/** `?tasks=a,b`: the ids, each once, no more than a list takes. */
function preselectedIds(): string[] {
  const raw = typeof route.query.tasks === 'string' ? route.query.tasks : ''
  return [...new Set(raw.split(',').filter(Boolean))].slice(0, MAX_TASKS)
}

/** Leave with the reason. Nothing was changed yet, so nothing is asked. */
async function refuse(reason: string, to: RouteLocationRaw) {
  toast.error(reason)
  await router.replace(to)
}

async function load() {
  try {
    if (listId) {
      const list = await api.fetchDetail(listId)
      eventId.value = list.event.id
      if (list.status === 'ended') {
        return await refuse(t('sharedListWizard.toasts.ended'), listsPage({ [LIST_KEY]: list.id }))
      }
      if (list.access === 'viewer') {
        return await refuse(
          t('sharedListWizard.toasts.readOnly'),
          listsPage({ [LIST_KEY]: list.id }),
        )
      }
      saved.value = list
      draft.value = draftFromDetail(list)
    }

    const ev = await api.fetchEvent(eventId.value)
    if (!canUseSharedLists(ev)) {
      return await refuse(t('sharedListWizard.toasts.noAccess'), { name: 'home' })
    }
    if (!ev.can_manage && ev.managers_share_lists === false) {
      return await refuse(t('sharedListWizard.toasts.managersDisabled'), listsPage())
    }
    event.value = ev

    if (!isEdit) {
      const from = typeof route.query.from === 'string' ? route.query.from : ''
      const source = from ? await api.fetchDetail(from) : null
      if (source && source.event.id === ev.id) {
        draft.value = draftFromDetail(source)
      } else {
        const found = await api.findCandidates(ev.id, preselectedIds())
        draft.value = blankDraft(
          found.map((task) => ({ id: task.id, name: task.name, unavailable: null })),
        )
        draft.value.title = autoTitle(
          found.map((task) => task.name),
          ev.name,
          t,
        )
      }
    }

    savedSignature.value = draftSignature(draft.value)
    void api.loadShifts(ev.id, offeredTaskIds.value)
    breadcrumbStore.setBreadcrumbs([
      {
        title: 'Shared lists',
        titleKey: 'navigation.sidebar.items.sharedLists.label',
        to: { name: 'shared-lists', params: { eventId: ev.id } },
      },
      isEdit
        ? { title: 'Edit list', titleKey: 'navigation.breadcrumbs.sharedListEdit' }
        : { title: 'Share a list', titleKey: 'navigation.breadcrumbs.sharedListCreate' },
    ])
  } catch (error) {
    toastApiError(error)
    await router.replace(listsPage())
  } finally {
    loading.value = false
  }
}

onMounted(load)

// --- Save ---------------------------------------------------------------

function buildMessage(list: SharedListDetail): string {
  return shareMessage(
    {
      eventName: list.event.name,
      eventDays: formatDaySpan(list.event.start_date, list.event.end_date),
      tasks: draft.value.tasks.filter((task) => !task.unavailable),
      shifts: included.value,
      url: sharedListUrl(list.code),
    },
    { day: shortDay, time: timeRange, days: daysText },
    t,
  )
}

async function submit() {
  if (submitting.value || !event.value) return
  reveal('settings')
  if (settingsBlocker.value || !tasksDone.value) return
  submitting.value = true
  try {
    if (saved.value && changes.value) {
      const list = await api.update(saved.value.id, changes.value)
      savedSignature.value = draftSignature(draft.value)
      toast.success(t('sharedListWizard.toasts.saved'))
      await router.push(listsPage({ [LIST_KEY]: list.id }))
    } else {
      const list = await api.create(event.value.id, payload.value)
      message.value = buildMessage(list)
      created.value = list
      goToSection('share')
    }
  } catch (error) {
    toastApiError(error)
  } finally {
    submitting.value = false
  }
}

// --- Leave --------------------------------------------------------------

onBeforeRouteLeave(async () => {
  if (!isDirty.value) return true
  return confirm({
    title: t('sharedListWizard.leaveGuard.title'),
    text: t('sharedListWizard.leaveGuard.text'),
    confirmText: t('sharedListWizard.leaveGuard.confirm'),
    cancelText: t('sharedListWizard.leaveGuard.cancel'),
    variant: 'destructive',
  })
})

/**
 * Once the list exists, wherever the wizard leads takes its place in the
 * history: Back would otherwise open it empty, ready to share the same tasks
 * a second time, rather than return to where the sharing began.
 */
function go(to: RouteLocationRaw) {
  void (created.value ? router.replace(to) : router.push(to))
}

function leave() {
  go(listsPage())
}

/** The new list's notice, with its QR code and the shifts it offers. */
function printNotice() {
  if (created.value) go({ name: 'print-list', params: { listId: created.value.id } })
}

/** The lists page's "how helpers see it" tab, showing the new list. */
function openPreview() {
  if (created.value) go(listsPage({ [TAB_KEY]: 'preview', [PREVIEW_KEY]: created.value.id }))
}
</script>

<template>
  <div class="mx-auto max-w-3xl space-y-6">
    <div class="space-y-2">
      <Button
        type="button"
        variant="ghost"
        size="sm"
        class="-ml-2 max-xl:hidden"
        data-testid="btn-back"
        @click="leave"
      >
        <ArrowLeft class="mr-1.5 h-4 w-4" aria-hidden="true" />
        {{ t('common.actions.back') }}
      </Button>
      <h1 data-testid="page-heading" class="text-2xl font-bold tracking-tight sm:text-3xl">
        {{ isEdit ? t('sharedListWizard.title.edit') : t('sharedListWizard.title.create') }}
      </h1>
      <p class="text-muted-foreground">
        {{ isEdit ? t('sharedListWizard.lede.edit') : t('sharedListWizard.lede.create') }}
      </p>
    </div>

    <p v-if="loading" class="py-12 text-center text-muted-foreground">
      {{ t('common.states.loading') }}
    </p>

    <div v-else-if="event" class="space-y-6">
      <p
        v-if="event.status !== 'published'"
        class="flex items-start gap-2 rounded-lg border border-warning/50 bg-warning/10 p-3 text-sm"
        data-testid="wizard-not-published"
      >
        <TriangleAlert class="mt-0.5 size-4 shrink-0 text-warning" aria-hidden="true" />
        {{ t('sharedListWizard.notPublished') }}
      </p>

      <!-- Not linear: `:disabled` below is the one gate, and it lets someone
           step back to fix something without stranding them there. -->
      <Stepper
        data-testid="wizard-stepper"
        class="w-full items-start gap-0"
        :linear="false"
        :model-value="currentStepNumber"
        @update:model-value="onStepChange"
      >
        <StepperItem
          v-for="(section, index) in sections"
          :key="section"
          class="relative flex w-full flex-col items-center"
          :step="index + 1"
          :completed="isStepCompleted(section)"
          :disabled="!isStepReachable(section)"
        >
          <StepperSeparator
            v-if="index < sections.length - 1"
            class="absolute top-5 right-[calc(-50%+1.25rem)] left-[calc(50%+1.25rem)] h-0.5 rounded-full bg-border group-data-[state=completed]:bg-primary/50"
          />
          <StepperTrigger
            :data-testid="`step-${section}`"
            class="outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
          >
            <StepperIndicator
              class="h-8 w-8 border bg-background text-sm font-semibold text-muted-foreground group-data-[state=completed]:border-primary/40 group-data-[state=completed]:bg-primary/10 group-data-[state=completed]:text-primary"
              :class="
                stepHasProblem(section)
                  ? 'border-destructive/60 bg-destructive/10 text-destructive group-data-[state=active]:bg-destructive group-data-[state=active]:text-destructive-foreground'
                  : ''
              "
            >
              <TriangleAlert v-if="stepHasProblem(section)" class="h-4 w-4" aria-hidden="true" />
              <Check v-else-if="isStepCompleted(section)" class="h-4 w-4" aria-hidden="true" />
              <template v-else>{{ index + 1 }}</template>
            </StepperIndicator>
            <!-- Below sm the words go and the numbers stay; the footer names the step. -->
            <StepperTitle
              class="hidden text-xs sm:block"
              :class="
                section === activeSection
                  ? 'font-semibold text-foreground'
                  : isStepReachable(section)
                    ? 'font-medium text-muted-foreground'
                    : 'font-normal text-muted-foreground/60 italic'
              "
            >
              {{ t(`sharedListWizard.steps.${section}`) }}
            </StepperTitle>
          </StepperTrigger>
        </StepperItem>
      </Stepper>

      <Card data-testid="wizard-step-card">
        <CardHeader>
          <CardTitle
            data-testid="wizard-step-heading"
            tabindex="-1"
            class="flex items-center gap-2 outline-none"
          >
            <component
              :is="stepIcons[activeSection]"
              class="h-5 w-5 text-primary"
              aria-hidden="true"
            />
            {{ t(`sharedListWizard.sections.${activeSection}.title`) }}
          </CardTitle>
          <CardDescription>
            {{ t(`sharedListWizard.sections.${activeSection}.description`) }}
          </CardDescription>
        </CardHeader>

        <CardContent>
          <WizardTasksStep
            v-if="activeSection === 'tasks'"
            v-model:excluded="draft.excluded"
            :event-id="event.id"
            :picked="draft.tasks"
            :shifts-by-task="api.shiftsByTask.value"
            :shifts="loadedShifts"
            :included="included"
            :shifts-loading="api.shiftsLoading.value"
            :shifts-failed="!shiftsReady && !!api.shiftsError.value"
            @pick="pickTask"
            @unpick="unpickTask"
            @retry="retryShifts"
          />
          <WizardSettingsStep
            v-else-if="activeSection === 'settings'"
            v-model:title="titleModel"
            v-model:intro="draft.intro"
            v-model:share-note="draft.shareNote"
            v-model:ask-email="draft.askEmail"
            v-model:ask-phone="draft.askPhone"
            v-model:show-names="draft.showNames"
            v-model:max-per-person="draft.maxPerPerson"
            v-model:ends-mode="draft.endsMode"
            v-model:ends-on="draft.endsOn"
            :saved-show-names="saved?.show_names ?? null"
            :included-count="included.length"
            :max-options="maxOptions"
            :last-shift="lastIncluded"
            :today="today"
          />
          <WizardShareStep
            v-else-if="created"
            v-model:message="message"
            :url="sharedListUrl(created.code)"
            @print="printNotice"
          />
        </CardContent>

        <CardFooter class="flex-col items-stretch gap-3 border-t">
          <p
            v-if="stepBlockedReason"
            id="wizard-step-blocked"
            class="flex items-start gap-2 rounded-lg border border-destructive/50 bg-destructive/5 p-3 text-sm text-destructive"
            data-testid="wizard-step-blocked"
          >
            <TriangleAlert class="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            <span class="min-w-0 flex-1">{{ stepBlockedReason }}</span>
          </p>

          <div
            class="flex flex-col-reverse gap-3 sm:grid sm:grid-cols-[1fr_auto_1fr] sm:items-center sm:gap-4"
          >
            <Button
              v-if="activeSection === 'settings'"
              type="button"
              variant="ghost"
              class="w-full sm:w-auto sm:justify-self-start"
              data-testid="btn-step-back"
              @click="goToSection('tasks')"
            >
              <ArrowLeft class="mr-1.5 h-4 w-4" aria-hidden="true" />
              {{ t('common.actions.previousStep') }}
            </Button>
            <span v-else class="hidden sm:block" />

            <!-- The wizard's live region: reka's own is hard-coded English. -->
            <p
              class="text-center text-xs text-muted-foreground"
              data-testid="wizard-step-position"
              role="status"
              aria-live="polite"
              aria-atomic="true"
            >
              {{
                t('sharedListWizard.stepPosition', {
                  current: currentStepNumber,
                  total: sections.length,
                })
              }}
            </p>

            <div
              class="flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:gap-3 sm:justify-self-end"
            >
              <template v-if="activeSection === 'share'">
                <Button
                  type="button"
                  variant="outline"
                  class="w-full sm:w-auto"
                  data-testid="btn-preview"
                  @click="openPreview"
                >
                  <Eye class="h-4 w-4" aria-hidden="true" />
                  {{ t('sharedListWizard.actions.preview') }}
                </Button>
                <Button
                  type="button"
                  class="w-full sm:w-auto"
                  data-testid="btn-done"
                  @click="leave"
                >
                  {{ t('sharedListWizard.actions.done') }}
                </Button>
              </template>
              <template v-else>
                <Button
                  type="button"
                  variant="outline"
                  class="w-full sm:w-auto"
                  data-testid="btn-cancel"
                  @click="leave"
                >
                  {{ t('common.actions.cancel') }}
                </Button>
                <!-- aria-disabled, not disabled: pressing it says what is missing. -->
                <Button
                  v-if="activeSection === 'tasks'"
                  type="button"
                  class="w-full aria-disabled:opacity-50 sm:w-auto"
                  :aria-disabled="!tasksDone"
                  :aria-describedby="stepBlockedReason ? 'wizard-step-blocked' : undefined"
                  data-testid="btn-step-next"
                  @click="goToSettings"
                >
                  {{ t('common.actions.next') }}
                </Button>
                <Button
                  v-else
                  type="button"
                  class="w-full aria-disabled:opacity-50 sm:w-auto"
                  :aria-disabled="settingsBlocker !== '' || submitting"
                  :aria-describedby="stepBlockedReason ? 'wizard-step-blocked' : undefined"
                  data-testid="btn-submit"
                  @click="submit"
                >
                  {{
                    submitting
                      ? t('common.states.saving')
                      : isEdit
                        ? t('common.actions.save')
                        : t('sharedListWizard.actions.publish')
                  }}
                </Button>
              </template>
            </div>
          </div>
        </CardFooter>
      </Card>
    </div>
  </div>
</template>
