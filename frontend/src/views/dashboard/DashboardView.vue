<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { referenceApi, requestApi } from '@/api'
import RequestTable from '@/components/RequestTable.vue'
import { useAuthStore } from '@/stores/auth'
import type { Dashboard, RequestSummary, TaskInboxItem } from '@/types/api'
import { showError } from '@/utils/feedback'

const auth = useAuthStore()
const stats = ref<Dashboard | null>(null)
const recent = ref<RequestSummary[]>([])
const returned = ref<RequestSummary[]>([])
const tasks = ref<TaskInboxItem[]>([])
const assigned = ref<RequestSummary[]>([])
const loading = ref(true)

const firstName = computed(() => auth.me?.display_name.split(' ')[0] ?? '')
const greeting = computed(() => {
  const h = new Date().getHours()
  return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening'
})

onMounted(async () => {
  try {
    const jobs: Promise<unknown>[] = [
      referenceApi.dashboard().then((d) => (stats.value = d)),
      requestApi.list({ scope: 'mine', page_size: 5 }).then((p) => (recent.value = p.items)),
      requestApi.list({ scope: 'mine', status: ['RETURNED'] }).then((p) => (returned.value = p.items)),
    ]
    if (auth.isApprover) jobs.push(requestApi.myTasks().then((t) => (tasks.value = t)))
    if (auth.hasScope('assigned')) {
      jobs.push(requestApi.list({ scope: 'assigned', status: ['APPROVED'] }).then((p) => (assigned.value = p.items)))
    }
    await Promise.all(jobs)
  } catch (e) {
    showError(e)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h1>{{ greeting }}, {{ firstName }}</h1>
        <p class="sub">
          Requests need at least 5 working days of notice before the planned start date. Anything shorter is treated as
          urgent and needs a justification.
        </p>
      </div>
      <el-button type="primary" @click="$router.push('/requests/new')">New request</el-button>
    </div>

    <div v-if="stats" class="tiles">
      <template v-if="auth.isApprover">
        <div class="tile" :class="{ attention: stats.pending_tasks }">
          <span class="label">Waiting for your decision</span>
          <span class="value">{{ stats.pending_tasks }}</span>
        </div>
        <div class="tile" :class="{ attention: stats.pending_urgent }">
          <span class="label">Of which urgent</span>
          <span class="value">{{ stats.pending_urgent }}</span>
        </div>
        <div class="tile" :class="{ attention: stats.overdue_tasks }">
          <span class="label">Overdue</span>
          <span class="value">{{ stats.overdue_tasks }}</span>
        </div>
        <div class="tile">
          <span class="label">{{ auth.isTeamLeader ? 'Open team requests' : 'Your open requests' }}</span>
          <span class="value">{{ auth.isTeamLeader ? stats.team_requests_open : stats.my_open }}</span>
        </div>
      </template>
      <template v-else>
        <div class="tile">
          <span class="label">Awaiting approval</span>
          <span class="value">{{ stats.my_open }}</span>
        </div>
        <div class="tile" :class="{ attention: stats.my_returned }">
          <span class="label">Rejected, to revise</span>
          <span class="value">{{ stats.my_returned }}</span>
        </div>
        <div class="tile">
          <span class="label">Approved</span>
          <span class="value">{{ stats.my_approved }}</span>
        </div>
        <div class="tile">
          <span class="label">{{ auth.hasScope('assigned') ? 'Active assignments' : 'Drafts' }}</span>
          <span class="value">{{ auth.hasScope('assigned') ? stats.assigned_active : stats.my_drafts }}</span>
        </div>
      </template>
    </div>

    <section v-if="auth.isApprover" class="panel">
      <div class="panel-head">
        <h2>Waiting for your decision</h2>
        <RouterLink to="/approvals">Open approvals</RouterLink>
      </div>
      <RequestTable :rows="tasks.map((t) => t.request)" :loading="loading" empty="Nothing is waiting for you." />
    </section>

    <section v-if="returned.length" class="panel">
      <div class="panel-head"><h2>Rejected: revise and resubmit, or withdraw</h2></div>
      <RequestTable :rows="returned" />
    </section>

    <section v-if="assigned.length" class="panel">
      <div class="panel-head">
        <h2>Your assignments</h2>
        <RouterLink :to="{ path: '/requests', query: { scope: 'assigned' } }">View all</RouterLink>
      </div>
      <RequestTable :rows="assigned" />
    </section>

    <section class="panel">
      <div class="panel-head">
        <h2>Your recent requests</h2>
        <RouterLink :to="{ path: '/requests', query: { scope: 'mine' } }">View all</RouterLink>
      </div>
      <RequestTable :rows="recent" :loading="loading" empty="You have not raised any requests yet." />
    </section>
  </div>
</template>
