export const ROLES = {
  super_admin: "Super Admin",
  admin: "Admin",
  manager: "Manager",
  cashier: "Cashier",
  warehouse: "Warehouse",
} as const;

export const CUSTOMER_TYPES = {
  retail: "Retail",
  wholesale: "Wholesale",
  distributor: "Distributor",
} as const;

export const CUSTOMER_STATUSES = {
  active: "Active",
  inactive: "Inactive",
  blacklisted: "Blacklisted",
} as const;

export const VOUCHER_STATUSES = {
  draft: "Draft",
  confirmed: "Confirmed",
  partially_paid: "Partially Paid",
  paid: "Paid",
  cancelled: "Cancelled",
} as const;

export const EXPENSE_CATEGORIES = {
  labour: "Labour",
  utilities: "Utilities",
  transport: "Transport",
  maintenance: "Maintenance",
  packaging: "Packaging",
  administrative: "Administrative",
  marketing: "Marketing",
  rent: "Rent",
  other: "Other",
} as const;

export const EXPENSE_STATUSES = {
  pending: "Pending",
  approved: "Approved",
  paid: "Paid",
  rejected: "Rejected",
} as const;

export const INVENTORY_ITEM_TYPES = {
  raw_material: "Raw Material",
  finished_oil: "Finished Oil",
  packaging: "Packaging",
} as const;

export const WEIGHT_UNITS = {
  viss: "Viss",
  tical: "Tical",
  kg: "KG",
  liter: "Liter",
  unit: "Unit",
} as const;

export const BATCH_STATUSES = {
  planned: "Planned",
  in_progress: "In Progress",
  completed: "Completed",
  cancelled: "Cancelled",
} as const;

export const MOVEMENT_TYPES = {
  purchase_in: "Purchase In",
  production_output: "Production Output",
  sale_out: "Sale Out",
  production_consumption: "Production Consumption",
  adjustment_in: "Adjustment In",
  adjustment_out: "Adjustment Out",
  return_in: "Return In",
  transfer_in: "Transfer In",
  transfer_out: "Transfer Out",
  opening_balance: "Opening Balance",
  wastage: "Wastage",
  sample_out: "Sample Out",
  correction: "Correction",
  void_reversal: "Void Reversal",
} as const;
