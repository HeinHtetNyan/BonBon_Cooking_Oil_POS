import type { PaymentMethod } from "@/types";
import { apiClient } from "./client";

export const financeApi = {
  listPaymentMethods: async (): Promise<PaymentMethod[]> => {
    const res = await apiClient.get("/finance/payment-methods");
    return res.data.data ?? res.data;
  },
};
