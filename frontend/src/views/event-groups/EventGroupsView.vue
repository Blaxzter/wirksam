<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import type { DateValue } from '@internationalized/date'
import { Plus, Search, Trash2 } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { toast } from 'vue-sonner'

import { useAuthStore } from '@/stores/auth'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { useDialog } from '@/composables/useDialog'

import Badge from '@/components/ui/badge/Badge.vue'
import Button from '@/components/ui/button/Button.vue'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { DatePicker } from '@/components/ui/date-picker'
import { DateRangePicker } from '@/components/ui/date-range-picker'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import Input from '@/components/ui/input/Input.vue'
import Label from '@/components/ui/label/Label.vue'
import Textarea from '@/components/ui/textarea/Textarea.vue'

import type { EventGroupListResponse, EventGroupRead } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'
import { formatDate } from '@/lib/format'
import { statusVariant } from '@/lib/status'

const { t } = useI18n()
const router = useRouter()
const authStore = useAuthStore()
const { get, post, delete: del } = useAuthenticatedClient()
const { confirmDestructive } = useDialog()

const groups = ref<EventGroupRead[]>([])
const loading = ref(false)
const searchQuery = ref('')
const showCreateDialog = ref(false)

// Date filter
const dateFrom = ref<string | null>(null)
const dateTo = ref<string | null>(null)
const markedDays = ref<Set<string>>(new Set())

async function handleVisibleMonth(range: { from: string; to: string }) {
  try {
    const res = await get<{ data: string[] }>({
      url: '/events/active-dates',
      query: { date_from: range.from, date_to: range.to },
    })
    markedDays.value = new Set(res.data)
  } catch {
    // Non-critical
  }
}

const createForm = ref({ name: '', description: '' })
const startDate = ref<DateValue>()
const endDate = ref<DateValue>()

const filteredGroups = computed(() => {
  if (!searchQuery.value) return groups.value
  const query = searchQuery.value.toLowerCase()
  return groups.value.filter(
    (g) => g.name.toLowerCase().includes(query) || g.description?.toLowerCase().includes(query),
  )
})

const loadGroups = async () => {
  loading.value = true
  try {
    const query: Record<string, unknown> = { limit: 100 }
    query.date_from = dateFrom.value ?? new Date().toISOString().slice(0, 10)
    if (dateTo.value) query.date_to = dateTo.value

    const response = await get<{ data: EventGroupListResponse }>({
      url: '/event-groups/',
      query,
    })
    groups.value = response.data.items
  } catch (error) {
    toastApiError(error)
  } finally {
    loading.value = false
  }
}

watch([dateFrom, dateTo], () => loadGroups())

const handleCreate = async () => {
  if (!startDate.value || !endDate.value) return
  try {
    await post({
      url: '/event-groups/',
      body: {
        name: createForm.value.name,
        description: createForm.value.description || undefined,
        start_date: startDate.value.toString(),
        end_date: endDate.value.toString(),
      },
    })
    showCreateDialog.value = false
    createForm.value = { name: '', description: '' }
    startDate.value = undefined
    endDate.value = undefined
    toast.success(t('duties.eventGroups.create'))
    await loadGroups()
  } catch (error) {
    toastApiError(error)
  }
}

const handleDelete = async (group: EventGroupRead) => {
  const confirmed = await confirmDestructive(t('duties.eventGroups.deleteConfirm'))
  if (!confirmed) return

  try {
    await del({ url: `/event-groups/${group.id}` })
    toast.success(t('duties.eventGroups.delete'))
    await loadGroups()
  } catch (error) {
    toastApiError(error)
  }
}

const navigateToGroup = (group: EventGroupRead) => {
  router.push({ name: 'event-group-detail', params: { groupId: group.id } })
}

onMounted(loadGroups)
</script>

<template>
  <div class="mx-auto max-w-7xl space-y-6">
    <!-- Header -->
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div class="space-y-2">
        <h1 data-testid="page-heading" class="text-3xl font-bold">{{ t('duties.eventGroups.title') }}</h1>
        <p class="text-muted-foreground">{{ t('duties.eventGroups.subtitle') }}</p>
      </div>
      <Button v-if="authStore.isAdmin" data-testid="btn-create-group" @click="showCreateDialog = true">
        <Plus class="mr-2 h-4 w-4" />
        {{ t('duties.eventGroups.create') }}
      </Button>
    </div>

    <!-- Search & Filter -->
    <div class="flex flex-wrap items-center gap-4">
      <div class="relative flex-1">
        <Search class="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input v-model="searchQuery" data-testid="input-search" :placeholder="t('common.actions.search')" class="pl-10" />
      </div>
      <DateRangePicker
        :date-from="dateFrom"
        :date-to="dateTo"
        :marked-days="markedDays"
        @update:date-from="dateFrom = $event"
        @update:date-to="dateTo = $event"
        @update:visible-month="handleVisibleMonth"
      />
    </div>

    <!-- Loading -->
    <div v-if="loading" class="py-12 text-center text-muted-foreground">
      {{ t('common.states.loading') }}
    </div>

    <template v-else>
      <div v-if="filteredGroups.length === 0" class="py-12 text-center text-muted-foreground">
        {{ t('duties.eventGroups.empty') }}
      </div>

      <div v-else class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <Card
          v-for="group in filteredGroups"
          :key="group.id"
          class="cursor-pointer transition-colors hover:bg-muted/50"
          @click="navigateToGroup(group)"
        >
          <CardHeader class="pb-3">
            <div class="flex items-start justify-between">
              <CardTitle class="text-lg">{{ group.name }}</CardTitle>
              <Badge data-testid="group-status" :variant="statusVariant(group.status)">
                {{ t(`duties.eventGroups.statuses.${group.status ?? 'draft'}`) }}
              </Badge>
            </div>
            <CardDescription v-if="group.description">
              {{ group.description }}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div class="flex items-center justify-between text-sm text-muted-foreground">
              <span>{{ formatDate(group.start_date) }} – {{ formatDate(group.end_date) }}</span>
              <Button
                v-if="authStore.isAdmin"
                variant="ghost"
                size="icon"
                class="h-8 w-8"
                @click.stop="handleDelete(group)"
              >
                <Trash2 class="h-4 w-4 text-destructive" />
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </template>

    <!-- Create Dialog -->
    <Dialog v-model:open="showCreateDialog">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{{ t('duties.eventGroups.create') }}</DialogTitle>
          <DialogDescription>{{ t('duties.eventGroups.subtitle') }}</DialogDescription>
        </DialogHeader>
        <form class="space-y-4" @submit.prevent="handleCreate">
          <div class="space-y-2">
            <Label>{{ t('duties.eventGroups.fields.name') }}</Label>
            <Input v-model="createForm.name" required />
          </div>
          <div class="space-y-2">
            <Label>{{ t('duties.eventGroups.fields.description') }}</Label>
            <Textarea v-model="createForm.description" />
          </div>
          <div class="grid grid-cols-2 gap-4">
            <div class="space-y-2">
              <Label>{{ t('duties.eventGroups.fields.startDate') }}</Label>
              <DatePicker v-model="startDate" :placeholder="t('duties.eventGroups.pickDate')" />
            </div>
            <div class="space-y-2">
              <Label>{{ t('duties.eventGroups.fields.endDate') }}</Label>
              <DatePicker v-model="endDate" :placeholder="t('duties.eventGroups.pickDate')" />
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" @click="showCreateDialog = false">
              {{ t('common.actions.cancel') }}
            </Button>
            <Button type="submit">{{ t('common.actions.create') }}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  </div>
</template>
