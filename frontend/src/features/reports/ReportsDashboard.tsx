import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { reportsApi } from "@/api/reports";
import { formatCurrency, formatDate } from "@/lib/utils";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell,
} from "recharts";

const COLORS = ["#4f46e5", "#06b6d4", "#f59e0b", "#ef4444", "#10b981", "#8b5cf6", "#f97316", "#ec4899", "#64748b"];

function DateRangeFilter({ start, end, onStartChange, onEndChange }: {
  start: string; end: string; onStartChange: (v: string) => void; onEndChange: (v: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-wrap gap-3 items-end">
      <div className="space-y-1">
        <Label className="text-xs">{t("common.startDate")}</Label>
        <Input type="date" value={start} onChange={(e) => onStartChange(e.target.value)} className="w-36" />
      </div>
      <div className="space-y-1">
        <Label className="text-xs">{t("common.endDate")}</Label>
        <Input type="date" value={end} onChange={(e) => onEndChange(e.target.value)} className="w-36" />
      </div>
    </div>
  );
}

function SalesTab() {
  const { t } = useTranslation();
  const today = new Date();
  const monthAgo = new Date(today.getFullYear(), today.getMonth() - 1, today.getDate());
  const [start, setStart] = useState(monthAgo.toISOString().split("T")[0]);
  const [end, setEnd] = useState(today.toISOString().split("T")[0]);

  const { data, isLoading } = useQuery({
    queryKey: ["sales-summary", start, end],
    queryFn: () => reportsApi.salesSummary(start, end),
    enabled: !!start && !!end,
  });

  const total = data?.reduce((s, r) => s + Number(r.total_amount), 0) ?? 0;
  const paid = data?.reduce((s, r) => s + Number(r.total_paid), 0) ?? 0;

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-4 flex-wrap">
        <DateRangeFilter start={start} end={end} onStartChange={setStart} onEndChange={setEnd} />
        <div className="flex flex-wrap gap-3 w-full sm:w-auto sm:ml-auto">
          <Card className="p-3 flex-1 min-w-28"><p className="text-xs text-muted-foreground">{t("reports.totalSales")}</p><p className="font-bold">{formatCurrency(total)}</p></Card>
          <Card className="p-3 flex-1 min-w-28"><p className="text-xs text-muted-foreground">{t("reports.totalPaid")}</p><p className="font-bold text-green-600">{formatCurrency(paid)}</p></Card>
          <Card className="p-3 flex-1 min-w-28"><p className="text-xs text-muted-foreground">{t("reports.outstanding")}</p><p className="font-bold text-orange-600">{formatCurrency(total - paid)}</p></Card>
        </div>
      </div>

      {isLoading ? (
        <Skeleton className="h-64" />
      ) : (
        <>
          <Card>
            <CardHeader><CardTitle className="text-sm">{t("reports.dailySales")}</CardTitle></CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={data ?? []}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis dataKey="sale_date" tickFormatter={(v) => v.slice(5)} tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`} />
                  <Tooltip formatter={(v) => formatCurrency(Number(v))} />
                  <Bar dataKey="total_amount" fill="#4f46e5" radius={[3, 3, 0, 0]} name={t("common.total")} />
                  <Bar dataKey="total_paid" fill="#10b981" radius={[3, 3, 0, 0]} name={t("vouchers.paid")} />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-0 overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("common.date")}</TableHead>
                    <TableHead className="text-right">{t("reports.voucherCount")}</TableHead>
                    <TableHead className="text-right">{t("common.total")}</TableHead>
                    <TableHead className="text-right">{t("reports.totalPaid")}</TableHead>
                    <TableHead className="text-right">{t("reports.outstanding")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data?.map((r) => (
                    <TableRow key={r.sale_date}>
                      <TableCell>{formatDate(r.sale_date)}</TableCell>
                      <TableCell className="text-right">{r.voucher_count}</TableCell>
                      <TableCell className="text-right">{formatCurrency(r.total_amount)}</TableCell>
                      <TableCell className="text-right text-green-600">{formatCurrency(r.total_paid)}</TableCell>
                      <TableCell className="text-right text-orange-600">{formatCurrency(r.total_outstanding)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

function ExpensesTab() {
  const { t } = useTranslation();
  const today = new Date();
  const monthAgo = new Date(today.getFullYear(), today.getMonth() - 1, today.getDate());
  const [start, setStart] = useState(monthAgo.toISOString().split("T")[0]);
  const [end, setEnd] = useState(today.toISOString().split("T")[0]);

  const { data, isLoading } = useQuery({
    queryKey: ["expense-summary", start, end],
    queryFn: () => reportsApi.expenseSummary(start, end),
    enabled: !!start && !!end,
  });

  const catLabel = (k: string) => t(`expenseCategories.${k}`, { defaultValue: k });

  return (
    <div className="space-y-5">
      <DateRangeFilter start={start} end={end} onStartChange={setStart} onEndChange={setEnd} />
      {isLoading ? (
        <Skeleton className="h-64" />
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          <Card>
            <CardHeader><CardTitle className="text-sm">{t("reports.byCategory")}</CardTitle></CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={200}>
                <PieChart>
                  <Pie
                    data={(data ?? []).map((r) => ({ ...r, total_amount: Number(r.total_amount) }))}
                    dataKey="total_amount"
                    nameKey="category"
                    cx="50%"
                    cy="50%"
                    outerRadius={75}
                    label={({ name }) => catLabel(String(name))}
                  >
                    {data?.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                  </Pie>
                  <Tooltip formatter={(v) => formatCurrency(Number(v))} />
                </PieChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-0 overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("common.category")}</TableHead>
                    <TableHead className="text-right">{t("reports.count")}</TableHead>
                    <TableHead className="text-right">{t("common.total")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data?.map((r) => (
                    <TableRow key={r.category}>
                      <TableCell>{catLabel(r.category)}</TableCell>
                      <TableCell className="text-right">{r.expense_count}</TableCell>
                      <TableCell className="text-right font-medium">{formatCurrency(r.total_amount)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}

function InventoryTab() {
  const { t } = useTranslation();
  const { data, isLoading } = useQuery({
    queryKey: ["inventory-balance-report"],
    queryFn: () => reportsApi.inventoryBalance(),
  });

  return (
    <div className="space-y-5">
      {isLoading ? (
        <Skeleton className="h-64" />
      ) : (
        <Card>
          <CardContent className="p-0 overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("common.code")}</TableHead>
                  <TableHead>{t("common.name")}</TableHead>
                  <TableHead>{t("common.type")}</TableHead>
                  <TableHead className="text-right">{t("inventory.balance")}</TableHead>
                  <TableHead>{t("common.unit")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data?.map((r) => (
                  <TableRow key={r.item_id}>
                    <TableCell className="font-mono text-sm">{r.item_code}</TableCell>
                    <TableCell>{r.item_name}</TableCell>
                    <TableCell>{t(`inventoryItemTypes.${r.item_type}`, { defaultValue: r.item_type })}</TableCell>
                    <TableCell className="text-right">{Number(r.current_balance).toLocaleString()}</TableCell>
                    <TableCell className="uppercase">{r.unit}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function DebtTab() {
  const { t } = useTranslation();
  const { data, isLoading } = useQuery({
    queryKey: ["customer-debt-report"],
    queryFn: () => reportsApi.customerDebts(),
  });

  return (
    <div className="space-y-5">
      {isLoading ? (
        <Skeleton className="h-64" />
      ) : (
        <Card>
          <CardContent className="p-0 overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("common.code")}</TableHead>
                  <TableHead>{t("common.name")}</TableHead>
                  <TableHead className="text-right">{t("reports.totalSales")}</TableHead>
                  <TableHead className="text-right">{t("reports.outstanding")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data?.map((r) => (
                  <TableRow key={r.customer_id}>
                    <TableCell className="font-mono text-sm">{r.customer_code}</TableCell>
                    <TableCell className="font-medium">{r.customer_name}</TableCell>
                    <TableCell className="text-right">{formatCurrency(Number(r.total_debt))}</TableCell>
                    <TableCell className="text-right text-orange-600 font-medium">{formatCurrency(Number(r.outstanding_debt))}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export function ReportsDashboard() {
  const { t } = useTranslation();
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold">{t("reports.title")}</h1>
        <p className="text-sm text-muted-foreground">{t("reports.subtitle")}</p>
      </div>

      <Tabs defaultValue="sales">
        <TabsList>
          <TabsTrigger value="sales">{t("reports.sales")}</TabsTrigger>
          <TabsTrigger value="expenses">{t("reports.expenses")}</TabsTrigger>
          <TabsTrigger value="inventory">{t("reports.inventoryTab")}</TabsTrigger>
          <TabsTrigger value="debts">{t("reports.customerDebts")}</TabsTrigger>
        </TabsList>
        <TabsContent value="sales"><SalesTab /></TabsContent>
        <TabsContent value="expenses"><ExpensesTab /></TabsContent>
        <TabsContent value="inventory"><InventoryTab /></TabsContent>
        <TabsContent value="debts"><DebtTab /></TabsContent>
      </Tabs>
    </div>
  );
}
