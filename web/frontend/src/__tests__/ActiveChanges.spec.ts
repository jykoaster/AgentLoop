import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ActiveChanges from '../components/active-changes/ActiveChanges.vue'
import * as api from '../api'
import type { ChangeRow, RunStatus } from '../api'

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return {
    ...actual,
    getChanges: vi.fn(),
    getRun: vi.fn(),
    getStageDetail: vi.fn(),
    getChangeFiles: vi.fn(),
    getChangeFile: vi.fn(),
    postNewTask: vi.fn(),
    postRerun: vi.fn(),
    postAnswer: vi.fn(),
  }
})

const mockedApi = vi.mocked(api)

function makeRow(overrides: Partial<ChangeRow> = {}): ChangeRow {
  return {
    change_name: 'feat-login',
    branch_name: 'feat/login',
    task: '新增登入頁',
    iteration: 0,
    stages: {
      analyze_plan: 'done',
      human_confirm: 'done',
      execute: 'running',
      review: 'pending',
      archive: 'pending',
    },
    stage_notes: {},
    ...overrides,
  }
}

const IDLE_RUN: RunStatus = { active: false }

beforeEach(() => {
  vi.clearAllMocks()
  mockedApi.getChanges.mockResolvedValue([])
  mockedApi.getRun.mockResolvedValue(IDLE_RUN)
  mockedApi.getStageDetail.mockResolvedValue({ status: 'pending', note: '', fields: {}, log: '' })
})

afterEach(() => {
  vi.useRealTimers()
})

