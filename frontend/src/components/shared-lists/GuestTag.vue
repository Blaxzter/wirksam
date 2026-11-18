<script setup lang="ts">
/**
 * "No account": marks someone who signed up through a shared list, wherever
 * the people on a shift are listed. They cannot be messaged in the app, only
 * at the address they typed, which only the people running the task see.
 */
import { useI18n } from 'vue-i18n'

import { Badge } from '@/components/ui/badge'

const { t } = useI18n()
</script>

<template>
  <Badge
    variant="outline"
    class="shrink-0 rounded-full font-semibold text-muted-foreground"
    data-testid="guest-tag"
  >
    {{ t('sharedLists.guest.tag') }}
  </Badge>
</template>
