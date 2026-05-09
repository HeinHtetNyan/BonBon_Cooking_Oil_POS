export type SuccessResponse<T> = T;

export interface PaginatedResponse<T> {
  success: true;
  data: T[];
  page: number;
  per_page: number;
  total: number;
  total_pages: number;
}

export interface ApiError {
  detail: string | { msg: string; type: string }[];
  status_code?: number;
}
