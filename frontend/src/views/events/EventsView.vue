<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { Plus, Search, Trash2 } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { toast } from 'vue-sonner'

import type { EventListResponse, EventRead } from '@/client/types.gen'
import Badge from '@/components/ui/badge/Badge.vue'
import Button from '@/components/ui/button/Button.vue'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
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
import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { useDialog } from '@/composables/useDialog'
import { toastApiError } from '@/lib/api-errors'
import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const router = useRouter()
const authStore = useAuthStore()
const { get, post, delete: del } = useAuthenticatedClient()
const { confirmDestructive } = useDialog()

const events = ref<EventRead[]>([])
const loading = ref(false)
const searchQuery = ref('')
const showCreateDialog = ref(false)

// Create form
const createForm = ref({
  name: '',
  description: '',
  start_date: '',
  end_date: '',
})

const filteredEvents = computed(() => {
  if (!searchQuery.value) return events.value
  const query = searchQuery.value.toLowerCase()
  return events.value.filter(
    (e) =>
      e.name.toLowerCase().includes(query) ||
      e.description?.toLowerCase().includes(query),
  )
})

const statusVariant = (status?: string) => {
  switch (status) {
    case 'published':
      return 'default'
    case 'draft':
      return 'secondary'
    case 'archived':
      return 'outline'
    default:
      return 'secondary'
  }
}

const formatDate = (dateStr: string) => {
  return new Date(dateStr).toLocaleDateString()
}

const loadEvents = async () => {
  loading.value = true
  try {
    const response = await get<{ data: EventListResponse }>({
      url: '/events/',
      query: { limit: 100 },
    })
    events.value = response.data.items
  } catch (error) {
    toastApiError(error)
  } finally {
    loading.value = false
  }
}

const handleCreate = async () => {
  try {
    await post({
      url: '/events/',
      body: {
        name: createForm.value.name,
        description: createForm.value.description || undefined,
        start_date: createForm.value.start_date,
        end_date: createForm.value.end_date,
      },
    })
    showCreateDialog.value = false
    createForm.value = { name: '', description: '', start_date: '', end_date: '' }
    toast.success(t('duties.events.create'))
    await loadEvents()
  } catch (error) {
    toastApiError(error)
  }
}

const handleDelete = async (event: EventRead) => {
  const confirmed = await confirmDestructive(t('duties.events.deleteConfirm'))
  if (!confirmed) return

  try {
    await del({ url: `/events/${event.id}` })
    toast.success(t('duties.events.delete'))
    await loadEvents()
  } catch (error) {
    toastApiError(error)
  }
}

const navigateToEvent = (event: EventRead) => {
  router.push({ name: 'event-detail', params: { eventId: event.id } })
}

onMounted(loadEvents)
</script>

<template>
  <div class="mx-auto max-w-7xl space-y-6">
    <!-- Header -->
    <div class="flex items-start justify-between">
      <div class="space-y-2">
        <h1 class="text-3xl font-bold">{{ t('duties.events.title') }}</h1>
        <p class="text-muted-foreground">{{ t('duties.events.subtitle') }}</p>
      </div>
      <Button v-if="authStore.isAdmin" @click="showCreateDialog = true">
        <Plus class="mr-2 h-4 w-4" />
        {{ t('duties.events.create') }}
      </Button>
    </div>

    <!-- Search -->
    <div class="relative">
      <Search class="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
      <Input
        v-model="searchQuery"
        :placeholder="t('common.actions.search')"
        class="pl-10"
      />
    </div>

    <!-- Loading -->
    <div v-if="loading" class="text-center py-12 text-muted-foreground">
      {{ t('common.states.loading') }}
    </div>

    <!-- Empty -->
    <div
      v-else-if="filteredEvents.length === 0"
      class="text-center py-12 text-muted-foreground"
    >
      {{ t('duties.events.empty') }}
    </div>

    <!-- Event Grid -->
    <div v-else class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
      <Card
        v-for="event in filteredEvents"
        :key="event.id"
        class="cursor-pointer transition-colors hover:bg-muted/50"
        @click="navigateToEvent(event)"
      >
        <CardHeader class="pb-3">
          <div class="flex items-start justify-between">
            <CardTitle class="text-lg">{{ event.name }}</CardTitle>
            <Badge :variant="statusVariant(event.status)">
              {{ t(`duties.events.statuses.${event.status ?? 'draft'}`) }}
            </Badge>
          </div>
          <CardDescription v-if="event.description">
            {{ event.description }}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div class="flex items-center justify-between text-sm text-muted-foreground">
            <span>{{ formatDate(event.start_date) }} - {{ formatDate(event.end_date) }}</span>
            <Button
              v-if="authStore.isAdmin"
              variant="ghost"
              size="icon"
              class="h-8 w-8"
              @click.stop="handleDelete(event)"
            >
              <Trash2 class="h-4 w-4 text-destructive" />
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>

    <!-- Create Event Dialog -->
    <Dialog v-model:open="showCreateDialog">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{{ t('duties.events.create') }}</DialogTitle>
          <DialogDescription>{{ t('duties.events.subtitle') }}</DialogDescription>
        </DialogHeader>
        <form class="space-y-4" @submit.prevent="handleCreate">
          <div class="space-y-2">
            <Label>{{ t('duties.events.fields.name') }}</Label>
            <Input v-model="createForm.name" required />
          </div>
          <div class="space-y-2">
            <Label>{{ t('duties.events.fields.description') }}</Label>
            <Input v-model="createForm.description" />
          </div>
          <div class="grid grid-cols-2 gap-4">
            <div class="space-y-2">
              <Label>{{ t('duties.events.fields.startDate') }}</Label>
              <Input v-model="createForm.start_date" type="date" required />
            </div>
            <div class="space-y-2">
              <Label>{{ t('duties.events.fields.endDate') }}</Label>
              <Input v-model="createForm.end_date" type="date" required />
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
