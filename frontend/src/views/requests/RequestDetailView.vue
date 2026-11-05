<script setup lang="ts">
import { ElMessageBox } from 'element-plus'
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { requestApi } from '@/api'
import EngineerPicker from '@/components/EngineerPicker.vue'
import HistoryTimeline from '@/components/HistoryTimeline.vue'
import StatusTag from '@/components/StatusTag.vue'
import UrgentBadge from '@/components/UrgentBadge.vue'
import WorkflowSteps from '@/components/WorkflowSteps.vue'
import { useAuthStore } from '@/stores/auth'
import type { Action, AllocationCandidate, AllocationInput, ChangeOut, RequestDetail } from '@/types/api'
import { errorMessage, fieldErrors, showError, showSuccess } from '@/utils/feedback'
import { fmtDate, fmtDateTime, fmtRange, TYPE_LABEL } from '@/utils/format'

type Busy = Action | 'DELETE' | 'CHANGE' | 'CHANGE_APPROVE' | 'CHANGE_REJECT' | 'CHANGE_WITHDRAW'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const request = ref<RequestDetail | null>(null)
const loading = ref(true)
const candidates = ref<AllocationCandidate[]>([])
const picks = ref<Record<number, number>>({})
const comment = ref('')
const busy = ref<Busy | null>(null)
const actionError = ref<string | null>(null)

const changeOpen = ref(false)
const changeForm = reactive({ new_start: '', new_end: '', new_headcount: 1, reason: '' })
const changeErrors = ref<Record<string, string>>({})
const changeError = ref<string | null>(null)

const id = computed(() => Number(route.params.id))
const can = (a: Action) => request.value?.available_actions.includes(a) ?? false
const isDecider = computed(() => can('APPROVE'))
const isTlStep = computed(() => request.value?.status === 'PENDING_TL_REVIEW' && isDecider.value)
const isDirectorStep = computed(() => request.value?.status === 'PENDING_DIRECTOR_APPROVAL' && isDecider.value)
const pendingChange = computed<ChangeOut | undefined>(() => request.value?.changes.find((c) => c.status === 'PENDING'))
const pastChanges = computed(() => request.value?.changes.filter((c) => c.status !== 'PENDING').reverse() ?? [])
const reviewingChange = computed(() => !!request.value?.change_awaiting_me && !!pendingChange.value)
const isRequester = computed(() => request.value?.requester.id === auth.me?.id)
const canCopy = computed(() => !!request.value && request.value.status !== 'DRAFT')

const priorityText = computed(() => {
  const r = request.value
  if (!r) return ''
  if (!r.is_urgent) return r.notice_working_days !== null ? `Normal (${r.notice_working_days} working days notice)` : 'Normal'
  return r.urgency_reason === 'SHORT_NOTICE'
    ? `Urgent: short notice of ${r.notice_working_days} working days`
    : 'Urgent: declared by the requester'
})

function allocationInput(): AllocationInput[] {
  return Object.entries(picks.value).map(([engineer, pct]) => ({ engineer_id: Number(engineer), allocation_pct: pct }))
}

async function load(): Promise<void> {
  loading.value = true
  actionError.value = null
  try {
    const r = await requestApi.get(id.value)
    request.value = r
    comment.value = ''
    changeOpen.value = false
    candidates.value = []
    picks.value = {}
    if (isTlStep.value) {
      candidates.value = await requestApi.candidates(r.id)
      picks.value = Object.fromEntries(candidates.value.filter((c) => c.is_preferred).map((c) => [c.engineer.id, 100]))
    } else if (reviewingChange.value && pendingChange.value) {
      const c = pendingChange.value
      candidates.value = await requestApi.candidates(r.id, { start: c.new_start, end: c.new_end })
      picks.value = Object.fromEntries(r.allocations.map((a) => [a.engineer.id, a.allocation_pct]))
    }
  } catch (e) {
    showError(e)
    if (!request.value) await router.replace({ name: 'requests' })
  } finally {
    loading.value = false
  }
}

watch(id, load, { immediate: true })

async function confirm(message: string, title: string, confirmText: string): Promise<boolean> {
  try {
    await ElMessageBox.confirm(message, title, { confirmButtonText: confirmText, cancelButtonText: 'Keep it', type: 'warning' })
    return true
  } catch {
    return false
  }
}

async function run(action: Busy, call: () => Promise<unknown>, done: string): Promise<boolean> {
  busy.value = action
  actionError.value = null
  try {
    await call()
    showSuccess(done)
    await auth.refresh()
    await load()
    return true
  } catch (e) {
    actionError.value = errorMessage(e)
    return false
  } finally {
    busy.value = null
  }
}

