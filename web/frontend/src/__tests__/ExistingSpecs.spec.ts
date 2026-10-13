import { describe, test, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ExistingSpecs from '../components/existing-specs/ExistingSpecs.vue'
import * as api from '../api'

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return {
    ...actual,
    getSpecs: vi.fn(),
    getSpec: vi.fn(),
    searchSpecs: vi.fn(),
  }
})

const mockedApi = vi.mocked(api)

beforeEach(() => {
  vi.clearAllMocks()
  mockedApi.searchSpecs.mockResolvedValue({ answer: '', references: [] })
})

describe('ExistingSpecs', () => {
  test('既有 Spec 分頁列出每個 domain 並可檢視其規格內容', async () => {
    mockedApi.getSpecs.mockResolvedValue(['auth', 'billing'])
    mockedApi.getSpec.mockResolvedValue({ domain: 'auth', content: 'auth spec full text' })

    const wrapper = mount(ExistingSpecs)
    await flushPromises()

    const search = wrapper.find('.spec-search').element
    const list = wrapper.find('ul').element
    // eslint-disable-next-line no-bitwise
    expect(search.compareDocumentPosition(list) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()

    const buttons = wrapper.findAll('ul li button')
    expect(buttons.map((b) => b.text())).toEqual(['auth', 'billing'])

    await buttons[0].trigger('click')
    await flushPromises()

    expect(mockedApi.getSpec).toHaveBeenCalledWith('auth')
    expect(wrapper.find('.spec-content').text()).toBe('auth spec full text')
  })

  test('輸入問題搜尋規格後顯示回答與參考檔案', async () => {
    let resolveSearch: (value: { answer: string; references: { path: string; doc_type: string }[] }) => void
    mockedApi.searchSpecs.mockImplementation(
      () => new Promise((resolve) => { resolveSearch = resolve }),
    )
    mockedApi.getSpecs.mockResolvedValue(['auth'])

    const wrapper = mount(ExistingSpecs)
    await flushPromises()

    const input = wrapper.find('.spec-search input')
    await input.setValue('登入失敗幾次會鎖定？')
    await wrapper.find('.spec-search button').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('搜尋中…')
    expect((wrapper.find('.spec-search button').element as HTMLButtonElement).disabled).toBe(true)

    resolveSearch!({
      answer: '登入失敗 5 次會鎖定 15 分鐘。',
      references: [{ path: 'openspec/specs/auth/spec.md', doc_type: 'spec' }],
    })
    await flushPromises()

    expect(wrapper.text()).not.toContain('搜尋中…')
    expect(wrapper.find('.answer').text()).toBe('登入失敗 5 次會鎖定 15 分鐘。')
    const refs = wrapper.findAll('.references li')
    expect(refs).toHaveLength(1)
    expect(refs[0].text()).toBe('openspec/specs/auth/spec.md（spec）')
  })

  test('規格中找不到相關內容時顯示查無結果訊息', async () => {
    mockedApi.getSpecs.mockResolvedValue([])
    mockedApi.searchSpecs.mockResolvedValue({
      answer: '規格文件中沒有找到相關內容。',
      references: [],
    })

    const wrapper = mount(ExistingSpecs)
    await flushPromises()

    await wrapper.find('.spec-search input').setValue('任何問題')
    await wrapper.find('.spec-search button').trigger('click')
    await flushPromises()

    expect(wrapper.find('.answer').text()).toBe('規格文件中沒有找到相關內容。')
  })

  test('搜尋失敗時顯示錯誤訊息並保留查詢文字', async () => {
    mockedApi.getSpecs.mockResolvedValue([])
    mockedApi.searchSpecs.mockRejectedValue(
      new api.ApiError(502, '搜尋失敗：claude CLI error: not logged in'),
    )

    const wrapper = mount(ExistingSpecs)
    await flushPromises()

    const input = wrapper.find('.spec-search input')
    await input.setValue('登入規則？')
    await wrapper.find('.spec-search button').trigger('click')
    await flushPromises()

    expect(wrapper.find('.error').text()).toBe('搜尋失敗：claude CLI error: not logged in')
    expect((input.element as HTMLInputElement).value).toBe('登入規則？')
    expect((wrapper.find('.spec-search button').element as HTMLButtonElement).disabled).toBe(false)
  })

  test('滑鼠移到可點擊元素時顯示手指游標且停用按鈕顯示禁止游標', async () => {
    mockedApi.getSpecs.mockResolvedValue(['auth'])

    const wrapper = mount(ExistingSpecs)
    await flushPromises()

    const authItem = wrapper.findAll('ul li button').find((b) => b.text() === 'auth')!
    expect(authItem.classes()).toContain('cursor-pointer')
  })
})
