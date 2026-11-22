<script setup lang="ts">
import { computed, ref } from 'vue'

import { ImageUp, LoaderIcon, Palette, Trash2 } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'

import { useAuthStore } from '@/stores/auth'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'

import EventColourPicker from '@/components/events/EventColourPicker.vue'
import EventLogo from '@/components/events/EventLogo.vue'

import type { EventRead } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'
import type { ColourKind } from '@/lib/custom-colour'
import { hasDarkTile } from '@/lib/event-appearance'

/**
 * The event's look, for its admins: a logo (with an optional version for
 * dark mode), two of the preset colours and a base tone. Each saves at once,
 * like a profile picture: there is nothing to half-fill here, and a colour
 * shows on the whole page the moment it lands.
 */
const props = defineProps<{
  event: EventRead
}>()

const emit = defineEmits<{
  updated: [event: EventRead]
}>()

const { t } = useI18n()
const authStore = useAuthStore()
const { getAuthToken, patch, delete: del } = useAuthenticatedClient()

const ACCEPT = 'image/png,image/jpeg,image/webp,image/gif'

type Variant = 'light' | 'dark'
/** Where each logo lives, and the copy for each, under `appearance.logo`. */
const LOGO = {
  light: { path: 'logo', copy: 'duties.events.appearance.logo' },
  dark: { path: 'logo/dark', copy: 'duties.events.appearance.logo.dark' },
} as const

const fileInput = ref<HTMLInputElement | null>(null)
const darkFileInput = ref<HTMLInputElement | null>(null)
const uploading = ref<Variant | null>(null)
const removing = ref<Variant | null>(null)
const savingColour = ref<ColourKind | null>(null)
const savingTile = ref(false)

const hasLogo = computed(() => !!props.event.logo_etag)
const hasDarkLogo = computed(() => !!props.event.logo_dark_etag)
const uploadBlocked = computed(() => !!props.event.is_sandbox || !!authStore.profile?.is_sandbox)

function applied(updated: EventRead) {
  emit('updated', updated)
  // The open event wears the new look straight away.
  void authStore.refreshSelectedEvent(updated.id)
}

/**
 * Raw `fetch` (the generated client does not do multipart) answers with a
 * plain Response; shape a failure like an axios error so `toastApiError`
 * translates the problem `code` the same way as for every other request.
 */
async function responseError(response: Response) {
  const data: unknown = await response.json().catch(() => null)
  return Object.assign(new Error(`Upload failed: ${response.status}`), {
    isAxiosError: true,
    response: { status: response.status, data },
  })
}

async function upload(file: File, variant: Variant) {
  if (uploading.value) return
  uploading.value = variant
  try {
    const formData = new FormData()
    formData.append('file', file, file.name)
    const token = await getAuthToken()
    const response = await fetch(
      `${import.meta.env.VITE_API_URL}/events/${props.event.id}/${LOGO[variant].path}`,
      { method: 'PUT', headers: { Authorization: `Bearer ${token}` }, body: formData },
    )
    if (!response.ok) throw await responseError(response)
    applied((await response.json()) as EventRead)
    toast.success(t(`${LOGO[variant].copy}.uploaded`))
  } catch (error) {
    toastApiError(error)
  } finally {
    uploading.value = null
    const input = variant === 'light' ? fileInput.value : darkFileInput.value
    if (input) input.value = ''
  }
}

function onFileSelected(e: Event, variant: Variant) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) void upload(file, variant)
}

async function removeLogo(variant: Variant) {
  removing.value = variant
  try {
    const res = await del<{ data: EventRead }>({
      url: `/events/${props.event.id}/${LOGO[variant].path}`,
    })
    applied(res.data)
    toast.success(t(`${LOGO[variant].copy}.removed`))
  } catch (error) {
    toastApiError(error)
  } finally {
    removing.value = null
  }
}

async function setTile(value: boolean) {
  savingTile.value = true
  try {
    const res = await patch<{ data: EventRead }>({
      url: `/events/${props.event.id}`,
      body: { logo_dark_tile: value },
    })
    applied(res.data)
  } catch (error) {
    toastApiError(error)
  } finally {
    savingTile.value = false
  }
}

const KINDS = ['primary', 'secondary', 'base'] as const
const FIELD = {
  primary: 'primary_color',
  secondary: 'secondary_color',
  base: 'base_color',
} as const

async function pickColour(kind: ColourKind, next: string | null) {
  const field = FIELD[kind]
  if (next === (props.event[field] ?? null) || savingColour.value) return
  savingColour.value = kind
  try {
    const res = await patch<{ data: EventRead }>({
      url: `/events/${props.event.id}`,
      body: { [field]: next },
    })
    applied(res.data)
  } catch (error) {
    toastApiError(error)
  } finally {
    savingColour.value = null
  }
}
</script>

