import type {
  ExpenseApproveRequest,
  ExpenseCategory,
  ExpenseCreate,
  ExpensePaymentCreate,
  ExpensePaymentResponse,
  ExpenseResponse,
  ExpenseStatus,
  ExpenseUpdate,
  PaginatedResponse,
  SuccessResponse,
} from "@/types";
import { apiClient } from "./client";

export const expensesApi = {
  list: async (params: {
    page?: number;
    per_page?: number;
    category?: ExpenseCategory;
    status?: ExpenseStatus;
    start_date?: string;
    end_date?: string;
  } = {}): Promise<PaginatedResponse<ExpenseResponse>> => {
    const res = await apiClient.get("/expenses/", { params });
    return res.data;
  },

  get: async (id: string): Promise<SuccessResponse<ExpenseResponse>> => {
    const res = await apiClient.get(`/expenses/${id}`);
    return res.data;
  },

  create: async (data: ExpenseCreate): Promise<SuccessResponse<ExpenseResponse>> => {
    const res = await apiClient.post("/expenses/", data);
    return res.data;
  },

  update: async (id: string, data: ExpenseUpdate): Promise<SuccessResponse<ExpenseResponse>> => {
    const res = await apiClient.patch(`/expenses/${id}`, data);
    return res.data;
  },

  approve: async (id: string, data: ExpenseApproveRequest): Promise<SuccessResponse<ExpenseResponse>> => {
    const res = await apiClient.post(`/expenses/${id}/approve`, data);
    return res.data;
  },

  recordPayment: async (
    id: string,
    data: ExpensePaymentCreate,
  ): Promise<SuccessResponse<ExpensePaymentResponse>> => {
    const res = await apiClient.post(`/expenses/${id}/payments`, data);
    return res.data;
  },
};
