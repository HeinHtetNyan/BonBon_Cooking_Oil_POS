export interface AuditLog {
  id: string;
  action: string;
  actor_id: string | null;
  actor_username: string | null;
  actor_role: string | null;
  resource_type: string | null;
  resource_id: string | null;
  before_data: Record<string, unknown> | null;
  after_data: Record<string, unknown> | null;
  ip_address: string | null;
  user_agent: string | null;
  request_id: string | null;
  status_code: number | null;
  duration_ms: number | null;
  tenant_id: string;
  created_at: string;
}

export interface AuditLogListParams {
  actor_id?: string;
  action?: string;
  resource_type?: string;
  start_date?: string;
  end_date?: string;
  page?: number;
  per_page?: number;
}
