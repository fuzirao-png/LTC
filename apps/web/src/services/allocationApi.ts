import { config } from '../config/runtime';
import { createHttpClient } from './http';

const http = createHttpClient(config.allocationApiBase);
function createIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => { const r = Math.random() * 16 | 0; const v = c === 'x' ? r : (r & 0x3 | 0x8); return v.toString(16); });
}


// ---- v3.6 Backend-aligned types ----

export type PipelineStage = 'new' | 'contacted' | 'engaged' | 'meeting' | 'proposal' | 'won' | 'lost' | 'dormant';

/** Matches backend PoolLead schema (pool endpoint) */
export interface PoolLead {
  lead_id: string;
  company_id: string;
  company_name: string;
  website?: string | null;
  company_intro?: string | null;
  industry_code?: string | null;
  country_code?: string | null;
  city?: string | null;
  icp_score?: number | null;
  icp_grade?: string | null;
  required_sales_tier: 'MA' | 'SA' | 'A';
  pool_region_code: string;
  allocation_status: 'claimable';
  pipeline_stage: PipelineStage;
  sla_due_at: string | null;
  current_owner_user_id: string | null;
  version: number;
}

/** Matches backend LeadListItem schema (mine/list endpoints) */
export interface LeadListItem {
  lead_id: string;
  company_id: string;
  company_name: string;
  website?: string | null;
  company_intro?: string | null;
  industry_code?: string | null;
  country_code?: string | null;
  city?: string | null;
  icp_score?: number | null;
  icp_grade?: string | null;
  required_sales_tier: string;
  pool_region_code: string | null;
  allocation_status: string;
  pipeline_stage: PipelineStage;
  sla_due_at: string | null;
  current_owner_user_id: string | null;
  owner_name?: string | null;
  owner_username?: string | null;
  customer_size_grade?: 'A' | 'B' | 'C' | null;
  last_activity_at: string | null;
  version: number;
}

/** Matches backend LeadCommandData (claim/assign etc responses) */
export interface LeadCommandData {
  lead_id: string;
  assignment_id: string | null;
  previous_assignment_id: string | null;
  allocation_status: 'claimable' | 'claimed';
  owner_user_id: string | null;
  from_owner_user_id: string | null;
  assigned_at: string | null;
  sla_due_at: string | null;
  pipeline_stage: PipelineStage;
  version: number;
}

/** Backend envelope wrapper */
export interface Envelope<T> {
  request_id: string;
  data: T;
  page?: { next_cursor: string | null; has_more: boolean };
}

async function fetchAllPages<T>(path: string, params: Record<string, unknown> = {}): Promise<T[]> {
  const items: T[] = [];
  const seenCursors = new Set<string>();
  let cursor: string | null = null;

  do {
    const response = await http.get<Envelope<T[]>>(path, {
      params: { ...params, limit: 100, ...(cursor ? { cursor } : {}) },
    });
    const data: Envelope<T[]> = response.data;
    items.push(...(data.data || []));

    const nextCursor: string | null = data.page?.has_more ? data.page.next_cursor : null;
    if (!nextCursor || seenCursors.has(nextCursor)) break;
    seenCursors.add(nextCursor);
    cursor = nextCursor;
  } while (cursor);

  return items;
}

/** Legacy type kept for UI backward-compat — maps from PoolLead/LeadListItem */
export interface LeadPoolItem {
  lead_id: string;
  company_id?: string;
  name: string;
  industry?: string;
  intro?: string;
  website?: string;
  city?: string;
  country?: string;
  region?: string;
  sales_tier: 'MA' | 'SA' | 'A';
  icp_score?: number;
  icp_grade?: string;
  score?: number;
  customer_size_grade?: 'A' | 'B' | 'C';
  pool_status: 'claimable' | 'claimed';
  pipeline_stage?: PipelineStage;
  owner_username?: string | null;
  owner_name?: string | null;
  claimed_at?: string | null;
  version?: number;
}

export interface LoginPayload {
  username: string;
  password: string;
}

