import type {
  CancelBatchRequest,
  CompleteBatchRequest,
  PaginatedResponse,
  ProductionBatchCreate,
  ProductionBatchResponse,
  ProductionBatchStatus,
  ProductionBatchUpdate,
  SuccessResponse,
} from "@/types";
import { apiClient } from "./client";

export const productionApi = {
  list: async (params: {
    page?: number;
    per_page?: number;
    status?: ProductionBatchStatus;
  } = {}): Promise<PaginatedResponse<ProductionBatchResponse>> => {
    const res = await apiClient.get("/production/batches", { params });
    return res.data;
  },

  get: async (id: string): Promise<SuccessResponse<ProductionBatchResponse>> => {
    const res = await apiClient.get(`/production/batches/${id}`);
    return res.data;
  },

  create: async (data: ProductionBatchCreate): Promise<SuccessResponse<ProductionBatchResponse>> => {
    const res = await apiClient.post("/production/batches", data);
    return res.data;
  },

  update: async (
    id: string,
    data: ProductionBatchUpdate,
  ): Promise<SuccessResponse<ProductionBatchResponse>> => {
    const res = await apiClient.patch(`/production/batches/${id}`, data);
    return res.data;
  },

  start: async (id: string): Promise<SuccessResponse<ProductionBatchResponse>> => {
    const res = await apiClient.post(`/production/batches/${id}/start`);
    return res.data;
  },

  complete: async (
    id: string,
    data: CompleteBatchRequest,
  ): Promise<SuccessResponse<ProductionBatchResponse>> => {
    const res = await apiClient.post(`/production/batches/${id}/complete`, data);
    return res.data;
  },

  cancel: async (
    id: string,
    data: CancelBatchRequest,
  ): Promise<SuccessResponse<ProductionBatchResponse>> => {
    const res = await apiClient.post(`/production/batches/${id}/cancel`, data);
    return res.data;
  },
};
