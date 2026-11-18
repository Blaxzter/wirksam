<script setup lang="ts">
/**
 * The search box above a server-paginated table.
 *
 * It reports what was typed once the typing pauses (`debounce` ms), so a
 * request goes out per search rather than per key; Enter and the clear button
 * report at once. A value set from outside (a link that clears the search)
 * replaces what is in the box.
 */
import { ref, watch } from 'vue'

import { Search, X } from '@lucide/vue'
import { useDebounceFn } from '@vueuse/core'
import { useI18n } from 'vue-i18n'

import { MAX_SEARCH_LENGTH } from '@/composables/useTableQuery'

import { Input } from '@/components/ui/input'

const props = withDefaults(
  defineProps<{
    /** The search the table runs, as committed. */
    modelValue: string
    /** Names the field for a screen reader; there is no visible label. */
    label: string
    placeholder?: string
    debounce?: number
  }>(),
  { placeholder: undefined, debounce: 300 },
)

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const { t } = useI18n()

const draft = ref(props.modelValue)

watch(
  () => props.modelValue,
  (value) => {
    if (value !== draft.value.trim()) draft.value = value
  },
)

function commit() {
  const value = draft.value.trim()
  if (value !== props.modelValue) emit('update:modelValue', value)
}

const commitLater = useDebounceFn(commit, () => props.debounce)

function onInput(value: string | number) {
  draft.value = String(value)
  void commitLater()
}

function clear() {
  draft.value = ''
  commit()
}
</script>

<template>
  <div class="relative w-full min-w-0">
    <Search
      class="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
      aria-hidden="true"
    />
    <Input
      :model-value="draft"
      type="search"
      :aria-label="props.label"
      :placeholder="props.placeholder"
      :maxlength="MAX_SEARCH_LENGTH"
      enterkeyhint="search"
      class="h-11 pr-10 pl-9 sm:h-9 [&::-webkit-search-cancel-button]:appearance-none"
      @update:model-value="onInput"
      @keydown.enter.prevent="commit"
    />
    <button
      v-if="draft"
      type="button"
      class="absolute top-1/2 right-1 flex size-9 -translate-y-1/2 items-center justify-center rounded-md text-muted-foreground outline-none hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50 sm:size-7"
      :aria-label="t('common.actions.reset')"
      data-testid="search-clear"
      @click="clear"
    >
      <X class="size-4" aria-hidden="true" />
    </button>
  </div>
</template>
