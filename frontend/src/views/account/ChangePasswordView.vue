<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { authApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { errorMessage, fieldErrors, showSuccess } from '@/utils/feedback'

const auth = useAuthStore()
const router = useRouter()
const form = reactive({ current: '', next: '', confirm: '' })
const errors = ref<Record<string, string>>({})
const message = ref<string | null>(null)
const saving = ref(false)

async function save(): Promise<void> {
  errors.value = {}
  message.value = null
  if (form.next !== form.confirm) {
    errors.value = { confirm: 'The two new passwords do not match.' }
    return
  }
  saving.value = true
  try {
    await authApi.changePassword(form.current, form.next)
    await auth.refresh()
    showSuccess('Password changed.')
    await router.replace({ name: 'dashboard' })
  } catch (e) {
    errors.value = fieldErrors(e)
    message.value = errorMessage(e)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="page narrow">
    <div>
      <h1>Change password</h1>
      <p v-if="auth.me?.must_change_password" class="sub">
        You signed in with a temporary password. Choose your own password to continue.
      </p>
      <p v-else class="sub">Use at least 10 characters and mix letters with numbers or symbols.</p>
    </div>
    <section class="panel">
      <el-form label-position="top" @submit.prevent="save">
        <el-form-item label="Current password" :error="errors.current_password" for="pw-current">
          <el-input id="pw-current" v-model="form.current" type="password" show-password autocomplete="current-password" />
        </el-form-item>
        <el-form-item label="New password" :error="errors.new_password" for="pw-new">
          <el-input id="pw-new" v-model="form.next" type="password" show-password autocomplete="new-password" />
        </el-form-item>
        <el-form-item label="Repeat new password" :error="errors.confirm" for="pw-confirm">
          <el-input id="pw-confirm" v-model="form.confirm" type="password" show-password autocomplete="new-password" />
        </el-form-item>
        <el-alert v-if="message" :title="message" type="error" :closable="false" class="alert" />
        <el-button type="primary" native-type="submit" :loading="saving">Change password</el-button>
      </el-form>
    </section>
  </div>
</template>

<style scoped>
.narrow {
  max-width: 480px;
}
.alert {
  margin-bottom: 14px;
}
</style>
