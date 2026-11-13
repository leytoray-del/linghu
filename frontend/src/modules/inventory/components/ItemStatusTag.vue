<script setup lang="ts">
import { ITEM_STATUS_LABEL, ITEM_STATUS_TONE } from '../format'
import type { ItemStatus } from '../types'
import ToneTag from './ToneTag.vue'

defineProps<{ status: ItemStatus }>()
</script>

<template>
  <ToneTag :label="ITEM_STATUS_LABEL[status]" :tone="ITEM_STATUS_TONE[status]" />
</template>
