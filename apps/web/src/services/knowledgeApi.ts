import { api } from '../shared/api/client'

export interface KnowledgeItem {
  id: string
  content: string
  knowledge_id?: string | null
  knowledge_title?: string | null
  knowledge_filename?: string | null
  knowledge_source?: string | null
  score?: number | null
  metadata: Record<string, unknown>
}

export interface KnowledgeSearchResponse {
  request_id: string
  data: {
    query: string
    items: KnowledgeItem[]
    knowledge_base_ids: string[]
  }
}

export const knowledgeApi = {
  async search(query: string, limit = 10) {
    const response = await api.post<KnowledgeSearchResponse>('/knowledge/search', { query, limit })
    return response.data
  },
}
