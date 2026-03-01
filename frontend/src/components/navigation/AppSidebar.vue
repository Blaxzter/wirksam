<script setup lang="ts">
import { BookCheck, CalendarDays } from 'lucide-vue-next'

import AppLogo from '@/components/icons/AppLogo.vue'

import type { SidebarProps } from '@/components/ui/sidebar'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarRail,
} from '@/components/ui/sidebar'

import NavMain from '@/components/navigation/NavMain.vue'
import NavUser from '@/components/navigation/NavUser.vue'
import TeamSwitcher from '@/components/navigation/TeamSwitcher.vue'

interface AppSidebarProps extends SidebarProps {
  open?: boolean
}

const props = withDefaults(defineProps<AppSidebarProps>(), {
  collapsible: 'icon',
  open: true,
})

const data = {
  teams: [
    {
      name: 'DutyHub',
      logo: AppLogo,
      plan: 'Free',
    },
  ],
  navMain: [
    {
      title: 'Events',
      titleKey: 'navigation.sidebar.items.events.label',
      icon: CalendarDays,
      routeName: 'events',
      isActive: true,
    },
    {
      title: 'My Bookings',
      titleKey: 'navigation.sidebar.items.myBookings.label',
      icon: BookCheck,
      routeName: 'my-bookings',
    },
  ],
}
</script>

<template>
  <Sidebar v-bind="props">
    <SidebarHeader>
      <TeamSwitcher :teams="data.teams" />
    </SidebarHeader>
    <SidebarContent>
      <NavMain :items="data.navMain" :open="props.open" />
    </SidebarContent>
    <SidebarFooter>
      <NavUser />
    </SidebarFooter>
    <SidebarRail />
  </Sidebar>
</template>
