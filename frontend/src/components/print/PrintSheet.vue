<script setup lang="ts">
/**
 * One printed sheet: a header the browser repeats on every page, a QR code
 * when there is somewhere to sign up online, the place on the venue plan, and
 * the shifts of one task, or of each task on a shared list.
 *
 * Everything sits in one <table> so the browser can repeat the <thead> on every
 * printed page; a fixed layout keeps it to the screen's width on a phone,
 * where the shifts scroll sideways instead. `ready()` resolves once the QR
 * code and the map have drawn.
 */
import { nextTick, useTemplateRef } from 'vue'

import { CalendarDays, MapPin, Tag } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import PrintShiftDays from '@/components/print/PrintShiftDays.vue'
import QrCode from '@/components/print/QrCode.vue'
import VenueMiniMap from '@/components/venue-map/VenueMiniMap.vue'

import type { TaskBookingEntry } from '@/client/types.gen'
import type { SheetMap, SheetOptions, SheetSection } from '@/lib/print-sheet'

interface SheetMeta {
  days: string
  location?: string | null
  category?: string | null
}

const props = defineProps<{
  heading: string
  /** A small line over the heading: the event. */
  kicker?: string | null
  /** The task's description or the list's intro, as plain text. */
  text?: string | null
  meta?: SheetMeta | null
  /** Where the code leads, and the line under it. */
  qr?: { url: string; caption: string } | null
  sections: readonly SheetSection[]
  options: SheetOptions
  bookings: ReadonlyMap<string, readonly TaskBookingEntry[]>
  map?: SheetMap | null
  /** Start the sheet on a new page. */
  pageBreak?: boolean
}>()

const { t } = useI18n()

const miniMap = useTemplateRef<InstanceType<typeof VenueMiniMap>>('miniMap')

let qrDrawn: () => void = () => {}
const qrReady = new Promise<void>((resolve) => (qrDrawn = resolve))

async function ready(): Promise<void> {
  if (props.qr) await qrReady
  if (props.map) {
    await nextTick()
    await miniMap.value?.ready()
  }
}

defineExpose({ ready })
</script>

<template>
  <table
    :class="{ 'print-page-break': pageBreak }"
    class="w-full table-fixed border-collapse"
    data-testid="print-sheet"
  >
    <thead :class="options.repeatHeader ? 'print-repeat-header' : ''">
      <tr>
        <th class="text-left font-normal p-0 pb-4">
          <div class="flex items-start justify-between gap-4">
            <div class="space-y-2 flex-1 min-w-0">
              <p v-if="kicker" class="text-sm text-muted-foreground">{{ kicker }}</p>
              <h1 class="text-3xl font-bold break-words">{{ heading }}</h1>
              <p v-if="text" class="text-muted-foreground text-lg whitespace-pre-line break-words">
                {{ text }}
              </p>
              <div
                v-if="meta"
                class="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground"
              >
                <span class="flex items-center gap-1">
                  <CalendarDays class="h-4 w-4" aria-hidden="true" />
                  {{ meta.days }}
                </span>
                <span v-if="meta.location" class="flex items-center gap-1">
                  <MapPin class="h-4 w-4" aria-hidden="true" />
                  {{ meta.location }}
                </span>
                <span v-if="meta.category" class="flex items-center gap-1">
                  <Tag class="h-4 w-4" aria-hidden="true" />
                  {{ meta.category }}
                </span>
              </div>
            </div>
            <figure v-if="qr" class="shrink-0 w-28 text-center space-y-1" data-testid="print-qr">
              <div class="flex justify-center">
                <QrCode
                  :value="qr.url"
                  :size="112"
                  :alt="t('sharedLists.detail.qrAlt', { url: qr.url })"
                  @ready="qrDrawn"
                />
              </div>
              <figcaption class="text-xs text-muted-foreground">{{ qr.caption }}</figcaption>
            </figure>
          </div>
          <hr class="border-foreground/20 mt-4" />
        </th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td class="p-0">
          <!-- Below the header rather than in it, so a repeated header does not
               print the map again on every page. -->
          <div v-if="map" class="mb-4 max-w-md print-keep-together" data-testid="print-mini-map">
            <VenueMiniMap
              ref="miniMap"
              :event-id="map.eventId"
              :pin="map.pin"
              :location-id="map.locationId"
              :link-to-map="false"
              static
            />
          </div>
          <!-- On a phone the columns scroll sideways; on paper they fit the page. -->
          <div
            class="space-y-6 overflow-x-auto print:overflow-visible"
            role="region"
            tabindex="0"
            :aria-label="t('print.shiftsRegion')"
          >
            <section v-for="section in sections" :key="section.key" class="space-y-3">
              <h2 v-if="section.heading" class="text-xl font-semibold print-keep-with-next">
                {{ section.heading }}
              </h2>
              <PrintShiftDays
                :shifts="section.shifts"
                :batches="section.batches"
                :options="options"
                :bookings="bookings"
                :can-see-contacts="section.canSeeContacts"
              />
            </section>
          </div>
        </td>
      </tr>
    </tbody>
  </table>
</template>
