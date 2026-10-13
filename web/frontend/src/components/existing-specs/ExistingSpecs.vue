<script setup lang="ts">
import { ref } from 'vue'
import * as api from '../../api'
import SpecSearch from './SpecSearch.vue'

const domains = ref<string[]>([])
const selected = ref('')
const content = ref('')

async function load(): Promise<void> {
  domains.value = await api.getSpecs()
}
void load()

async function openDomain(domain: string): Promise<void> {
  selected.value = domain
  const result = await api.getSpec(domain)
  content.value = result.content
}
</script>

<template>
  <div class="flex flex-col gap-3 rounded-xl border border-line bg-surface p-5 shadow-lg">
    <SpecSearch />
    <p v-if="domains.length === 0" class="text-fg-muted">目前沒有既有 Spec</p>
    <ul v-else class="flex flex-col gap-1">
      <li v-for="d in domains" :key="d">
        <button
          type="button"
          class="w-full rounded-md px-2 py-1 text-left text-sm text-fg transition-colors cursor-pointer hover:bg-surface-muted"
          @click="openDomain(d)"
        >
          <font-awesome-icon icon="book" class="mr-1 text-fg-muted" />{{ d }}
        </button>
      </li>
    </ul>
    <pre v-if="selected" class="spec-content whitespace-pre-wrap rounded-md bg-surface-muted p-3 font-mono text-sm">{{ content }}</pre>
  </div>
</template>
