<script setup lang="ts">
import { TERMINAL_COMMANDS } from '@/lib/content-pages'

/**
 * Running WirkSam yourself: the commands from the page, typed out one after the
 * other, and then the server is up. It types once and stays, as a terminal does.
 */
</script>

<template>
  <div class="flex aspect-[4/3] items-center justify-center p-5 sm:p-8">
    <div
      class="a-float w-full overflow-hidden rounded-xl border border-white/10 bg-neutral-900 text-neutral-100 shadow-2xl"
    >
      <div class="flex items-center gap-1.5 border-b border-white/10 px-3 py-2.5">
        <span class="size-2.5 rounded-full bg-[#ff5f57]" />
        <span class="size-2.5 rounded-full bg-[#febc2e]" />
        <span class="size-2.5 rounded-full bg-[#28c840]" />
      </div>
      <div class="space-y-2 p-4 font-mono text-[11px] leading-relaxed sm:p-5 sm:text-[13px]">
        <p
          v-for="(line, index) in TERMINAL_COMMANDS"
          :key="line"
          class="type flex gap-2.5"
          :style="{ animationDelay: `${0.4 + index * 0.8}s` }"
        >
          <span class="text-neutral-400">$</span>
          <span class="min-w-0 break-all">{{ line }}</span>
        </p>
        <p
          class="type flex items-center gap-2.5 pt-1"
          :style="{ animationDelay: `${0.4 + TERMINAL_COMMANDS.length * 0.8}s` }"
        >
          <span class="size-2 rounded-full bg-[#28c840]" />
          <span class="h-2 w-28 rounded-full bg-white/25" />
          <span class="h-2 w-12 rounded-full bg-white/15" />
          <span class="caret h-3.5 w-2 bg-neutral-300" />
        </p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.type {
  animation: type 0.7s steps(24) both;
}
@keyframes type {
  from {
    clip-path: inset(0 100% 0 0);
  }
  to {
    clip-path: inset(0 0 0 0);
  }
}

.caret {
  animation: blink 1s steps(1) infinite;
}
@keyframes blink {
  50% {
    opacity: 0;
  }
}
</style>
