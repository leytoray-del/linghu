<script setup lang="ts">
import { WITHDRAWAL_STATUS_LABEL, WITHDRAWAL_STATUS_TONE } from '../format'
import type { WithdrawalStatus } from '../types'
import ToneTag from './ToneTag.vue'

defineProps<{ status: WithdrawalStatus }>()
</script>

<template>
  <ToneTag :label="WITHDRAWAL_STATUS_LABEL[status]" :tone="WITHDRAWAL_STATUS_TONE[status]" />
</template>
