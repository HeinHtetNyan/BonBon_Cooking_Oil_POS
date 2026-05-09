import type {
  ChangePasswordRequest,
  LoginRequest,
  LoginResponse,
  TokenResponse,
} from "@/types";
import { apiClient } from "./client";

export const authApi = {
  login: async (data: LoginRequest): Promise<LoginResponse> => {
    const res = await apiClient.post<LoginResponse>("/auth/login", data);
    return res.data;
  },

  refresh: async (refresh_token: string): Promise<TokenResponse> => {
    const res = await apiClient.post<TokenResponse>("/auth/refresh", {
      refresh_token,
    });
    return res.data;
  },

  me: async () => {
    const res = await apiClient.get("/auth/me");
    return res.data;
  },

  logout: async (refresh_token?: string) => {
    await apiClient.post("/auth/logout", { refresh_token });
  },

  changePassword: async (data: ChangePasswordRequest) => {
    const res = await apiClient.post("/auth/change-password", data);
    return res.data;
  },
};
