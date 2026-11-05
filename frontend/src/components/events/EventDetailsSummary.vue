<script setup lang="ts">
/**
 * The Details tab for someone who can't change the event: what it is and when,
 * in place of a form whose save the server would refuse.
 */
import { useI18n } from 'vue-i18n'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

import type { EventRead } from '@/client/types.gen'
import { formatDate } from '@/lib/format'
import { timeZoneLabel } from '@/lib/timezones'

defineProps<{
  event: EventRead
}>()

const { t } = useI18n()
</script>

<template>
  <Card data-testid="event-details-summary">
    <CardHeader>
      <CardTitle>{{ t('duties.events.detail.aboutTitle') }}</CardTitle>
      <CardDescription>{{ t('duties.events.detail.aboutHint') }}</CardDescription>
    </CardHeader>
    <CardContent>
      <dl class="space-y-4 text-sm">
        <div v-if="event.description">
          <dt class="font-medium">{{ t('duties.events.fields.description') }}</dt>
          <dd class="mt-1 whitespace-pre-line text-muted-foreground">{{ event.description }}</dd>
        </div>
        <div class="grid grid-cols-2 gap-4">
          <div>
            <dt class="font-medium">{{ t('duties.events.fields.startDate') }}</dt>
            <dd class="mt-1 text-muted-foreground">{{ formatDate(event.start_date) }}</dd>
          </div>
          <div>
            <dt class="font-medium">{{ t('duties.events.fields.endDate') }}</dt>
            <dd class="mt-1 text-muted-foreground">{{ formatDate(event.end_date) }}</dd>
          </div>
        </div>
        <div>
          <dt class="font-medium">{{ t('duties.events.timezone.label') }}</dt>
          <dd class="mt-1 text-muted-foreground">{{ timeZoneLabel(event.timezone) }}</dd>
        </div>
        <div>
          <dt class="font-medium">{{ t('duties.events.fields.visibility') }}</dt>
          <dd class="mt-1 text-muted-foreground">
            {{ t(`duties.events.visibility.${event.visibility ?? 'private'}.label`) }}:
            {{ t(`duties.events.visibility.${event.visibility ?? 'private'}.hint`) }}
          </dd>
        </div>
      </dl>
    </CardContent>
  </Card>
</template>
