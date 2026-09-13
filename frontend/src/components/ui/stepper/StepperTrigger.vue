<script lang="ts" setup>
import type { StepperTriggerProps } from "reka-ui"
import type { HTMLAttributes } from "vue"
import { reactiveOmit } from "@vueuse/core"
import { StepperTrigger, useForwardProps } from "reka-ui"
import { cn } from "@/lib/utils"

const props = defineProps<StepperTriggerProps & { class?: HTMLAttributes["class"] }>()

const delegatedProps = reactiveOmit(props, "class")

const forwarded = useForwardProps(delegatedProps)
</script>

<template>
  <StepperTrigger
    v-bind="forwarded"
    :class="cn(
      'p-1 flex flex-col items-center text-center gap-1 rounded-md',
      // A step is a control, so it has to feel like one: a pointer and a hover
      // surface where it can be opened, and the refusal spelled out where it
      // cannot. The item keeps its pointer events precisely so `not-allowed`
      // can be seen on the disabled button.
      'cursor-pointer transition-colors hover:bg-accent/60',
      'data-[disabled]:cursor-not-allowed data-[disabled]:hover:bg-transparent',
      props.class,
    )"
  >
    <slot />
  </StepperTrigger>
</template>
