<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { emailActionApi } from '@/api'
import { ApiError } from '@/api/http'
import EngineerPicker from '@/components/EngineerPicker.vue'
import StatusTag from '@/components/StatusTag.vue'
import UrgentBadge from '@/components/UrgentBadge.vue'
import type { Action, EmailActionResult, EmailActionView } from '@/types/api'
import { errorMessage } from '@/utils/feedback'
import { fmtDateTime, fmtRange, STEP_LABEL, TYPE_LABEL } from '@/utils/format'

const route = useRoute()
const token = String(route.params.token)

const view = ref<EmailActionView | null>(null)
const loading = ref(true)
const loadError = ref<{ title: string; detail: string } | null>(null)
const action = ref<Action>('APPROVE')
const comment = ref('')
const picks = ref<Record<number, number>>({})
const submitting = ref(false)
const actionError = ref<string | null>(null)
const result = ref<EmailActionResult | null>(null)
/** One-click approval from the director's email: approve as soon as the page is visible. */
const instant = ref(false)

const r = computed(() => view.value?.request ?? null)
const isChange = computed(() => view.value?.step === 'CHANGE_REVIEW')
const needsEngineers = computed(
  () => action.value === 'APPROVE' && (view.value?.step === 'TL_REVIEW' || isChange.value),
)
const commentRequired = computed(() => action.value !== 'APPROVE')
const headcount = computed(() => (isChange.value ? view.value?.change?.new_headcount : r.value?.headcount) ?? null)

const LABELS: Record<string, string> = {
  APPROVE: 'Approve',
  RETURN: 'Return to requester',
  REJECT: 'Reject',
}
const confirmLabel = computed(() => {
  if (action.value === 'APPROVE') {
    if (isChange.value) return 'Approve change'
    return view.value?.step === 'TL_REVIEW' ? 'Approve and send to director' : 'Approve and confirm resources'
  }
  if (action.value === 'REJECT') return isChange.value ? 'Reject change' : 'Reject request'
  return 'Return to requester'
})

onMounted(async () => {
  try {
    const v = await emailActionApi.view(token)
    view.value = v
    picks.value = Object.fromEntries(v.preselected.map((p) => [p.engineer_id, p.allocation_pct]))
    const wanted = String(route.query.do ?? '').toUpperCase() as Action
    if (v.actions.includes(wanted)) action.value = wanted
    if (route.query.instant === '1' && wanted === 'APPROVE' && v.step === 'DIRECTOR_APPROVAL') {
      instant.value = true
      whenVisible(confirm)
    }
  } catch (e) {
    const status = e instanceof ApiError ? e.status : 0
    loadError.value = {
      title: status === 409 ? 'Already handled' : status === 410 ? 'Link expired' : 'This link cannot be used',
      detail: errorMessage(e),
    }
  } finally {
    loading.value = false
  }
})

/** Run once the tab is in front of the person, so a link opened in the background does not act unseen. */
function whenVisible(run: () => void): void {
  if (document.visibilityState === 'visible') {
    run()
    return
  }
  const onChange = (): void => {
    if (document.visibilityState === 'visible') {
      document.removeEventListener('visibilitychange', onChange)
      run()
    }
  }
  document.addEventListener('visibilitychange', onChange)
}

