import { createBrowserRouter, Navigate } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import { ProtectedRoute } from "./ProtectedRoute";
import { LoginPage } from "@/features/auth/LoginPage";
import { Dashboard } from "@/features/dashboard/Dashboard";
import { VoucherList } from "@/features/vouchers/VoucherList";
import { VoucherCreate } from "@/features/vouchers/VoucherCreate";
import { VoucherDetail } from "@/features/vouchers/VoucherDetail";
import { CustomerList } from "@/features/customers/CustomerList";
import { CustomerDetail } from "@/features/customers/CustomerDetail";
import { InventoryList } from "@/features/inventory/InventoryList";
import { BatchList } from "@/features/production/BatchList";
import { BatchDetail } from "@/features/production/BatchDetail";
import { BatchCreate } from "@/features/production/BatchCreate";
import { ExpenseList } from "@/features/expenses/ExpenseList";
import { ReportsDashboard } from "@/features/reports/ReportsDashboard";
import { UserList } from "@/features/users/UserList";

export const router = createBrowserRouter([
  {
    path: "/login",
    element: <LoginPage />,
  },
  {
    element: <ProtectedRoute />,
    children: [
      {
        element: <AppLayout />,
        children: [
          { path: "/", element: <Navigate to="/dashboard" replace /> },
          { path: "/dashboard", element: <Dashboard /> },
          { path: "/vouchers", element: <VoucherList /> },
          { path: "/vouchers/new", element: <VoucherCreate /> },
          { path: "/vouchers/:id", element: <VoucherDetail /> },
          { path: "/customers", element: <CustomerList /> },
          { path: "/customers/:id", element: <CustomerDetail /> },
          { path: "/inventory", element: <InventoryList /> },
          {
            element: <ProtectedRoute requiredRoles={["warehouse", "manager", "admin", "super_admin"]} />,
            children: [
              { path: "/production", element: <BatchList /> },
              { path: "/production/new", element: <BatchCreate /> },
              { path: "/production/:id", element: <BatchDetail /> },
            ],
          },
          { path: "/expenses", element: <ExpenseList /> },
          {
            element: <ProtectedRoute requiredRoles={["manager", "admin", "super_admin"]} />,
            children: [{ path: "/reports", element: <ReportsDashboard /> }],
          },
          {
            element: <ProtectedRoute requiredRoles={["admin", "super_admin", "manager"]} />,
            children: [{ path: "/users", element: <UserList /> }],
          },
        ],
      },
    ],
  },
]);
