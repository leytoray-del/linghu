<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { requestApi } from '@/api'
import { ApiError } from '@/api/http'
import NoticePanel from '@/components/NoticePanel.vue'
import { useLookupStore } from '@/stores/lookups'
import type { NoticePreview, RequestDetail, RequestInput, RequestType } from '@/types/api'
import { errorMessage, fieldErrors, showError, showSuccess } from '@/utils/feedback'

const route = useRoute()
const router = useRouter()
const lookups = useLookupStore()

const editingId = computed(() => (route.params.id ? Number(route.params.id) : null))
const existing = ref<RequestDetail | null>(null)
const copiedFrom = ref<string | null>(null)
const loading = ref(true)
const saving = ref<'draft' | 'submit' | null>(null)
const errors = ref<Record<string, string>>({})
const formError = ref<string | null>(null)
const preview = ref<NoticePreview | null>(null)
const previewLoading = ref(false)

const form = reactive<RequestInput>({
  request_type: 'PROJECT',
  priority_declared: 'NORMAL',
  project_name: null,
  wbs_code: null,
  client_name: null,
  support_type_id: null,
  headcount: 1,
  preferred_engineer_ids: [],
  preferred_engineers_note: null,
  man_days: null,
  planned_start: null,
  planned_end: null,
  scope_description: null,
  task_schedule: null,
  urgent_justification: null,
})

const team = computed(() => lookups.teamFor(form.support_type_id))
const isProject = computed(() => form.request_type === 'PROJECT')
const shortNotice = computed(() => preview.value?.is_short_notice ?? false)
const showJustification = computed(() => shortNotice.value || form.priority_declared === 'URGENT')
const isReturned = computed(() => existing.value?.status === 'RETURNED')
const lastReturn = computed(() =>
  existing.value ? [...existing.value.events].reverse().find((e) => e.action === 'RETURN') : undefined,
)
const today = computed(() => lookups.data?.today ?? '')

function disabledStart(d: Date): boolean {
  return today.value ? d < new Date(`${today.value}T00:00:00`) : false
}
function disabledEnd(d: Date): boolean {
  const from = form.planned_start ?? today.value
  return from ? d < new Date(`${from}T00:00:00`) : false
}

let previewTimer: number | undefined
watch(
  () => form.planned_start,
  (start) => {
    window.clearTimeout(previewTimer)
    if (!start) {
      preview.value = null
      return
    }
    previewLoading.value = true
    previewTimer = window.setTimeout(async () => {
      try {
        preview.value = await requestApi.noticePreview(start)
      } catch (e) {
        showError(e)
      } finally {
        previewLoading.value = false
      }
    }, 200)
  },
)

// Clear a field's server-side error as soon as the user changes that field.
for (const key of Object.keys(form) as (keyof RequestInput)[]) {
  watch(
    () => form[key],
    () => {
      if (errors.value[key]) {
        const next = { ...errors.value }
        delete next[key]
        errors.value = next
        if (!Object.keys(next).length) formError.value = null
      }
    },
    { deep: true },
  )
}

/** True while Urgent was chosen by the form because of short notice, not by the user. */
const autoUrgent = ref(false)

watch(shortNotice, (short) => {
  if (short) {
    if (form.priority_declared !== 'URGENT') autoUrgent.value = true
    form.priority_declared = 'URGENT'
  } else if (autoUrgent.value) {
    // The new date gives enough notice, so undo the automatic choice. A user's own choice stays.
    form.priority_declared = 'NORMAL'
    autoUrgent.value = false
  }
})

watch(
  () => form.support_type_id,
  (next, prev) => {
    if (prev !== null && next !== prev) form.preferred_engineer_ids = []
  },
)