async function decide(action: 'APPROVE' | 'RETURN' | 'REJECT'): Promise<void> {
  const r = request.value!
  const text = comment.value.trim() || null
  if ((action === 'RETURN' || action === 'REJECT') && !text) {
    actionError.value = 'Add a comment so the requester knows what to change or why the request was declined.'
    return
  }
  if (action === 'REJECT' && !(await confirm('The requester will have to raise a new request.', 'Reject this request?', 'Reject'))) {
    return
  }
  const allocations = isTlStep.value && action === 'APPROVE' ? allocationInput() : []
  const messages = {
    APPROVE: isTlStep.value ? 'Approved and sent to the director.' : 'Approved. The requester and engineers have been notified.',
    RETURN: 'Returned to the requester.',
    REJECT: 'Request rejected.',
  }
  await run(action, () => requestApi.decide(r.id, action, r.version, text, allocations), messages[action])
}

async function submit(): Promise<void> {
  const r = request.value!
  await run('SUBMIT', () => requestApi.submit(r.id, r.version), `${r.display_no} submitted.`)
}

async function withdraw(): Promise<void> {
  const r = request.value!
  if (!(await confirm('The reviewers will be told, and any proposed engineers will be released.', 'Withdraw this request?', 'Withdraw'))) return
  await run('WITHDRAW', () => requestApi.withdraw(r.id, r.version, comment.value.trim() || null), 'Request withdrawn.')
}

async function cancel(): Promise<void> {
  const r = request.value!
  const text = comment.value.trim()
  if (!text) {
    actionError.value = 'Explain in the comment why the approved request is being cancelled.'
    return
  }
  if (!(await confirm('The allocated engineers will be released and notified.', 'Cancel this approved request?', 'Cancel request'))) return
  await run('CANCEL', () => requestApi.cancel(r.id, r.version, text), 'Request cancelled.')
}

async function close(): Promise<void> {
  const r = request.value!
  await run('CLOSE', () => requestApi.close(r.id, r.version), 'Request closed.')
}

async function removeDraft(): Promise<void> {
  const r = request.value!
  if (!(await confirm('This draft will be deleted permanently.', 'Delete draft?', 'Delete'))) return
  busy.value = 'DELETE'
  try {
    await requestApi.remove(r.id)
    showSuccess('Draft deleted.')
    await router.replace({ name: 'requests', query: { scope: 'mine' } })
  } catch (e) {
    showError(e)
  } finally {
    busy.value = null
  }
}

// ---------------------------------------------------------------- changes to an approved request

function openChange(): void {
  const r = request.value!
  Object.assign(changeForm, {
    new_start: r.planned_start ?? '',
    new_end: r.planned_end ?? '',
    new_headcount: r.headcount ?? 1,
    reason: '',
  })
  changeErrors.value = {}
  changeError.value = null
  changeOpen.value = true
}

async function sendChange(): Promise<void> {
  const r = request.value!
  busy.value = 'CHANGE'
  changeErrors.value = {}
  changeError.value = null
  try {
    await requestApi.requestChange(r.id, { version: r.version, ...changeForm })
    showSuccess('Change sent to the team leader for review.')
    await load()
  } catch (e) {
    changeErrors.value = fieldErrors(e)
    changeError.value = errorMessage(e)
  } finally {
    busy.value = null
  }
}

async function decideChange(action: 'APPROVE' | 'REJECT'): Promise<void> {
  const r = request.value!
  const change = pendingChange.value!
  const text = comment.value.trim() || null
  if (action === 'REJECT' && !text) {
    actionError.value = 'Add a comment that explains why the change is rejected.'
    return
  }
  await run(
    action === 'APPROVE' ? 'CHANGE_APPROVE' : 'CHANGE_REJECT',
    () => requestApi.decideChange(r.id, change.id, action, text, action === 'APPROVE' ? allocationInput() : []),
    action === 'APPROVE' ? 'Change approved. The requester and engineers have been notified.' : 'Change rejected.',
  )
}

async function withdrawChange(): Promise<void> {
  const r = request.value!
  await run('CHANGE_WITHDRAW', () => requestApi.withdrawChange(r.id, pendingChange.value!.id), 'Change request withdrawn.')
}

const requesterActions = computed(
  () =>
    can('SUBMIT') || can('WITHDRAW') || can('CANCEL') || can('CLOSE') || request.value?.can_edit || request.value?.can_delete,
)
const CHANGE_TONE: Record<string, string> = { APPROVED: 'success', REJECTED: 'danger', WITHDRAWN: 'info', PENDING: 'warning' }
</script>

