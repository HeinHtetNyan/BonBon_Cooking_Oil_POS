import type {
  CustomerDebtReportRow,
  DashboardSummary,
  ExpenseSummaryRow,
  InventoryBalanceReportRow,
  InventoryItemType,
  ProductionReportRow,
  SalesSummaryRow,
} from "@/types";
import { apiClient } from "./client";

export const reportsApi = {
  dashboard: async (): Promise<DashboardSummary> => {
    const res = await apiClient.get("/reports/dashboard");
    return res.data.data ?? res.data;
  },

  inventoryBalance: async (params: {
    item_type?: InventoryItemType;
    low_stock_only?: boolean;
  } = {}): Promise<InventoryBalanceReportRow[]> => {
    const res = await apiClient.get("/reports/inventory/balance", { params });
    return res.data.data ?? res.data;
  },

  salesSummary: async (start_date: string, end_date: string): Promise<SalesSummaryRow[]> => {
    const res = await apiClient.get("/reports/sales/summary", {
      params: { start_date, end_date },
    });
    return res.data.data ?? res.data;
  },

  expenseSummary: async (start_date: string, end_date: string): Promise<ExpenseSummaryRow[]> => {
    const res = await apiClient.get("/reports/expenses/summary", {
      params: { start_date, end_date },
    });
    return res.data.data ?? res.data;
  },

  customerDebts: async (): Promise<CustomerDebtReportRow[]> => {
    const res = await apiClient.get("/reports/customers/debts");
    return res.data.data ?? res.data;
  },

  production: async (params: {
    start_date?: string;
    end_date?: string;
  } = {}): Promise<ProductionReportRow[]> => {
    const res = await apiClient.get("/reports/production", { params });
    return res.data.data ?? res.data;
  },
};
