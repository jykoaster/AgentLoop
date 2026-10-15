import { describe, test, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ArchivedChanges from '../components/archived-changes/ArchivedChanges.vue'
import * as api from '../api'

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return {
    ...actual,
    getArchive: vi.fn(),
    getArchiveFiles: vi.fn(),
    getArchiveFile: vi.fn(),
  }
})

const mockedApi = vi.mocked(api)

beforeEach(() => {
  vi.clearAllMocks()
})

describe('ArchivedChanges', () => {
  test('已封存任務分頁每個封存 change 一列並可瀏覽其文件', async () => {
    mockedApi.getArchive.mockResolvedValue([
      { dir: '2026-10-01-feat-b', date: '2026-10-01', name: 'feat-b' },
      { dir: '2026-09-01-feat-a', date: '2026-09-01', name: 'feat-a' },
    ])
    mockedApi.getArchiveFiles.mockResolvedValue(['proposal.md', 'tasks.md'])
    mockedApi.getArchiveFile.mockResolvedValue({ path: 'proposal.md', content: '# proposal' })

    const wrapper = mount(ArchivedChanges)
    await flushPromises()

    const rows = wrapper.findAll('li button')
    expect(rows.map((r) => r.text())).toEqual(['2026-10-01 feat-b', '2026-09-01 feat-a'])

    await rows[0].trigger('click')
    await flushPromises()

    expect(mockedApi.getArchiveFiles).toHaveBeenCalledWith('2026-10-01-feat-b')
    const fileButtons = wrapper.findAll('.file-browser li button')
    expect(fileButtons.map((b) => b.text())).toEqual(['proposal.md', 'tasks.md'])

    await fileButtons[0].trigger('click')
    await flushPromises()
    expect(wrapper.find('.file-content').text()).toBe('# proposal')
  })

  test('沒有任何封存任務時顯示空狀態', async () => {
    mockedApi.getArchive.mockResolvedValue([])
    const wrapper = mount(ArchivedChanges)
    await flushPromises()

    expect(wrapper.text()).toContain('目前沒有已封存的任務')
  })
})
