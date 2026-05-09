import type { PaginatedResponse, SuccessResponse, UserCreate, UserResponse, UserSummary, UserUpdate } from "@/types";
import { apiClient } from "./client";

export const usersApi = {
  list: async (page = 1, per_page = 25): Promise<PaginatedResponse<UserSummary>> => {
    const res = await apiClient.get("/users", { params: { page, per_page } });
    return res.data;
  },

  get: async (id: string): Promise<SuccessResponse<UserResponse>> => {
    const res = await apiClient.get(`/users/${id}`);
    return res.data;
  },

  create: async (data: UserCreate): Promise<SuccessResponse<UserResponse>> => {
    const res = await apiClient.post("/users", data);
    return res.data;
  },

  update: async (id: string, data: UserUpdate): Promise<SuccessResponse<UserResponse>> => {
    const res = await apiClient.patch(`/users/${id}`, data);
    return res.data;
  },
};
