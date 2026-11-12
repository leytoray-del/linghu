<script setup lang="ts">
import { ref } from 'vue'

import EmailTab from './EmailTab.vue'
import CategoriesTab from '@/modules/inventory/admin/CategoriesTab.vue'
import ModelsTab from '@/modules/inventory/admin/ModelsTab.vue'

import HolidaysTab from './HolidaysTab.vue'
import LocationsTab from './LocationsTab.vue'
import ProjectsTab from './ProjectsTab.vue'
import SettingsTab from './SettingsTab.vue'
import SupportTypesTab from './SupportTypesTab.vue'
import TeamsTab from './TeamsTab.vue'
import UsersTab from './UsersTab.vue'

const tab = ref('users')
</script>

<template>
  <div class="page">
    <div>
      <h1>Administration</h1>
      <p class="sub">Accounts, projects and locations shared by every module, and the settings of each module.</p>
    </div>
    <section class="panel">
      <el-tabs v-model="tab">
        <el-tab-pane label="Users" name="users" lazy><UsersTab /></el-tab-pane>
        <el-tab-pane label="Projects" name="projects" lazy><ProjectsTab /></el-tab-pane>
        <el-tab-pane label="Locations" name="locations" lazy><LocationsTab /></el-tab-pane>
        <el-tab-pane label="Teams and approvers" name="teams" lazy><TeamsTab /></el-tab-pane>
        <el-tab-pane label="Types of support" name="types" lazy><SupportTypesTab /></el-tab-pane>
        <el-tab-pane label="Public holidays" name="holidays" lazy><HolidaysTab /></el-tab-pane>
        <el-tab-pane label="Workflow rules" name="settings" lazy><SettingsTab /></el-tab-pane>
        <el-tab-pane label="Email delivery" name="email" lazy><EmailTab /></el-tab-pane>
        <el-tab-pane label="Inventory categories" name="inv-categories" lazy><CategoriesTab /></el-tab-pane>
        <el-tab-pane label="Models and suppliers" name="inv-models" lazy><ModelsTab /></el-tab-pane>
      </el-tabs>
    </section>
  </div>
</template>
