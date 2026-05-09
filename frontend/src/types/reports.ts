export interface DashboardSummary {
  today_sales_count: number;
  today_sales_amount: number;
  today_expenses_amount: number;
  this_month_sales_amount: number;
  this_month_expenses_amount: number;
  all_time_sales_amount: number;
  all_time_expenses_amount: number;
  outstanding_debts_count: number;
  outstanding_debts_total: number;
  low_stock_items_count: number;
  active_production_batches: number;
}

export interface InventoryBalanceReportRow {
  item_id: string;
  item_code: string;
  item_name: string;
  item_type: string;
  unit: string;
  current_balance: number;
  is_low_stock: boolean;
}

export interface SalesSummaryRow {
  sale_date: string;
  voucher_count: number;
  total_amount: number;
  total_paid: number;
  total_outstanding: number;
}

export interface ExpenseSummaryRow {
  category: string;
  expense_count: number;
  total_amount: number;
}

export interface CustomerDebtReportRow {
  customer_id: string;
  customer_code: string;
  customer_name: string;
  total_debt: number;
  outstanding_debt: number;
  debt_count: number;
}

export interface ProductionReportRow {
  id: string;
  batch_number: string;
  status: string;
  output_item_id: string;
  expected_output: number;
  actual_output: number | null;
  yield_percentage: number | null;
  total_cost: number;
  start_date: string;
  completion_date: string | null;
}
