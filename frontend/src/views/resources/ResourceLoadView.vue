<script setup lang="ts">
import dayjs from 'dayjs'
import { computed, onMounted, ref, watch } from 'vue'

import { referenceApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { useLookupStore } from '@/stores/lookups'
import type { LoadAssignment, LoadOut } from '@/types/api'
import { showError } from '@/utils/feedback'
import { fmtRange } from '@/utils/format'

const WEEKS = 12
const auth = useAuthStore()
const lookups = useLookupStore()
const data = ref<LoadOut | null>(null)
const loading = ref(true)
const teamId = ref<number | undefined>(undefined)
const weekStart = ref(dayjs().startOf('week').add(1, 'day'))

const teams = computed(() => {
  const all = lookups.data?.teams ?? []
  if (auth.can('resources.overview')) return all
  return all.filter((t) => auth.me?.led_team_ids.includes(t.id))
})

const weeks = computed(() =>
  Array.from({ length: WEEKS }, (_, i) => {
    const start = weekStart.value.add(i, 'week')
    return { start: start.format('YYYY-MM-DD'), end: start.add(4, 'day').format('YYYY-MM-DD'), label: start.format('D MMM') }
  }),
)

async function load(): Promise<void> {
  loading.value = true
  try {
    data.value = await referenceApi.load({
      start: weeks.value[0]!.start,
      end: weeks.value[WEEKS - 1]!.end,
      team_id: teamId.value,
    })
  } catch (e) {
    showError(e)
  } finally {
    loading.value = false
  }
}

function inWeek(assignments: LoadAssignment[], w: { start: string; end: string }): LoadAssignment[] {
  return assignments.filter((a) => a.start_date <= w.end && a.end_date >= w.start)
}

function weekPct(list: LoadAssignment[]): number {
  return list.reduce((sum, a) => sum + a.allocation_pct, 0)
}

function cellClass(list: LoadAssignment[]): string[] {
  const pct = weekPct(list)
  const classes = [pct === 0 ? '' : pct <= 100 ? 'l1' : pct <= 150 ? 'l2' : 'l3']
  if (list.some((a) => a.status === 'PROPOSED')) classes.push('pending')
  return classes
}

function shift(by: number): void {
  weekStart.value = weekStart.value.add(by, 'week')
}

watch([teamId, weekStart], load)
onMounted(async () => {
  await lookups.load().catch(showError)
  await load()
})
</script>

<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h1>Resource load</h1>
        <p class="sub">
          How much of each engineer's time is booked per week, including allocations that are still waiting for the
          director.
        </p>
      </div>
      <div class="controls">
        <el-select v-if="teams.length > 1" v-model="teamId" clearable placeholder="All teams" class="team">
          <el-option v-for="t in teams" :key="t.id" :label="t.name" :value="t.id" />
        </el-select>
        <el-button-group>
          <el-button @click="shift(-4)">Earlier</el-button>
          <el-button @click="weekStart = dayjs().startOf('week').add(1, 'day')">This week</el-button>
          <el-button @click="shift(4)">Later</el-button>
        </el-button-group>
      </div>
    </div>

    <div class="legend">
      <span><i class="l1"></i>Up to 100% booked</span>
      <span><i class="l2"></i>101–150%</span>
      <span><i class="l3"></i>Over 150%</span>
      <span><i class="pending"></i>Includes pending approval</span>
    </div>

    <section v-loading="loading" class="panel">
      <div class="scroll">
        <table class="heat">
          <thead>
            <tr>
              <th class="eng">Engineer</th>
              <th v-for="w in weeks" :key="w.start">w/c {{ w.label }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="e in data?.engineers ?? []" :key="e.engineer.id">
              <td class="eng">
                <b>{{ e.engineer.display_name }}</b>
                <div class="muted small">{{ e.team_name }}<template v-if="e.skills"> · {{ e.skills }}</template></div>
              </td>
              <td v-for="w in weeks" :key="w.start" class="cell" :class="cellClass(inWeek(e.assignments, w))">
                <el-tooltip v-if="inWeek(e.assignments, w).length" placement="top">
                  <template #content>
                    <div v-for="a in inWeek(e.assignments, w)" :key="a.request_id">
                      {{ a.display_no }} {{ a.project_name }} · {{ a.allocation_pct }}% · {{ fmtRange(a.start_date, a.end_date) }}{{ a.status === 'PROPOSED' ? ' (pending)' : '' }}
                    </div>
                  </template>
                  <span>{{ weekPct(inWeek(e.assignments, w)) }}%</span>
                </el-tooltip>
              </td>
            </tr>
            <tr v-if="!loading && !data?.engineers.length">
              <td :colspan="WEEKS + 1" class="muted empty">No engineers are set up for this team yet.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>

<style scoped>
.controls {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}
.team {
  width: 200px;
}
.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  font-size: 12px;
  color: var(--erf-muted);
}
.legend span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.legend i {
  width: 14px;
  height: 14px;
  border-radius: 3px;
  border: 1px solid var(--erf-line);
  display: inline-block;
}
.scroll {
  overflow-x: auto;
}
.heat {
  border-collapse: collapse;
  width: 100%;
  min-width: 900px;
}
.heat th,
.heat td {
  border-bottom: 1px solid var(--erf-line);
  padding: 8px;
  text-align: center;
  font-size: 12px;
}
.heat th {
  color: var(--erf-muted);
  font-weight: 600;
  white-space: nowrap;
  background: var(--erf-surface-2);
}
.heat .eng {
  text-align: left;
  min-width: 200px;
  font-size: 13px;
}
.cell {
  font-family: var(--erf-mono);
  min-width: 58px;
}
.l1 {
  background: color-mix(in srgb, var(--erf-ok) 18%, transparent);
}
.l2 {
  background: color-mix(in srgb, var(--erf-warn) 28%, transparent);
}
.l3 {
  background: color-mix(in srgb, var(--erf-bad) 30%, transparent);
}
.pending {
  background-image: repeating-linear-gradient(
    45deg,
    transparent 0 5px,
    color-mix(in srgb, var(--erf-accent) 22%, transparent) 5px 7px
  );
}
.small {
  font-size: 12px;
}
.empty {
  padding: 24px;
}
</style>
