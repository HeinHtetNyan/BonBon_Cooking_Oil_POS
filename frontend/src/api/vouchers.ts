import type {
  ConfirmVoucherRequest,
  PaginatedResponse,
  SuccessResponse,
  VoidVoucherRequest,
  VoucherCreate,
  VoucherResponse,
  VoucherStatus,
  VoucherType,
  VoucherUpdate,
} from "@/types";
import { apiClient } from "./client";

interface ListVouchersParams {
  page?: number;
  per_page?: number;
  status?: VoucherStatus;
  customer_id?: string;
  voucher_type?: VoucherType;
  start_date?: string;
  end_date?: string;
  q?: string;
}

export const vouchersApi = {
  list: async (params: ListVouchersParams = {}): Promise<PaginatedResponse<VoucherResponse>> => {
    const res = await apiClient.get("/vouchers", { params });
    return res.data;
  },

  get: async (id: string): Promise<SuccessResponse<VoucherResponse>> => {
    const res = await apiClient.get(`/vouchers/${id}`);
    return res.data;
  },

  getByNumber: async (number: string): Promise<SuccessResponse<VoucherResponse>> => {
    const res = await apiClient.get(`/vouchers/number/${number}`);
    return res.data;
  },

  create: async (data: VoucherCreate): Promise<SuccessResponse<VoucherResponse>> => {
    const res = await apiClient.post("/vouchers", data);
    return res.data;
  },

  updateItems: async (
    id: string,
    items: VoucherCreate["items"],
  ): Promise<SuccessResponse<VoucherResponse>> => {
    const res = await apiClient.put(`/vouchers/${id}/items`, items);
    return res.data;
  },

  confirm: async (
    id: string,
    data: ConfirmVoucherRequest = {},
  ): Promise<SuccessResponse<VoucherResponse>> => {
    const res = await apiClient.post(`/vouchers/${id}/confirm`, data);
    return res.data;
  },

  void: async (
    id: string,
    data: VoidVoucherRequest,
  ): Promise<SuccessResponse<VoucherResponse>> => {
    const res = await apiClient.post(`/vouchers/${id}/void`, data);
    return res.data;
  },

  update: async (
    id: string,
    data: VoucherUpdate,
  ): Promise<SuccessResponse<VoucherResponse>> => {
    const res = await apiClient.patch(`/vouchers/${id}`, data);
    return res.data;
  },

  recordPayment: async (
    id: string,
    data: { payment_method_code: string; amount: number; reference_number?: string; notes?: string },
  ): Promise<SuccessResponse<VoucherResponse>> => {
    const res = await apiClient.post(`/vouchers/${id}/payments`, data);
    return res.data;
  },
};