describe('ActiveChanges', () => {
  test('執行中任務分頁為每個未封存的 change 顯示一列階段卡片', async () => {
    mockedApi.getChanges.mockResolvedValue([makeRow()])
    const wrapper = mount(ActiveChanges)
    await flushPromises()

    const rows = wrapper.findAll('.change-row')
    expect(rows).toHaveLength(1)
    expect(rows[0].text()).toContain('feat-login')
    expect(rows[0].text()).toContain('feat/login')
    expect(rows[0].text()).toContain('新增登入頁')
    expect(rows[0].text()).toContain('第 0 次迭代')

    const cards = rows[0].findAll('.stage-card')
    expect(cards.map((c) => c.attributes('data-status'))).toEqual([
      'done', 'done', 'running', 'pending', 'pending',
    ])
    expect(cards.map((c) => c.classes()).map((classes) =>
      classes.find((cls) => cls.startsWith('border-l-stage-')),
    )).toEqual([
      'border-l-stage-done', 'border-l-stage-done', 'border-l-stage-running',
      'border-l-stage-pending', 'border-l-stage-pending',
    ])
    const badges = cards.map((c) => c.find('.stage-status'))
    expect(badges.map((b) => b.classes().find((cls) => cls.startsWith('bg-stage-')))).toEqual([
      'bg-stage-done', 'bg-stage-done', 'bg-stage-running', 'bg-stage-pending', 'bg-stage-pending',
    ])
    expect(badges.map((b) => b.text())).toEqual(['完成', '完成', '執行中', '尚未開始', '尚未開始'])
    expect(cards.map((c) => c.classes().includes('animate-breathe'))).toEqual([
      false, false, true, false, false,
    ])
    expect(rows[0].find('.view-files-button').exists()).toBe(true)
  })

  test('沒有任何執行中任務時顯示空狀態與新增任務入口', async () => {
    const wrapper = mount(ActiveChanges)
    await flushPromises()

    expect(wrapper.text()).toContain('目前沒有執行中的任務')
    const button = wrapper.find('.empty-state button')
    expect(button.exists()).toBe(true)
    expect(button.text()).toBe('新增任務')
  })

  test('沒有階段狀態紀錄的舊任務以尚未開始顯示所有階段', async () => {
    mockedApi.getChanges.mockResolvedValue([
      makeRow({
        stages: {
          analyze_plan: 'pending', human_confirm: 'pending', execute: 'pending',
          review: 'pending', archive: 'pending',
        },
      }),
    ])
    const wrapper = mount(ActiveChanges)
    await flushPromises()

    const cards = wrapper.findAll('.stage-card')
    expect(cards.every((c) => c.attributes('data-status') === 'pending')).toBe(true)
    const rerunButtons = wrapper.findAll('.rerun-button')
    expect(rerunButtons).toHaveLength(4)
  })

  test('從任務列開啟該 change 的規格文件', async () => {
    mockedApi.getChanges.mockResolvedValue([makeRow()])
    mockedApi.getChangeFiles.mockResolvedValue(['proposal.md', 'tasks.md', 'specs/auth/spec.md'])
    mockedApi.getChangeFile.mockResolvedValue({ path: 'specs/auth/spec.md', content: '# auth spec' })

    const wrapper = mount(ActiveChanges)
    await flushPromises()
    await wrapper.find('[aria-label="檢視規格文件"]').trigger('click')
    await flushPromises()

    const fileButtons = wrapper.findAll('.file-browser li button')
    expect(fileButtons.map((b) => b.text())).toEqual([
      'proposal.md', 'tasks.md', 'specs/auth/spec.md',
    ])

    await fileButtons[2].trigger('click')
    await flushPromises()
    expect(wrapper.find('.file-content').text()).toBe('# auth spec')
  })

  test('階段等待人工回覆時卡片顯示驚嘆號並可在詳情中回覆', async () => {
    vi.useFakeTimers()
    const pendingRow = makeRow({
      stages: {
        analyze_plan: 'running', human_confirm: 'pending', execute: 'pending',
        review: 'pending', archive: 'pending',
      },
    })
    mockedApi.getChanges.mockResolvedValue([pendingRow])
    mockedApi.getRun.mockResolvedValue({
      active: true, change_name: 'feat-login', label: 'feat-login', task: '新增登入頁',
      stage: 'analyze_plan',
      question: {
        id: 'q1', stage: 'analyze_plan', kind: 'choice',
        prompt: '網頁服務要用什麼技術棧？',
        options: ['1. FastAPI（建議）', '2. Flask', '3. Django'],
        required: false, multiline: false,
      },
    })
    mockedApi.postAnswer.mockResolvedValue({ ok: true })

    const wrapper = mount(ActiveChanges)
    await flushPromises()

    const analyzeCard = wrapper.findAll('.stage-card')[0]
    expect(analyzeCard.find('.question-mark').exists()).toBe(true)

    await analyzeCard.trigger('click')
    await flushPromises()

    const row = wrapper.find('[data-change-name="feat-login"]')
    expect(row.find('.question-prompt').text()).toBe('網頁服務要用什麼技術棧？')
    const optionButtons = row.findAll('.question-form > button')
    expect(optionButtons).toHaveLength(3)

    await optionButtons[0].trigger('click')
    expect(mockedApi.postAnswer).toHaveBeenCalledWith('q1', '1')

    mockedApi.getRun.mockResolvedValue({
      active: true, change_name: 'feat-login', label: 'feat-login', stage: 'analyze_plan',
      question: null,
    })
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()

    const analyzeCardAfter = wrapper.findAll('.stage-card')[0]
    expect(analyzeCardAfter.find('.question-mark').exists()).toBe(false)
    expect(analyzeCardAfter.attributes('data-status')).toBe('running')
  })

  test('重跑某階段時從該階段開始並接續後續流程', async () => {
    mockedApi.getChanges.mockResolvedValue([
      makeRow({
        stages: {
          analyze_plan: 'done', human_confirm: 'done', execute: 'error',
          review: 'done', archive: 'pending',
        },
      }),
    ])
    mockedApi.postRerun.mockResolvedValue({ run_id: 'r1' })

    const wrapper = mount(ActiveChanges)
    await flushPromises()

    const rerunButtons = wrapper.findAll('[aria-label="重跑"]')
    expect(rerunButtons).toHaveLength(4)

    vi.spyOn(window, 'confirm').mockReturnValue(true)
    await rerunButtons[1].trigger('click') // execute 是第 2 張卡（analyze_plan 也有重跑，故 index 1 對應 execute）
    await flushPromises()

    expect(mockedApi.postRerun).toHaveBeenCalledWith('feat-login', 'execute')
  })

  test('已有執行進行中時其他啟動動作停用並顯示原因', async () => {
    mockedApi.getChanges.mockResolvedValue([
      makeRow({ change_name: 'fix-css', branch_name: 'fix/css', stages: makeRow().stages }),
    ])
    mockedApi.getRun.mockResolvedValue({ active: true, change_name: 'feat-login', label: 'feat-login' })

    const wrapper = mount(ActiveChanges)
    await flushPromises()

    const newTaskButton = wrapper.find('.new-task-button')
    expect((newTaskButton.element as HTMLButtonElement).disabled).toBe(true)

    const rerunButtons = wrapper.findAll('[aria-label="重跑"]')
    expect(rerunButtons.length).toBeGreaterThan(0)
    for (const btn of rerunButtons) {
      expect((btn.element as HTMLButtonElement).disabled).toBe(true)
      expect(btn.attributes('title')).toBe('目前已有 feat-login 執行中')
    }
  })

  test('重跑按鈕停用時滑鼠停留提示顯示停用原因', async () => {
    mockedApi.getChanges.mockResolvedValue([
      makeRow({ change_name: 'fix-css', branch_name: 'fix/css' }),
    ])
    mockedApi.getRun.mockResolvedValue({ active: true, change_name: 'feat-login', label: 'feat-login' })

    const wrapper = mount(ActiveChanges)
    await flushPromises()

    const reviewCard = wrapper.findAll('.stage-card')[3]
    const rerunButton = reviewCard.find('[aria-label="重跑"]')
    expect(rerunButton.attributes('title')).toBe('目前已有 feat-login 執行中')
    expect(rerunButton.text()).toBe('')
    expect((rerunButton.element as HTMLButtonElement).disabled).toBe(true)
  })

  test('執行進行中再送出啟動要求時系統拒絕', async () => {
    mockedApi.getChanges.mockResolvedValue([makeRow()])
    mockedApi.getRun.mockResolvedValue({ active: true, change_name: 'feat-login', label: 'feat-login' })
    mockedApi.postNewTask.mockRejectedValue(new api.ApiError(409, '目前已有 feat-login 執行中'))

    const wrapper = mount(ActiveChanges)
    await flushPromises()

    expect((wrapper.find('.new-task-button').element as HTMLButtonElement).disabled).toBe(true)
  })

  test('新增任務後以 analyze_plan 卡片引導初始提問', async () => {
    mockedApi.getRun.mockResolvedValue(IDLE_RUN)
    const wrapper = mount(ActiveChanges)
    await flushPromises()

    await wrapper.find('.empty-state button').trigger('click')
    await flushPromises()
    const textarea = wrapper.find('.new-task-dialog textarea')
    await textarea.setValue('新增登入頁')
    mockedApi.postNewTask.mockResolvedValue({ run_id: 'r1' })
    mockedApi.getRun.mockResolvedValue({
      active: true, change_name: '', label: '新增登入頁', task: '新增登入頁', stage: 'analyze_plan',
      question: null,
    })
    await wrapper.find('.new-task-dialog button:not(:disabled)').trigger('click')
    await flushPromises()

    expect(mockedApi.postNewTask).toHaveBeenCalledWith('新增登入頁')
    const tempRow = wrapper.find('.change-row[data-change-name="(temp)"]')
    expect(tempRow.exists()).toBe(true)
    expect(tempRow.text()).toContain('新增登入頁')
    expect(tempRow.findAll('.stage-card')[0].attributes('data-status')).toBe('running')
  })

  test('點擊階段卡片後詳情展開在該任務列卡片下方且各列可各自展開一個', async () => {
    mockedApi.getChanges.mockResolvedValue([
      makeRow(),
      makeRow({ change_name: 'fix-css', branch_name: 'fix/css' }),
    ])

    const wrapper = mount(ActiveChanges)
    await flushPromises()

    const featRow = () => wrapper.find('[data-change-name="feat-login"]')
    const cssRow = () => wrapper.find('[data-change-name="fix-css"]')

    await featRow().findAll('.stage-card')[3].trigger('click') // review
    await flushPromises()
    expect(featRow().find('.stage-detail-panel').exists()).toBe(true)
    expect(cssRow().find('.stage-detail-panel').exists()).toBe(false)
    expect(wrapper.findAll('.stage-detail-panel')).toHaveLength(1)
    expect(mockedApi.getStageDetail).toHaveBeenCalledWith('feat-login', 'review')

    await cssRow().findAll('.stage-card')[2].trigger('click') // execute
    await flushPromises()
    expect(wrapper.findAll('.stage-detail-panel')).toHaveLength(2)
    expect(mockedApi.getStageDetail).toHaveBeenCalledWith('fix-css', 'execute')

    await featRow().findAll('.stage-card')[0].trigger('click') // analyze_plan
    await flushPromises()
    expect(wrapper.findAll('.stage-detail-panel')).toHaveLength(2)
    expect(mockedApi.getStageDetail).toHaveBeenCalledWith('feat-login', 'analyze_plan')

    await cssRow().find('[aria-label="關閉"]').trigger('click')
    await flushPromises()
    expect(cssRow().find('.stage-detail-panel').exists()).toBe(false)
    expect(featRow().find('.stage-detail-panel').exists()).toBe(true)
  })

  test('任務列收合後只保留標題列且展開後恢復原詳情', async () => {
    vi.useFakeTimers()
    mockedApi.getChanges.mockResolvedValue([makeRow()])

    const wrapper = mount(ActiveChanges)
    await flushPromises()

    const row = () => wrapper.find('[data-change-name="feat-login"]')

    await row().findAll('.stage-card')[3].trigger('click') // review
    await flushPromises()
    expect(row().find('.stage-detail-panel').exists()).toBe(true)

    const collapseButton = row().find('[aria-label="收合"]')
    expect(collapseButton.exists()).toBe(true)
    expect(collapseButton.attributes('title')).toBe('收合')
    expect(collapseButton.find('svg[data-icon="chevron-up"]').exists()).toBe(true)

    await collapseButton.trigger('click')
    await flushPromises()

    expect(row().find('.stage-card').exists()).toBe(false)
    expect(row().find('.stage-detail-panel').exists()).toBe(false)
    expect(row().find('[aria-label="檢視規格文件"]').exists()).toBe(false)
    expect(row().find('.change-name').exists()).toBe(true)

    const expandButton = row().find('[aria-label="展開"]')
    expect(expandButton.exists()).toBe(true)
    expect(expandButton.attributes('title')).toBe('展開')
    expect(expandButton.find('svg[data-icon="chevron-down"]').exists()).toBe(true)

    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()

    expect(row().find('.stage-card').exists()).toBe(false)
    expect(row().find('[aria-label="展開"]').exists()).toBe(true)

    await row().find('[aria-label="展開"]').trigger('click')
    await flushPromises()

    expect(row().findAll('.stage-card')).toHaveLength(5)
    expect(row().find('.stage-detail-panel').exists()).toBe(true)
    expect(mockedApi.getStageDetail).toHaveBeenCalledWith('feat-login', 'review')
  })

  test('純圖示按鈕以滑鼠停留提示與無障礙名稱呈現原本文字', async () => {
    mockedApi.getChanges.mockResolvedValue([makeRow()])

    const wrapper = mount(ActiveChanges)
    await flushPromises()

    const cards = wrapper.findAll('.stage-card')
    const executeCard = cards[2]
    const rerunButton = executeCard.find('[aria-label="重跑"]')
    expect(rerunButton.exists()).toBe(true)
    expect(rerunButton.text()).toBe('')
    expect(rerunButton.attributes('title')).toBe('重跑')
    expect(rerunButton.find('svg[data-icon="rotate-right"]').exists()).toBe(true)
    expect(rerunButton.classes()).toContain('text-warning')

    const filesButton = wrapper.find('[aria-label="檢視規格文件"]')
    expect(filesButton.exists()).toBe(true)
    expect(filesButton.text()).toBe('')
    expect(filesButton.attributes('title')).toBe('檢視規格文件')

    const reviewCard = cards[3]
    await reviewCard.trigger('click')
    await flushPromises()

    const row = wrapper.find('[data-change-name="feat-login"]')
    const closeButton = row.find('[aria-label="關閉"]')
    expect(closeButton.exists()).toBe(true)
    expect(closeButton.text()).toBe('')
    expect(closeButton.attributes('title')).toBe('關閉')
    expect(closeButton.classes()).toContain('text-danger')

    await closeButton.trigger('click')
    await flushPromises()
    expect(row.find('.stage-detail-panel').exists()).toBe(false)
  })

  test('主要操作與階段狀態徽章在文字旁顯示對應圖示', async () => {
    mockedApi.getChanges.mockResolvedValue([
      makeRow({
        stages: {
          analyze_plan: 'running', human_confirm: 'pending', execute: 'error',
          review: 'done', archive: 'pending',
        },
      }),
    ])
    mockedApi.getRun.mockResolvedValue({
      active: true, change_name: 'feat-login', label: 'feat-login', stage: 'analyze_plan',
      question: {
        id: 'q1', stage: 'analyze_plan', kind: 'text',
        prompt: '分支名稱？', options: [], required: false, multiline: false,
      },
    })

    const wrapper = mount(ActiveChanges)
    await flushPromises()

    const newTaskButton = wrapper.find('.new-task-button')
    expect(newTaskButton.find('svg[data-icon]').exists()).toBe(true)
    expect(newTaskButton.text()).toContain('新增任務')

    const badges = wrapper.findAll('.stage-status')
    expect(badges.map((b) => b.text())).toEqual(['執行中', '尚未開始', '錯誤', '完成', '尚未開始'])
    const icons = badges.map((b) => b.find('svg').attributes('data-icon'))
    expect(new Set(icons)).toEqual(new Set(['spinner', 'clock', 'circle-xmark', 'circle-check']))

    const analyzeCard = wrapper.findAll('.stage-card')[0]
    expect(analyzeCard.find('.question-mark').text()).toBe('!')
  })

  test('滑鼠移到可點擊元素時顯示手指游標且停用按鈕顯示禁止游標', async () => {
    mockedApi.getChanges.mockResolvedValue([
      makeRow({ change_name: 'fix-css', branch_name: 'fix/css' }),
    ])
    mockedApi.getRun.mockResolvedValue({ active: true, change_name: 'feat-login', label: 'feat-login' })
    const confirmSpy = vi.spyOn(window, 'confirm')

    const wrapper = mount(ActiveChanges)
    await flushPromises()

    const analyzeCard = wrapper.findAll('.stage-card')[0]
    expect(analyzeCard.classes()).toContain('cursor-pointer')

    const reviewCard = wrapper.findAll('.stage-card')[3]
    const rerunButton = reviewCard.find('[aria-label="重跑"]')
    expect(rerunButton.classes()).toContain('disabled:cursor-not-allowed')
    expect((rerunButton.element as HTMLButtonElement).disabled).toBe(true)

    await rerunButton.trigger('click')
    expect(confirmSpy).not.toHaveBeenCalled()
  })

  test('任務描述為空白時無法送出新增任務', async () => {
    const wrapper = mount(ActiveChanges)
    await flushPromises()

    await wrapper.find('.empty-state button').trigger('click')
    await flushPromises()

    const textarea = wrapper.find('.new-task-dialog textarea')
    await textarea.setValue('   ')
    const submitButton = wrapper
      .findAll('.new-task-dialog button')
      .find((b) => b.text() === '送出')!
    expect((submitButton.element as HTMLButtonElement).disabled).toBe(true)
  })
})
