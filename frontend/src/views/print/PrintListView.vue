<script setup lang="ts">
/**
 * A shared list's notice: its title and intro, a QR code to its public page,
 * and the shifts it offers, by task and day, with their free places and lines
 * to sign up on paper. The same sheet as a task's (`PrintSheet`).
 *
 * Open to whoever may read the list's details. While the list is not open the
 * toolbar says so and offers the fix instead of printing a code that leads
 * nowhere.
 */
import { computed, onMounted, ref, useTemplateRef } from 'vue'

import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'

import { useSharedListsStore } from '@/stores/sharedLists'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { useFormatters } from '@/composables/useFormatters'
import { usePrintSheet } from '@/composables/usePrintSheet'

import PrintListStatus from '@/components/print/PrintListStatus.vue'
import PrintSheet from '@/components/print/PrintSheet.vue'
import PrintSheetOptions from '@/components/print/PrintSheetOptions.vue'
import PrintToolbar from '@/components/print/PrintToolbar.vue'
import { canManageList } from '@/components/shared-lists/useSharedListActions'

import type { EventRead, SharedListDetail } from '@/client/types.gen'
import type { SheetSection } from '@/lib/print-sheet'
import { lockedForManager, sharedListUrl } from '@/lib/shared-lists'
import { sharedLocationId } from '@/lib/venue-map'

const { t } = useI18n()
const route = useRoute()
const { get } = useAuthenticatedClient()
const { formatDaySpan } = useFormatters()
const store = useSharedListsStore()
const sheet = usePrintSheet()

const listId = computed(() => String(route.params.listId))

const list = ref<SharedListDetail | null>(null)
const event = ref<EventRead | null>(null)
const sections = ref<SheetSection[]>([])
const loading = ref(true)
const sheetEl = useTemplateRef<InstanceType<typeof PrintSheet>>('sheetEl')
const toolbar = useTemplateRef<InstanceType<typeof PrintToolbar>>('toolbar')

const live = computed(() => list.value?.effective_status === 'live')
const locked = computed(() => !!list.value && lockedForManager(list.value, event.value))
const map = computed(() => sheet.mapFor(list.value?.event.id))

const shownSections = computed(() =>
  sections.value
    .map((section) => ({ ...section, shifts: sheet.visible(section.shifts) }))
    .filter((section) => section.shifts.length > 0),
)

/** The list as it is now, one section per task it offers shifts of. False if it cannot be read. */
async function load(): Promise<boolean> {
  try {
    const { list: detail, offered } = await sheet.fetchListSheet(listId.value)
    // The fixes in the toolbar go through the lists store, which reloads by event.
    store.setEvent(detail.event.id)
    const shifts = [...offered.values()].flat()
    const [eventRes] = await Promise.all([
      get<{ data: EventRead }>({ url: `/events/${detail.event.id}` }),
      sheet.loadLocation(shifts.length ? sharedLocationId(shifts, null) : null),
    ])
    const tasks = detail.detail_tasks.filter((task) => offered.has(task.id))
    list.value = detail
    event.value = eventRes.data
    sections.value = tasks.map((task) => ({
      key: task.id,
      heading: tasks.length > 1 ? task.name : null,
      shifts: offered.get(task.id) ?? [],
      batches: [],
      canSeeContacts: canManageList(detail),
    }))
    return true
  } catch {
    list.value = null
    return false
  }
}

const groups = () => sections.value.map((section) => section.shifts)
const taskIds = () => sections.value.map((section) => section.key)

/** After a fix in the toolbar: the list as it is now, the viewer's choices kept, focus on printing. */
async function refreshList() {
  if (await load()) sheet.refresh(groups(), taskIds())
  void toolbar.value?.focusPrint()
}

function print() {
  if (sheetEl.value) void sheet.print([sheetEl.value])
}

onMounted(async () => {
  if (await load()) sheet.reset(groups(), taskIds())
  loading.value = false
})
</script>

<template>
  <div class="print-page mx-auto max-w-5xl w-full space-y-4 p-4 print:p-0">
    <PrintToolbar
      ref="toolbar"
      data-testid="print-toolbar"
      :disabled="loading || sheet.bookingsLoading.value || !live"
      @print="print"
    >
      <PrintListStatus v-if="list" :list="list" :locked="locked" @changed="refreshList" />
      <PrintSheetOptions
        v-if="live"
        v-model:show-title="sheet.showTitle.value"
        v-model:show-location="sheet.showLocation.value"
        v-model:repeat-header="sheet.repeatHeader.value"
        v-model:show-map="sheet.showMap.value"
        v-model:paper-lines="sheet.paperLines.value"
        v-model:selected-dates="sheet.selectedDates.value"
        :include-names="sheet.includeNames.value"
        :dates="sheet.dates.value"
        :has-map="!!sheet.pin.value"
        listed
        :bookings-loading="sheet.bookingsLoading.value"
        @update:include-names="sheet.setIncludeNames"
      />
    </PrintToolbar>

    <p v-if="loading" class="py-12 text-center text-muted-foreground">
      {{ t('common.states.loading') }}
    </p>

    <p
      v-else-if="!list"
      class="py-12 text-center text-muted-foreground"
      data-testid="print-list-missing"
    >
      {{ t('print.list.notFound') }}
    </p>

    <div v-else data-testid="print-content">
      <PrintSheet
        ref="sheetEl"
        :heading="list.title"
        :kicker="list.event.name"
        :text="list.intro"
        :meta="{ days: formatDaySpan(list.event.start_date, list.event.end_date) }"
        :qr="live ? { url: sharedListUrl(list.code), caption: t('print.listQrCaption') } : null"
        :sections="shownSections"
        :options="sheet.options.value"
        :bookings="sheet.bookings.value"
        :map="map"
      />
      <p v-if="!live" class="py-6 text-muted-foreground">{{ t('print.list.notOpen') }}</p>
    </div>
  </div>
</template>
