<script setup lang="ts">
import { RouterLink } from 'vue-router'

import { DropdownMenuItem } from '@/components/ui/dropdown-menu'

/**
 * The legal pages as one small line at the foot of the user menu. Inside the
 * app they are needed rarely, so they live here instead of under every page.
 */
const links = [
  { name: 'privacy', label: 'preauth.layout.footer.privacy' },
  { name: 'terms', label: 'preauth.layout.footer.terms' },
  { name: 'impressum', label: 'preauth.layout.footer.impressum' },
] as const
</script>

<template>
  <div class="flex flex-wrap justify-center gap-x-1 px-1 pb-0.5" data-testid="menu-legal-links">
    <DropdownMenuItem
      v-for="link in links"
      :key="link.name"
      as-child
      class="text-muted-foreground px-1.5 py-1 text-xs"
    >
      <RouterLink :to="{ name: link.name }" :data-testid="`menu-legal-${link.name}`">
        {{ $t(link.label) }}
      </RouterLink>
    </DropdownMenuItem>
  </div>
</template>