export interface CustomerAssignedEvent {
  event_type: 'customer.assigned';
  event_id: string;
  occurred_at: string;
  company_id: string;
  customerName: string;
  source: string;
  payload: {
    industry?: string;
    intro?: string;
    website?: string;
    country?: string;
    city?: string;
    region?: string;
    icp_score?: number;
    icp_grade?: string;
    sales_tier?: 'MA' | 'SA' | 'A';
    [key: string]: unknown;
  };
}

// ---- Backend → UI type converters ----

function poolLeadToItem(p: PoolLead): LeadPoolItem {
  return {
    lead_id: p.lead_id,
    company_id: p.company_id,
    name: p.company_name,
    industry: p.industry_code || '',
    intro: p.company_intro || '',
    website: p.website || '',
    city: p.city || '',
    country: p.country_code || '',
    sales_tier: p.required_sales_tier,
    score: p.icp_score ?? undefined,
    icp_score: p.icp_score ?? undefined,
    icp_grade: p.icp_grade ?? undefined,
    pool_status: 'claimable',
    pipeline_stage: p.pipeline_stage,
    region: p.pool_region_code,
    version: p.version,
  };
}

function listItemToLeadPoolItem(item: LeadListItem): LeadPoolItem {
  return {
    lead_id: item.lead_id,
    company_id: item.company_id,
    name: item.company_name,
    industry: item.industry_code || '',
    intro: item.company_intro || '',
    website: item.website || '',
    city: item.city || '',
    country: item.country_code || '',
    sales_tier: (item.required_sales_tier as 'MA' | 'SA' | 'A') || 'A',
    score: item.icp_score ?? undefined,
    icp_score: item.icp_score ?? undefined,
    icp_grade: item.icp_grade ?? undefined,
    pool_status: item.allocation_status as 'claimable' | 'claimed',
    pipeline_stage: item.pipeline_stage,
    region: item.pool_region_code || undefined,
    owner_name: item.owner_name || null,
    owner_username: item.owner_username || null,
    customer_size_grade: item.customer_size_grade || undefined,
    claimed_at: item.allocation_status === 'claimed' ? item.last_activity_at : null,
    version: item.version,
  };
}