onMounted(async () => {
  try {
    await lookups.load(true)
    if (editingId.value) {
      const r = await requestApi.get(editingId.value)
      if (!r.can_edit) {
        showError(new ApiError(403, 'forbidden', 'This request can no longer be edited.'))
        await router.replace({ name: 'request-detail', params: { id: r.id } })
        return
      }
      existing.value = r
      Object.assign(form, {
        request_type: r.request_type,
        priority_declared: r.priority_declared,
        project_name: r.project_name,
        wbs_code: r.wbs_code,
        client_name: r.client_name,
        support_type_id: r.support_type?.id ?? null,
        headcount: r.headcount,
        preferred_engineer_ids: r.preferred_engineers.map((u) => u.id),
        preferred_engineers_note: r.preferred_engineers_note,
        man_days: r.man_days,
        planned_start: r.planned_start,
        planned_end: r.planned_end,
        scope_description: r.scope_description,
        task_schedule: r.task_schedule,
        urgent_justification: r.urgent_justification,
      })
      autoUrgent.value = r.urgency_reason === 'SHORT_NOTICE'
    } else if (route.query.copy) {
      // Copy the content of an earlier request. Dates, priority and justification start fresh.
      const src = await requestApi.get(Number(route.query.copy))
      copiedFrom.value = src.display_no
      Object.assign(form, {
        request_type: src.request_type,
        project_name: src.project_name,
        wbs_code: src.wbs_code,
        client_name: src.client_name,
        support_type_id: lookups.supportType(src.support_type?.id ?? null) ? src.support_type?.id ?? null : null,
        headcount: src.headcount,
        preferred_engineer_ids: src.preferred_engineers.map((u) => u.id),
        preferred_engineers_note: src.preferred_engineers_note,
        man_days: src.man_days,
        scope_description: src.scope_description,
        task_schedule: src.task_schedule,
      })
    }
  } catch (e) {
    showError(e)
  } finally {
    loading.value = false
  }
})

function payload(): RequestInput {
  return {
    ...form,
    man_days: isProject.value || form.man_days ? form.man_days : null,
    urgent_justification: showJustification.value ? form.urgent_justification : null,
  }
}

async function save(submit: boolean): Promise<void> {
  errors.value = {}
  formError.value = null
  saving.value = submit ? 'submit' : 'draft'
  try {
    let result: RequestDetail
    if (existing.value) {
      result = await requestApi.update(existing.value.id, payload(), existing.value.version)
      existing.value = result
      if (submit) result = await requestApi.submit(result.id, result.version)
    } else {
      result = await requestApi.create(payload(), submit)
    }
    if (submit) {
      const handlers = result.current_handlers.map((h) => h.display_name).join(', ')
      showSuccess(`${result.display_no} submitted. ${handlers} has been notified by email.`)
    } else {
      showSuccess('Draft saved. Only you can see it until you submit it.')
    }
    await router.push({ name: 'request-detail', params: { id: result.id } })
  } catch (e) {
    errors.value = fieldErrors(e)
    formError.value = errorMessage(e)
  } finally {
    saving.value = null
  }
}
</script>

