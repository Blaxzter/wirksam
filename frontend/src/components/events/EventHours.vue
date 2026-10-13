<script setup lang="ts">
import { computed, ref } from 'vue'

import { AlertTriangle, Clock, Download, Plus } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { useDialog } from '@/composables/useDialog'

import Button from '@/components/ui/button/Button.vue'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  ResponsiveDialog,
  ResponsiveDialogBody,
  ResponsiveDialogContent,
  ResponsiveDialogDescription,
  ResponsiveDialogFooter,
  ResponsiveDialogHeader,
  ResponsiveDialogTitle,
} from '@/components/ui/responsive-dialog'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

import HoursBreakdown from '@/components/events/HoursBreakdown.vue'
import WorkLogFormDialog from '@/components/events/WorkLogFormDialog.vue'

import type {
  EventMemberRead,
  VolunteerHours,
  VolunteerHoursDetail,
  WorkLogRead,
} from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'
import { formatHours } from '@/lib/format'

const props = defineProps<{
  eventId: string
  hours: VolunteerHours[]
  members: EventMemberRead[]
}>()

const emit = defineEmits<{ updated: [] }>()

const { t } = useI18n()
const { get, delete: del } = useAuthenticatedClient()
const { confirmDestructive } = useDialog()

const hoursLabel = (minutes: number) => t('duties.hours.unit', { value: formatHours(minutes) })
const displayName = (h: VolunteerHours) => h.name ?? h.email ?? '?'

/** Members with nothing yet stay listed in the members card; here they are noise. */
const rows = computed(() =>
  props.hours.filter((h) => h.total_minutes > 0 || h.shift_count > 0 || h.upcoming_shift_count > 0),
)

const untimedCount = computed(() => props.hours.reduce((n, h) => n + h.untimed_shift_count, 0))

// --- Export ---

const exporting = ref(false)

