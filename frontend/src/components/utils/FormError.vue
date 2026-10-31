<script setup lang="ts">
/**
 * Why the server refused a form, kept on the form itself.
 *
 * A toast is gone after a few seconds and sits in a corner the visitor was not
 * looking at; whoever glances back at the form after it fades sees no sign that
 * anything went wrong. This row stays put next to the submit button until the
 * visitor changes something or tries again — the form decides when to clear it.
 *
 * `role="alert"` so a screen reader announces it the moment it appears, without
 * the visitor having to go looking for it.
 */
import { CircleAlertIcon } from '@lucide/vue'

defineProps<{
  /** The message to show; nothing is rendered while it is empty. */
  message?: string | null
}>()
</script>

<template>
  <div
    v-if="message"
    class="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2.5 text-sm text-destructive"
    role="alert"
    data-testid="form-error"
  >
    <CircleAlertIcon class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
    <p>{{ message }}</p>
  </div>
</template>
