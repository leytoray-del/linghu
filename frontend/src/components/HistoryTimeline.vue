<script setup lang="ts">
import { computed } from 'vue'

import type { EventOut } from '@/types/api'
import { EVENT_LABEL, fmtDateTime } from '@/utils/format'

const props = defineProps<{ events: EventOut[] }>()
const ordered = computed(() => [...props.events].reverse())

function detail(e: EventOut): string {
  const p = e.payload ?? {}
  if (typeof p.change === 'string') {
    const names = Array.isArray(p.engineers) ? ` · ${(p.engineers as string[]).join(', ')}` : ''
    return `${p.change}${names}`
  }
  if (Array.isArray(p.engineers)) return (p.engineers as string[]).join(', ')
  if (e.action === 'SUBMIT' || e.action === 'RESUBMIT') {
    const days = p.notice_working_days as number | undefined
    if (p.is_urgent) return p.urgency_reason === 'SHORT_NOTICE' ? `Urgent: ${days} working days notice` : 'Declared urgent'
    return days !== undefined ? `${days} working days notice` : ''
  }
  return ''
}
</script>

<template>
  <div class="timeline">
    <div v-for="e in ordered" :key="e.id" class="event">
      <div>
        <b>{{ e.actor?.display_name ?? 'System' }}</b> · {{ EVENT_LABEL[e.action] ?? e.action }}
      </div>
      <div class="meta">{{ fmtDateTime(e.created_at) }}<template v-if="detail(e)"> · {{ detail(e) }}</template></div>
      <div v-if="e.comment" class="comment pre">{{ e.comment }}</div>
    </div>
  </div>
</template>

<style scoped>
.timeline {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.event {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding-left: 12px;
  border-left: 2px solid var(--erf-line);
}
.meta {
  font-size: 12px;
  color: var(--erf-muted);
}
.comment {
  background: var(--erf-surface-2);
  padding: 6px 10px;
  border-radius: var(--erf-radius);
  font-size: 13px;
  margin-top: 4px;
}
</style>
