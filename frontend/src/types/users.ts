export type UserRole =
  | "super_admin"
  | "admin"
  | "manager"
  | "cashier"
  | "warehouse";

export type UserStatus =
  | "active"
  | "inactive"
  | "suspended"
  | "pending_verification";

export interface UserResponse {
  id: string;
  username: string;
  email: string;
  full_name: string;
  phone: string | null;
  role: UserRole;
  status: UserStatus;
  avatar_url: string | null;
  last_login_at: string | null;
  created_at: string;
  updated_at: string;
  is_deleted: boolean;
}

export interface UserSummary {
  id: string;
  username: string;
  full_name: string;
  role: UserRole;
  status: UserStatus;
}

export interface UserCreate {
  username: string;
  email: string;
  full_name: string;
  phone?: string;
  role: UserRole;
  password: string;
}

export interface UserUpdate {
  full_name?: string;
  phone?: string;
  avatar_url?: string;
  role?: UserRole;
  status?: UserStatus;
}