<template>
  <div v-loading="loading" class="page">
    <template v-if="request">
      <div class="page-head">
        <div>
          <div class="mono muted">{{ request.display_no }}<template v-if="request.round > 1"> · round {{ request.round }}</template></div>
          <h1>{{ request.project_name || '(untitled draft)' }}</h1>
          <p class="sub">
            Requested by {{ request.requester.display_name }}
            <template v-if="request.first_submitted_at"> on {{ fmtDateTime(request.first_submitted_at) }}</template>
          </p>
        </div>
        <div class="head-tags">
          <UrgentBadge v-if="request.is_urgent" />
          <el-tag v-if="pendingChange" type="warning" size="small">Change pending</el-tag>
          <StatusTag :status="request.status" />
          <el-button v-if="canCopy" size="small" @click="router.push({ name: 'request-new', query: { copy: request.id } })">
            Copy as new request
          </el-button>
        </div>
      </div>

      <div class="layout">
        <div class="main-col">
          <!-- Team leader review: assign engineers and decide -->
          <section v-if="isTlStep" class="panel action">
            <h2>Your review</h2>
            <EngineerPicker v-model="picks" :candidates="candidates" :headcount="request.headcount" />
            <el-input
              v-model="comment"
              type="textarea"
              :autosize="{ minRows: 2 }"
              placeholder="Comment. Required when returning or rejecting, or when you assign fewer engineers than requested."
            />
            <el-alert v-if="actionError" :title="actionError" type="error" :closable="false" show-icon />
            <div class="buttons">
              <el-button type="primary" :loading="busy === 'APPROVE'" @click="decide('APPROVE')">Approve and send to director</el-button>
              <el-button :loading="busy === 'RETURN'" @click="decide('RETURN')">Return to requester</el-button>
              <el-button type="danger" plain :loading="busy === 'REJECT'" @click="decide('REJECT')">Reject</el-button>
            </div>
          </section>

          <!-- Director decision -->
          <section v-if="isDirectorStep" class="panel action">
            <div class="panel-head">
              <h2>Your decision</h2>
              <span class="muted small">The team leader has proposed the engineers listed below.</span>
            </div>
            <el-input v-model="comment" type="textarea" :autosize="{ minRows: 2 }" placeholder="Comment. Required when returning or rejecting." />
            <el-alert v-if="actionError" :title="actionError" type="error" :closable="false" show-icon />
            <div class="buttons">
              <el-button type="primary" :loading="busy === 'APPROVE'" @click="decide('APPROVE')">Approve and confirm resources</el-button>
              <el-button :loading="busy === 'RETURN'" @click="decide('RETURN')">Return to requester</el-button>
              <el-button type="danger" plain :loading="busy === 'REJECT'" @click="decide('REJECT')">Reject</el-button>
            </div>
          </section>

          <!-- A change waiting for review -->
          <section v-if="pendingChange" class="panel" :class="{ action: reviewingChange }">
            <div class="panel-head">
              <h2>{{ reviewingChange ? 'Change waiting for your review' : 'Change waiting for the team leader' }}</h2>
              <span class="muted small">Asked by {{ pendingChange.requested_by.display_name }} on {{ fmtDateTime(pendingChange.created_at) }}</span>
            </div>
            <dl class="details compact">
              <dt>Planned period</dt>
              <dd>
                {{ fmtRange(pendingChange.old_start, pendingChange.old_end) }} →
                <b>{{ fmtRange(pendingChange.new_start, pendingChange.new_end) }}</b>
              </dd>
              <dt>Engineers required</dt>
              <dd>{{ pendingChange.old_headcount }} → <b>{{ pendingChange.new_headcount }}</b></dd>
              <dt>Reason</dt>
              <dd class="pre">{{ pendingChange.reason }}</dd>
            </dl>
            <template v-if="reviewingChange">
              <p class="muted no-margin">Confirm the engineers for the new period. Availability below is for the new dates.</p>
              <EngineerPicker v-model="picks" :candidates="candidates" :headcount="pendingChange.new_headcount" />
              <el-input v-model="comment" type="textarea" :autosize="{ minRows: 2 }" placeholder="Comment. Required when rejecting." />
              <el-alert v-if="actionError" :title="actionError" type="error" :closable="false" show-icon />
              <div class="buttons">
                <el-button type="primary" :loading="busy === 'CHANGE_APPROVE'" @click="decideChange('APPROVE')">Approve change</el-button>
                <el-button type="danger" plain :loading="busy === 'CHANGE_REJECT'" @click="decideChange('REJECT')">Reject change</el-button>
              </div>
            </template>
            <div v-else-if="isRequester" class="buttons">
              <el-button :loading="busy === 'CHANGE_WITHDRAW'" @click="withdrawChange">Withdraw change request</el-button>
            </div>
          </section>

          <!-- Requester actions -->
          <section v-if="!isDecider && !reviewingChange && (requesterActions || request.can_request_change)" class="panel" :class="{ action: request.status === 'RETURNED' || request.status === 'DRAFT' }">
            <div class="panel-head">
              <h2 v-if="request.status === 'RETURNED'">This request was returned to you</h2>
              <h2 v-else-if="request.status === 'DRAFT'">This request is a draft</h2>
              <h2 v-else-if="request.current_handlers.length">Waiting for {{ request.current_handlers.map((h) => h.display_name).join(', ') }}</h2>
              <h2 v-else>Actions</h2>
            </div>
            <p v-if="request.status === 'RETURNED'" class="muted no-margin">Read the comment in the history, update the request and resubmit it.</p>
            <p v-if="request.status === 'DRAFT'" class="muted no-margin">Only you can see a draft. Submit it to start the approval.</p>

            <el-form v-if="changeOpen" class="change-form" label-position="top" @submit.prevent="sendChange">
              <p class="muted no-margin">
                Ask the team leader to move the dates or change the number of engineers. The request stays approved with
                its current engineers until the change is approved.
              </p>
              <div class="grid">
                <el-form-item label="New start date" :error="changeErrors.new_start">
                  <el-date-picker v-model="changeForm.new_start" type="date" value-format="YYYY-MM-DD" format="D MMM YYYY" />
                </el-form-item>
                <el-form-item label="New end date" :error="changeErrors.new_end">
                  <el-date-picker v-model="changeForm.new_end" type="date" value-format="YYYY-MM-DD" format="D MMM YYYY" />
                </el-form-item>
                <el-form-item label="Engineers required" :error="changeErrors.new_headcount">
                  <el-input-number v-model="changeForm.new_headcount" :min="1" :max="50" />
                </el-form-item>
              </div>
              <el-form-item label="Reason for the change" :error="changeErrors.reason" for="change-reason">
                <el-input id="change-reason" v-model="changeForm.reason" type="textarea" :autosize="{ minRows: 2 }" maxlength="5000" />
              </el-form-item>
              <el-alert v-if="changeError" :title="changeError" type="error" :closable="false" show-icon />
              <div class="buttons">
                <el-button type="primary" :loading="busy === 'CHANGE'" @click="sendChange">Send for review</el-button>
                <el-button @click="changeOpen = false">Cancel</el-button>
              </div>
            </el-form>

            <template v-else>
              <el-input
                v-if="can('WITHDRAW') || can('CANCEL')"
                v-model="comment"
                type="textarea"
                :autosize="{ minRows: 2 }"
                :placeholder="can('CANCEL') ? 'Reason for cancelling (required to cancel).' : 'Reason for withdrawing (optional).'"
              />
              <el-alert v-if="actionError" :title="actionError" type="error" :closable="false" show-icon />
              <div class="buttons">
                <el-button v-if="request.can_edit" :type="request.status === 'RETURNED' ? 'primary' : 'default'" @click="router.push({ name: 'request-edit', params: { id: request.id } })">
                  {{ request.status === 'RETURNED' ? 'Revise and resubmit' : 'Edit' }}
                </el-button>
                <el-button v-if="can('SUBMIT') && request.status === 'DRAFT'" type="primary" :loading="busy === 'SUBMIT'" @click="submit">Submit</el-button>
                <el-button v-if="request.can_request_change" @click="openChange">Request a change</el-button>
                <el-button v-if="can('CLOSE')" :loading="busy === 'CLOSE'" @click="close">Mark as completed</el-button>
                <el-button v-if="can('CANCEL')" type="danger" plain :loading="busy === 'CANCEL'" @click="cancel">Cancel request</el-button>
                <el-button v-if="can('WITHDRAW')" type="danger" plain :loading="busy === 'WITHDRAW'" @click="withdraw">Withdraw</el-button>
                <el-button v-if="request.can_delete" type="danger" plain :loading="busy === 'DELETE'" @click="removeDraft">Delete draft</el-button>
              </div>
            </template>
          </section>

          <section class="panel">
            <h2>Request details</h2>
            <dl class="details">
              <dt>Request type</dt><dd>{{ request.request_type ? TYPE_LABEL[request.request_type] : '—' }}</dd>
              <dt>Priority</dt><dd>{{ priorityText }}</dd>
              <dt>Project / opportunity</dt><dd>{{ request.project_name || '—' }}</dd>
              <dt>Project / WBS code</dt><dd>{{ request.wbs_code || '—' }}</dd>
              <dt>Client</dt><dd>{{ request.client_name || '—' }}</dd>
              <dt>Type of support</dt><dd>{{ request.support_type?.name ?? '—' }}<template v-if="request.team"> · {{ request.team.name }}</template></dd>
              <dt>Engineers required</dt><dd>{{ request.headcount ?? '—' }}</dd>
              <dt>Preferred engineers</dt>
              <dd>
                {{ request.preferred_engineers.map((u) => u.display_name).join(', ') || '—' }}
                <template v-if="request.preferred_engineers_note"><br /><span class="muted">{{ request.preferred_engineers_note }}</span></template>
              </dd>
              <dt>Man-days awarded</dt><dd>{{ request.man_days ?? 'Not applicable' }}</dd>
              <dt>Planned period</dt><dd>{{ fmtRange(request.planned_start, request.planned_end) }}</dd>
              <dt>Scope description</dt><dd class="pre">{{ request.scope_description || '—' }}</dd>
              <dt>Task schedule</dt><dd class="pre">{{ request.task_schedule || '—' }}</dd>
              <template v-if="request.is_urgent">
                <dt>Urgent justification</dt><dd class="pre">{{ request.urgent_justification || '—' }}</dd>
              </template>
            </dl>
          </section>

          <section v-if="request.allocations.length" class="panel">
            <div class="panel-head">
              <h2>Allocated engineers</h2>
              <span class="muted small">{{ request.allocations[0]?.status === 'CONFIRMED' ? 'Confirmed' : 'Proposed by the team leader' }}</span>
            </div>
            <ul class="alloc">
              <li v-for="a in request.allocations" :key="a.id">
                <span>
                  <b>{{ a.engineer.display_name }}</b> <span class="muted">{{ a.engineer.job_title }}</span>
                  <el-tag size="small" :type="a.allocation_pct < 100 ? 'warning' : 'info'" class="pct">{{ a.allocation_pct }}%</el-tag>
                </span>
                <span class="mono">{{ fmtDate(a.start_date) }} – {{ fmtDate(a.end_date) }}</span>
              </li>
            </ul>
          </section>

          <section v-if="pastChanges.length" class="panel">
            <h2>Change history</h2>
            <div v-for="c in pastChanges" :key="c.id" class="change">
              <div>
                <el-tag size="small" :type="CHANGE_TONE[c.status] as 'success'">{{ c.status.toLowerCase() }}</el-tag>
                {{ c.summary }}
              </div>
              <div class="muted small">
                Asked by {{ c.requested_by.display_name }} · {{ fmtDateTime(c.created_at) }}<template v-if="c.decided_by"> · decided by {{ c.decided_by.display_name }}</template>
              </div>
              <div class="muted small pre">Reason: {{ c.reason }}<template v-if="c.decision_comment"><br />Decision: {{ c.decision_comment }}</template></div>
            </div>
          </section>
        </div>

        <aside class="side">
          <section class="panel">
            <h2>Progress</h2>
            <WorkflowSteps :request="request" />
          </section>
          <section class="panel">
            <h2>History</h2>
            <HistoryTimeline :events="request.events" />
          </section>
        </aside>
      </div>
    </template>
  </div>
