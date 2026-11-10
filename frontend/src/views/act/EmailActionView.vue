<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { emailActionApi } from '@/api'
import { ApiError } from '@/api/http'
import EngineerPicker from '@/components/EngineerPicker.vue'
import StatusTag from '@/components/StatusTag.vue'
import type { Action, EmailActionResult, EmailActionView, EventOut } from '@/types/api'
import { errorMessage } from '@/utils/feedback'
import { EVENT_LABEL, fmtDate, fmtDateTime, fmtRange, STEP_LABEL, TYPE_LABEL } from '@/utils/format'

const route = useRoute()
const token = String(route.params.token)

const view = ref<EmailActionView | null>(null)
const loading = ref(true)
const loadError = ref<{ title: string; detail: string } | null>(null)
const action = ref<Action>('APPROVE')
const comment = ref('')
const commentBox = ref<HTMLTextAreaElement | null>(null)
const decisionSection = ref<HTMLElement | null>(null)
const picks = ref<Record<number, number>>({})
const submitting = ref(false)
const actionError = ref<string | null>(null)
const result = ref<EmailActionResult | null>(null)

const r = computed(() => view.value?.request ?? null)
const isChange = computed(() => view.value?.step === 'CHANGE_REVIEW')
const isTeamLeader = computed(() => view.value?.step === 'TL_REVIEW')
const needsEngineers = computed(() => action.value === 'APPROVE' && (isTeamLeader.value || isChange.value))
const commentRequired = computed(() => action.value !== 'APPROVE')
const headcount = computed(() => (isChange.value ? view.value?.change?.new_headcount : r.value?.headcount) ?? null)

const VERB: Record<string, string> = { APPROVE: 'approve', RETURN: 'return', REJECT: 'reject' }
const confirmLabel = computed(() => {
  if (isChange.value) return action.value === 'APPROVE' ? 'Confirm change approval' : 'Confirm change rejection'
  if (action.value === 'APPROVE') return 'Confirm approval'
  return 'Confirm rejection'
})
const decisionTitle = computed(() => {
  const what = isChange.value ? 'this change' : 'this request'
  if (action.value === 'APPROVE') {
    if (isChange.value) return 'You are approving this change'
    return isTeamLeader.value ? 'You are approving and assigning engineers' : 'You are giving final approval'
  }
  return `You are rejecting ${what}`
})
const decisionHint = computed(() => {
  if (action.value === 'APPROVE') {
    if (isChange.value) return 'Choose the engineers for the new period and how much of each person’s time it needs.'
    if (isTeamLeader.value) return 'Choose the engineers and how much of each person’s time this work needs. The request then goes to the director.'
    return 'The engineers below are confirmed and everyone involved is notified by email.'
  }
  if (isChange.value) return 'The request keeps its current dates and engineers. Tell the requester why.'
  return 'The requester can revise the request and submit it again, or withdraw it. Tell them why.'
})
const otherActions = computed(() => (view.value?.actions ?? []).filter((a) => a !== action.value))
const otherLabel = (a: Action) =>
  a === 'APPROVE' ? (isChange.value ? 'Approve the change instead' : 'Approve instead') : isChange.value ? 'Reject the change instead' : 'Reject instead'

/** Comments made at earlier steps, such as the team leader's note to the director. */
const notes = computed<EventOut[]>(() => (r.value?.events ?? []).filter((e) => e.comment && e.action !== 'CREATE'))

const facts = computed(() => {
  const x = r.value
  if (!x) return []
  return [
    ['Client', x.client_name || '—'],
    ['Requested by', x.requester.display_name],
    ['Planned period', fmtRange(x.planned_start, x.planned_end)],
    ['Priority', x.is_urgent ? `Urgent · ${x.notice_working_days ?? '?'} working days notice` : `Normal · ${x.notice_working_days ?? '?'} working days notice`],
    ['Type of support', `${x.support_type?.name ?? '—'}${x.team ? ` · ${x.team.name}` : ''}`],
    ['Engineers needed', String(x.headcount ?? '—')],
    ['Request type', x.request_type ? TYPE_LABEL[x.request_type] : '—'],
    ['Man-days', x.man_days === null ? 'Not applicable' : String(x.man_days)],
    ['WBS code', x.wbs_code || '—'],
    ['Preferred engineers', x.preferred_engineers.map((u) => u.display_name).join(', ') || '—'],
  ]
})