async function confirm(): Promise<void> {
  actionError.value = null
  if (commentRequired.value && !comment.value.trim()) {
    actionError.value = 'Add a comment so the requester knows what to change or why it was declined.'
    return
  }
  if (needsEngineers.value && !Object.keys(picks.value).length) {
    actionError.value = 'Select at least one engineer.'
    return
  }
  submitting.value = true
  try {
    result.value = await emailActionApi.act(token, {
      action: action.value,
      comment: comment.value.trim() || null,
      allocations: needsEngineers.value
        ? Object.entries(picks.value).map(([id, pct]) => ({ engineer_id: Number(id), allocation_pct: pct }))
        : [],
    })
  } catch (e) {
    actionError.value = errorMessage(e)
    instant.value = false
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="act">
    <header class="brand">
      <span>Engineering</span>
      <b>Resource Requests</b>
    </header>

    <main v-loading="loading" class="body">
      <section v-if="loadError" class="panel">
        <h1>{{ loadError.title }}</h1>
        <p class="sub">{{ loadError.detail }}</p>
        <RouterLink to="/">Sign in to the system</RouterLink>
      </section>

      <section v-else-if="result" class="panel done">
        <div class="tick" aria-hidden="true">✓</div>
        <h1>{{ result.status === 'APPROVED' ? 'Approved' : 'Done' }}</h1>
        <p>{{ result.message }}</p>
        <dl v-if="r" class="details compact">
          <dt>Project</dt><dd>{{ r.project_name }} · {{ r.client_name }}</dd>
          <dt>Planned period</dt><dd>{{ fmtRange(r.planned_start, r.planned_end) }}</dd>
          <template v-if="r.allocations.length">
            <dt>Engineers</dt><dd>{{ r.allocations.map((a) => `${a.engineer.display_name} (${a.allocation_pct}%)`).join(', ') }}</dd>
          </template>
        </dl>
        <p class="muted">The requester and the people involved have been notified by email. You can close this page.</p>
        <RouterLink :to="`/requests/${result.request_id}`">Open {{ result.display_no }} in the system</RouterLink>
      </section>

      <section v-else-if="instant && view" class="panel done">
        <h1>Approving {{ view.request.display_no }}…</h1>
        <p class="muted">{{ view.request.project_name }} · {{ view.request.client_name }}</p>
      </section>

      <template v-else-if="view && r">
        <div class="head">
          <div>
            <div class="mono muted">{{ r.display_no }} · {{ STEP_LABEL[view.step] }} for {{ view.assignee.display_name }}</div>
            <h1>{{ r.project_name }}</h1>
            <p class="sub">{{ r.client_name }} · requested by {{ r.requester.display_name }}</p>
          </div>
          <div class="tags">
            <UrgentBadge v-if="r.is_urgent" />
            <StatusTag :status="r.status" />
          </div>
        </div>

        <section class="panel decision">
          <h2>Your decision</h2>
          <el-radio-group v-model="action">
            <el-radio-button v-for="a in view.actions" :key="a" :value="a">
              {{ isChange && a !== 'RETURN' ? `${LABELS[a]} change` : LABELS[a] }}
            </el-radio-button>
          </el-radio-group>

          <template v-if="needsEngineers">
            <p v-if="isChange" class="muted no-margin">Availability below is for the new period of the change.</p>
            <EngineerPicker v-model="picks" :candidates="view.candidates" :headcount="headcount" />
          </template>

          <el-input
            v-model="comment"
            type="textarea"
            :autosize="{ minRows: 2 }"
            maxlength="5000"
            :placeholder="commentRequired ? 'Comment (required)' : 'Comment (optional; required if you assign fewer engineers than requested)'"
          />
          <el-alert v-if="actionError" :title="actionError" type="error" :closable="false" show-icon />
          <div class="buttons">
            <el-button :type="action === 'REJECT' ? 'danger' : 'primary'" :loading="submitting" @click="confirm">
              {{ confirmLabel }}
            </el-button>
            <span class="muted small">This link works until {{ fmtDateTime(view.expires_at) }} or until the request is handled.</span>
          </div>
        </section>

        <section v-if="view.change" class="panel">
          <h2>Requested change</h2>
          <dl class="details">
            <dt>Planned period</dt>
            <dd>{{ fmtRange(view.change.old_start, view.change.old_end) }} → <b>{{ fmtRange(view.change.new_start, view.change.new_end) }}</b></dd>
            <dt>Engineers required</dt>
            <dd>{{ view.change.old_headcount }} → <b>{{ view.change.new_headcount }}</b></dd>
            <dt>Reason</dt>
            <dd class="pre">{{ view.change.reason }}</dd>
          </dl>
        </section>

        <section class="panel">
          <h2>Request details</h2>
          <dl class="details">
            <dt>Request type</dt><dd>{{ r.request_type ? TYPE_LABEL[r.request_type] : '—' }}</dd>
            <dt>Priority</dt>
            <dd>{{ r.is_urgent ? 'Urgent' : 'Normal' }}<template v-if="r.notice_working_days !== null"> · {{ r.notice_working_days }} working days notice</template></dd>
            <dt>Project / WBS code</dt><dd>{{ r.wbs_code || '—' }}</dd>
            <dt>Type of support</dt><dd>{{ r.support_type?.name }}<template v-if="r.team"> · {{ r.team.name }}</template></dd>
            <dt>Engineers required</dt><dd>{{ r.headcount }}</dd>
            <dt>Preferred engineers</dt><dd>{{ r.preferred_engineers.map((u) => u.display_name).join(', ') || '—' }}</dd>
            <dt>Man-days awarded</dt><dd>{{ r.man_days ?? 'Not applicable' }}</dd>
            <dt>Planned period</dt><dd>{{ fmtRange(r.planned_start, r.planned_end) }}</dd>
            <template v-if="r.allocations.length">
              <dt>Engineers assigned</dt>
              <dd>{{ r.allocations.map((a) => `${a.engineer.display_name} (${a.allocation_pct}%)`).join(', ') }}</dd>
            </template>
            <dt>Scope description</dt><dd class="pre">{{ r.scope_description }}</dd>
            <dt>Task schedule</dt><dd class="pre">{{ r.task_schedule }}</dd>
            <template v-if="r.is_urgent">
              <dt>Urgent justification</dt><dd class="pre">{{ r.urgent_justification }}</dd>
            </template>
          </dl>
        </section>
      </template>
    </main>
  </div>
</template>

<style scoped>
.act {
  min-height: 100%;
  background: linear-gradient(180deg, var(--erf-rail) 0 180px, var(--erf-bg) 180px);
  padding: 0 16px 48px;
}
.brand {
  max-width: 860px;
  margin: 0 auto;
  padding: 20px 0;
  display: flex;
  flex-direction: column;
  color: #fff;
}
.brand span {
  font-family: var(--erf-mono);
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  opacity: 0.7;
}
.body {
  max-width: 860px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 200px;
}
.head {
  background: var(--erf-surface);
  border: 1px solid var(--erf-line);
  border-radius: var(--erf-radius);
  padding: 18px;
  display: flex;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.tags {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}
.decision {
  border-color: color-mix(in srgb, var(--erf-accent) 45%, var(--erf-line));
}
.done {
  text-align: center;
  align-items: center;
}
.done .details {
  text-align: left;
  width: min(560px, 100%);
}
.done h1 {
  color: var(--erf-ok);
}
.tick {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: var(--erf-ok);
  color: #fff;
  font-size: 30px;
  line-height: 56px;
  font-weight: 700;
}
.details.compact {
  gap: 4px 16px;
}
.buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
}
.small {
  font-size: 12px;
}
.no-margin {
  margin: 0;
}
.details {
  display: grid;
  grid-template-columns: 180px minmax(0, 1fr);
  gap: 8px 16px;
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