</template>

<style scoped>
.head-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  gap: 20px;
  align-items: start;
}
.main-col,
.side {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}
.action {
  border-color: color-mix(in srgb, var(--erf-accent) 45%, var(--erf-line));
}
.small {
  font-size: 12px;
}
.no-margin {
  margin: 0;
}
.buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.buttons .el-button + .el-button {
  margin-left: 0;
}
.details {
  display: grid;
  grid-template-columns: 200px minmax(0, 1fr);
  gap: 10px 16px;
  margin: 0;
}
.details.compact {
  grid-template-columns: 160px minmax(0, 1fr);
  gap: 6px 16px;
}
.details dt {
  color: var(--erf-muted);
  font-size: 13px;
}
.details dd {
  margin: 0;
  overflow-wrap: anywhere;
}
.alloc {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.alloc li {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.pct {
  margin-left: 6px;
}
.change-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0 14px;
}
.change {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding-top: 8px;
  border-top: 1px solid var(--erf-line);
}
:deep(.el-date-editor.el-input),
:deep(.el-input-number) {
  width: 100%;
}
@media (max-width: 1020px) {
  .layout {
    grid-template-columns: minmax(0, 1fr);
  }
}
@media (max-width: 640px) {
  .details,
  .details.compact,
  .grid {
    grid-template-columns: minmax(0, 1fr);
    gap: 2px;
  }
  .details dd {
    margin-bottom: 8px;
  }
}
</style>
