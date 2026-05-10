import { apiClient } from "./client";
import type { AuditLog, AuditLogListParams } from "@/types/audit";
import type { PaginatedResponse } from "@/types/api";

export const auditApi = {
  list: async (params: AuditLogListParams = {}): Promise<PaginatedResponse<AuditLog>> => {
    const res = await apiClient.get("/audit/logs", { params });
    return res.data;
  },
};
