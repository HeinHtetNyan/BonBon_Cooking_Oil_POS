import type {
  CustomerCreate,
  CustomerDebtResponse,
  CustomerResponse,
  CustomerStatus,
  CustomerSummary,
  CustomerType,
  CustomerUpdate,
  DebtPaymentCreate,
  PaginatedResponse,
  SuccessResponse,
} from "@/types";
import { apiClient } from "./client";

export const customersApi = {
  list: async (params: {
    page?: number;
    per_page?: number;
    q?: string;
    customer_type?: CustomerType;
    status?: CustomerStatus;
  } = {}): Promise<PaginatedResponse<CustomerResponse>> => {
    const res = await apiClient.get("/customers", { params });
    return res.data;
  },

  search: async (q: string, limit = 10): Promise<CustomerSummary[]> => {
    const res = await apiClient.get("/customers/search", { params: { q, limit } });
    return res.data;
  },

  get: async (id: string): Promise<SuccessResponse<CustomerResponse>> => {
    const res = await apiClient.get(`/customers/${id}`);
    return res.data;
  },

  create: async (data: CustomerCreate): Promise<SuccessResponse<CustomerResponse>> => {
    const res = await apiClient.post("/customers", data);
    return res.data;
  },

  update: async (id: string, data: CustomerUpdate): Promise<SuccessResponse<CustomerResponse>> => {
    const res = await apiClient.patch(`/customers/${id}`, data);
    return res.data;
  },

  deactivate: async (id: string): Promise<SuccessResponse<CustomerResponse>> => {
    const res = await apiClient.delete(`/customers/${id}`);
    return res.data;
  },

  getDebts: async (id: string) => {
    const res = await apiClient.get(`/customers/${id}/debts`);
    return res.data;
  },

  listDebts: async (customerId: string): Promise<CustomerDebtResponse[]> => {
    const res = await apiClient.get(`/finance/debts`, {
      params: { customer_id: customerId },
    });
    return res.data;
  },

  recordDebtPayment: async (
    debtId: string,
    data: DebtPaymentCreate,
  ): Promise<SuccessResponse<CustomerDebtResponse>> => {
    const res = await apiClient.post(`/finance/debts/${debtId}/payments`, data);
    return res.data;
  },
};
