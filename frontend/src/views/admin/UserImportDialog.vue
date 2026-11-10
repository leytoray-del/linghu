<script setup lang="ts">
import { computed, ref, watch } from "vue";

import { adminApi } from "@/api";
import type { UserImportResult, UserImportRow } from "@/types/api";
import { errorMessage, fieldErrors, showSuccess } from "@/utils/feedback";

const open = defineModel<boolean>({ required: true });
const emit = defineEmits<{ imported: [] }>();

/** Remembered in this browser only, so the password never has to be stored in the code. */
const PASSWORD_KEY = "erf.import.initialPassword";
function rememberedPassword(): string {
  try {
    return localStorage.getItem(PASSWORD_KEY) ?? "";
  } catch {
    return "";
  }
}

const fileName = ref("");
const fileData = ref("");
const password = ref(rememberedPassword());
const preview = ref<UserImportResult | null>(null);
const busy = ref(false);
const error = ref<string | null>(null);
const passwordError = ref("");
const input = ref<HTMLInputElement | null>(null);
const showUnchanged = ref(false);

const OUTCOME: Record<
  UserImportRow["outcome"],
  { label: string; type: "success" | "primary" | "info" | "danger" }
> = {
  create: { label: "New", type: "success" },
  update: { label: "Update", type: "primary" },
  unchanged: { label: "No change", type: "info" },
  error: { label: "Not imported", type: "danger" },
};

const rows = computed(() =>
  (preview.value?.rows ?? []).filter(
    (r) => showUnchanged.value || r.outcome !== "unchanged",
  ),
);
const toApply = computed(() =>
  preview.value ? preview.value.created + preview.value.updated : 0,
);

watch(open, (isOpen) => {
  if (!isOpen) return;
  fileName.value = "";
  fileData.value = "";
  preview.value = null;
  error.value = null;
  passwordError.value = "";
  password.value = rememberedPassword();
});

function readFile(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1] ?? "");
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

async function pick(event: Event): Promise<void> {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (!file) return;
  error.value = null;
  preview.value = null;
  if (file.size > 2 * 1024 * 1024) {
    error.value = "This file is larger than 2 MB. Split it into smaller files.";
    return;
  }
  fileName.value = file.name;
  fileData.value = await readFile(file);
  if (input.value) input.value.value = "";
  await check();
}

async function send(apply: boolean): Promise<UserImportResult | null> {
  if (!fileData.value) return null;
  if (!password.value) {
    passwordError.value =
      "Enter the password that new people will use to sign in for the first time.";
    return null;
  }
  busy.value = true;
  error.value = null;
  passwordError.value = "";
  try {
    return await adminApi.importUsers(fileData.value, password.value, apply);
  } catch (e) {
    passwordError.value = fieldErrors(e).initial_password ?? "";
    error.value = passwordError.value ? null : errorMessage(e);
    return null;
  } finally {
    busy.value = false;
  }
}

async function check(): Promise<void> {
  preview.value = await send(false);
}

async function apply(): Promise<void> {
  const result = await send(true);
  if (!result) return;
  try {
    localStorage.setItem(PASSWORD_KEY, password.value);
  } catch {
    /* Remembering the password is only a convenience. */
  }
  const parts = [`${result.created} added`, `${result.updated} updated`];
  if (result.errors) parts.push(`${result.errors} not imported`);
  showSuccess(`Import finished: ${parts.join(", ")}.`);
  open.value = false;
  emit("imported");
}
</script>

<template>
  <el-dialog
    v-model="open"
    title="Import users from Excel"
    width="min(860px, 96vw)"
    :close-on-click-modal="false"
  >
    <div class="steps">
      <div class="step">
        <b>1. Fill in the template</b>
        <span class="muted">People are matched by email address: existing people are updated, new
          people are added.</span>
        <el-button tag="a" :href="adminApi.userImportTemplateUrl" size="small">
          Download template
        </el-button>
      </div>

      <el-form label-position="top" class="step" @submit.prevent>
        <el-form-item
          label="Initial password for new people"
          :error="passwordError"
          for="import-password"
        >
          <el-input
            id="import-password"
            v-model="password"
            type="password"
            show-password
            autocomplete="new-password"
            class="password"
          />
        </el-form-item>
        <span class="muted">New people must choose their own password when they first sign
          in.</span>
      </el-form>

      <div class="step">
        <b>2. Choose the completed file</b>
        <div class="file">
          <el-button :loading="busy && !preview" @click="input?.click()">
            Choose Excel file
          </el-button>
          <span v-if="fileName" class="muted">{{ fileName }}</span>
          <input ref="input" type="file" accept=".xlsx" hidden @change="pick" />
        </div>
      </div>
    </div>

    <el-alert
      v-if="error"
      :title="error"
      type="error"
      :closable="false"
      show-icon
    />

    <template v-if="preview">
      <div class="summary">
        <span><b>{{ preview.created }}</b> to add</span>
        <span><b>{{ preview.updated }}</b> to update</span>
        <span><b>{{ preview.unchanged }}</b> with no change</span>
        <span :class="{ bad: preview.errors }"><b>{{ preview.errors }}</b> not imported</span>
        <el-checkbox
          v-if="preview.unchanged"
          v-model="showUnchanged"
          size="small"
        >
          Show people with no change
        </el-checkbox>
      </div>
      <el-table
        :data="rows"
        max-height="340"
        size="small"
        empty-text="Nothing to show."
      >
        <el-table-column label="Row" prop="row" width="60" />
        <el-table-column label="Person" min-width="220">
          <template #default="{ row }">
            <div>{{ row.name || "—" }}</div>
            <div class="muted small">{{ row.email || "(no email)" }}</div>
          </template>
        </el-table-column>
        <el-table-column label="Result" width="120">
          <template #default="{ row }">
            <el-tag
              :type="OUTCOME[row.outcome as UserImportRow['outcome']].type"
              size="small"
            >
              {{
                OUTCOME[row.outcome as UserImportRow["outcome"]].label
              }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="Details" min-width="300">
          <template #default="{ row }">
            <div v-if="row.error" class="bad">{{ row.error }}</div>
            <div v-for="c in row.changes" :key="c" class="small">{{ c }}</div>
          </template>
        </el-table-column>
      </el-table>
      <p v-if="preview.errors" class="muted small">
        Rows marked "Not imported" are skipped. Correct them in the file and
        import it again at any time.
      </p>
    </template>

    <template #footer>
      <el-button @click="open = false">Cancel</el-button>
      <el-button
        type="primary"
        :disabled="!preview || !toApply"
        :loading="busy && !!preview"
        @click="apply"
      >
        {{
          preview && toApply
            ? `Import ${toApply} ${toApply === 1 ? "person" : "people"}`
            : "Import"
        }}
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.steps {
  display: grid;
  gap: 14px;
  margin-bottom: 14px;
}
.step {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
}
.step :deep(.el-form-item) {
  margin-bottom: 0;
  width: 100%;
}
.password {
  width: min(320px, 100%);
}
.file {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}
.summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 18px;
  align-items: center;
  margin: 6px 0 10px;
}
.bad {
  color: var(--erf-bad);
}
.small {
  font-size: 12px;
}
</style>
