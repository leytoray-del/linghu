<script setup lang="ts">
import { ITEM_STATUS_LABEL, ITEM_STATUS_TONE } from '../format'
import type { ItemStatus } from '../types'

defineProps<{ status: ItemStatus }>()
</script>

<template>
  <span class="status" :class="`tone-${ITEM_STATUS_TONE[status]}`">{{ ITEM_STATUS_LABEL[status] }}</span>
</template>

<style scoped>
.status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 500;
  padding: 2px 9px;
  border-radius: 999px;
  white-space: nowrap;
}
.status::before {
  content: '';
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}
.tone-accent {
  color: var(--erf-accent);
  background: color-mix(in srgb, var(--erf-accent) 12%, transparent);
}
.tone-ok {
  color: var(--erf-ok);
  background: color-mix(in srgb, var(--erf-ok) 14%, transparent);
}
.tone-warn {
  color: var(--erf-warn);
  background: color-mix(in srgb, var(--erf-warn) 14%, transparent);
}
.tone-bad {
  color: var(--erf-bad);
  background: color-mix(in srgb, var(--erf-bad) 12%, transparent);
}
.tone-muted {
  color: var(--erf-muted);
  background: var(--erf-surface-2);
}
</style>