onMounted(async () => {
  try {
    const v = await emailActionApi.view(token)
    view.value = v
    picks.value = Object.fromEntries(v.preselected.map((p) => [p.engineer_id, p.allocation_pct]))
    const wanted = String(route.query.do ?? '').toUpperCase() as Action
    if (v.actions.includes(wanted)) action.value = wanted
  } catch (e) {
    const status = e instanceof ApiError ? e.status : 0
    loadError.value = {
      title: status === 409 ? 'Already handled' : status === 410 ? 'This link has expired' : 'This link cannot be used',
      detail: errorMessage(e),
    }
  } finally {
    loading.value = false
  }
})

async function switchTo(a: Action): Promise<void> {
  action.value = a
  actionError.value = null
  await nextTick()
  decisionSection.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  if (a !== 'APPROVE') commentBox.value?.focus({ preventScroll: true })
}

async function confirm(): Promise<void> {
  actionError.value = null
  if (commentRequired.value && !comment.value.trim()) {
    actionError.value = `Add a comment before you ${VERB[action.value]}: the requester needs to know why.`
    decisionSection.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    commentBox.value?.focus({ preventScroll: true })
    return
  }
  if (needsEngineers.value && !Object.keys(picks.value).length) {
    actionError.value = 'Select at least one engineer.'
    decisionSection.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
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
    window.scrollTo({ top: 0 })
  } catch (e) {
    actionError.value = errorMessage(e)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="act">
    <header class="top">
      <div class="inner">
        <span class="brand">Engineering Resource Requests</span>
      </div>
    </header>

    <main v-loading="loading" class="inner page">
      <!-- Link cannot be used -->
      <section v-if="loadError" class="card state">
        <h1>{{ loadError.title }}</h1>
        <p>{{ loadError.detail }}</p>
        <RouterLink to="/" class="text-link">Sign in to the system</RouterLink>
      </section>

      <!-- Decision recorded -->
      <section v-else-if="result" class="card state done">
        <div class="tick" aria-hidden="true">✓</div>
        <h1>{{ result.status === 'APPROVED' ? 'Approved' : 'Done' }}</h1>
        <p>{{ result.message }}</p>
        <dl v-if="r" class="facts">
          <div><dt>Project</dt><dd>{{ r.project_name }}</dd></div>
          <div><dt>Planned period</dt><dd>{{ fmtRange(r.planned_start, r.planned_end) }}</dd></div>
        </dl>
        <p class="muted small">Everyone involved has been notified by email. You can close this page.</p>
        <RouterLink :to="`/requests/${result.request_id}`" class="text-link">Open {{ result.display_no }} in the system</RouterLink>
      </section>

      <template v-else-if="view && r">
        <!-- Who and what -->
        <section class="card head">
          <div class="head-row">
            <span class="ref">{{ r.display_no }}</span>
            <span v-if="r.is_urgent" class="urgent">URGENT</span>
            <StatusTag :status="r.status" />
          </div>
          <h1>{{ r.project_name }}</h1>
          <p class="muted">{{ STEP_LABEL[view.step] }} for <b>{{ view.assignee.display_name }}</b></p>
        </section>

        <!-- The change being reviewed -->
        <section v-if="view.change" class="card">
          <h2>Requested change</h2>
          <div class="change">
            <div>
              <span class="label">Planned period</span>
              <span class="old">{{ fmtRange(view.change.old_start, view.change.old_end) }}</span>
              <span class="new">{{ fmtRange(view.change.new_start, view.change.new_end) }}</span>
            </div>
            <div>
              <span class="label">Engineers needed</span>
              <span class="old">{{ view.change.old_headcount }}</span>
              <span class="new">{{ view.change.new_headcount }}</span>
            </div>
          </div>
          <p class="block">{{ view.change.reason }}</p>
        </section>

        <!-- Key facts -->
        <section class="card">
          <h2>Request</h2>
          <dl class="facts">
            <div v-for="[label, value] in facts" :key="label"><dt>{{ label }}</dt><dd>{{ value }}</dd></div>
          </dl>
        </section>

        <!-- Engineers proposed by the team leader (shown to the director) -->
        <section v-if="r.allocations.length && !needsEngineers" class="card">
          <h2>{{ r.allocations[0]?.status === 'CONFIRMED' ? 'Assigned engineers' : 'Engineers proposed by the team leader' }}</h2>
          <ul class="people">
            <li v-for="a in r.allocations" :key="a.id">
              <span>{{ a.engineer.display_name }}<small v-if="a.engineer.job_title">{{ a.engineer.job_title }}</small></span>
              <span class="pct">{{ a.allocation_pct }}%</span>
            </li>
          </ul>
        </section>

        <!-- Comments from earlier steps -->
        <section v-if="notes.length" class="card">
          <h2>Comments</h2>
          <div v-for="e in notes" :key="e.id" class="note">
            <span class="note-who">{{ e.actor?.display_name ?? 'System' }} · {{ EVENT_LABEL[e.action] ?? e.action }} · {{ fmtDateTime(e.created_at) }}</span>
            <p class="block">{{ e.comment }}</p>
          </div>
        </section>

        <section class="card">
          <h2>Scope of work</h2>
          <p class="block">{{ r.scope_description || '—' }}</p>
          <h2 class="spaced">Task schedule</h2>
          <p class="block">{{ r.task_schedule || '—' }}</p>
          <template v-if="r.is_urgent">
            <h2 class="spaced">Why it is urgent</h2>
            <p class="block">{{ r.urgent_justification || '—' }}</p>
          </template>
          <p class="muted small spaced">Submitted {{ fmtDate(r.first_submitted_at) }} · {{ r.round > 1 ? `round ${r.round}` : 'first submission' }}</p>
        </section>

        <!-- Decision -->
        <section ref="decisionSection" class="card decision" :class="`is-${action.toLowerCase()}`">
          <h2>{{ decisionTitle }}</h2>
          <p class="muted">{{ decisionHint }}</p>

          <EngineerPicker v-if="needsEngineers" v-model="picks" :candidates="view.candidates" :headcount="headcount" />

          <label class="comment-label" for="act-comment">
            Comment <span class="muted">{{ commentRequired ? '(required)' : '(optional)' }}</span>
          </label>
          <textarea
            id="act-comment"
            ref="commentBox"
            v-model="comment"
            rows="3"
            maxlength="5000"
            :placeholder="commentRequired ? 'Tell the requester why' : 'Add a note for the requester'"
          ></textarea>

          <div v-if="otherActions.length" class="others">
            <span class="muted small">Not what you want?</span>
            <button v-for="a in otherActions" :key="a" type="button" class="link-btn" :class="{ danger: a === 'REJECT' }" @click="switchTo(a)">
              {{ otherLabel(a) }}
            </button>
          </div>
        </section>

        <!-- Always-visible confirmation bar -->
        <div class="bar">
          <p v-if="actionError" class="bar-error" role="alert">{{ actionError }}</p>
          <button type="button" class="confirm" :class="`is-${action.toLowerCase()}`" :disabled="submitting" @click="confirm">
            {{ submitting ? 'Saving…' : confirmLabel }}
          </button>
          <span class="bar-note">No sign-in needed. Link valid until {{ fmtDateTime(view.expires_at) }}.</span>
        </div>
      </template>
    </main>
  </div>
</template>

<style scoped>
.act {
  min-height: 100%;
  background: var(--erf-bg);
}
.inner {
  max-width: 720px;
  margin: 0 auto;
  padding-left: max(16px, env(safe-area-inset-left, 0px));
  padding-right: max(16px, env(safe-area-inset-right, 0px));
}
.top {
  background: var(--erf-rail);
  color: #fff;
  padding-top: env(safe-area-inset-top, 0px);
}
.top .inner {
  padding-block: 14px;
}
.brand {
  font-weight: 600;
  font-size: 14px;
  letter-spacing: 0.01em;
}
.page {
  padding-block: 16px 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 240px;
}
.card {
  background: var(--erf-surface);
  border: 1px solid var(--erf-line);
  border-radius: 10px;
  padding: 18px;
  min-width: 0;
}
h1 {
  font-size: 22px;
  line-height: 1.25;
  margin: 6px 0 4px;
  overflow-wrap: anywhere;
}
h2 {
  font-size: 15px;
  margin: 0 0 10px;
}
.spaced {
  margin-top: 18px;
}
p {
  margin: 0;
}
.small {
  font-size: 13px;
}
.head-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.ref {
  font-family: var(--erf-mono);
  font-size: 13px;
  color: var(--erf-muted);
}
.urgent {
  font-family: var(--erf-mono);
  font-size: 11px;
  letter-spacing: 0.06em;
  color: var(--erf-bad);
  border: 1px solid color-mix(in srgb, var(--erf-bad) 50%, transparent);
  border-radius: 4px;
  padding: 0 6px;
}
.facts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px 18px;
  margin: 0;
}
.facts div {
  min-width: 0;
}
.facts dt {
  font-size: 12px;
  color: var(--erf-muted);
  margin-bottom: 2px;
}
.facts dd {
  margin: 0;
  font-size: 15px;
  overflow-wrap: anywhere;
}
.block {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  line-height: 1.6;
  font-size: 15px;
}
.people {
  list-style: none;
  margin: 0;
  padding: 0;
}
.people li {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 10px 0;
  border-top: 1px solid var(--erf-line);
}
.people li:first-child {
  border-top: 0;
  padding-top: 0;
}
.people small {
  display: block;
  color: var(--erf-muted);
  font-size: 12px;
}
.pct {
  font-family: var(--erf-mono);
  font-weight: 600;
  background: var(--erf-surface-2);
  border-radius: 999px;
  padding: 2px 10px;
}
.note + .note {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--erf-line);
}
.note-who {
  display: block;
  font-size: 12px;
  color: var(--erf-muted);
  margin-bottom: 4px;
}
.change {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 12px;
}
.change .label {
  display: block;
  font-size: 12px;
  color: var(--erf-muted);
}
.change .old {
  display: block;
  text-decoration: line-through;
  color: var(--erf-muted);
}
.change .new {
  display: block;
  font-weight: 600;
}
.decision {
  border-width: 2px;
  border-color: var(--erf-accent);
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.decision.is-reject {
  border-color: var(--erf-bad);
}
.decision.is-return {
  border-color: var(--erf-bad);
}
.decision h2 {
  font-size: 17px;
  margin: 0;
}
.comment-label {
  font-weight: 500;
  font-size: 14px;
  margin-top: 4px;
}
textarea {
  width: 100%;
  font: inherit;
  font-size: 16px; /* 16px stops iPhone from zooming into the field */
  color: inherit;
  background: var(--erf-surface);
  border: 1px solid var(--erf-line);
  border-radius: 8px;
  padding: 10px 12px;
  resize: vertical;
}
textarea:focus {
  outline: 2px solid var(--erf-accent);
  outline-offset: 1px;
}
.others {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 14px;
  margin-top: 4px;
}
.link-btn {
  background: none;
  border: 0;
  padding: 8px 0;
  font: inherit;
  font-size: 14px;
  color: var(--erf-accent);
  text-decoration: underline;
  cursor: pointer;
}
.link-btn.danger {
  color: var(--erf-bad);
}
.bar {
  position: sticky;
  bottom: 0;
  margin-top: 4px;
  margin-left: calc(-1 * max(16px, env(safe-area-inset-left, 0px)));
  margin-right: calc(-1 * max(16px, env(safe-area-inset-right, 0px)));
  padding-top: 12px;
  padding-bottom: calc(12px + env(safe-area-inset-bottom, 0px));
  padding-left: max(16px, env(safe-area-inset-left, 0px));
  padding-right: max(16px, env(safe-area-inset-right, 0px));
  background: color-mix(in srgb, var(--erf-surface) 94%, transparent);
  backdrop-filter: blur(6px);
  border-top: 1px solid var(--erf-line);
  display: flex;
  flex-direction: column;
  gap: 6px;
  z-index: 5;
}
.bar-error {
  color: var(--erf-bad);
  font-size: 14px;
}
.confirm {
  width: 100%;
  min-height: 50px;
  border: 0;
  border-radius: 10px;
  font: inherit;
  font-size: 17px;
  font-weight: 600;
  color: #fff;
  background: var(--erf-accent);
  cursor: pointer;
}
.confirm.is-reject {
  background: var(--erf-bad);
}
.confirm.is-return {
  background: var(--erf-bad);
}
.confirm:disabled {
  opacity: 0.6;
  cursor: progress;
}
.confirm:focus-visible {
  outline: 3px solid color-mix(in srgb, var(--erf-accent) 45%, transparent);
  outline-offset: 2px;
}
.bar-note {
  font-size: 12px;
  color: var(--erf-muted);
  text-align: center;
}
.state {
  display: flex;
  flex-direction: column;
  gap: 10px;
  align-items: flex-start;
}
.done {
  align-items: center;
  text-align: center;
}
.done .facts {
  text-align: left;
  width: 100%;
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
.text-link {
  color: var(--erf-accent);
  font-weight: 500;
  padding: 6px 0;
}
@media (min-width: 640px) {
  .facts {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .bar {
    margin-left: 0;
    margin-right: 0;
    border: 1px solid var(--erf-line);
    border-bottom: 0;
    border-radius: 10px 10px 0 0;
  }
}
@media (prefers-reduced-motion: reduce) {
  * {
    scroll-behavior: auto !important;
  }
}
</style>
