<script setup lang="ts">
import type { Component } from 'vue'
import { computed } from 'vue'

import {
  ArrowRightIcon,
  BellIcon,
  CalendarCheckIcon,
  CalendarRangeIcon,
  ChartNoAxesColumnIcon,
  CopyPlusIcon,
  MapIcon,
  QrCodeIcon,
  RocketIcon,
  ServerIcon,
  ShieldCheckIcon,
  SmartphoneIcon,
  TicketIcon,
  UsersIcon,
  UsersRoundIcon,
} from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import ContentPageShell from '@/components/content/ContentPageShell.vue'
import ContentRelated from '@/components/content/ContentRelated.vue'
import LandingSection from '@/components/landing/LandingSection.vue'

import {
  ACCENT_COLORS,
  DOC_GROUPS,
  type DocKind,
  GROUP_ACCENTS,
  docPageById,
  docRouteName,
  pageLook,
} from '@/lib/content-pages'

/** The overview of all feature pages, or of all guides. */
const props = defineProps<{ kind: DocKind }>()

const { t } = useI18n()

const base = computed(() => `preauth.docs.hubs.${props.kind}`)

/** One grid for the whole overview, in group order, with the group named on each card. */
const cards = computed(() =>
  DOC_GROUPS[props.kind].flatMap((group) =>
    group.pages.flatMap((id) => {
      const page = docPageById(id)
      const color = ACCENT_COLORS[GROUP_ACCENTS[props.kind][group.key] ?? 'green']
      return page ? [{ page, group: group.key, color }] : []
    }),
  ),
)

const look = computed(() => pageLook(props.kind === 'feature' ? 'features' : 'guides'))

const ICONS: Record<string, Component> = {
  featureShiftPlanning: CalendarRangeIcon,
  featureVenueMap: MapIcon,
  featureMembers: UsersIcon,
  featurePeopleInCharge: ShieldCheckIcon,
  featureTeams: UsersRoundIcon,
  featureBooking: CalendarCheckIcon,
  featureNotifications: BellIcon,
  featureVouchers: TicketIcon,
  featureHoursAndReports: ChartNoAxesColumnIcon,
  featureSelfHosting: ServerIcon,
  guideFirstEvent: RocketIcon,
  guideVolunteerStart: SmartphoneIcon,
  guidePeopleInCharge: ShieldCheckIcon,
  guideVouchers: TicketIcon,
  guideRedeemVouchers: QrCodeIcon,
  guideTeams: UsersRoundIcon,
  guideVenueMap: MapIcon,
  guideNextYear: CopyPlusIcon,
}
</script>

<template>
  <ContentPageShell
    :eyebrow="t(`${base}.eyebrow`)"
    :title="t(`${base}.title`)"
    :lede="t(`${base}.lede`)"
    :breadcrumb="t(`${base}.breadcrumb`)"
    :cta-title="t('preauth.docs.ctaTitle')"
    :art="look.art"
    :color="look.color"
  >

    <LandingSection id="overview" width="wide">
      <ul class="grid gap-5 sm:grid-cols-2">
        <li
          v-for="card in cards"
          :key="card.page.key"
          :data-group="card.group"
          :style="{ '--art': card.color }"
        >
          <RouterLink
            :to="{ name: docRouteName(card.page) }"
            :data-testid="`doc-card-${card.page.key}`"
            class="group relative flex h-full flex-col overflow-hidden rounded-2xl border bg-card p-5 pl-6 shadow-sm transition-shadow hover:shadow-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
          >
            <!-- The group's colour runs down the card's edge. -->
            <span class="absolute inset-y-0 left-0 w-1.5 bg-(--art)" aria-hidden="true" />
            <span class="flex items-center gap-3">
              <span
                class="flex size-10 shrink-0 items-center justify-center rounded-lg bg-(--art)/18"
                aria-hidden="true"
              >
                <component :is="ICONS[card.page.key]" class="size-5 text-foreground" />
              </span>
              <span class="min-w-0 flex-1">
                <span
                  class="block text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground"
                  data-testid="doc-group-label"
                >
                  {{ t(`preauth.docs.groups.${kind}.${card.group}`) }}
                </span>
                <!-- The cards are the page's sections, so their names are its headings. -->
                <h2 class="mt-1 font-semibold">
                  {{ t(`preauth.docs.pages.${card.page.key}.name`) }}
                </h2>
              </span>
              <ArrowRightIcon
                class="size-4 shrink-0 text-primary transition-transform group-hover:translate-x-0.5"
                aria-hidden="true"
              />
            </span>
            <span class="mt-3 text-sm leading-relaxed text-muted-foreground">
              {{ t(`preauth.docs.pages.${card.page.key}.tagline`) }}
            </span>
          </RouterLink>
        </li>
      </ul>
    </LandingSection>

    <ContentRelated />
  </ContentPageShell>
</template>
