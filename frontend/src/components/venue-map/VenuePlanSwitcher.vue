<script setup lang="ts">
import { computed } from 'vue'

import { useI18n } from 'vue-i18n'

import ChipNav from '@/components/utils/ChipNav.vue'

/**
 * Scrollable chips for picking one of an event's venue plans ("Grounds",
 * "Hall, ground floor", …). `v-model` is the selected plan id.
 *
 * Shown as-is even for a single plan — the map view hides it then, the editor
 * does not. The `trailing` slot sits after the chips (the editor's "add plan"
 * button).
 */
const props = defineProps<{
  plans: ReadonlyArray<{ id: string; name: string }>
}>()

const selectedId = defineModel<string | null>({ default: null })

const { t } = useI18n()

const items = computed(() => props.plans.map((plan) => ({ label: plan.name })))

const activeIndex = computed({
  get: () => props.plans.findIndex((plan) => plan.id === selectedId.value),
  set: (index: number) => {
    const plan = props.plans[index]
    if (plan) selectedId.value = plan.id
  },
})
</script>

<template>
  <nav
    class="flex min-w-0 items-center gap-2"
    :aria-label="t('venueMap.planSwitcher.label')"
    data-testid="plan-switcher"
  >
    <ChipNav v-model="activeIndex" :items="items" variant="rounded" class="min-w-0 flex-1" />
    <slot name="trailing" />
  </nav>
</template>
