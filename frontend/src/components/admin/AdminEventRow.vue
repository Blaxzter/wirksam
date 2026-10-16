<script setup lang="ts">
import { CheckCircle2, Copy, Globe, Lock, Pencil, Star, Trash2, Users } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import Badge from '@/components/ui/badge/Badge.vue'
import Button from '@/components/ui/button/Button.vue'

import HintTooltip from '@/components/utils/HintTooltip.vue'

import type { EventRead } from '@/client/types.gen'
import { roleLabelKey } from '@/lib/event-roles'
import { formatDate } from '@/lib/format'
import { statusVariant } from '@/lib/status'

defineProps<{
  event: EventRead
  selectedEventId: string | null
  muted?: boolean
  /** Only the platform superadmin can curate the home screen. */
  canFeature?: boolean
  featuringId?: string | null
}>()

defineEmits<{
  edit: [event: EventRead]
  clone: [event: EventRead]
  delete: [event: EventRead]
  toggleFeatured: [event: EventRead]
}>()

const { t } = useI18n()
</script>

<template>
  <tr
    data-testid="admin-event-row"
    :data-current="event.id === selectedEventId ? 'true' : undefined"
    :class="[
      muted ? 'text-muted-foreground hover:bg-muted/30' : 'hover:bg-muted/30',
      event.id === selectedEventId ? 'bg-primary/5 border-l-2 border-l-primary' : '',
    ]"
  >
    <td class="px-4 py-2">
      <div class="flex flex-wrap items-center gap-2">
        <span class="font-medium" :class="muted ? 'text-foreground/80' : ''">{{ event.name }}</span>
        <Badge
          v-if="event.id === selectedEventId"
          variant="default"
          class="gap-1"
          data-testid="badge-current-event"
        >
          <CheckCircle2 class="size-3" />
          {{ t('duties.selectEvent.pick.current') }}
        </Badge>
        <Badge v-if="event.my_role" variant="outline">
          {{ t(roleLabelKey(event.my_role)) }}
        </Badge>
      </div>
      <HintTooltip v-if="event.description" :label="event.description">
        <div class="truncate text-xs" :class="muted ? '' : 'text-muted-foreground'">
          {{ event.description }}
        </div>
      </HintTooltip>
    </td>
    <td class="px-4 py-2">{{ formatDate(event.start_date) }}</td>
    <td class="px-4 py-2">{{ formatDate(event.end_date) }}</td>
    <td class="px-4 py-2">
      <div class="flex flex-wrap items-center gap-1.5">
        <Badge :variant="statusVariant(event.status)">
          {{ t(`duties.events.statuses.${event.status ?? 'draft'}`) }}
        </Badge>
        <Badge variant="outline" class="gap-1">
          <component :is="event.visibility === 'public' ? Globe : Lock" class="size-3" />
          {{ t(`duties.events.visibility.${event.visibility}.label`) }}
        </Badge>
      </div>
    </td>
    <td class="px-4 py-2">
      <span class="flex items-center gap-1.5 text-sm text-muted-foreground">
        <Users class="size-3.5" />
        {{ event.member_count ?? 0 }}
      </span>
    </td>
    <td class="px-4 py-2 text-right">
      <div class="flex items-center justify-end gap-0.5">
        <!-- The span takes the hover: a disabled button gets no pointer events.
             It is focusable only while the button is off, so a keyboard user
             can still reach the reason, and then carries it as its name. -->
        <HintTooltip
          v-if="canFeature"
          :label="
            event.visibility !== 'public'
              ? t('duties.events.featured.requiresPublic')
              : event.is_featured
                ? t('duties.events.featured.unfeature', { name: event.name })
                : t('duties.events.featured.feature', { name: event.name })
          "
        >
          <span
            class="inline-flex"
            :tabindex="event.visibility !== 'public' ? 0 : undefined"
            :role="event.visibility !== 'public' ? 'note' : undefined"
            :aria-label="
              event.visibility !== 'public' ? t('duties.events.featured.requiresPublic') : undefined
            "
          >
            <Button
              variant="ghost"
              size="icon"
              class="h-8 w-8"
              data-testid="btn-toggle-featured"
              :disabled="featuringId === event.id || event.visibility !== 'public'"
              :aria-label="
                event.is_featured
                  ? t('duties.events.featured.unfeature', { name: event.name })
                  : t('duties.events.featured.feature', { name: event.name })
              "
              @click="$emit('toggleFeatured', event)"
            >
              <Star
                class="h-4 w-4"
                :class="event.is_featured ? 'fill-amber-400 text-amber-500' : ''"
              />
            </Button>
          </span>
        </HintTooltip>
        <HintTooltip :label="t('admin.events.editEvent', { name: event.name })">
          <Button
            variant="ghost"
            size="icon"
            class="h-8 w-8"
            data-testid="btn-edit-event"
            :aria-label="t('admin.events.editEvent', { name: event.name })"
            @click="$emit('edit', event)"
          >
            <Pencil class="h-4 w-4" />
          </Button>
        </HintTooltip>
        <HintTooltip :label="t('duties.events.clone.rowAction', { name: event.name })">
          <Button
            variant="ghost"
            size="icon"
            class="h-8 w-8"
            data-testid="btn-clone-event-row"
            :aria-label="t('duties.events.clone.rowAction', { name: event.name })"
            @click="$emit('clone', event)"
          >
            <Copy class="h-4 w-4" />
          </Button>
        </HintTooltip>
        <HintTooltip :label="t('admin.events.deleteEvent', { name: event.name })">
          <Button
            variant="ghost"
            size="icon"
            class="h-8 w-8"
            data-testid="btn-delete-event"
            :aria-label="t('admin.events.deleteEvent', { name: event.name })"
            @click="$emit('delete', event)"
          >
            <Trash2 class="h-4 w-4 text-destructive" />
          </Button>
        </HintTooltip>
      </div>
    </td>
  </tr>
</template>
