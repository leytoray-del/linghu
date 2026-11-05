<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import { referenceApi, requestApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import type { ReportSummary } from '@/types/api'
import { showError } from '@/utils/feedback'
import { fmtHours } from '@/utils/format'

const auth = useAuthStore()
const year = ref(new Date().getFullYear())
const report = ref<ReportSummary | null>(null)
const loading = ref(true)

const years = computed(() => {
  const now = new Date().getFullYear()
  return [now, now - 1, now - 2]
})
const monthMax = computed(() => Math.max(1, ...(report.value?.by_month.map((m) => m.normal + m.urgent) ?? [1])))
const exportHref = computed(() =>
  requestApi.exportUrl({ scope: auth.hasScope('all') ? 'all' : 'team' }),
)

async function load(): Promise<void> {
  loading.value = true
  try {
    report.value = await referenceApi.report(year.value)
  } catch (e) {
    showError(e)
  } finally {
    loading.value = false
  }
}

function maxOf(list: { count: number }[]): number {
  return Math.max(1, ...list.map((x) => x.count))
}

watch(year, load)
onMounted(load)
</script>

<template>
  <div v-loading="loading" class="page">
    <div class="page-head">
      <div>
        <h1>Reports</h1>
        <p class="sub">
          Requests first submitted in the selected year{{ auth.hasRole('DIRECTOR', 'ADMIN', 'VIEWER') ? '' : ' for the teams you lead' }}.
          Drafts are not counted.
        </p>
      </div>
      <div class="controls">
        <el-select v-model="year" class="year">
          <el-option v-for="y in years" :key="y" :label="String(y)" :value="y" />
        </el-select>
        <el-button tag="a" :href="exportHref">Export requests to Excel</el-button>
      </div>
    </div>

    <template v-if="report">
      <div class="tiles">
        <div class="tile"><span class="label">Requests submitted</span><span class="value">{{ report.total }}</span></div>
        <div class="tile" :class="{ attention: report.urgent_share > 0.25 }">
          <span class="label">Urgent share</span>
          <span class="value">{{ Math.round(report.urgent_share * 100) }}%</span>
        </div>
        <div class="tile"><span class="label">Median team leader decision</span><span class="value">{{ fmtHours(report.median_tl_hours) }}</span></div>
        <div class="tile"><span class="label">Median director decision</span><span class="value">{{ fmtHours(report.median_director_hours) }}</span></div>
      </div>

      <div class="grid">
        <section class="panel">
          <div class="panel-head">
            <h2>Requests per month</h2>
            <div class="legend"><span><i class="normal"></i>Normal</span><span><i class="urgent"></i>Urgent</span></div>
          </div>
          <div class="bars">
            <div v-for="m in report.by_month" :key="m.month" class="bar">
              <span>{{ m.month }}</span>
              <span class="track">
                <span class="fill normal" :style="{ width: `${(m.normal / monthMax) * 100}%` }"></span>
                <span class="fill urgent" :style="{ width: `${(m.urgent / monthMax) * 100}%` }"></span>
              </span>
              <span class="v">{{ m.normal + m.urgent }}</span>
            </div>
          </div>
        </section>

        <section class="panel">
          <h2>By status</h2>
          <div class="bars">
            <div v-for="s in report.by_status" :key="s.name" class="bar wide">
              <span>{{ s.name }}</span>
              <span class="track"><span class="fill normal" :style="{ width: `${(s.count / maxOf(report.by_status)) * 100}%` }"></span></span>
              <span class="v">{{ s.count }}</span>
            </div>
            <p v-if="!report.by_status.length" class="muted">No requests in this year.</p>
          </div>
        </section>

        <section class="panel">
          <h2>By type of support</h2>
          <div class="bars">
            <div v-for="s in report.by_support_type" :key="s.name" class="bar wide">
              <span>{{ s.name }}</span>
              <span class="track"><span class="fill normal" :style="{ width: `${(s.count / maxOf(report.by_support_type)) * 100}%` }"></span></span>
              <span class="v">{{ s.count }}</span>
            </div>
          </div>
        </section>

        <section class="panel">
          <h2>Approved work</h2>
          <div class="kv">
            <span>Approved or completed requests</span><span>{{ report.approved }}</span>
            <span>Man-days in approved project requests</span><span>{{ report.approved_man_days }}</span>
            <template v-for="t in report.by_team" :key="t.name">
              <span>Requests for the {{ t.name }}</span><span>{{ t.count }}</span>
            </template>
          </div>
        </section>
      </div>
    </template>
  </div>
</template>

<style scoped>
.controls {
  display: flex;
  gap: 10px;
}
.year {
  width: 110px;
}
.grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px;
}
.legend {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: var(--erf-muted);
}
.legend span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.legend i {
  width: 12px;
  height: 12px;
  border-radius: 3px;
  display: inline-block;
}
.bars {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.bar {
  display: grid;
  grid-template-columns: 40px minmax(0, 1fr) 36px;
  gap: 10px;
  align-items: center;
  font-size: 13px;
}
.bar.wide {
  grid-template-columns: 170px minmax(0, 1fr) 36px;
}
.track {
  height: 14px;
  background: var(--erf-surface-2);
  border-radius: 3px;
  overflow: hidden;
  display: flex;
}
.fill.normal,
.legend .normal {
  background: var(--erf-accent);
}
.fill.urgent,
.legend .urgent {
  background: var(--erf-bad);
}
.fill {
  height: 100%;
}
.v {
  font-family: var(--erf-mono);
  font-size: 12px;
  text-align: right;
}
.kv {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px 16px;
  font-size: 13px;
}
.kv span:nth-child(even) {
  font-family: var(--erf-mono);
  text-align: right;
}
@media (max-width: 900px) {
  .grid {
    grid-template-columns: minmax(0, 1fr);
  }
  .bar.wide {
    grid-template-columns: 120px minmax(0, 1fr) 32px;
  }
}
</style>
