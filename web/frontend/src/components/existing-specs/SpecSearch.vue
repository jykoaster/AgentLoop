<script setup lang="ts">
import { ref, computed } from 'vue'
import * as api from '../../api'

const query = ref('')
const answer = ref('')
const references = ref<{ path: string; doc_type: string }[]>([])
const searching = ref(false)
const error = ref('')

const canSearch = computed(() => query.value.trim().length > 0 && !searching.value)

async function search(): Promise<void> {
  if (!canSearch.value) return
  searching.value = true
  error.value = ''
  answer.value = ''
  references.value = []
  try {
    const result = await api.searchSpecs(query.value.trim())
    answer.value = result.answer
    references.value = result.references
  } catch (e) {
    // 後端 502 的 detail 已經是「搜尋失敗：...」完整句子，前端不再疊加前綴。
    error.value = e instanceof api.ApiError ? e.message : String(e)
  } finally {
    searching.value = false
  }
}
</script>

<template>
  <div class="spec-search flex flex-col items-start gap-2">
    <div class="flex gap-2">
      <input
        v-model="query"
        type="text"
        placeholder="輸入問題搜尋規格"
        class="rounded-md border border-line bg-bg px-2 py-1 text-fg placeholder:text-fg-muted focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/40"
      />
      <button
        type="button"
        class="cursor-pointer rounded-md bg-primary px-3 py-2 text-on-accent shadow-sm transition-colors hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-50"
        :disabled="!canSearch"
        @click="search"
      >
        <font-awesome-icon icon="magnifying-glass" class="mr-1" />搜尋
      </button>
    </div>
    <p v-if="searching" class="text-fg-muted">搜尋中…</p>
    <p v-if="error" class="error text-danger">{{ error }}</p>
    <template v-if="!searching && !error && answer">
      <p class="answer">{{ answer }}</p>
      <ul class="references flex flex-col gap-1 text-sm text-fg-muted">
        <li v-for="ref in references" :key="ref.path">{{ ref.path }}（{{ ref.doc_type }}）</li>
      </ul>
    </template>
  </div>
</template>
