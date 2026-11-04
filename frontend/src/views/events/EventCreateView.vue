<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import type { DateValue } from '@internationalized/date'
import { CalendarDays, ChevronDown, Clock } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { toast } from 'vue-sonner'

import { useBreadcrumbStore } from '@/stores/breadcrumb'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import EventTimezonePicker from '@/components/events/EventTimezonePicker.vue'
import EventVisibilityPicker from '@/components/events/EventVisibilityPicker.vue'
import Button from '@/components/ui/button/Button.vue'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { DatePicker } from '@/components/ui/date-picker'
import Input from '@/components/ui/input/Input.vue'
import Label from '@/components/ui/label/Label.vue'
import Textarea from '@/components/ui/textarea/Textarea.vue'
import { TimePicker } from '@/components/ui/time-picker'

import type { EventRead } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'
import type { EventVisibility } from '@/lib/event-roles'
import { browserTimeZone } from '@/lib/timezones'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const { post } = useAuthenticatedClient()
const breadcrumbStore = useBreadcrumbStore()

/**
 * Where cancelling — and finishing — lands.
 *
 * The picker is a full-screen flow of its own, so somebody who started there
 * has to end up back there rather than in a management list they have never
 * seen. Everything else came from that list.
 */
const fromPicker = computed(() => route.query.returnTo === 'select-event')
const pickerMode = computed(() => (typeof route.query.mode === 'string' ? route.query.mode : null))
const pickerPath = computed(() =>
  pickerMode.value ? `/app/select-event?mode=${pickerMode.value}` : '/app/select-event',
)

function goBack() {
  if (fromPicker.value) {
    void router.push(pickerPath.value)
    return
  }
  void router.push({ name: 'my-events' })
}

// The header's mobile back arrow follows the breadcrumb trail, so the trail has
// to point at wherever this form was opened from.
onMounted(() => {
  breadcrumbStore.setBreadcrumbs([
    fromPicker.value
      ? {
          title: 'Select an event',
          titleKey: 'duties.selectEvent.pick.title',
          to: pickerPath.value,
        }
      : { title: 'My Events', titleKey: 'admin.events.title', to: { name: 'my-events' } },
    { title: 'Create Event', titleKey: 'duties.events.createView.title' },
  ])
})

const name = ref('')
const description = ref('')
const startDate = ref<DateValue>()
const endDate = ref<DateValue>()
// Whoever creates an event is usually where it happens.
const timezone = ref(browserTimeZone())
// Private by default: an event should not be discoverable until its owner
// decides it should be.
const visibility = ref<EventVisibility>('private')
const startTime = ref('')
const endTime = ref('')
const timesOpen = ref(false)
const submitting = ref(false)

const dayCount = computed(() => {
  if (!startDate.value || !endDate.value) return null
  const start = startDate.value.toDate('UTC').getTime()
  const end = endDate.value.toDate('UTC').getTime()
  if (end < start) return null
  return Math.round((end - start) / 86_400_000) + 1
})

const defaultTimesError = computed<string | null>(() => {
  if (!startTime.value || !endTime.value) return null
  if (endTime.value <= startTime.value) return t('duties.events.fields.defaultTimesInvalid')
  return null
})

const timesSummary = computed(() => {
  if (startTime.value && endTime.value) {
    return t('duties.events.createView.timesSummary', {
      start: startTime.value,
      end: endTime.value,
    })
  }
  return t('duties.events.createView.timesEmpty')
})

const canSubmit = computed(
  () => !!name.value.trim() && !!startDate.value && !!endDate.value && !defaultTimesError.value,
)

