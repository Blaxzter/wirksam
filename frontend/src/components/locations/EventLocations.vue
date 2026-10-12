<script setup lang="ts">
import { ref } from 'vue'

import { MapPin, Pencil, Plus, Trash2 } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { useDialog } from '@/composables/useDialog'
import { invalidateLocations, useLocations } from '@/composables/useLocations'

import Button from '@/components/ui/button/Button.vue'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

import LocationDescription from '@/components/locations/LocationDescription.vue'
import LocationFormDialog from '@/components/locations/LocationFormDialog.vue'

import type { LocationRead } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'

/**
 * The "Locations" tab of the event settings: every place of the event as a
 * card, with add, edit and delete.
 *
 * Deleting a location does not touch the tasks and shifts that use it — they
 * keep its name as plain text — which is what the confirmation says.
 */
const props = defineProps<{ eventId: string }>()

const { t } = useI18n()
const { delete: del } = useAuthenticatedClient()
const { confirmDestructive } = useDialog()

const { locations, loading, error, reload } = useLocations(() => props.eventId)

const formOpen = ref(false)
const editing = ref<LocationRead | null>(null)
const deletingId = ref<string | null>(null)

function openCreate() {
  editing.value = null
  formOpen.value = true
}

function openEdit(location: LocationRead) {
  editing.value = location
  formOpen.value = true
}

async function remove(location: LocationRead) {
  const confirmed = await confirmDestructive({
    title: t('locations.settings.deleteConfirm', { name: location.name }),
    text: t('locations.settings.deleteHint'),
    confirmText: t('locations.settings.delete'),
  })
  if (!confirmed) return
  deletingId.value = location.id
  try {
    await del({ url: `/locations/${location.id}` })
    invalidateLocations(props.eventId)
    toast.success(t('locations.toast.deleted'))
  } catch (error) {
    toastApiError(error)
  } finally {
    deletingId.value = null
  }
}
</script>

<template>
  <Card data-testid="section-event-locations">
    <CardHeader class="flex flex-row flex-wrap items-start justify-between gap-3">
      <div class="min-w-0 space-y-1">
        <CardTitle class="flex items-center gap-2">
          <MapPin class="h-5 w-5 shrink-0" />
          {{ t('locations.settings.title') }}
        </CardTitle>
        <CardDescription>{{ t('locations.settings.description') }}</CardDescription>
      </div>
      <Button data-testid="btn-add-location" @click="openCreate">
        <Plus class="mr-1.5 h-4 w-4" />
        {{ t('locations.settings.add') }}
      </Button>
    </CardHeader>

    <CardContent>
      <div v-if="loading && locations.length === 0" class="space-y-2">
        <Skeleton v-for="i in 3" :key="i" class="h-16 w-full" />
      </div>

      <!-- A failed load is not "no locations": the admin would add them again. -->
      <div
        v-else-if="error && locations.length === 0"
        class="flex flex-col items-center gap-3 rounded-md border border-dashed px-4 py-8 text-center text-sm"
        role="alert"
        data-testid="locations-error"
      >
        <p class="text-muted-foreground max-w-sm">{{ t('locations.settings.loadError') }}</p>
        <Button variant="outline" data-testid="locations-retry" @click="reload">
          {{ t('locations.settings.retry') }}
        </Button>
      </div>

      <div
        v-else-if="locations.length === 0"
        class="text-muted-foreground flex flex-col items-center gap-2 rounded-md border border-dashed px-4 py-8 text-center text-sm"
        data-testid="locations-empty"
      >
        <MapPin class="h-6 w-6" />
        <p class="max-w-sm">{{ t('locations.settings.empty') }}</p>
      </div>

      <ul v-else class="space-y-2">
        <li
          v-for="location in locations"
          :key="location.id"
          class="flex items-start gap-3 rounded-md border px-3 py-2.5"
          :data-testid="`location-row-${location.id}`"
        >
          <div class="min-w-0 flex-1 space-y-1">
            <p class="truncate font-medium">{{ location.name }}</p>
            <LocationDescription
              v-if="location.description || location.address || location.map_url"
              :location="location"
              compact
            />
          </div>
          <div class="flex shrink-0 items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              class="size-8"
              :aria-label="`${t('locations.settings.edit')}: ${location.name}`"
              :data-testid="`btn-edit-location-${location.id}`"
              @click="openEdit(location)"
            >
              <Pencil class="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              class="text-muted-foreground hover:text-destructive size-8"
              :disabled="deletingId === location.id"
              :aria-label="`${t('locations.settings.delete')}: ${location.name}`"
              :data-testid="`btn-delete-location-${location.id}`"
              @click="remove(location)"
            >
              <Trash2 class="h-4 w-4" />
            </Button>
          </div>
        </li>
      </ul>
    </CardContent>

    <LocationFormDialog v-model:open="formOpen" :event-id="eventId" :location="editing" />
  </Card>
</template>
