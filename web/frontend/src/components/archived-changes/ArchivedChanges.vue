<script setup lang="ts">
import { ref } from 'vue'
import * as api from '../../api'
import type { ArchiveRow } from '../../api'
import { usePolling } from '../../composables/usePolling'
import FileBrowser from '../utils/FileBrowser.vue'

const rows = ref<ArchiveRow[]>([])
const openDir = ref('')

async function load(): Promise<void> {
  rows.value = await api.getArchive()
}

usePolling(load)
</script>

<template>
  <div class="flex flex-col gap-2 rounded-xl border border-line bg-surface p-5 shadow-lg">
    <p v-if="rows.length === 0" class="text-fg-muted">目前沒有已封存的任務</p>
    <ul v-else class="flex flex-col gap-1">
      <li v-for="row in rows" :key="row.dir">
        <button
          type="button"
          class="w-full rounded-md px-2 py-2 text-left text-sm text-fg transition-colors cursor-pointer hover:bg-surface-muted"
          @click="openDir = row.dir"
        >
          <font-awesome-icon icon="box-archive" class="mr-1 text-fg-muted" />{{ row.date }} {{ row.name }}
        </button>
      </li>
    </ul>
    <FileBrowser v-if="openDir" mode="archive" :target="openDir" @close="openDir = ''" />
  </div>
</template>