export const allocationApi = {
  // ---- IAM endpoints (correct paths) ----

  async me() {
    const { data } = await http.get<Envelope<{
      user: {
        user_id: string;
        username: string;
        display_name: string;
        account_type: 'sales' | 'strategic';
        sales_tier: 'MA' | 'SA' | 'A' | null;
        region_code: string | null;
        capacity_limit: number | null;
        status: string;
        active_assignment_count: number;
      };
      capabilities: string[];
    }>>('/auth/me');
    return data;
  },

  async login(payload: LoginPayload) {
    const { data } = await http.post('/auth/login', payload);
    return data;
  },

  async logout() {
    const { data } = await http.post('/auth/logout');
    return data;
  },

  async refreshToken() {
    const { data } = await http.post('/auth/refresh');
    return data;
  },

  // ---- Sales CRM (new v3.6 paths, remapped to UI-friendly LeadPoolItem) ----

  async pool(refresh = false): Promise<{ items: LeadPoolItem[]; total: number }> {
    const { data } = await http.get<Envelope<PoolLead[]>>('/sales-leads/pool', {
      params: { limit: 100 }, headers: refresh ? { 'Cache-Control': 'no-cache' } : undefined,
    });
    const items: PoolLead[] = (data as any).data || [];
    return { items: items.map(poolLeadToItem), total: items.length };
  },

  async mine(refresh = false): Promise<{ items: LeadPoolItem[]; total: number }> {
    const { data } = await http.get<Envelope<LeadListItem[]>>('/sales-leads/mine', {
      params: { limit: 100 }, headers: refresh ? { 'Cache-Control': 'no-cache' } : undefined,
    });
    const items: LeadListItem[] = (data as any).data || [];
    return { items: items.map(listItemToLeadPoolItem), total: items.length };
  },

  async all(): Promise<{ items: LeadPoolItem[]; total: number }> {
    const items = await fetchAllPages<LeadListItem>('/sales-leads');
    return { items: items.map(listItemToLeadPoolItem), total: items.length };
  },

  async assignLead(leadId: string, assigneeUserId: string, version: number): Promise<LeadCommandData> {
    const { data } = await http.post<Envelope<LeadCommandData>>(
      `/sales-leads/${encodeURIComponent(leadId)}:assign`,
      { assignee_user_id: assigneeUserId, reason_code: 'manager_assignment', reason_text: '主管手动分配，销售只考核最终结果' },
      { headers: { 'Idempotency-Key': createIdempotencyKey(), 'If-Match': String(version) } },
    );
    return (data as any).data;
  },

  async claim(leadId: string, version: number): Promise<LeadPoolItem> {
    const { data } = await http.post<Envelope<LeadCommandData>>(
      `/sales-leads/${encodeURIComponent(leadId)}:claim`,
      undefined,
      {
        headers: {
          'Idempotency-Key': createIdempotencyKey(),
          'If-Match': String(version),
        },
      },
    );
    const cmd: LeadCommandData = (data as any).data;
    return {
      lead_id: cmd.lead_id,
      name: '',
      sales_tier: 'A',
      pool_status: cmd.allocation_status,
      pipeline_stage: cmd.pipeline_stage,
      version: cmd.version,
    };
  },

  // ---- Legacy compat (kept for transition) ----

  /** @deprecated Use pool() instead */
  async claimable(refresh = false) {
    return this.pool(refresh);
  },

  // ---- Internal events ----

  /** POST /api/v1/internal/events/customer-assigned — sync assigned customer to analysis */
  async ingestAssignedCustomer(event: CustomerAssignedEvent) {
    try {
      const { data } = await http.post<{ success: boolean }>('/internal/events/customer-assigned', {
        client_id: event.company_id,
        customerName: event.customerName,
        source: event.source || 'claim',
        payload: event.payload || {},
      });
      if ((data as any)?.success) {
        return { lead_id: event.company_id, name: event.customerName, sales_tier: 'A', pool_status: 'claimable' } as LeadPoolItem;
      }
    } catch (err) {
      console.warn('ingestAssignedCustomer: event delivery failed, continuing', err);
    }
    return { lead_id: event.company_id, name: event.customerName, sales_tier: 'A', pool_status: 'claimable' } as LeadPoolItem;
  },

  // ---- Sales management (strategic only) ----

  /** GET /api/v1/users — list all users (strategic only) */
  async listUsers(): Promise<Array<{
    user_id: string; username: string; display_name: string;
    account_type: string; sales_tier: string | null; region_code: string | null;
    status: string; capacity_limit: number | null;
    active_assignment_count: number; version: number;
  }>> {
    return fetchAllPages('/users');
  },

  /** POST /api/v1/users/{user_id}:depart — mark user departed */
  async departUser(userId: string, reason: string, version: number): Promise<any> {
    const { data } = await http.post<Envelope<any>>(`/users/${encodeURIComponent(userId)}:depart`, { reason }, {
      headers: {
        'Idempotency-Key': createIdempotencyKey(),
        'If-Match': `"${version}"`,
      },
    });
    return (data as any).data;
  },

  async listHandoverLeads(): Promise<Array<{
    lead_id: string; company_id: string; company_name: string;
    departed_user_id: string; departed_user_name: string;
    sales_tier: string; region_code: string | null;
    required_sales_tier: string; customer_grade: string | null;
    customer_region_code: string | null;
    country_code: string | null; country_name: string | null;
    pipeline_stage: string; allocation_status: 'claimed'; version: number;
  }>> {
    const { data } = await http.get<Envelope<any[]>>('/sales-leads/handover');
    return (data as any).data || [];
  },

  async returnHandoverToPool(departedUserId: string): Promise<any> {
    const { data } = await http.post<Envelope<any>>('/sales-leads:handover-return-to-pool', {
      departed_user_id: departedUserId,
    }, { headers: { 'Idempotency-Key': createIdempotencyKey() } });
    return (data as any).data;
  },

  async assignHandoverLead(leadId: string, targetUserId: string, version: number, reasonText?: string): Promise<any> {
    const { data } = await http.post<Envelope<any>>(
      `/sales-leads/${encodeURIComponent(leadId)}:handover-assign`,
      { to_assignee_user_id: targetUserId, reason_text: reasonText || 'departure handover assignment' },
      { headers: { 'Idempotency-Key': createIdempotencyKey(), 'If-Match': `\"${version}\"` } },
    );
    return (data as any).data;
  },
};
