<script setup lang="ts">
/**
 * A table set off from the page as a card: a border, the cards' background, a
 * tinted header row and room at its outer edges, so the rows read as one block
 * rather than as lines across the page.
 */
</script>

<template>
  <div
    data-slot="table-card"
    class="overflow-hidden rounded-xl border bg-card [&_td:first-child]:pl-4 [&_td:last-child]:pr-4 [&_th:first-child]:pl-4 [&_th:last-child]:pr-4 [&_thead_tr]:bg-muted/50"
  >
    <slot />
  </div>
</template>
