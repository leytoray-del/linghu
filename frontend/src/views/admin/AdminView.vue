<script setup lang="ts">
import { ref } from 'vue'

import EmailTab from './EmailTab.vue'
import HolidaysTab from './HolidaysTab.vue'
import SettingsTab from './SettingsTab.vue'
import SupportTypesTab from './SupportTypesTab.vue'
import TeamsTab from './TeamsTab.vue'
import UsersTab from './UsersTab.vue'

const tab = ref('users')
</script>

<template>
  <div class="page">
    <div>
      <h1>Settings</h1>
      <p class="sub">Maintain accounts, routing, the holiday calendar and workflow rules. Changes apply to new submissions.</p>
    </div>
    <section class="panel">
      <el-tabs v-model="tab">
        <el-tab-pane label="Users" name="users" lazy><UsersTab /></el-tab-pane>
        <el-tab-pane label="Teams and approvers" name="teams" lazy><TeamsTab /></el-tab-pane>
        <el-tab-pane label="Types of support" name="types" lazy><SupportTypesTab /></el-tab-pane>
        <el-tab-pane label="Public holidays" name="holidays" lazy><HolidaysTab /></el-tab-pane>
        <el-tab-pane label="Workflow rules" name="settings" lazy><SettingsTab /></el-tab-pane>
        <el-tab-pane label="Email delivery" name="email" lazy><EmailTab /></el-tab-pane>
      </el-tabs>
    </section>
  </div>
</template>
