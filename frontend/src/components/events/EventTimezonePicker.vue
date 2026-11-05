<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { Check, ChevronsUpDown, Globe, Search } from '@lucide/vue'
import {
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogOverlay,
  DialogPortal,
  DialogRoot,
  DialogTitle,
  VisuallyHidden,
} from 'reka-ui'
import { useI18n } from 'vue-i18n'

import { browserTimeZone, matchesTimeZone, timeZoneLabel, timeZoneNames } from '@/lib/timezones'

/**
 * Pick an event's time zone by searching for it.
 *
 * A field that opens a picker: full screen on a phone, with the list above the
 * keyboard as in `EventMemberPicker`, and a centred panel on anything wider. The
 * layout is all CSS, so there is one list and one way of using it. The current
 * zone and the device's own come first until something is typed.
 */
const zone = defineModel<string>({ required: true })

defineProps<{
  inputId?: string
  disabled?: boolean
}>()

const { t } = useI18n()

const open = ref(false)
const search = ref('')

// Asked for when the picker opens: a few hundred names nobody needs until then.
const zones = computed(() => (open.value ? timeZoneNames(zone.value, browserTimeZone()) : []))

const matches = computed(() => {
  if (search.value.trim()) return zones.value.filter((z) => matchesTimeZone(z, search.value))
  const first = [...new Set([zone.value, browserTimeZone()])]
  return [...first, ...zones.value.filter((z) => !first.includes(z))]
})

function pick(next: string) {
  zone.value = next
  open.value = false
}

/** Enter in the search: the first row, once something is typed. */
function pickFirst() {
  const first = matches.value[0]
  if (search.value.trim() && first) pick(first)
}

// A search left behind in a closed picker would greet the next opening.
watch(open, (isOpen) => {
  if (!isOpen) search.value = ''
})
</script>

<template>
  <button
    :id="inputId"
    type="button"
    class="border-input focus-visible:border-ring focus-visible:ring-ring/50 flex h-11 w-full items-center gap-2 rounded-md border bg-transparent px-3 text-left text-base shadow-xs outline-none focus-visible:ring-[3px] disabled:cursor-not-allowed disabled:opacity-50 sm:h-9 sm:text-sm"
    :disabled="disabled"
    aria-haspopup="dialog"
    :aria-expanded="open"
    data-testid="timezone-picker"
    @click="open = true"
  >
    <Globe class="size-4 shrink-0 opacity-60" aria-hidden="true" />
    <span class="min-w-0 flex-1 truncate" data-testid="timezone-picker-value">
      {{ timeZoneLabel(zone) }}
    </span>
    <ChevronsUpDown class="size-4 shrink-0 opacity-50" aria-hidden="true" />
  </button>

  <DialogRoot v-model:open="open">
    <DialogPortal>
      <!-- The overlay is what locks the page behind: reka's scroll lock lives in it. -->
      <DialogOverlay class="bg-background fixed inset-0 z-60 sm:bg-black/50" />
      <DialogContent
        class="bg-background text-foreground fixed inset-0 z-60 flex flex-col overflow-hidden focus:outline-none data-[state=open]:animate-in data-[state=open]:fade-in-0 sm:inset-auto sm:top-[12vh] sm:left-1/2 sm:h-[min(30rem,76vh)] sm:w-full sm:max-w-md sm:-translate-x-1/2 sm:rounded-xl sm:border sm:shadow-lg"
        data-testid="timezone-picker-sheet"
      >
        <header class="space-y-2 border-b px-4 pt-3.5 pb-3">
          <DialogTitle class="text-base font-semibold">
            {{ t('duties.events.timezone.label') }}
          </DialogTitle>
          <VisuallyHidden>
            <DialogDescription>{{ t('duties.events.timezone.hint') }}</DialogDescription>
          </VisuallyHidden>
          <div class="flex items-center gap-2">
            <label
              class="border-ring focus-within:ring-ring/40 flex min-h-11 min-w-0 flex-1 items-center gap-2 rounded-xl border-2 px-3 focus-within:ring-[3px]"
            >
              <Search class="text-muted-foreground size-4.5 shrink-0" aria-hidden="true" />
              <span class="sr-only">{{ t('duties.events.timezone.search') }}</span>
              <input
                v-model="search"
                type="search"
                autocomplete="off"
                autocapitalize="off"
                spellcheck="false"
                enterkeyhint="go"
                class="min-w-0 flex-1 bg-transparent text-base outline-none placeholder:text-muted-foreground [&::-webkit-search-cancel-button]:appearance-none"
                :placeholder="t('duties.events.timezone.search')"
                data-testid="timezone-picker-input"
                @keydown.enter.prevent="pickFirst"
              />
            </label>
            <DialogClose
              class="text-primary min-h-11 shrink-0 rounded-md px-1.5 text-base font-semibold focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
            >
              {{ t('common.actions.cancel') }}
            </DialogClose>
          </div>
        </header>

        <!-- The one thing that scrolls, as in EventMemberPicker's sheet. -->
        <div
          class="min-h-0 flex-1 overflow-y-auto overscroll-contain pb-[env(safe-area-inset-bottom)] [scrollbar-color:auto] [scrollbar-width:auto]"
        >
          <ul class="px-2 py-2" data-testid="timezone-picker-list">
            <li v-for="option in matches" :key="option">
              <button
                type="button"
                class="hover:bg-accent focus-visible:ring-ring flex min-h-11 w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-base focus-visible:ring-2 focus-visible:outline-none sm:min-h-9 sm:text-sm"
                :aria-current="option === zone ? 'true' : undefined"
                :data-testid="`timezone-option-${option}`"
                @click="pick(option)"
              >
                <span class="min-w-0 flex-1 truncate">{{ timeZoneLabel(option) }}</span>
                <Check v-if="option === zone" class="size-4 shrink-0" aria-hidden="true" />
              </button>
            </li>
          </ul>
          <p
            v-if="matches.length === 0"
            class="text-muted-foreground px-5 py-6 text-center text-sm"
          >
            {{ t('duties.events.timezone.noMatch') }}
          </p>
        </div>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>
