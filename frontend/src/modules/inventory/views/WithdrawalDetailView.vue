<script setup lang="ts">
import { ElMessageBox } from 'element-plus'
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import { errorMessage, fieldErrors, showError, showSuccess } from '@/utils/feedback'
import { fmtDateTime } from '@/utils/format'

import { inventoryApi } from '../api'
import ItemStatusTag from '../components/ItemStatusTag.vue'
import WithdrawalStatusTag from '../components/WithdrawalStatusTag.vue'
import { WITHDRAWAL_EVENT_LABEL } from '../format'
import type { WithdrawalDetail } from '../types'

const route = useRoute()
const auth = useAuthStore()
const w = ref<WithdrawalDetail | null>(null)
const comment = ref('')
const errors = ref<Record<string, string>>({})
const formError = ref<string | null>(null)
const saving = ref(false)

const STEP_NAME = { PM: 'Project manager', OM: 'Operations manager' } as const
const TASK_TEXT: Record<string, string> = { PENDING: 'Waiting', APPROVED: 'Approved', REJECTED: 'Rejected', SKIPPED: 'Not needed', CLOSED: 'Closed' }

async function load(): Promise<void> {
  try {
    w.value = await inventoryApi.withdrawal(Number(route.params.id))
  } catch (e) {
    showError(e)
  }
}
watch(() => route.params.id, load, { immediate: true })

async function decide(approve: boolean): Promise<void> {
  if (!w.value) return
  errors.value = {}
  formError.value = null
  if (!approve && !comment.value.trim()) {
    errors.value = { comment: 'Tell the requester why, so they know what to change.' }
    return
  }
  saving.value = true
  try {
    w.value = await inventoryApi.decideWithdrawal(w.value.id, w.value.version, approve, comment.value.trim() || null)
    comment.value = ''
    showSuccess(
      approve
        ? w.value.status === 'APPROVED'
          ? `Approved. The items are now recorded at ${w.value.to_location.name}.`
          : 'Approved. The operations manager is asked next.'
        : 'Rejected and sent back to the requester.',
    )
    auth.refresh().catch(() => {})
  } catch (e) {
    errors.value = fieldErrors(e)
    formError.value = errorMessage(e)
  } finally {
    saving.value = false
  }
}

