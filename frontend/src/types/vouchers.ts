import type { WeightUnit } from "./inventory";
export type { WeightUnit };

export type VoucherType = "sale" | "return";
export type VoucherStatus =
  | "draft"
  | "confirmed"
  | "partially_paid"
  | "paid"
  | "cancelled";

export interface VoucherItemCreate {
  inventory_item_id: string;
  quantity: number;
  unit: WeightUnit;
  unit_price: number;
  discount_percent?: number;
  notes?: string;
}

export interface VoucherItemResponse {
  id: string;
  inventory_item_id: string;
  quantity: number;
  unit: WeightUnit;
  unit_price: number;
  discount_percent: number;
  line_total: number;
  notes: string | null;
}

export interface VoucherPaymentCreate {
  payment_method_id: string;
  amount: number;
  reference_number?: string;
  notes?: string;
}

export interface VoucherPaymentResponse {
  id: string;
  payment_method_id: string;
  amount: number;
  reference_number: string | null;
  created_at: string;
}

export interface VoucherExtraCharge {
  description: string;
  amount: number;
}

export interface VoucherCreate {
  customer_id?: string;
  voucher_type?: VoucherType;
  sale_date: string;
  items: VoucherItemCreate[];
  payments?: VoucherPaymentCreate[];
  extra_charges?: VoucherExtraCharge[];
  notes?: string;
}

export interface VoucherUpdate {
  notes?: string;
  customer_id?: string | null;
  sale_date?: string;
  extra_charges?: VoucherExtraCharge[];
}

export interface VoucherResponse {
  id: string;
  voucher_number: string;
  voucher_type: VoucherType;
  status: VoucherStatus;
  customer_id: string | null;
  subtotal: number;
  discount_amount: number;
  tax_amount: number;
  extra_charges: VoucherExtraCharge[];
  total_amount: number;
  paid_amount: number;
  outstanding_amount: number;
  sale_date: string;
  notes: string | null;
  created_by: string;
  version_number: number;
  items: VoucherItemResponse[];
  payments: VoucherPaymentResponse[];
  created_at: string;
  updated_at: string;
}

export interface ConfirmVoucherRequest {
  expected_version?: number;
}

export interface VoidVoucherRequest {
  reason: string;
  expected_version?: number;
}