async function exportCsv() {
  exporting.value = true
  try {
    const response = await get<{ data: string }>({ url: `/events/${props.eventId}/hours/export` })
    const blob = new Blob([response.data], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'worked-hours.csv'
    a.click()
    URL.revokeObjectURL(url)
  } catch (error) {
    toastApiError(error)
  } finally {
    exporting.value = false
  }
}

// --- Detail dialog ---

const detailOpen = ref(false)
const detail = ref<VolunteerHoursDetail | null>(null)

async function loadDetail(userId: string) {
  try {
    const res = await get<{ data: VolunteerHoursDetail }>({
      url: `/events/${props.eventId}/hours/${userId}`,
    })
    detail.value = res.data
  } catch (error) {
    toastApiError(error)
  }
}

async function openDetail(row: VolunteerHours) {
  detail.value = null
  detailOpen.value = true
  await loadDetail(row.user_id)
}

// --- Entry form ---

const formOpen = ref(false)
const formUserId = ref<string | null>(null)
const formEntry = ref<WorkLogRead | null>(null)

function addEntry(userId: string | null = null) {
  formUserId.value = userId
  formEntry.value = null
  formOpen.value = true
}

function editEntry(entry: WorkLogRead) {
  formUserId.value = entry.user_id
  formEntry.value = entry
  formOpen.value = true
}

async function deleteEntry(entry: WorkLogRead) {
  if (!(await confirmDestructive(t('duties.hours.detail.deleteConfirm')))) return
  try {
    await del({ url: `/events/${props.eventId}/work-logs/${entry.id}` })
    toast.success(t('duties.hours.detail.deleted'))
    await afterChange()
  } catch (error) {
    toastApiError(error)
  }
}

async function afterChange() {
  emit('updated')
  if (detailOpen.value && detail.value) await loadDetail(detail.value.summary.user_id)
}
</script>

<template>
  <Card data-testid="section-event-hours">
    <CardHeader>
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div class="space-y-1">
          <CardTitle class="flex items-center gap-2">
            <Clock class="h-5 w-5 shrink-0" />
            {{ t('duties.hours.event.title') }}
          </CardTitle>
          <CardDescription>{{ t('duties.hours.event.subtitle') }}</CardDescription>
        </div>
        <div class="flex shrink-0 gap-2">
          <Button
            variant="outline"
            size="sm"
            data-testid="btn-export-hours"
            :disabled="exporting"
            @click="exportCsv"
          >
            <Download class="mr-1.5 h-4 w-4" />
            {{ t('duties.hours.event.export') }}
          </Button>
          <Button size="sm" data-testid="btn-add-hours" @click="addEntry()">
            <Plus class="mr-1.5 h-4 w-4" />
            {{ t('duties.hours.event.add') }}
          </Button>
        </div>
      </div>
    </CardHeader>

    <CardContent class="space-y-3">
      <p v-if="rows.length === 0" class="text-sm text-muted-foreground">
        {{ t('duties.hours.event.empty') }}
      </p>

      <Table v-else>
        <TableHeader>
          <TableRow>
            <TableHead>{{ t('duties.hours.event.volunteer') }}</TableHead>
            <TableHead class="text-right">{{ t('duties.hours.event.shifts') }}</TableHead>
            <TableHead class="hidden text-right sm:table-cell">
              {{ t('duties.hours.event.shiftHours') }}
            </TableHead>
            <TableHead class="hidden text-right sm:table-cell">
              {{ t('duties.hours.event.manual') }}
            </TableHead>
            <TableHead class="text-right">{{ t('duties.hours.event.total') }}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow
            v-for="row in rows"
            :key="row.user_id"
            class="cursor-pointer"
            data-testid="event-hours-row"
            tabindex="0"
            :aria-label="t('duties.hours.event.openDetails', { name: displayName(row) })"
            @click="openDetail(row)"
            @keydown.enter="openDetail(row)"
          >
            <TableCell>
              <p class="font-medium">{{ displayName(row) }}</p>
              <p v-if="!row.role" class="text-xs text-muted-foreground">
                {{ t('duties.hours.event.formerMember') }}
              </p>
            </TableCell>
            <TableCell class="text-right tabular-nums">{{ row.shift_count }}</TableCell>
            <TableCell class="hidden text-right tabular-nums sm:table-cell">
              {{ hoursLabel(row.shift_minutes) }}
            </TableCell>
            <TableCell class="hidden text-right tabular-nums sm:table-cell">
              {{ hoursLabel(row.manual_minutes) }}
            </TableCell>
            <TableCell class="text-right font-semibold tabular-nums">
              {{ hoursLabel(row.total_minutes) }}
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>

      <p v-if="untimedCount > 0" class="flex items-center gap-1.5 text-xs text-muted-foreground">
        <AlertTriangle class="h-3.5 w-3.5 shrink-0" />
        {{ t('duties.hours.event.untimed', { count: untimedCount }, untimedCount) }}
      </p>
    </CardContent>
  </Card>

  <ResponsiveDialog v-model:open="detailOpen">
    <ResponsiveDialogContent dialog-class="sm:max-w-lg">
      <ResponsiveDialogHeader>
        <ResponsiveDialogTitle>
          {{ t('duties.hours.detail.title', { name: detail ? displayName(detail.summary) : '' }) }}
        </ResponsiveDialogTitle>
        <ResponsiveDialogDescription v-if="detail" class="text-left">
          {{
            t('duties.hours.detail.description', {
              total: hoursLabel(detail.summary.total_minutes),
              shifts: hoursLabel(detail.summary.shift_minutes),
              manual: hoursLabel(detail.summary.manual_minutes),
            })
          }}
        </ResponsiveDialogDescription>
      </ResponsiveDialogHeader>

      <ResponsiveDialogBody class="max-h-[60vh] overflow-y-auto pb-2">
        <div v-if="!detail" class="py-6 text-center text-sm text-muted-foreground">
          {{ t('common.states.loading') }}
        </div>
        <HoursBreakdown v-else :detail="detail" can-edit @edit="editEntry" @delete="deleteEntry" />
      </ResponsiveDialogBody>

      <ResponsiveDialogFooter v-if="detail?.summary.role" class="sm:justify-start">
        <Button size="sm" @click="addEntry(detail.summary.user_id)">
          <Plus class="mr-1.5 h-4 w-4" />
          {{ t('duties.hours.event.add') }}
        </Button>
      </ResponsiveDialogFooter>
    </ResponsiveDialogContent>
  </ResponsiveDialog>

  <WorkLogFormDialog
    v-model:open="formOpen"
    :event-id="eventId"
    :members="members"
    :user-id="formUserId"
    :entry="formEntry"
    @saved="afterChange"
  />
</template>