async function handleSubmit() {
  if (!canSubmit.value || submitting.value) return
  submitting.value = true
  try {
    const res = await post<{ data: EventRead }>({
      url: '/events/',
      body: {
        name: name.value.trim(),
        description: description.value.trim() || undefined,
        start_date: startDate.value!.toString(),
        end_date: endDate.value!.toString(),
        timezone: timezone.value,
        visibility: visibility.value,
        default_start_time: startTime.value ? `${startTime.value}:00` : undefined,
        default_end_time: endTime.value ? `${endTime.value}:00` : undefined,
        // Published rather than the schema's draft default: somebody who fills
        // in this form wants the event to exist. Drafting stays available from
        // the event's settings.
        status: 'published',
      },
    })
    toast.success(t('duties.events.created'))
    if (fromPicker.value) {
      // `created` tells the picker to stage the new event as the selection, so
      // the person lands back on it already highlighted.
      const query = new URLSearchParams()
      if (pickerMode.value) query.set('mode', pickerMode.value)
      query.set('created', res.data.id)
      void router.replace(`/app/select-event?${query.toString()}`)
    } else {
      void router.replace({ name: 'my-events' })
    }
  } catch (error) {
    toastApiError(error)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="mx-auto max-w-2xl space-y-6 pb-4">
    <div class="space-y-2">
      <h1 data-testid="page-heading" class="text-2xl font-bold tracking-tight sm:text-3xl">
        {{ t('duties.events.createView.title') }}
      </h1>
      <p class="text-muted-foreground">{{ t('duties.events.createView.subtitle') }}</p>
    </div>

    <form class="space-y-4" @submit.prevent="handleSubmit">
      <!-- What it is -->
      <Card>
        <CardHeader>
          <CardTitle>{{ t('duties.events.createView.sections.basics') }}</CardTitle>
          <CardDescription>
            {{ t('duties.events.createView.sections.basicsHint') }}
          </CardDescription>
        </CardHeader>
        <CardContent class="space-y-4">
          <div class="space-y-2">
            <Label for="event-name">{{ t('duties.events.fields.name') }} *</Label>
            <Input
              id="event-name"
              v-model="name"
              data-testid="input-event-name"
              :placeholder="t('duties.events.createView.namePlaceholder')"
              required
            />
          </div>
          <div class="space-y-2">
            <Label for="event-description">{{ t('duties.events.fields.description') }}</Label>
            <Textarea id="event-description" v-model="description" :rows="3" />
            <p class="text-xs text-muted-foreground">
              {{ t('duties.events.createView.descriptionHint') }}
            </p>
          </div>
        </CardContent>
      </Card>

      <!-- When it runs -->
      <Card>
        <CardHeader>
          <CardTitle class="flex items-center gap-2">
            <CalendarDays class="h-4 w-4 text-primary" />
            {{ t('duties.events.createView.sections.dates') }}
          </CardTitle>
          <CardDescription>
            {{ t('duties.events.createView.sections.datesHint') }}
          </CardDescription>
        </CardHeader>
        <CardContent class="space-y-3">
          <!-- Stacked on phones: side by side, each date button truncates its
               own label to an ellipsis on a 400px screen. -->
          <div class="grid gap-4 sm:grid-cols-2">
            <div class="space-y-2" data-testid="picker-start-date">
              <Label>{{ t('duties.events.fields.startDate') }} *</Label>
              <DatePicker
                v-model="startDate"
                :max-value="endDate"
                :placeholder="t('duties.events.pickDate')"
              />
            </div>
            <div class="space-y-2" data-testid="picker-end-date">
              <Label>{{ t('duties.events.fields.endDate') }} *</Label>
              <DatePicker
                v-model="endDate"
                :min-value="startDate"
                :highlight="startDate"
                :placeholder="t('duties.events.pickDate')"
              />
            </div>
          </div>
          <p v-if="dayCount" class="text-xs text-muted-foreground">
            {{ t('duties.events.createView.duration', { days: dayCount }, dayCount) }}
          </p>
          <div class="space-y-2">
            <Label for="event-timezone">{{ t('duties.events.timezone.label') }}</Label>
            <EventTimezonePicker v-model="timezone" input-id="event-timezone" />
            <p class="text-xs text-muted-foreground">
              {{ t('duties.events.timezone.hint') }}
            </p>
          </div>
        </CardContent>
      </Card>

      <!-- Who can see it -->
      <Card>
        <CardHeader>
          <CardTitle>{{ t('duties.events.fields.visibility') }}</CardTitle>
          <CardDescription>
            {{ t('duties.events.createView.sections.visibilityHint') }}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <EventVisibilityPicker v-model="visibility" />
        </CardContent>
      </Card>

      <!-- Folded away by default: most events never set it, and it was the
           bulk of what made the old dialog too tall to use on a phone. -->
      <Card class="py-0">
        <Collapsible v-model:open="timesOpen">
          <CollapsibleTrigger
            class="flex w-full items-center gap-3 p-6 text-left"
            data-testid="btn-toggle-default-times"
          >
            <Clock class="h-4 w-4 shrink-0 text-muted-foreground" />
            <span class="min-w-0 flex-1">
              <span class="block text-sm font-semibold">
                {{ t('duties.events.fields.defaultTimes') }}
                <span class="ml-1 font-normal text-muted-foreground">
                  · {{ t('duties.events.createView.optional') }}
                </span>
              </span>
              <span class="mt-0.5 block truncate text-xs text-muted-foreground">
                {{ timesSummary }}
              </span>
            </span>
            <ChevronDown
              :class="[
                'h-4 w-4 shrink-0 text-muted-foreground transition-transform',
                timesOpen ? 'rotate-180' : '',
              ]"
            />
          </CollapsibleTrigger>
          <CollapsibleContent>
            <div class="space-y-3 px-6 pb-6">
              <div class="grid gap-4 sm:grid-cols-2">
                <div class="space-y-2">
                  <Label class="text-xs text-muted-foreground">
                    {{ t('duties.events.fields.startTime') }}
                  </Label>
                  <TimePicker
                    v-model="startTime"
                    class="w-full"
                    :class="defaultTimesError ? 'border-destructive' : ''"
                    :placeholder="t('duties.events.fields.timeOptional')"
                  />
                </div>
                <div class="space-y-2">
                  <Label class="text-xs text-muted-foreground">
                    {{ t('duties.events.fields.endTime') }}
                  </Label>
                  <TimePicker
                    v-model="endTime"
                    class="w-full"
                    :class="defaultTimesError ? 'border-destructive' : ''"
                    :placeholder="t('duties.events.fields.timeOptional')"
                  />
                </div>
              </div>
              <p v-if="defaultTimesError" class="text-xs text-destructive">
                {{ defaultTimesError }}
              </p>
              <p class="text-xs text-muted-foreground">
                {{ t('duties.events.fields.defaultTimesHint') }}
              </p>
            </div>
          </CollapsibleContent>
        </Collapsible>
      </Card>

      <div
        class="flex flex-col-reverse gap-2 pt-2 sm:flex-row sm:items-center sm:justify-end sm:gap-3"
      >
        <Button
          type="button"
          variant="ghost"
          class="w-full sm:w-auto"
          data-testid="btn-cancel-create-event"
          :disabled="submitting"
          @click="goBack"
        >
          {{ t('common.actions.cancel') }}
        </Button>
        <Button
          type="submit"
          class="w-full sm:w-auto"
          data-testid="btn-submit-create-event"
          :disabled="!canSubmit || submitting"
        >
          {{ submitting ? t('common.states.saving') : t('duties.events.createView.submit') }}
        </Button>
      </div>
    </form>
  </div>
</template>
