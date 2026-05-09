export type InventoryItemType =
  | "raw_material"
  | "finished_oil"
  | "packaging";

export type MovementType =
  | "purchase_in"
  | "production_output"
  | "sale_out"
  | "production_consumption"
  | "adjustment_in"
  | "adjustment_out"
  | "return_in"
  | "transfer_in"
  | "transfer_out"
  | "opening_balance"
  | "wastage"
  | "sample_out"
  | "correction"
  | "void_reversal";

export type WeightUnit = "viss" | "tical" | "kg" | "liter" | "unit";
export type MovementStatus = "pending" | "confirmed" | "cancelled";

export interface InventoryItemCreate {
  name: string;
  item_type: InventoryItemType;
  unit: WeightUnit;
  description?: string;
  purchase_date?: string;
  reorder_level?: number;
  reorder_quantity?: number;
  initial_quantity?: number;
  unit_cost?: number;
}

export interface InventoryItemUpdate {
  name?: string;
  description?: string;
  purchase_date?: string;
  reorder_level?: number;
  reorder_quantity?: number;
}

export interface InventoryItemResponse {
  id: string;
  code: string;
  name: string;
  item_type: InventoryItemType;
  unit: WeightUnit;
  current_balance: number;
  purchase_date: string | null;
  reorder_level: number | null;
  reorder_quantity: number | null;
  is_low_stock: boolean;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface MovementCreate {
  item_id: string;
  movement_type: MovementType;
  quantity: number;
  unit: WeightUnit;
  unit_price?: number;
  transaction_date?: string;
  reference_type?: string;
  reference_id?: string;
  notes?: string;
}

export interface MovementResponse {
  id: string;
  item_id: string;
  movement_type: MovementType;
  quantity: number;
  unit: WeightUnit;
  unit_price: number | null;
  balance_after: number;
  reference_type: string | null;
  reference_id: string | null;
  notes: string | null;
  actor: string;
  status: MovementStatus;
  created_at: string;
}

export interface InventorySnapshotCreate {
  item_id: string;
  snapshot_date: string;
  notes?: string;
}

export interface InventorySnapshotResponse {
  id: string;
  item_id: string;
  snapshot_date: string;
  balance: number;
  unit: WeightUnit;
  created_at: string;
}
