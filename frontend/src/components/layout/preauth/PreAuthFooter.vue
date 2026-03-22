<script setup lang="ts">
import { formatDate } from '@/lib/format'

const appVersion = __APP_VERSION__
const appVersionDate = __APP_VERSION_DATE__
</script>

<template>
  <footer class="border-t mt-auto flex-shrink-0">
    <div
      class="max-w-7xl w-full mx-auto px-4 py-6 flex flex-col sm:flex-row items-center justify-between gap-2 text-sm text-muted-foreground"
    >
      <div class="flex flex-col items-center sm:items-start gap-1">
        <p>{{ $t('preauth.layout.footer.copyright') }}</p>
        <p class="text-xs">
          {{
            $t('preauth.layout.footer.version', {
              version: appVersion,
              date: formatDate(appVersionDate),
            })
          }}
        </p>
      </div>
      <nav class="flex items-center gap-4">
        <router-link :to="{ name: 'privacy' }" class="hover:text-foreground transition-colors">
          {{ $t('preauth.layout.footer.privacy') }}
        </router-link>
        <router-link :to="{ name: 'terms' }" class="hover:text-foreground transition-colors">
          {{ $t('preauth.layout.footer.terms') }}
        </router-link>
        <router-link :to="{ name: 'impressum' }" class="hover:text-foreground transition-colors">
          {{ $t('preauth.layout.footer.impressum') }}
        </router-link>
      </nav>
    </div>
  </footer>
</template>
