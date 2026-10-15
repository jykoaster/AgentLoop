import { onMounted, onUnmounted } from 'vue'

const DEFAULT_INTERVAL_MS = 2000

/** 掛載時立即執行一次，之後每 `intervalMs` 重複執行；卸載時自動清掉計時器。 */
export function usePolling(fn: () => void | Promise<void>, intervalMs = DEFAULT_INTERVAL_MS): void {
  let timer: ReturnType<typeof setInterval> | null = null

  onMounted(() => {
    void fn()
    timer = setInterval(() => {
      void fn()
    }, intervalMs)
  })

  onUnmounted(() => {
    if (timer !== null) clearInterval(timer)
  })
}
