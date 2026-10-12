<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { invalidateLocations } from '@/composables/useLocations'

import Button from '@/components/ui/button/Button.vue'
import Input from '@/components/ui/input/Input.vue'
import Label from '@/components/ui/label/Label.vue'
import {
  ResponsiveDialog,
  ResponsiveDialogBody,
  ResponsiveDialogContent,
  ResponsiveDialogFooter,
  ResponsiveDialogHeader,
  ResponsiveDialogTitle,
} from '@/components/ui/responsive-dialog'
import Textarea from '@/components/ui/textarea/Textarea.vue'

import type { LocationCreate, LocationRead } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'

/**
 * Create or edit one location of an event.
 *
 * Without `location` it creates (`POST /events/{id}/locations`), with one it
 * edits (`PATCH /locations/{id}`). Either way the shared location list is
 * invalidated so every picker, filter and map on screen picks up the change,
 * and the saved row is emitted for callers that want to select it.
 *
 * `priority` stacks the dialog above another open one — the picker inside the
 * task page's "create shift" dialog opens this on top of it.
 */
const props = withDefaults(
  defineProps<{
    open: boolean
    eventId: string
    location?: LocationRead | null
    /** Prefills the name when creating, e.g. from what was typed in the picker. */
    initialName?: string
    priority?: boolean
  }>(),
  { location: null, initialName: '', priority: false },
)

const emit = defineEmits<{
  'update:open': [value: boolean]
  saved: [location: LocationRead]
}>()

const { t } = useI18n()
const { post, patch } = useAuthenticatedClient()

const name = ref('')
const description = ref('')
const address = ref('')
const mapUrl = ref('')
const contact = ref('')
const saving = ref(false)

const isEdit = computed(() => !!props.location)

watch(
  () => props.open,
  (open) => {
    if (!open) return
    const loc = props.location
    name.value = loc?.name ?? props.initialName
    description.value = loc?.description ?? ''
    address.value = loc?.address ?? ''
    mapUrl.value = loc?.map_url ?? ''
    contact.value = loc?.contact ?? ''
  },
  { immediate: true },
)

// The API refuses anything but http(s); saying so here beats a server error.
const mapUrlInvalid = computed(() => {
  const url = mapUrl.value.trim()
  return url !== '' && !/^https?:\/\/\S+$/i.test(url)
})

const isValid = computed(() => name.value.trim().length > 0 && !mapUrlInvalid.value)

function body(): LocationCreate {
  // Empty optional fields go out as null so an edit can clear them.
  const orNull = (v: string) => v.trim() || null
  return {
    name: name.value.trim(),
    description: orNull(description.value),
    address: orNull(address.value),
    map_url: orNull(mapUrl.value),
    contact: orNull(contact.value),
  }
}

async function save() {
  if (!isValid.value || saving.value) return
  saving.value = true
  try {
    const res = props.location
      ? await patch<{ data: LocationRead }>({
          url: `/locations/${props.location.id}`,
          body: body(),
        })
      : await post<{ data: LocationRead }>({
          url: `/events/${props.eventId}/locations`,
          body: body(),
        })
    invalidateLocations(props.eventId)
    toast.success(t(isEdit.value ? 'locations.toast.updated' : 'locations.toast.created'))
    emit('saved', res.data)
    emit('update:open', false)
  } catch (error) {
    toastApiError(error)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <ResponsiveDialog :open="props.open" @update:open="emit('update:open', $event)">
    <ResponsiveDialogContent :priority="priority" data-testid="location-form-dialog">
      <ResponsiveDialogHeader>
        <ResponsiveDialogTitle>
          {{ isEdit ? t('locations.form.titleEdit') : t('locations.form.titleCreate') }}
        </ResponsiveDialogTitle>
      </ResponsiveDialogHeader>
      <ResponsiveDialogBody>
        <form id="location-form" class="space-y-4 pb-2" @submit.prevent="save">
          <div class="space-y-2">
            <Label for="location-name">{{ t('locations.form.name') }}</Label>
            <Input
              id="location-name"
              v-model="name"
              maxlength="120"
              required
              :placeholder="t('locations.form.namePlaceholder')"
              data-testid="location-form-name"
            />
          </div>
          <div class="space-y-2">
            <Label for="location-description">{{ t('locations.form.description') }}</Label>
            <Textarea
              id="location-description"
              v-model="description"
              rows="4"
              maxlength="10000"
              aria-describedby="location-description-hint"
              data-testid="location-form-description"
            />
            <p id="location-description-hint" class="text-muted-foreground text-xs">
              {{ t('locations.form.descriptionHint') }}
            </p>
          </div>
          <div class="space-y-2">
            <Label for="location-address">{{ t('locations.form.address') }}</Label>
            <Input
              id="location-address"
              v-model="address"
              maxlength="255"
              :placeholder="t('locations.form.addressPlaceholder')"
              data-testid="location-form-address"
            />
          </div>
          <div class="space-y-2">
            <Label for="location-map-url">{{ t('locations.form.mapUrl') }}</Label>
            <Input
              id="location-map-url"
              v-model="mapUrl"
              type="url"
              inputmode="url"
              maxlength="2048"
              placeholder="https://"
              :aria-invalid="mapUrlInvalid || undefined"
              aria-describedby="location-map-url-hint"
              data-testid="location-form-map-url"
            />
            <p
              id="location-map-url-hint"
              class="text-xs"
              :class="mapUrlInvalid ? 'text-destructive' : 'text-muted-foreground'"
            >
              {{
                mapUrlInvalid ? t('locations.form.mapUrlInvalid') : t('locations.form.mapUrlHint')
              }}
            </p>
          </div>
          <div class="space-y-2">
            <Label for="location-contact">{{ t('locations.form.contact') }}</Label>
            <Input
              id="location-contact"
              v-model="contact"
              maxlength="255"
              :placeholder="t('locations.form.contactPlaceholder')"
              data-testid="location-form-contact"
            />
          </div>
        </form>
      </ResponsiveDialogBody>
      <ResponsiveDialogFooter>
        <Button variant="outline" @click="emit('update:open', false)">
          {{ t('common.actions.cancel') }}
        </Button>
        <Button
          type="submit"
          form="location-form"
          :disabled="!isValid || saving"
          data-testid="location-form-save"
        >
          {{ t('locations.form.save') }}
        </Button>
      </ResponsiveDialogFooter>
    </ResponsiveDialogContent>
  </ResponsiveDialog>
</template>
