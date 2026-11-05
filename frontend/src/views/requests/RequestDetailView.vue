<script setup lang="ts">
import { ElMessageBox } from 'element-plus'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { requestApi } from '@/api'
import HistoryTimeline from '@/components/HistoryTimeline.vue'
import StatusTag from '@/components/StatusTag.vue'
import UrgentBadge from '@/components/UrgentBadge.vue'
import WorkflowSteps from '@/components/WorkflowSteps.vue'
import { useAuthStore } from '@/stores/auth'
import type { Action, AllocationCandidate, RequestDetail } from '@/types/api'
import { errorMessage, showError, showSuccess } from '@/utils/feedback'
import { fmtDate, fmtDateTime, fmtRange, TYPE_LABEL } from '@/utils/format'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const request = ref<RequestDetail | null>(null)
const loading = ref(true)
const candidates = ref<AllocationCandidate[]>([])
const selected = ref<number[]>([])
const comment = ref('')
const busy = ref<Action | 'DELETE' | null>(null)
const actionError = ref<string | null>(null)

const id = computed(() => Number(route.params.id))
const can = (a: Action) => request.value?.available_actions.includes(a) ?? false
const isDecider = computed(() => can('APPROVE'))
const isTlStep = computed(() => request.value?.status === 'PENDING_TL_REVIEW' && isDecider.value)
const isDirectorStep = computed(() => request.value?.status === 'PENDING_DIRECTOR_APPROVAL' && isDecider.value)

const priorityText = computed(() => {
  const r = request.value
  if (!r) return ''
  if (!r.is_urgent) return r.notice_working_days !== null ? `Normal (${r.notice_working_days} working days notice)` : 'Normal'
  return r.urgency_reason === 'SHORT_NOTICE'
    ? `Urgent: short notice of ${r.notice_working_days} working days`
    : 'Urgent: declared by the requester'
})

