<script setup lang="ts">
import { computed } from 'vue'

import { ChevronDown } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

import ChipNav from '@/components/utils/ChipNav.vue'

/**
 * Scrollable chips for picking one of an event's venue plans ("Grounds",
 * "Hall, ground floor", …). `v-model` is the selected plan id.
 *
 * Shown as-is even for a single plan — the map view hides it then, the editor
 * does not. The `trailing` slot sits after the chips (the editor's "add plan"
 * button).
 *
 * `compact` (the editor): below the `lg` breakpoint the chips give way to one
 * button with the plan's name and a menu of all plans, since chips cut off at
 * phone width. `hideMenu` leaves that button out, for when the page shows it
 * somewhere else (the embedded editor puts it in the page header).
 */
const props = withDefaults(
  defineProps<{
    plans: ReadonlyArray<{ id: string; name: string }>
    compact?: boolean
    hideMenu?: boolean
  }>(),
  { compact: false, hideMenu: false },
)

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

const selectedName = computed(
  () => props.plans.find((plan) => plan.id === selectedId.value)?.name ?? '',
)

const menuValue = computed({
  get: () => selectedId.value ?? '',
  set: (id: string) => {
    if (id) selectedId.value = id
  },
})
</script>

<template>
  <nav
    class="flex min-w-0 items-center gap-2"
    :aria-label="t('venueMap.planSwitcher.label')"
    data-testid="plan-switcher"
  >
    <ChipNav
      v-model="activeIndex"
      :items="items"
      variant="rounded"
      class="min-w-0 flex-1"
      :class="compact ? 'max-lg:hidden' : ''"
    />
    <DropdownMenu v-if="compact && !hideMenu">
      <DropdownMenuTrigger as-child>
        <Button
          variant="outline"
          class="min-w-0 flex-1 justify-between gap-1 lg:hidden"
          :aria-label="`${t('venueMap.planSwitcher.label')}: ${selectedName}`"
          data-testid="plan-switcher-menu"
        >
          <span class="min-w-0 truncate">{{ selectedName }}</span>
          <ChevronDown class="opacity-60" aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="start"
        class="max-w-[min(20rem,calc(100vw-2rem))] min-w-(--reka-dropdown-menu-trigger-width)"
      >
        <DropdownMenuRadioGroup v-model="menuValue">
          <DropdownMenuRadioItem
            v-for="plan in plans"
            :key="plan.id"
            :value="plan.id"
            class="py-2.5"
            :data-testid="`plan-switcher-option-${plan.id}`"
          >
            <span class="min-w-0 truncate">{{ plan.name }}</span>
          </DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
    <slot name="trailing" />
  </nav>
</template>
