<script setup lang="ts">
import { computed } from 'vue'

import type { AllocationCandidate } from '@/types/api'
import { fmtRange, PCT_OPTIONS } from '@/utils/format'

/** Selected engineers with their allocation, keyed by engineer id. */
const model = defineModel<Record<number, number>>({ required: true })
const props = defineProps<{ candidates: AllocationCandidate[]; headcount: number | null }>()

const count = computed(() => Object.keys(model.value).length)

function toggle(id: number, checked: boolean): void {
  const next = { ...model.value }
  if (checked) next[id] = next[id] ?? 100
  else delete next[id]
  model.value = next
}

function setPct(id: number, pct: number): void {
  model.value = { ...model.value, [id]: pct }
}

function load(c: AllocationCandidate): { text: string; tone: string } {
  const mine = model.value[c.engineer.id] ?? 0
  if (c.peak_pct === 0) return { text: 'Free in this period', tone: 'free' }
  const total = c.peak_pct + mine
  return {
    text: `Booked up to ${c.peak_pct}% elsewhere`,
    tone: total > 100 ? 'busy' : 'some',
  }
}

function tooltip(c: AllocationCandidate): string {
  return c.overlapping
    .map((o) => `${o.display_no} ${o.project_name ?? ''} · ${o.allocation_pct}% · ${fmtRange(o.start_date, o.end_date)}`)
    .join('\n')
}
</script>

<template>
  <div class="picker">
    <div class="count muted">
      Select {{ props.headcount ?? '' }} engineer{{ props.headcount === 1 ? '' : 's' }} · {{ count }} selected. Set how much
      of each person's time this work needs.
    </div>
    <div v-for="c in props.candidates" :key="c.engineer.id" class="row" :class="{ on: c.engineer.id in model }">
      <el-checkbox
        :model-value="c.engineer.id in model"
        :aria-label="`Assign ${c.engineer.display_name}`"
        @update:model-value="(v) => toggle(c.engineer.id, !!v)"
      />
      <div class="who" @click="toggle(c.engineer.id, !(c.engineer.id in model))">
        <b>{{ c.engineer.display_name }}</b>
        <el-tag v-if="c.is_preferred" size="small" class="pref">Preferred</el-tag>
        <div class="muted small">{{ c.skills || c.engineer.job_title }}</div>
      </div>
      <el-tooltip :disabled="!c.overlapping.length" :content="tooltip(c)" placement="top">
        <span class="load" :class="load(c).tone">{{ load(c).text }}</span>
      </el-tooltip>
      <el-select
        :model-value="model[c.engineer.id] ?? 100"
        :disabled="!(c.engineer.id in model)"
        size="small"
        class="pct"
        :aria-label="`Allocation for ${c.engineer.display_name}`"
        @update:model-value="(v: number) => setPct(c.engineer.id, v)"
      >
        <el-option v-for="p in PCT_OPTIONS" :key="p" :label="`${p}%`" :value="p" />
      </el-select>
    </div>
    <p v-if="!props.candidates.length" class="muted">No engineers are set up for this team yet.</p>
  </div>
</template>

<style scoped>
.picker {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.count {
  font-size: 12px;
}
.row {
  display: grid;
  grid-template-columns: 20px minmax(0, 1fr) auto 84px;
  gap: 10px;
  align-items: center;
  padding: 8px 12px;
  border: 1px solid var(--erf-line);
  border-radius: var(--erf-radius);
}
.row.on {
  border-color: var(--erf-accent);
  background: color-mix(in srgb, var(--erf-accent) 6%, var(--erf-surface));
}
.who {
  cursor: pointer;
  min-width: 0;
}
.pref {
  margin-left: 6px;
}
.small {
  font-size: 12px;
}
.load {
  font-family: var(--erf-mono);
  font-size: 11.5px;
  white-space: nowrap;
}
.load.free {
  color: var(--erf-ok);
}
.load.some {
  color: var(--erf-warn);
}
.load.busy {
  color: var(--erf-bad);
}
@media (max-width: 640px) {
  .row {
    grid-template-columns: 20px minmax(0, 1fr) 84px;
  }
  .load {
    grid-column: 2 / -1;
    grid-row: 2;
  }
}
</style>
