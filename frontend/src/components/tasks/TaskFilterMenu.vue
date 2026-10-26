<script setup lang="ts">
import { computed, ref } from 'vue'

import { Filter, RotateCcw } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { useAuthStore } from '@/stores/auth'
import { useTaskFiltersStore } from '@/stores/eventFilters'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { useLocations } from '@/composables/useLocations'

import { Badge } from '@/components/ui/badge'
import Button from '@/components/ui/button/Button.vue'
import { DateRangePicker } from '@/components/ui/date-range-picker'
import { Label } from '@/components/ui/label'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { Switch } from '@/components/ui/switch'

const { t } = useI18n()
const { get } = useAuthenticatedClient()
const filters = useTaskFiltersStore()
const authStore = useAuthStore()

// Only offered when the selected event has locations to choose from.
const { locations } = useLocations(() => authStore.selectedEventId)
const ALL_LOCATIONS = '__all'
const locationValue = computed({
  get: () => filters.locationId ?? ALL_LOCATIONS,
  set: (v: string) => (filters.locationId = v === ALL_LOCATIONS ? null : v),
})

const showHideFullShifts = computed(() => filters.viewMode === 'list')

// Fetch active dates for the visible month in the date picker
const markedDays = ref<Set<string>>(new Set())

async function handleVisibleMonth(range: { from: string; to: string }) {
  try {
    const res = await get<{ data: string[] }>({
      url: '/tasks/active-dates',
      query: { date_from: range.from, date_to: range.to },
    })
    markedDays.value = new Set(res.data)
  } catch {
    // Non-critical
  }
}
</script>

<template>
  <div class="flex items-center gap-2">
    <!-- Date range picker -->
    <DateRangePicker
      :date-from="filters.dateFrom"
      :date-to="filters.dateTo"
      :marked-days="markedDays"
      @update:date-from="filters.dateFrom = $event"
      @update:date-to="filters.dateTo = $event"
      @update:visible-month="handleVisibleMonth"
    />

    <!-- Filter menu popover -->
    <Popover>
      <PopoverTrigger as-child>
        <Button variant="outline" size="sm">
          <Filter class="h-4 w-4" />
          <span class="hidden sm:inline">{{ t('duties.tasks.filters.title') }}</span>
          <Badge
            v-if="filters.activeFilterCount > 0"
            variant="secondary"
            class="ml-1 shrink-0 px-1.5 py-0 text-[10px] leading-4"
          >
            {{ filters.activeFilterCount }}
          </Badge>
        </Button>
      </PopoverTrigger>
      <PopoverContent class="w-72" align="end">
        <div class="space-y-4">
          <div class="flex items-center justify-between">
            <h4 class="text-sm font-medium">{{ t('duties.tasks.filters.title') }}</h4>
            <Button
              v-if="filters.activeFilterCount > 0"
              variant="ghost"
              size="sm"
              class="h-auto px-2 py-1 text-xs"
              @click="filters.resetFilters()"
            >
              <RotateCcw class="mr-1 h-3 w-3" />
              {{ t('duties.tasks.filters.reset') }}
            </Button>
          </div>

          <Separator />

          <div class="space-y-3">
            <!-- My Bookings Only -->
            <div class="flex items-center justify-between">
              <Label for="filter-my-bookings" class="text-sm font-normal cursor-pointer">
                {{ t('duties.tasks.myBookingsFilter') }}
              </Label>
              <Switch
                id="filter-my-bookings"
                :model-value="filters.myBookingsOnly"
                @update:model-value="filters.myBookingsOnly = $event"
              />
            </div>

            <!-- Hide Fully Booked (list view only) -->
            <div v-if="showHideFullShifts" class="flex items-center justify-between">
              <Label for="filter-hide-full" class="text-sm font-normal cursor-pointer">
                {{ t('duties.tasks.hideFullShifts') }}
              </Label>
              <Switch
                id="filter-hide-full"
                :model-value="filters.hideFullShifts"
                @update:model-value="filters.hideFullShifts = $event"
              />
            </div>

            <!-- Hide tasks a team keeps the user from booking. Off by default. -->
            <div class="flex items-center justify-between gap-3">
              <Label for="filter-bookable-only" class="cursor-pointer flex-col items-start gap-0.5">
                <span class="text-sm">{{ t('teamLocks.filter.bookableOnly') }}</span>
                <span class="text-muted-foreground text-xs font-normal">
                  {{ t('teamLocks.filter.bookableOnlyHint') }}
                </span>
              </Label>
              <Switch
                id="filter-bookable-only"
                data-testid="filter-bookable-only"
                :model-value="filters.bookableOnly"
                @update:model-value="filters.bookableOnly = $event"
              />
            </div>

            <!-- Location -->
            <div v-if="locations.length > 0" class="space-y-1.5">
              <Label for="filter-location" class="text-sm font-normal">
                {{ t('locations.filter.label') }}
              </Label>
              <Select v-model="locationValue">
                <SelectTrigger
                  id="filter-location"
                  size="sm"
                  class="w-full"
                  data-testid="filter-location"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem :value="ALL_LOCATIONS">{{ t('locations.filter.all') }}</SelectItem>
                  <SelectItem
                    v-for="location in locations"
                    :key="location.id"
                    :value="location.id"
                    :data-testid="`filter-location-option-${location.id}`"
                  >
                    {{ location.name }}
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  </div>
</template>
