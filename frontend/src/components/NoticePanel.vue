<script setup lang="ts">
import type { NoticePreview } from '@/types/api'
import { fmtDate } from '@/utils/format'

defineProps<{ preview: NoticePreview | null; loading?: boolean }>()
</script>

<template>
  <div class="notice" :class="preview ? (preview.is_short_notice ? 'short' : 'ok') : ''">
    <template v-if="preview">
      <span class="hint">Notice period if submitted today ({{ fmtDate(preview.submitted_on) }})</span>
      <span class="big">{{ preview.notice_working_days }} working day{{ preview.notice_working_days === 1 ? '' : 's' }}</span>
      <span class="hint">
        Weekends and public holidays are excluded.
        <template v-if="preview.holidays.length">
          This period includes {{ preview.holidays.map((h) => `${h.name} (${fmtDate(h.holiday_date)})`).join(', ') }}.
        </template>
      </span>
      <span v-if="preview.is_short_notice">
        <b>This will be an urgent request.</b> The minimum is {{ preview.min_notice_working_days }} working days, so a
        justification is required and support depends on availability.
      </span>
      <span v-else>Meets the {{ preview.min_notice_working_days }}-working-day notice period.</span>
    </template>
    <span v-else class="hint">{{ loading ? 'Calculating…' : 'Pick a planned start date to see the notice period.' }}</span>
  </div>
</template>

<style scoped>
.notice {
  border: 1px solid var(--erf-line);
  border-radius: var(--erf-radius);
  background: var(--erf-surface);
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.big {
  font-size: 28px;
  font-weight: 600;
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
}
.ok .big {
  color: var(--erf-ok);
}
.short {
  border-color: color-mix(in srgb, var(--erf-bad) 55%, var(--erf-line));
  background: color-mix(in srgb, var(--erf-bad) 6%, var(--erf-surface));
}
.short .big {
  color: var(--erf-bad);
}
.hint {
  font-size: 12px;
  color: var(--erf-muted);
}
</style>
