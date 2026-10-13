<script setup lang="ts">
import { ref, onMounted } from 'vue'
import * as api from '../../api'
import type { SettingsView } from '../../api'

const emit = defineEmits<{ 'pick-folder': []; updated: [] }>()

const settings = ref<SettingsView | null>(null)
const oauthToken = ref('')
const apiKey = ref('')
const saved = ref(false)
const error = ref('')

async function load(): Promise<void> {
  settings.value = await api.getSettings()
}

onMounted(load)

async function save(): Promise<void> {
  saved.value = false
  error.value = ''
  try {
    settings.value = await api.putSettings({
      oauth_token: oauthToken.value,
      api_key: apiKey.value,
    })
    oauthToken.value = ''
    apiKey.value = ''
    saved.value = true
    emit('updated')
  } catch (e) {
    error.value = e instanceof api.ApiError ? e.message : String(e)
  }
}
</script>

<template>
  <div v-if="settings" class="settings-panel flex flex-col gap-4 rounded-xl border border-line bg-surface p-5 shadow-lg">
    <div class="field target-project flex flex-wrap items-center gap-2">
      <label class="w-32 font-medium text-fg">目標專案</label>
      <span class="value text-fg">{{ settings.target_project || '（未設定）' }}</span>
      <button
        type="button"
        class="btn-secondary px-2 py-1 text-sm"
        :disabled="settings.run_active"
        :title="settings.run_active ? '執行進行中，無法變更目標專案' : ''"
        @click="emit('pick-folder')"
      >
        <font-awesome-icon icon="folder-open" class="mr-1" />選擇資料夾
      </button>
      <p v-if="settings.run_active" class="hint text-sm text-fg-muted">執行進行中，無法變更目標專案</p>
    </div>

    <div class="field oauth-token flex items-center gap-2">
      <label class="w-32 font-medium text-fg">Claude OAuth token</label>
      <span class="value text-fg-muted">
        {{ settings.oauth_token.set ? `已設定（末四碼 ${settings.oauth_token.last4}）` : '未設定' }}
      </span>
      <input
        v-model="oauthToken"
        type="password"
        placeholder="留空則不變更"
        class="rounded-md border border-line bg-bg px-2 py-1 text-fg placeholder:text-fg-muted focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/40"
      />
    </div>

    <div class="field api-key flex items-center gap-2">
      <label class="w-32 font-medium text-fg">Anthropic API key</label>
      <span class="value text-fg-muted">
        {{ settings.api_key.set ? `已設定（末四碼 ${settings.api_key.last4}）` : '未設定' }}
      </span>
      <input
        v-model="apiKey"
        type="password"
        placeholder="留空則不變更"
        class="rounded-md border border-line bg-bg px-2 py-1 text-fg placeholder:text-fg-muted focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/40"
      />
    </div>

    <button
      type="button"
      class="save-button self-start rounded-md bg-primary px-3 py-2 text-on-accent shadow-sm transition-colors cursor-pointer hover:bg-primary-hover"
      @click="save"
    >
      <font-awesome-icon icon="floppy-disk" class="mr-1" />儲存
    </button>
    <p v-if="saved" class="text-success">已儲存</p>
    <p v-if="error" class="error text-danger">{{ error }}</p>
  </div>
</template>
