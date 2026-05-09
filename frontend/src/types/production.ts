export type ProductionBatchStatus =
  | "planned"
  | "in_progress"
  | "completed"
  | "cancelled";

import type { WeightUnit } from "./inventory";
export type { WeightUnit };

export interface MaterialUsageCreate {
  material_item_id: string;
  planned_quantity: number;
  unit: WeightUnit;
  unit_cost?: number;
}

export interface MaterialUsageResponse {
  id: string;
  batch_id: string;
  material_item_id: string;
  planned_quantity: number;
  actual_quantity: number | null;
  unit: WeightUnit;
  unit_cost: number | null;
}

export interface ProductionOutputCreate {
  output_item_id: string;
  quantity: number;
  unit: WeightUnit;
  notes?: string;
}

export interface ProductionOutputResponse {
  id: string;
  batch_id: string;
  output_item_id: string;
  quantity: number;
  unit: WeightUnit;
  notes: string | null;
}

export interface ProductionBatchCreate {
  output_item_id: string;
  expected_output: number;
  output_unit: WeightUnit;
  start_date: string;
  material_usages: MaterialUsageCreate[];
  notes?: string;
}

export interface ProductionBatchUpdate {
  notes?: string;
  total_labour_cost?: number;
  total_overhead_cost?: number;
}

export interface ProductionBatchResponse {
  id: string;
  batch_number: string;
  status: ProductionBatchStatus;
  output_item_id: string;
  expected_output: number;
  actual_output: number | null;
  output_unit: WeightUnit;
  yield_percentage: number | null;
  total_labour_cost: number;
  total_overhead_cost: number;
  total_material_cost: number;
  total_cost: number;
  start_date: string;
  completion_date: string | null;
  notes: string | null;
  material_usages: MaterialUsageResponse[];
  outputs: ProductionOutputResponse[];
  created_at: string;
  updated_at: string;
}

export interface ActualMaterialUsageEntry {
  usage_id: string;
  actual_quantity: number;
}

export interface CompleteBatchRequest {
  actual_material_usages: ActualMaterialUsageEntry[];
  outputs: ProductionOutputCreate[];
  labour_cost?: number;
  overhead_cost?: number;
}

export interface CancelBatchRequest {
  reason: string;
}