async function withdraw(): Promise<void> {
  if (!w.value) return
  try {
    await ElMessageBox.confirm('The items go back to stock and the request is closed.', `Withdraw ${w.value.request_no}?`, {
      confirmButtonText: 'Withdraw',
      cancelButtonText: 'Keep',
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    w.value = await inventoryApi.withdrawWithdrawal(w.value.id, w.value.version, null)
    showSuccess('Request withdrawn. The items are back in stock.')
  } catch (e) {
    showError(e)
  }
}
</script>

<template>
  <div v-if="w" class="page">
    <div class="page-head">
      <div>
        <RouterLink to="/inventory/withdrawals" class="back">Withdrawals</RouterLink>
        <h1 class="mono">{{ w.request_no }}</h1>
        <p class="sub">{{ w.project.name }} · requested by {{ w.requester.display_name }} on {{ fmtDateTime(w.submitted_at) }}</p>
      </div>
      <WithdrawalStatusTag :status="w.status" />
    </div>

    <section v-if="w.can_decide" class="panel decide">
      <h2>Your decision</h2>
      <p class="muted">
        {{ w.status === 'PENDING_PM' ? 'As the project manager' : 'As operations manager' }}: approve moving {{ w.item_count }}
        item{{ w.item_count === 1 ? '' : 's' }} to <b>{{ w.to_location.name }}</b>?
        {{ w.status === 'PENDING_OM' ? 'This is the final approval: the items move to the new location.' : '' }}
      </p>
      <el-form label-position="top" @submit.prevent>
        <el-form-item label="Comment (required to reject)" :error="errors.comment" for="w-comment">
          <el-input id="w-comment" v-model="comment" type="textarea" :autosize="{ minRows: 2 }" maxlength="2000" />
        </el-form-item>
      </el-form>
      <el-alert v-if="formError" :title="formError" type="error" :closable="false" show-icon />
      <div class="buttons">
        <el-button size="large" type="primary" :loading="saving" @click="decide(true)">Approve</el-button>
        <el-button size="large" type="danger" plain :loading="saving" @click="decide(false)">Reject</el-button>
      </div>
    </section>

    <section v-if="w.can_revise || w.can_withdraw" class="panel">
      <template v-if="w.status === 'RETURNED'">
        <h2>This request was rejected</h2>
        <p class="muted">Read the reason below. You can revise the request and submit it again, or withdraw it. The items are back in stock meanwhile.</p>
      </template>
      <div class="buttons">
        <el-button v-if="w.can_revise" type="primary" @click="$router.push(`/inventory/withdrawals/${w.id}/edit`)">Revise and resubmit</el-button>
        <el-button v-if="w.can_withdraw" @click="withdraw">Withdraw the request</el-button>
      </div>
    </section>

    <div class="cols">
      <section class="panel">
        <h2>Request</h2>
        <dl class="facts">
          <div><dt>New location</dt><dd><b>{{ w.to_location.name }}</b></dd></div>
          <div><dt>Project</dt><dd>{{ w.project.name }} <span class="mono muted">{{ w.project.code }}</span></dd></div>
          <div class="full"><dt>Reason</dt><dd class="pre">{{ w.reason }}</dd></div>
        </dl>
        <h3>Items ({{ w.item_count }})</h3>
        <ol class="rows">
          <li v-for="i in w.items" :key="i.id">
            <RouterLink :to="`/inventory/items/${i.id}`" class="mono">{{ i.serial_no }}</RouterLink>
            <span class="muted small grow">{{ i.category_name }} · {{ i.model_no }} · {{ i.location.name }}</span>
            <ItemStatusTag :status="i.status" />
          </li>
        </ol>
      </section>

      <section class="panel">
        <h2>Approval</h2>
        <ol class="steps">
          <li v-for="t in w.tasks" :key="`${t.round}-${t.step}`" :class="t.status.toLowerCase()">
            <b>{{ STEP_NAME[t.step] }}</b>
            <span class="small">
              {{ TASK_TEXT[t.status] }}
              <template v-if="t.decided_by"> · {{ t.decided_by.display_name }} · {{ fmtDateTime(t.decided_at) }}</template>
              <template v-else-if="t.approvers.length"> · {{ t.approvers.map((u) => u.display_name).join(', ') }}</template>
            </span>
            <span v-if="t.comment" class="reason small">{{ t.comment }}</span>
          </li>
          <li v-if="w.status === 'PENDING_PM'" class="later">
            <b>Operations manager</b><span class="small muted">After the PM</span>
          </li>
        </ol>
        <h3>History</h3>
        <ol class="events small">
          <li v-for="(e, n) in w.events" :key="n">
            <b>{{ WITHDRAWAL_EVENT_LABEL[e.action] ?? e.action }}</b>
            <span class="muted"> · {{ e.actor.display_name }} · {{ fmtDateTime(e.occurred_at) }}</span>
            <div v-if="e.comment" class="reason">{{ e.comment }}</div>
          </li>
        </ol>
      </section>
    </div>
  </div>
</template>

<style scoped>
.back {
  font-size: 13px;
  text-decoration: none;
}
.back::before {
  content: '‹ ';
}
.decide {
  border-color: var(--erf-accent);
}
.buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.buttons .el-button + .el-button {
  margin-left: 0;
}
.cols {
  display: grid;
  grid-template-columns: minmax(0, 1.3fr) minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}
@media (max-width: 860px) {
  .cols {
    grid-template-columns: minmax(0, 1fr);
  }
}
.facts {
  margin: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px 20px;
}
.facts dt {
  font-size: 12px;
  color: var(--erf-muted);
}
.facts dd {
  margin: 2px 0 0;
}
.facts .full {
  grid-column: 1 / -1;
}
h3 {
  font-size: 14px;
  margin: 6px 0 0;
}
.rows {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 6px;
}
.rows li {
  display: flex;
  align-items: center;
  gap: 10px;
  border: 1px solid var(--erf-line);
  border-radius: 8px;
  padding: 7px 10px;
  flex-wrap: wrap;
}
.grow {
  flex: 1;
  min-width: 0;
}
.small {
  font-size: 12.5px;
}
.steps {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 8px;
}
.steps li {
  display: grid;
  gap: 2px;
  padding: 8px 12px;
  border-radius: 8px;
  border-left: 4px solid var(--erf-line);
  background: var(--erf-surface-2);
}
.steps li.approved {
  border-left-color: var(--erf-ok);
}
.steps li.rejected {
  border-left-color: var(--erf-bad);
}
.steps li.pending {
  border-left-color: var(--erf-accent);
}
.steps li.later {
  opacity: 0.6;
}
.events {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 8px;
}
.reason {
  display: block;
  background: var(--erf-surface);
  border-radius: 6px;
  padding: 4px 8px;
  margin-top: 2px;
  white-space: pre-wrap;
}
</style>
