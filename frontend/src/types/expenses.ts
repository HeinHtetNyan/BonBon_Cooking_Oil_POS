export type ExpenseCategory =
  | "labour"
  | "utilities"
  | "transport"
  | "maintenance"
  | "packaging"
  | "administrative"
  | "marketing"
  | "rent"
  | "other";

export type ExpenseStatus = "pending" | "approved" | "paid" | "rejected";

export interface ExpenseCreate {
  category: ExpenseCategory;
  description: string;
  amount: number;
  expense_date: string;
  production_batch_id?: string;
  notes?: string;
  payment_method_code?: string;
  payment_reference?: string;
}

export interface ExpenseUpdate {
  description?: string;
  category?: ExpenseCategory;
  amount?: number;
  expense_date?: string;
  notes?: string;
}

export interface ExpenseApproveRequest {
  approved: boolean;
  notes?: string;
}

export interface ExpensePaymentCreate {
  payment_method_code: string;
  amount: number;
  reference_number?: string;
  notes?: string;
}

export interface ExpensePaymentResponse {
  id: string;
  expense_id: string;
  payment_method_id: string;
  amount: number;
  reference_number: string | null;
  notes: string | null;
  created_at: string;
}

export interface ExpenseResponse {
  id: string;
  reference_number: string;
  category: ExpenseCategory;
  description: string;
  amount: number;
  status: ExpenseStatus;
  expense_date: string;
  production_batch_id: string | null;
  notes: string | null;
  approved_by: string | null;
  created_at: string;
  updated_at: string;
  payments: ExpensePaymentResponse[];
}