<template>
  <Card data-testid="event-appearance">
    <CardHeader>
      <CardTitle class="flex items-center gap-2">
        <Palette class="size-5" />
        {{ t('duties.events.appearance.title') }}
      </CardTitle>
      <CardDescription>{{ t('duties.events.appearance.description') }}</CardDescription>
    </CardHeader>
    <CardContent class="space-y-6">
      <section class="space-y-3">
        <h3 class="text-sm font-medium">{{ t('duties.events.appearance.logo.title') }}</h3>
        <div class="flex flex-wrap items-center gap-4">
          <EventLogo :event="event" size="xl" data-testid="event-appearance-logo-preview" />
          <div class="flex flex-wrap gap-2">
            <input
              ref="fileInput"
              type="file"
              :accept="ACCEPT"
              class="hidden"
              data-testid="event-logo-input"
              @change="onFileSelected($event, 'light')"
            />
            <Button
              variant="outline"
              :disabled="!!uploading || uploadBlocked"
              data-testid="btn-event-logo-upload"
              @click="fileInput?.click()"
            >
              <LoaderIcon v-if="uploading === 'light'" class="animate-spin" />
              <ImageUp v-else />
              {{
                hasLogo
                  ? t('duties.events.appearance.logo.replace')
                  : t('duties.events.appearance.logo.upload')
              }}
            </Button>
            <Button
              v-if="hasLogo"
              variant="ghost"
              :disabled="!!removing"
              data-testid="btn-event-logo-remove"
              @click="removeLogo('light')"
            >
              <LoaderIcon v-if="removing === 'light'" class="animate-spin" />
              <Trash2 v-else />
              {{ t('duties.events.appearance.logo.remove') }}
            </Button>
          </div>
        </div>
        <p class="text-xs text-muted-foreground">
          {{
            uploadBlocked
              ? t('duties.events.appearance.logo.sandbox')
              : t('duties.events.appearance.logo.hint')
          }}
        </p>

        <!-- Dark mode: its own version of the logo, and whether it sits on white. -->
        <div
          v-if="hasLogo"
          class="space-y-4 rounded-lg border p-4"
          data-testid="event-logo-dark-section"
        >
          <div>
            <h4 class="text-sm font-medium">
              {{ t('duties.events.appearance.logo.dark.title') }}
            </h4>
            <p class="text-xs text-muted-foreground">
              {{ t('duties.events.appearance.logo.dark.hint') }}
            </p>
          </div>
          <div class="flex flex-wrap items-center gap-4">
            <!-- How it looks in dark mode, whichever mode this page is in. -->
            <div
              class="dark flex flex-col items-start gap-2 rounded-lg bg-sidebar p-3 text-sidebar-foreground"
              data-testid="event-logo-dark-preview"
            >
              <span class="text-xs">{{ t('duties.events.appearance.logo.dark.preview') }}</span>
              <EventLogo :event="event" size="xl" />
            </div>
            <div class="flex flex-wrap gap-2">
              <input
                ref="darkFileInput"
                type="file"
                :accept="ACCEPT"
                class="hidden"
                data-testid="event-logo-dark-input"
                @change="onFileSelected($event, 'dark')"
              />
              <Button
                variant="outline"
                :disabled="!!uploading || uploadBlocked"
                data-testid="btn-event-logo-dark-upload"
                @click="darkFileInput?.click()"
              >
                <LoaderIcon v-if="uploading === 'dark'" class="animate-spin" />
                <ImageUp v-else />
                {{
                  hasDarkLogo
                    ? t('duties.events.appearance.logo.dark.replace')
                    : t('duties.events.appearance.logo.dark.upload')
                }}
              </Button>
              <Button
                v-if="hasDarkLogo"
                variant="ghost"
                :disabled="!!removing"
                data-testid="btn-event-logo-dark-remove"
                @click="removeLogo('dark')"
              >
                <LoaderIcon v-if="removing === 'dark'" class="animate-spin" />
                <Trash2 v-else />
                {{ t('duties.events.appearance.logo.dark.remove') }}
              </Button>
            </div>
          </div>
          <div class="flex items-start justify-between gap-4">
            <div class="space-y-1">
              <Label for="event-logo-dark-tile">
                {{ t('duties.events.appearance.logo.dark.tile') }}
              </Label>
              <p id="event-logo-dark-tile-hint" class="text-xs text-muted-foreground">
                {{ t('duties.events.appearance.logo.dark.tileHint') }}
              </p>
            </div>
            <Switch
              id="event-logo-dark-tile"
              :model-value="hasDarkTile(event)"
              :disabled="savingTile"
              aria-describedby="event-logo-dark-tile-hint"
              class="mt-0.5"
              data-testid="switch-event-logo-dark-tile"
              @update:model-value="(v: boolean) => setTile(v)"
            />
          </div>
        </div>
      </section>

      <EventColourPicker
        v-for="kind in KINDS"
        :key="kind"
        :kind="kind"
        :model-value="event[FIELD[kind]]"
        :primary="event.primary_color"
        :disabled="savingColour !== null"
        @update:model-value="(value) => pickColour(kind, value)"
      />
      <p class="text-xs text-muted-foreground">{{ t('duties.events.appearance.colour.hint') }}</p>
    </CardContent>
  </Card>
</template>
