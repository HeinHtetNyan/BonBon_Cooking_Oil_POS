import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  TrendingUp, Users, Receipt, AlertTriangle, Droplets, DollarSign,
} from "lucide-react";
import { reportsApi } from "@/api/reports";
import { formatCurrency, formatDate, formatNumber } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";

function StatCard({
  title, value, subtitle, icon: Icon, color = "bg-primary",
}: {
  title: string; value: string; subtitle?: string; icon: React.ElementType; color?: string;
}) {
  return (
    <Card>
      <CardContent className="p-5">
        <div className="flex items-start justify-between">
          <div className="space-y-1">
            <p className="text-sm text-muted-foreground">{title}</p>
            <p className="text-2xl font-bold">{value}</p>
            {subtitle && <p className="text-xs text-muted-foreground">{subtitle}</p>}
          </div>
          <div className={`${color} p-2.5 rounded-lg`}>
            <Icon className="w-5 h-5 text-white" />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function getLast7Days(): { start: string; end: string } {
  const end = new Date();
  const start = new Date();
  start.setDate(end.getDate() - 6);
  return {
    start: start.toISOString().split("T")[0],
    end: end.toISOString().split("T")[0],
  };
}

export function Dashboard() {
  const { t } = useTranslation();

  const { data: summary, isLoading } = useQuery({
    queryKey: ["dashboard"],
    queryFn: reportsApi.dashboard,
    refetchInterval: 60_000,
  });

  const { start: weekStart, end: weekEnd } = getLast7Days();
  const { data: weeklySales } = useQuery({
    queryKey: ["weekly-sales", weekStart, weekEnd],
    queryFn: () => reportsApi.salesSummary(weekStart, weekEnd),
  });

  const { data: finishedOilItems } = useQuery({
    queryKey: ["inventory-balance", "finished_oil"],
    queryFn: () => reportsApi.inventoryBalance({ item_type: "finished_oil" }),
    refetchInterval: 60_000,
  });

  const { data: rawMaterials } = useQuery({
    queryKey: ["inventory-balance", "raw_material"],
    queryFn: () => reportsApi.inventoryBalance({ item_type: "raw_material" }),
    refetchInterval: 60_000,
  });

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold">{t("dashboard.title")}</h1>
          <p className="text-muted-foreground text-sm">{t("dashboard.subtitle")}</p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
          {Array.from({ length: 5 }).map((_, i) => (
            <Card key={i}><CardContent className="p-5"><Skeleton className="h-16" /></CardContent></Card>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">{t("dashboard.title")}</h1>
        <p className="text-muted-foreground text-sm">{t("dashboard.subtitle")}</p>
      </div>

      {/* Financial stat cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        <StatCard
          title={t("dashboard.todaySales")}
          value={formatCurrency(summary?.today_sales_amount ?? 0)}
          subtitle={`${summary?.today_sales_count ?? 0} ${t("dashboard.vouchers")}`}
          icon={TrendingUp}
          color="bg-indigo-500"
        />
        <StatCard
          title={t("dashboard.todayExpenses")}
          value={formatCurrency(summary?.today_expenses_amount ?? 0)}
          icon={Receipt}
          color="bg-orange-500"
        />
        <StatCard
          title={t("dashboard.thisMonthSales")}
          value={formatCurrency(summary?.this_month_sales_amount ?? 0)}
          icon={TrendingUp}
          color="bg-indigo-400"
        />
        <StatCard
          title={t("dashboard.thisMonthExpenses")}
          value={formatCurrency(summary?.this_month_expenses_amount ?? 0)}
          icon={Receipt}
          color="bg-orange-400"
        />
        <StatCard
          title={t("dashboard.outstandingDebts")}
          value={formatCurrency(summary?.outstanding_debts_total ?? 0)}
          subtitle={`${summary?.outstanding_debts_count ?? 0} ${t("dashboard.customers")}`}
          icon={Users}
          color="bg-red-500"
        />
      </div>

      {/* All-time totals + net profit */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard
          title={t("dashboard.allTimeSales")}
          value={formatCurrency(summary?.all_time_sales_amount ?? 0)}
          icon={TrendingUp}
          color="bg-emerald-500"
        />
        <StatCard
          title={t("dashboard.allTimeExpenses")}
          value={formatCurrency(summary?.all_time_expenses_amount ?? 0)}
          icon={Receipt}
          color="bg-rose-500"
        />
        <StatCard
          title={t("dashboard.netProfit")}
          value={formatCurrency((summary?.all_time_sales_amount ?? 0) - (summary?.all_time_expenses_amount ?? 0))}
          icon={DollarSign}
          color={(summary?.all_time_sales_amount ?? 0) >= (summary?.all_time_expenses_amount ?? 0) ? "bg-green-600" : "bg-red-600"}
        />
      </div>

      {/* Finished Oil Stock + Low Stock side by side */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Finished Oil Stock */}
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <div className="bg-blue-500 p-2 rounded-lg">
                <Droplets className="w-4 h-4 text-white" />
              </div>
              <CardTitle className="text-base">{t("dashboard.finishedOilStock")}</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            {!finishedOilItems || finishedOilItems.length === 0 ? (
              <p className="text-sm text-muted-foreground px-6 pb-4">{t("dashboard.noFinishedOil")}</p>
            ) : (
              <div className="divide-y divide-border">
                {finishedOilItems.map((item) => (
                  <div key={item.item_id} className="flex items-center justify-between px-6 py-3">
                    <div className="flex items-center gap-2 min-w-0">
                      {item.is_low_stock && (
                        <AlertTriangle className="w-3.5 h-3.5 text-red-500 shrink-0" />
                      )}
                      <span className={`text-sm font-medium truncate ${item.is_low_stock ? "text-red-500" : ""}`}>
                        {item.item_name}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <span className={`text-sm font-bold tabular-nums ${item.is_low_stock ? "text-red-500" : ""}`}>
                        {formatNumber(item.current_balance)}
                      </span>
                      <span className="text-xs text-muted-foreground uppercase">{item.unit}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Raw Materials Stock */}
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <div className="bg-yellow-500 p-2 rounded-lg">
                <AlertTriangle className="w-4 h-4 text-white" />
              </div>
              <CardTitle className="text-base">{t("dashboard.rawMaterialsStock")}</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            {!rawMaterials || rawMaterials.length === 0 ? (
              <p className="text-sm text-muted-foreground px-6 pb-4">{t("dashboard.noRawMaterials")}</p>
            ) : (
              <div className="divide-y divide-border">
                {rawMaterials.map((item) => (
                  <div key={item.item_id} className="flex items-center justify-between px-6 py-3">
                    <div className="flex items-center gap-2 min-w-0">
                      {item.is_low_stock && (
                        <AlertTriangle className="w-3.5 h-3.5 text-red-500 shrink-0" />
                      )}
                      <span className={`text-sm font-medium truncate ${item.is_low_stock ? "text-red-500" : ""}`}>
                        {item.item_name}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <span className={`text-sm font-bold tabular-nums ${item.is_low_stock ? "text-red-500" : ""}`}>
                        {formatNumber(item.current_balance)}
                      </span>
                      <span className="text-xs text-muted-foreground uppercase">{item.unit}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Weekly sales chart */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("dashboard.salesThisWeek")}</CardTitle>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={(weeklySales ?? []).map((r) => ({
              day: formatDate(r.sale_date),
              amount: Number(r.total_amount),
            }))}>
              <defs>
                <linearGradient id="salesGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#4f46e5" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#4f46e5" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="day" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`} />
              <Tooltip formatter={(v) => formatCurrency(Number(v))} />
              <Area type="monotone" dataKey="amount" stroke="#4f46e5" fill="url(#salesGrad)" strokeWidth={2} name={t("dashboard.salesThisWeek")} />
            </AreaChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
    </div>
  );
}