async function load(): Promise<void> {
  loading.value = true
  actionError.value = null
  try {
    request.value = await requestApi.get(id.value)
    comment.value = ''
    if (isTlStep.value) {
      candidates.value = await requestApi.candidates(id.value)
      selected.value = candidates.value.filter((c) => c.is_preferred).map((c) => c.engineer.id)
    } else {
      candidates.value = []
      selected.value = []
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
    await ElMessageBox.confirm(message, title, {
      confirmButtonText: confirmText,
      cancelButtonText: 'Keep it',
      type: 'warning',
    })
    return true
  } catch {
    return false
  }
}

async function run(action: Action, call: () => Promise<RequestDetail>, done: string): Promise<void> {
  busy.value = action
  actionError.value = null
  try {
    request.value = await call()
    showSuccess(done)
    await auth.refresh()
    await load()
  } catch (e) {
    actionError.value = errorMessage(e)
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
  const engineers = isTlStep.value && action === 'APPROVE' ? selected.value : []
  const messages = {
    APPROVE: isTlStep.value ? 'Approved and sent to the director.' : 'Approved. The requester and engineers have been notified.',
    RETURN: 'Returned to the requester.',
    REJECT: 'Request rejected.',
  }
  await run(action, () => requestApi.decide(r.id, action, r.version, text, engineers), messages[action])
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

function loadText(c: AllocationCandidate): { text: string; tone: string } {
  const n = c.overlapping.length
  if (n === 0) return { text: 'Free in this period', tone: 'free' }
  const pending = c.overlapping.filter((o) => o.status === 'PROPOSED').length
  return {
    text: `${n} other assignment${n > 1 ? 's' : ''}${pending ? ` (${pending} pending)` : ''}`,
    tone: n >= 2 ? 'busy' : 'some',
  }
}

const requesterActions = computed(() => can('SUBMIT') || can('WITHDRAW') || can('CANCEL') || can('CLOSE') || request.value?.can_edit || request.value?.can_delete)
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
          <StatusTag :status="request.status" />
        </div>
      </div>

      <div class="layout">
        <div class="main-col">
          <!-- Team leader review: assign engineers and decide -->
          <section v-if="isTlStep" class="panel action">
            <div class="panel-head">
              <h2>Your review</h2>
              <span class="muted small">Select {{ request.headcount }} engineer{{ request.headcount === 1 ? '' : 's' }} · {{ selected.length }} selected</span>
            </div>
            <el-checkbox-group v-model="selected" class="candidates">
              <el-checkbox v-for="c in candidates" :key="c.engineer.id" :value="c.engineer.id" border class="candidate">
                <div class="cand-body">
                  <div>
                    <b>{{ c.engineer.display_name }}</b>
                    <el-tag v-if="c.is_preferred" size="small" class="pref">Preferred</el-tag>
                    <div class="muted small">{{ c.skills || c.engineer.job_title }}</div>
                  </div>
                  <el-tooltip
                    :disabled="!c.overlapping.length"
                    :content="c.overlapping.map((o) => `${o.display_no} ${o.project_name} (${fmtRange(o.start_date, o.end_date)})`).join('\n')"
                    placement="left"
                  >
                    <span class="load" :class="loadText(c).tone">{{ loadText(c).text }}</span>
                  </el-tooltip>
                </div>
              </el-checkbox>
            </el-checkbox-group>
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

          <!-- Requester actions -->
          <section v-if="!isDecider && requesterActions" class="panel" :class="{ action: request.status === 'RETURNED' || request.status === 'DRAFT' }">
            <div class="panel-head">
              <h2 v-if="request.status === 'RETURNED'">This request was returned to you</h2>
              <h2 v-else-if="request.status === 'DRAFT'">This request is a draft</h2>
              <h2 v-else-if="request.current_handlers.length">Waiting for {{ request.current_handlers.map((h) => h.display_name).join(', ') }}</h2>
              <h2 v-else>Actions</h2>
            </div>
            <p v-if="request.status === 'RETURNED'" class="muted no-margin">Read the comment in the history, update the request and resubmit it.</p>
            <p v-if="request.status === 'DRAFT'" class="muted no-margin">Only you can see a draft. Submit it to start the approval.</p>
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
              <el-button v-if="can('CLOSE')" :loading="busy === 'CLOSE'" @click="close">Mark as completed</el-button>
              <el-button v-if="can('CANCEL')" type="danger" plain :loading="busy === 'CANCEL'" @click="cancel">Cancel request</el-button>
              <el-button v-if="can('WITHDRAW')" type="danger" plain :loading="busy === 'WITHDRAW'" @click="withdraw">Withdraw</el-button>
              <el-button v-if="request.can_delete" type="danger" plain :loading="busy === 'DELETE'" @click="removeDraft">Delete draft</el-button>
            </div>
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
              <span class="muted small">{{ request.allocations[0]?.status === 'CONFIRMED' ? 'Confirmed by the director' : 'Proposed by the team leader' }}</span>
            </div>
            <ul class="alloc">
              <li v-for="a in request.allocations" :key="a.id">
                <span><b>{{ a.engineer.display_name }}</b> <span class="muted">{{ a.engineer.job_title }}</span></span>
                <span class="mono">{{ fmtDate(a.start_date) }} – {{ fmtDate(a.end_date) }}</span>
              </li>
            </ul>
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
.candidates {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.candidate {
  height: auto !important;
  padding: 8px 12px !important;
  margin: 0 !important;
  width: 100%;
}
.candidate :deep(.el-checkbox__label) {
  flex: 1;
  min-width: 0;
}
.cand-body {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  white-space: normal;
}
.pref {
  margin-left: 6px;
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
.details {
  display: grid;
  grid-template-columns: 200px minmax(0, 1fr);
  gap: 10px 16px;
  margin: 0;
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
@media (max-width: 1020px) {
  .layout {
    grid-template-columns: minmax(0, 1fr);
  }
}
@media (max-width: 640px) {
  .details {
    grid-template-columns: minmax(0, 1fr);
    gap: 2px;
  }
  .details dd {
    margin-bottom: 8px;
  }
}
</style>
