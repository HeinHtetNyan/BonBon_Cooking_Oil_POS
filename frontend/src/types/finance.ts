export interface PaymentMethod {
  id: string;
  code: string;
  name: string;
  account_code: string;
  is_active: boolean;
}

export interface JournalEntry {
  id: string;
  transaction_date: string;
  debit_account_code: string;
  credit_account_code: string;
  amount: number;
  description: string;
  reference_type: string | null;
  reference_id: string | null;
  is_reversed: boolean;
  created_at: string;
}
