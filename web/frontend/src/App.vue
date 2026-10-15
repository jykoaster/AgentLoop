<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import * as api from './api'
import ActiveChanges from './components/active-changes/ActiveChanges.vue'
import ArchivedChanges from './components/archived-changes/ArchivedChanges.vue'
import ExistingSpecs from './components/existing-specs/ExistingSpecs.vue'
import SettingsPanel from './components/settings/SettingsPanel.vue'
import FolderPicker from './components/utils/FolderPicker.vue'

const TABS = ['執行中任務', '已封存任務', '既有 Spec', '設定'] as const
type Tab = (typeof TABS)[number]

const TAB_ICON: Record<Tab, string> = {
  '執行中任務': 'list-check',
  '已封存任務': 'box-archive',
  '既有 Spec': 'book',
  '設定': 'gear',
}

const activeTab = ref<Tab>('執行中任務')
const targetProject = ref('')
const showPicker = ref(false)

async function loadSettings(): Promise<void> {
  const settings = await api.getSettings()
  targetProject.value = settings.target_project
  if (!settings.target_project) {
    showPicker.value = true
  }
}

onMounted(loadSettings)

async function onFolderPicked(path: string): Promise<void> {
  await api.putSettings({ target_project: path })
  showPicker.value = false
  await loadSettings()
}

const hasProject = computed(() => !!targetProject.value)
</script>

<template>
  <div class="app min-h-screen bg-bg text-fg">
    <nav class="tabs flex items-center gap-1 border-b border-line bg-header px-4">
      <span class="mr-4 font-semibold text-fg">AgentLoop 控制台</span>
      <button
        v-for="tab in TABS"
        :key="tab"
        type="button"
        class="tab-button border-b-2 border-transparent px-4 py-3 text-fg-muted transition-colors cursor-pointer hover:text-fg"
        :class="{ 'active border-primary text-primary font-semibold': activeTab === tab }"
        :data-active="activeTab === tab"
        @click="activeTab = tab"
      >
        <font-awesome-icon :icon="TAB_ICON[tab]" />
        {{ tab }}
      </button>
    </nav>

    <main class="mx-auto max-w-5xl p-4">
      <template v-if="activeTab === '執行中任務'">
        <ActiveChanges v-if="hasProject" />
        <p v-else class="text-fg-muted">請先在設定選擇目標專案</p>
      </template>

      <template v-else-if="activeTab === '已封存任務'">
        <ArchivedChanges v-if="hasProject" />
        <p v-else class="text-fg-muted">請先在設定選擇目標專案</p>
      </template>

      <template v-else-if="activeTab === '既有 Spec'">
        <ExistingSpecs v-if="hasProject" />
        <p v-else class="text-fg-muted">請先在設定選擇目標專案</p>
      </template>

      <template v-else-if="activeTab === '設定'">
        <SettingsPanel @updated="loadSettings" @pick-folder="showPicker = true" />
      </template>
    </main>

    <FolderPicker v-if="showPicker" @picked="onFolderPicked" @close="showPicker = false" />
  </div>
</template>
