import type {
  InventoryItemCreate,
  InventoryItemResponse,
  InventoryItemType,
  InventoryItemUpdate,
  InventorySnapshotCreate,
  InventorySnapshotResponse,
  MovementCreate,
  MovementResponse,
  MovementType,
  PaginatedResponse,
  SuccessResponse,
} from "@/types";
import { apiClient } from "./client";

export const inventoryApi = {
  listItems: async (params: {
    page?: number;
    per_page?: number;
    item_type?: InventoryItemType;
    low_stock?: boolean;
  } = {}): Promise<PaginatedResponse<InventoryItemResponse>> => {
    const res = await apiClient.get("/inventory/items", { params });
    return res.data;
  },

  getItem: async (id: string): Promise<SuccessResponse<InventoryItemResponse>> => {
    const res = await apiClient.get(`/inventory/items/${id}`);
    return res.data;
  },

  createItem: async (data: InventoryItemCreate): Promise<SuccessResponse<InventoryItemResponse>> => {
    const res = await apiClient.post("/inventory/items", data);
    return res.data;
  },

  updateItem: async (
    id: string,
    data: InventoryItemUpdate,
  ): Promise<SuccessResponse<InventoryItemResponse>> => {
    const res = await apiClient.patch(`/inventory/items/${id}`, data);
    return res.data;
  },

  deleteItem: async (id: string): Promise<void> => {
    await apiClient.delete(`/inventory/items/${id}`);
  },

  listMovements: async (params: {
    page?: number;
    per_page?: number;
    item_id?: string;
    movement_type?: MovementType;
    start_date?: string;
    end_date?: string;
  } = {}): Promise<PaginatedResponse<MovementResponse>> => {
    const res = await apiClient.get("/inventory/movements", { params });
    return res.data;
  },

  createMovement: async (data: MovementCreate): Promise<SuccessResponse<MovementResponse>> => {
    const res = await apiClient.post("/inventory/movements", data);
    return res.data;
  },

  reverseMovement: async (
    id: string,
    reason: string,
  ): Promise<SuccessResponse<MovementResponse>> => {
    const res = await apiClient.post(`/inventory/movements/${id}/reverse`, null, {
      params: { reason },
    });
    return res.data;
  },

  createSnapshot: async (
    data: InventorySnapshotCreate,
  ): Promise<SuccessResponse<InventorySnapshotResponse>> => {
    const res = await apiClient.post("/inventory/snapshots", data);
    return res.data;
  },
};