<template>
  <div v-loading="loading" class="page">
    <div class="page-head">
      <div>
        <h1>{{ existing ? `Revise ${existing.display_no}` : 'New resource request' }}</h1>
        <p class="sub">
          {{
            isReturned
              ? 'Update the request based on the comment below, then resubmit it. It will go back to the team leader.'
              : copiedFrom
                ? `Copied from ${copiedFrom}. Check every field and choose new dates before you submit.`
                : 'Submit at least 5 working days before the planned start date. Fields marked * are required.'
          }}
        </p>
      </div>
    </div>

    <el-alert
      v-if="lastReturn && isReturned"
      type="warning"
      :closable="false"
      show-icon
      :title="`Rejected by ${lastReturn.actor?.display_name ?? 'reviewer'}`"
      :description="lastReturn.comment ?? ''"
    />

    <el-form class="layout" label-position="top" @submit.prevent="save(true)">
      <div class="main-col">
        <section class="panel">
          <h2>Project / opportunity</h2>
          <div class="grid">
            <el-form-item label="Request type" required :error="errors.request_type" class="full">
              <el-radio-group :model-value="form.request_type ?? undefined" @update:model-value="(v) => (form.request_type = v as RequestType)">
                <el-radio-button value="PROJECT">Project</el-radio-button>
                <el-radio-button value="PRESALES">Pre-sales</el-radio-button>
                <el-radio-button value="OTHER">Other</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="Project / opportunity name" required :error="errors.project_name" class="full" for="f-project">
              <el-input id="f-project" v-model="form.project_name" maxlength="200" placeholder="e.g. CSPL Data Migration Phase 2" />
            </el-form-item>
            <el-form-item label="Project / WBS code" :error="errors.wbs_code" for="f-wbs">
              <el-input id="f-wbs" v-model="form.wbs_code" maxlength="64" placeholder="If any" />
            </el-form-item>
            <el-form-item label="Client name" required :error="errors.client_name" for="f-client">
              <el-input id="f-client" v-model="form.client_name" maxlength="200" />
            </el-form-item>
          </div>
        </section>

        <section class="panel">
          <h2>Resources</h2>
          <div class="grid">
            <el-form-item label="Type of support" required :error="errors.support_type_id" for="f-type">
              <el-select id="f-type" v-model="form.support_type_id" placeholder="Select…">
                <el-option v-for="s in lookups.data?.support_types ?? []" :key="s.id" :label="s.name" :value="s.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="Number of engineers / developers" required :error="errors.headcount" for="f-headcount">
              <el-input-number id="f-headcount" v-model="form.headcount" :min="1" :max="50" />
            </el-form-item>
            <el-form-item label="Preferred engineers / developers" :error="errors.preferred_engineer_ids" class="full">
              <el-select
                v-model="form.preferred_engineer_ids"
                multiple
                :disabled="!team"
                :placeholder="team ? 'Optional' : 'Choose the type of support first'"
              >
                <el-option v-for="e in team?.engineers ?? []" :key="e.id" :label="e.display_name" :value="e.id">
                  <span>{{ e.display_name }}</span>
                  <span class="opt-hint">{{ e.skills }}</span>
                </el-option>
              </el-select>
            </el-form-item>
            <el-form-item label="Other preferences" :error="errors.preferred_engineers_note" class="full" for="f-pref-note">
              <el-input id="f-pref-note" v-model="form.preferred_engineers_note" maxlength="500" placeholder="Optional, for example someone outside the list" />
            </el-form-item>
            <el-form-item :label="`Man-days awarded / approved allocation`" :required="isProject" :error="errors.man_days" for="f-mandays">
              <el-input-number id="f-mandays" v-model="form.man_days" :min="0.5" :step="0.5" :precision="1" :controls="false" :value-on-clear="null" placeholder="Number" />
              <div class="hint">{{ isProject ? 'Required for project requests.' : 'Not required. Leave blank if not applicable.' }}</div>
            </el-form-item>
            <div></div>
            <el-form-item label="Planned start date" required :error="errors.planned_start">
              <el-date-picker v-model="form.planned_start" type="date" value-format="YYYY-MM-DD" format="D MMM YYYY" :disabled-date="disabledStart" placeholder="From" />
            </el-form-item>
            <el-form-item label="Planned end date" required :error="errors.planned_end">
              <el-date-picker v-model="form.planned_end" type="date" value-format="YYYY-MM-DD" format="D MMM YYYY" :disabled-date="disabledEnd" placeholder="To" />
            </el-form-item>
          </div>
        </section>

        <section class="panel">
          <h2>Scope and schedule</h2>
          <el-form-item label="Scope description" required :error="errors.scope_description" for="f-scope">
            <el-input
              id="f-scope"
              v-model="form.scope_description"
              type="textarea"
              :autosize="{ minRows: 5 }"
              maxlength="10000"
              placeholder="List the work items and the estimated duration."
            />
          </el-form-item>
          <el-form-item label="Detailed task schedule with timing" required :error="errors.task_schedule" for="f-schedule">
            <el-input
              id="f-schedule"
              v-model="form.task_schedule"
              type="textarea"
              :autosize="{ minRows: 3 }"
              maxlength="5000"
              placeholder="e.g. To support HSA on site 3 times per week for 2 to 3 months."
            />
          </el-form-item>
          <el-form-item label="Priority" required>
            <el-radio-group v-model="form.priority_declared">
              <el-radio-button value="NORMAL" :disabled="shortNotice">Normal</el-radio-button>
              <el-radio-button value="URGENT">Urgent</el-radio-button>
            </el-radio-group>
            <div class="hint full-width">
              {{
                shortNotice
                  ? 'Set to Urgent automatically because the notice is shorter than 5 working days.'
                  : 'Choose Urgent only if there is a business reason. A justification will be required.'
              }}
            </div>
          </el-form-item>
          <el-form-item v-if="showJustification" label="Justification for urgent request" required :error="errors.urgent_justification" for="f-justification">
            <el-input
              id="f-justification"
              v-model="form.urgent_justification"
              type="textarea"
              :autosize="{ minRows: 3 }"
              maxlength="5000"
              placeholder="Explain why the request could not be raised 5 working days in advance."
            />
          </el-form-item>
        </section>

        <el-alert v-if="formError" :title="formError" type="error" :closable="false" show-icon />

        <div class="buttons">
          <el-button @click="router.back()">Cancel</el-button>
          <el-button v-if="!isReturned" :loading="saving === 'draft'" @click="save(false)">Save draft</el-button>
          <el-button v-else :loading="saving === 'draft'" @click="save(false)">Save changes</el-button>
          <el-button type="primary" native-type="submit" :loading="saving === 'submit'">
            {{ isReturned ? 'Resubmit' : 'Submit request' }}
          </el-button>
        </div>
      </div>

      <aside class="side">
        <NoticePanel :preview="preview" :loading="previewLoading" />
        <section class="panel">
          <h2>Approval route</h2>
          <ol class="route">
            <li>
              <span class="dot">1</span>
              <div>
                <div>{{ team ? team.approvers.join(', ') || 'No team leader set up' : 'Team leader' }}</div>
                <div class="hint">{{ team ? `${team.name} · reviews and assigns engineers` : 'Decided by the type of support' }}</div>
              </div>
            </li>
            <li>
              <span class="dot">2</span>
              <div>
                <div>{{ lookups.data?.directors.join(', ') || 'Director' }}</div>
                <div class="hint">Final approval</div>
              </div>
            </li>
          </ol>
        </section>
      </aside>
    </el-form>
  </div>
</template>

<style scoped>
.layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 20px;
  align-items: start;
}
.main-col {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}
.grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  column-gap: 18px;
}
.full {
  grid-column: 1 / -1;
}
.full-width {
  width: 100%;
}
.hint {
  font-size: 12px;
  color: var(--erf-muted);
  line-height: 1.4;
}
.opt-hint {
  float: right;
  color: var(--erf-muted);
  font-size: 12px;
  margin-left: 12px;
}
.buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
}
.side {
  display: flex;
  flex-direction: column;
  gap: 14px;
  position: sticky;
  top: 16px;
}
.route {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.route li {
  display: grid;
  grid-template-columns: 22px minmax(0, 1fr);
  gap: 8px;
}
.dot {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-family: var(--erf-mono);
  font-size: 11px;
  background: var(--erf-surface-2);
  border: 1px solid var(--erf-line);
}
:deep(.el-select),
:deep(.el-date-editor.el-input),
:deep(.el-input-number) {
  width: 100%;
}
@media (max-width: 1020px) {
  .layout {
    grid-template-columns: minmax(0, 1fr);
  }
  .side {
    position: static;
  }
}
@media (max-width: 640px) {
  .grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
