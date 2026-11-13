<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import { showError } from '@/utils/feedback'
import { fmtDateTime } from '@/utils/format'

import { inventoryApi } from '../api'
import WithdrawalStatusTag from '../components/WithdrawalStatusTag.vue'
import type { Withdrawal } from '../types'

type Scope = 'waiting' | 'mine' | 'all'
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const scopes = computed(() => {
  const list: { value: Scope; label: string }[] = []
  if ((auth.me?.withdrawal_task_count ?? 0) > 0 || auth.hasRole('OPS_MANAGER')) list.push({ value: 'waiting', label: 'Waiting for me' })
  list.push({ value: 'mine', label: 'My requests' })
  list.push({ value: 'all', label: 'All I can see' })
  return list
})
const scope = ref<Scope>((route.query.scope as Scope) || scopes.value[0]!.value)
const rows = ref<Withdrawal[]>([])
const loading = ref(false)

async function load(): Promise<void> {
  loading.value = true
  try {
    rows.value = await inventoryApi.withdrawals(scope.value)
  } catch (e) {
    showError(e)
  } finally {
    loading.value = false
  }
}
watch(
  scope,
  (s) => {
    router.replace({ query: { scope: s } })
    load()
  },
  { immediate: true },
)
</script>

<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h1>Withdrawals</h1>
        <p class="sub">Requests to move items of a project to a new location. The project's PM approves first, then an operations manager.</p>
      </div>
      <el-button v-if="auth.can('inventory.withdraw')" type="primary" @click="$router.push('/inventory/withdrawals/new')">Request withdrawal</el-button>
    </div>
    <section class="panel">
      <el-segmented v-model="scope" :options="scopes" />
      <div v-loading="loading" class="list">
        <RouterLink v-for="w in rows" :key="w.id" :to="`/inventory/withdrawals/${w.id}`" class="row">
          <div class="top">
            <b class="mono">{{ w.request_no }}</b>
            <WithdrawalStatusTag :status="w.status" />
          </div>
          <div>{{ w.item_count }} item{{ w.item_count === 1 ? '' : 's' }} of <b>{{ w.project.name }}</b> to <b>{{ w.to_location.name }}</b></div>
          <div class="muted small">
            {{ w.requester.display_name }} · {{ fmtDateTime(w.submitted_at) }}
            <template v-if="w.waiting_for.length"> · waiting for {{ w.waiting_for.map((u) => u.display_name).join(', ') }}</template>
          </div>
        </RouterLink>
        <p v-if="!loading && !rows.length" class="muted">Nothing here.</p>
      </div>
    </section>
  </div>
</template>

<style scoped>
.list {
  display: grid;
  gap: 8px;
  min-height: 60px;
}
.row {
  display: grid;
  gap: 3px;
  padding: 12px 14px;
  border: 1px solid var(--erf-line);
  border-radius: 10px;
  color: inherit;
  text-decoration: none;
  font-size: 14px;
}
.row:hover {
  border-color: var(--erf-accent);
}
.top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}
.small {
  font-size: 12.5px;
}
</style>
