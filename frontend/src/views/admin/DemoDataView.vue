<script setup lang="ts">
import { ref } from 'vue'

import { Loader2, PackagePlus, Trash2 } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'

import { toastApiError } from '@/lib/api-errors'

const { t } = useI18n()
const { post, delete: del } = useAuthenticatedClient()

const numEvents = ref(10)
const numEventGroups = ref(3)
const numUsers = ref(5)
const numSlotsPerEvent = ref(4)
const publishEvents = ref(true)

const creating = ref(false)
const deleting = ref(false)

interface DemoDataCreatedResponse {
  data: {
    event_groups_created: number
    events_created: number
    users_created: number
    duty_slots_created: number
    bookings_created: number
  }
}

interface DemoDataDeletedResponse {
  data: {
    events_deleted: number
    event_groups_deleted: number
    users_deleted: number
    duty_slots_deleted: number
    bookings_deleted: number
  }
}

async function handleCreate() {
  creating.value = true
  try {
    const response = await post<DemoDataCreatedResponse>({
      url: '/demo-data/',
      body: {
        num_events: numEvents.value,
        num_event_groups: numEventGroups.value,
        num_users: numUsers.value,
        num_slots_per_event: numSlotsPerEvent.value,
        publish_events: publishEvents.value,
      },
    })
    const d = response.data
    toast.success(
      t('admin.demoData.createSuccess', {
        events: d.events_created,
        groups: d.event_groups_created,
        users: d.users_created,
        slots: d.duty_slots_created,
        bookings: d.bookings_created,
      }),
    )
  } catch (error) {
    toastApiError(error)
  } finally {
    creating.value = false
  }
}

async function handleDelete() {
  deleting.value = true
  try {
    const response = await del<DemoDataDeletedResponse>({
      url: '/demo-data/',
    })
    const d = response.data
    toast.success(
      t('admin.demoData.deleteSuccess', {
        events: d.events_deleted,
        groups: d.event_groups_deleted,
        users: d.users_deleted,
        slots: d.duty_slots_deleted,
        bookings: d.bookings_deleted,
      }),
    )
  } catch (error) {
    toastApiError(error)
  } finally {
    deleting.value = false
  }
}
</script>

<template>
  <div class="space-y-6">
    <div>
      <h1 data-testid="page-heading" class="text-2xl font-bold tracking-tight">{{ t('admin.demoData.title') }}</h1>
      <p class="text-muted-foreground">{{ t('admin.demoData.subtitle') }}</p>
    </div>

    <div class="grid gap-6 md:grid-cols-2">
      <!-- Create Card -->
      <Card>
        <CardHeader>
          <CardTitle>{{ t('admin.demoData.create.title') }}</CardTitle>
          <CardDescription>{{ t('admin.demoData.create.description') }}</CardDescription>
        </CardHeader>
        <CardContent class="space-y-4">
          <div class="grid gap-2">
            <Label for="numEvents">{{ t('admin.demoData.fields.numEvents') }}</Label>
            <Input id="numEvents" v-model.number="numEvents" type="number" :min="1" :max="50" />
          </div>
          <div class="grid gap-2">
            <Label for="numEventGroups">{{ t('admin.demoData.fields.numEventGroups') }}</Label>
            <Input
              id="numEventGroups"
              v-model.number="numEventGroups"
              type="number"
              :min="0"
              :max="10"
            />
          </div>
          <div class="grid gap-2">
            <Label for="numUsers">{{ t('admin.demoData.fields.numUsers') }}</Label>
            <Input id="numUsers" v-model.number="numUsers" type="number" :min="0" :max="20" />
          </div>
          <div class="grid gap-2">
            <Label for="numSlotsPerEvent">{{ t('admin.demoData.fields.numSlotsPerEvent') }}</Label>
            <Input
              id="numSlotsPerEvent"
              v-model.number="numSlotsPerEvent"
              type="number"
              :min="1"
              :max="20"
            />
          </div>
          <div class="flex items-center gap-3">
            <Switch id="publishEvents" v-model:checked="publishEvents" />
            <Label for="publishEvents">{{ t('admin.demoData.fields.publishEvents') }}</Label>
          </div>
        </CardContent>
        <CardFooter>
          <Button data-testid="btn-create-demo" :disabled="creating" @click="handleCreate">
            <Loader2 v-if="creating" class="animate-spin" />
            <PackagePlus v-else />
            {{ t('admin.demoData.create.button') }}
          </Button>
        </CardFooter>
      </Card>

      <!-- Delete Card -->
      <Card>
        <CardHeader>
          <CardTitle>{{ t('admin.demoData.delete.title') }}</CardTitle>
          <CardDescription>{{ t('admin.demoData.delete.description') }}</CardDescription>
        </CardHeader>
        <CardContent>
          <p class="text-sm text-muted-foreground">
            {{ t('admin.demoData.delete.info') }}
          </p>
        </CardContent>
        <CardFooter>
          <Button data-testid="btn-delete-demo" variant="destructive" :disabled="deleting" @click="handleDelete">
            <Loader2 v-if="deleting" class="animate-spin" />
            <Trash2 v-else />
            {{ t('admin.demoData.delete.button') }}
          </Button>
        </CardFooter>
      </Card>
    </div>
  </div>
</template>
