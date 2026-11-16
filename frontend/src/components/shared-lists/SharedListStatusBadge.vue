<script setup lang="ts">
/**
 * A list's status as a pill: open, paused, expired or ended. An open list's
 * dot pulses gently, and holds still for anyone who asked for less motion.
 */
import { computed } from 'vue'

import { useI18n } from 'vue-i18n'

import { Badge } from '@/components/ui/badge'

import { type EffectiveStatus, effectiveStatusBadge } from '@/lib/shared-lists'

const props = defineProps<{ status: EffectiveStatus }>()

const { t } = useI18n()

const badge = computed(() => effectiveStatusBadge(props.status))
</script>

<template>
  <Badge
    :variant="badge.variant"
    class="gap-1.5 rounded-full font-semibold"
    :class="badge.variant === 'outline' ? 'text-muted-foreground' : ''"
    :data-status="props.status"
    data-testid="shared-list-status"
  >
    <span aria-hidden="true" class="relative inline-flex size-1.5 rounded-full bg-current">
      <span
        v-if="badge.pulse"
        class="absolute inset-0 animate-ping rounded-full bg-current opacity-75 motion-reduce:animate-none"
      />
    </span>
    {{ t(badge.labelKey) }}
  </Badge>
</template>
