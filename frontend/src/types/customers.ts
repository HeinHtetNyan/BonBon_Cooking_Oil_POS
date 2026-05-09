export type CustomerType = "retail" | "wholesale" | "distributor";
export type CustomerStatus = "active" | "inactive" | "blacklisted";

export interface CustomerCreate {
  name: string;
  phone: string;
  address?: string;
  customer_type: CustomerType;
  notes?: string;
}

export interface CustomerUpdate {
  name?: string;
  phone?: string;
  address?: string;
  customer_type?: CustomerType;
  credit_limit?: number;
  notes?: string;
  status?: CustomerStatus;
}

export interface CustomerResponse {
  id: string;
  code: string;
  name: string;
  phone: string;
  address: string | null;
  customer_type: CustomerType;
  status: CustomerStatus;
  credit_limit: number;
  credit_balance: number;
  available_credit: number;
  total_debt: number;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface CustomerSummary {
  id: string;
  code: string;
  name: string;
  phone: string;
  customer_type: CustomerType;
  status: CustomerStatus;
  credit_balance: number;
}

export type DebtStatus = "outstanding" | "partially_paid" | "paid" | "written_off";

export interface CustomerDebtResponse {
  id: string;
  customer_id: string;
  voucher_id: string | null;
  original_amount: number;
  paid_amount: number;
  outstanding_amount: number;
  status: DebtStatus;
  due_date: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface DebtPaymentCreate {
  payment_method_code: string;
  amount: number;
  reference_number?: string;
  notes?: string;
}
