<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { Loader2 } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import type { FeedTaskItem } from '@/client/types.gen'

import TaskQuickViewCard from './TaskQuickViewCard.vue'

const PAGE_SIZE = 8

const props = defineProps<{
  tasks: FeedTaskItem[]
  focusMode?: 'today' | 'first-available'
  hideFullShifts?: boolean
}>()

const emit = defineEmits<{
  navigate: [task: FeedTaskItem]
  delete: [task: FeedTaskItem]
  clickShift: [slotId: string, task: FeedTaskItem]
  teamJoined: []
}>()

const { t } = useI18n()

const visibleCount = ref(PAGE_SIZE)
const loadingMore = ref(false)
const sentinelRef = ref<HTMLElement | null>(null)
let observer: IntersectionObserver | null = null

const sortedTasks = computed(() => {
  const todayStr = new Date().toISOString().slice(0, 10)
  return [...props.tasks].sort((a, b) => {
    const nextA = a.slot_window_start ?? a.start_date
    const nextB = b.slot_window_start ?? b.start_date
    const diffA = nextA >= todayStr ? 0 : 1
    const diffB = nextB >= todayStr ? 0 : 1
    if (diffA !== diffB) return diffA - diffB
    return nextA.localeCompare(nextB)
  })
})

const visibleTasks = computed(() => {
  return sortedTasks.value.slice(0, visibleCount.value)
})

const hasMore = computed(() => {
  return visibleCount.value < props.tasks.length
})

function loadMoreTasks() {
  if (loadingMore.value || !hasMore.value) return
  loadingMore.value = true
  visibleCount.value = Math.min(visibleCount.value + PAGE_SIZE, props.tasks.length)
  loadingMore.value = false
}

function setupObserver() {
  if (observer) observer.disconnect()
  observer = new IntersectionObserver(
    (entries) => {
      if (entries[0]?.isIntersecting && hasMore.value && !loadingMore.value) {
        loadMoreTasks()
      }
    },
    { rootMargin: '200px' },
  )
  if (sentinelRef.value) observer.observe(sentinelRef.value)
}

watch(
  () => props.tasks,
  async () => {
    visibleCount.value = PAGE_SIZE
    await nextTick()
    setupObserver()
  },
)

onMounted(async () => {
  await nextTick()
  setupObserver()
})

onBeforeUnmount(() => {
  observer?.disconnect()
})
</script>

<template>
  <div v-if="tasks.length === 0" class="py-12 text-center text-muted-foreground">
    {{ t('duties.tasks.empty') }}
  </div>

  <div v-else data-testid="task-list" class="space-y-3">
    <TaskQuickViewCard
      v-for="item in visibleTasks"
      :key="item.id"
      :task="item"
      :visible-days="5"
      :hide-full-shifts="hideFullShifts"
      @navigate="emit('navigate', $event)"
      @delete="emit('delete', $event)"
      @click-shift="(slotId, ev) => emit('clickShift', slotId, ev)"
      @team-joined="emit('teamJoined')"
    />

    <!-- Infinite scroll sentinel -->
    <div v-if="hasMore" ref="sentinelRef" class="flex items-center justify-center py-4">
      <Loader2 v-if="loadingMore" class="h-5 w-5 animate-spin text-muted-foreground" />
    </div>

    <!-- End of list -->
    <p v-else class="py-4 text-center text-xs text-muted-foreground">
      {{ t('duties.tasks.quickView.noMore') }}
    </p>
  </div>
</template>
