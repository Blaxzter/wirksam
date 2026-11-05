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
  DOC_GROUPS,
  type DocKind,
  type DocPage,
  docPageById,
  docRouteName,
} from '@/lib/content-pages'

/** The overview of all feature pages, or of all guides. */
const props = defineProps<{ kind: DocKind }>()

const { t } = useI18n()

const base = computed(() => `preauth.docs.hubs.${props.kind}`)

const groups = computed(() =>
  DOC_GROUPS[props.kind].map((group) => ({
    key: group.key,
    pages: group.pages.map((id) => docPageById(id)).filter((p): p is DocPage => Boolean(p)),
  })),
)

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
  >
    <LandingSection id="overview" width="wide">
      <div class="space-y-14">
        <section v-for="group in groups" :key="group.key" :data-testid="`docs-group-${group.key}`">
          <h2 class="text-2xl font-semibold tracking-tight">
            {{ t(`preauth.docs.groups.${kind}.${group.key}`) }}
          </h2>
          <ul class="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <li v-for="page in group.pages" :key="page.key">
              <RouterLink
                :to="{ name: docRouteName(page) }"
                :data-testid="`doc-card-${page.key}`"
                class="group flex h-full flex-col rounded-2xl border bg-card p-5 shadow-sm transition-shadow hover:shadow-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
              >
                <span class="flex items-center gap-3 font-semibold">
                  <span
                    class="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10"
                    aria-hidden="true"
                  >
                    <component :is="ICONS[page.key]" class="size-4.5 text-primary" />
                  </span>
                  <span class="min-w-0 flex-1">{{ t(`preauth.docs.pages.${page.key}.name`) }}</span>
                  <ArrowRightIcon
                    class="size-4 shrink-0 text-primary transition-transform group-hover:translate-x-0.5"
                    aria-hidden="true"
                  />
                </span>
                <span class="mt-3 text-sm leading-relaxed text-muted-foreground">
                  {{ t(`preauth.seo.${page.key}.description`) }}
                </span>
              </RouterLink>
            </li>
          </ul>
        </section>
      </div>
    </LandingSection>

    <ContentRelated />
  </ContentPageShell>
</template>
