<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { adminApi } from '@/api'
import type { AdminTeam, AdminUser } from '@/types/api'
import { errorMessage, showError, showSuccess } from '@/utils/feedback'

const teams = ref<AdminTeam[]>([])
const users = ref<AdminUser[]>([])
const selection = ref<Record<number, number[]>>({})
const loading = ref(true)
const saving = ref<number | null>(null)
const error = ref<string | null>(null)

const leaders = computed(() => users.value.filter((u) => u.is_active && u.roles.includes('TEAM_LEADER')))

async function load(): Promise<void> {
  loading.value = true
  try {
    ;[teams.value, users.value] = await Promise.all([adminApi.teams(), adminApi.users()])
    selection.value = Object.fromEntries(teams.value.map((t) => [t.id, t.approvers.map((a) => a.id)]))
  } catch (e) {
    showError(e)
  } finally {
    loading.value = false
  }
}

async function save(team: AdminTeam): Promise<void> {
  saving.value = team.id
  error.value = null
  try {
    await adminApi.setApprovers(team.id, selection.value[team.id] ?? [])
    showSuccess(`Approvers for the ${team.name} saved.`)
    await load()
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    saving.value = null
  }
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="tab">
    <p class="muted intro">
      Requests are routed to the approvers of the team that owns the type of support. If a team has several approvers,
      any one of them can act, and the others' tasks close automatically. Only users with the team leader role can be
      chosen.
    </p>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <div v-for="t in teams" :key="t.id" class="team">
      <div>
        <b>{{ t.name }}</b>
        <div class="muted small mono">{{ t.code }}</div>
      </div>
      <el-select v-model="selection[t.id]" multiple placeholder="Choose approvers" class="pick">
        <el-option v-for="u in leaders" :key="u.id" :label="u.display_name" :value="u.id" />
      </el-select>
      <el-button type="primary" :loading="saving === t.id" @click="save(t)">Save</el-button>
    </div>
  </div>
</template>

<style scoped>
.tab {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.intro {
  margin: 0;
  max-width: 70ch;
}
.team {
  display: grid;
  grid-template-columns: 200px minmax(0, 1fr) auto;
  gap: 14px;
  align-items: center;
  padding: 12px 0;
  border-top: 1px solid var(--erf-line);
}
.small {
  font-size: 12px;
}
.pick {
  width: 100%;
}
@media (max-width: 700px) {
  .team {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
