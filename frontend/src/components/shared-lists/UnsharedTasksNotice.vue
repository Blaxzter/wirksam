<script setup lang="ts">
/**
 * "„Bar“ und „Kasse“ haben 6 freie Plätze, die in keiner offenen Liste
 * stehen": free places nobody without an account can reach right now, with a
 * way to the tasks tab filtered to them.
 */
import { computed } from 'vue'

import { TriangleAlert } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { Button } from '@/components/ui/button'

import { useSharedListText } from '@/components/shared-lists/sharedListText'

import type { UnsharedNotice } from '@/client/types.gen'

const props = defineProps<{ notice: UnsharedNotice }>()

const emit = defineEmits<{ show: [] }>()

const { t } = useI18n()
const { quotedNames } = useSharedListText()

const text = computed(() =>
  t(
    'sharedLists.notice.text',
    {
      names: quotedNames(props.notice.task_names, props.notice.task_count),
      places: t('sharedLists.notice.places', { count: props.notice.free }, props.notice.free),
    },
    props.notice.task_count,
  ),
)
</script>

<template>
  <div
    v-if="props.notice.task_count > 0"
    class="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border border-warning/30 bg-warning/10 px-3 py-2.5 text-sm"
    data-testid="unshared-tasks-notice"
  >
    <TriangleAlert class="size-4 shrink-0 text-warning" aria-hidden="true" />
    <p class="min-w-0 flex-1 basis-60">{{ text }}</p>
    <Button
      variant="link"
      size="sm"
      class="h-auto px-0 text-foreground underline underline-offset-3"
      data-testid="unshared-tasks-show"
      @click="emit('show')"
    >
      {{ t('sharedLists.notice.cta', props.notice.task_count) }}
    </Button>
  </div>
</template>
