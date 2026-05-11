import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Eye, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { customersApi } from "@/api/customers";
import { vouchersApi } from "@/api/vouchers";
import { formatCurrency, formatDate } from "@/lib/utils";
import { useAuthStore } from "@/store/auth";
import { useToast } from "@/hooks/useToast";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import type { VoucherStatus } from "@/types";

function voucherPaymentVariant(status: VoucherStatus): string {
  if (status === "paid") return "success";
  if (status === "partially_paid") return "warning";
  if (status === "cancelled") return "destructive";
  return "outline";
}

export function CustomerDetail() {
  const { t } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const { user } = useAuthStore();
  const isManager = user?.role && ["manager", "admin", "super_admin"].includes(user.role);

  const { data, isLoading } = useQuery({
    queryKey: ["customer", id],
    queryFn: () => customersApi.get(id!),
    enabled: !!id,
  });

  const { data: vouchersData } = useQuery({
    queryKey: ["vouchers", "customer", id],
    queryFn: () => vouchersApi.list({ customer_id: id, per_page: 50 }),
    enabled: !!id,
  });

  const { data: debtsData } = useQuery({
    queryKey: ["customer-debts", id],
    queryFn: () => customersApi.listDebts(id!),
    enabled: !!id,
  });

  const cancelDebtMutation = useMutation({
    mutationFn: (debtId: string) =>
      customersApi.cancelDebt(debtId, "Written off by manager"),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["customer-debts", id] });
      queryClient.invalidateQueries({ queryKey: ["customer", id] });
      toast({ title: t("customers.debtWrittenOff"), variant: "success" as "default" });
    },
    onError: () => {
      toast({ title: t("common.error"), variant: "destructive" });
    },
  });

  const outstandingDebts = debtsData?.data?.filter(
    (d) => d.status === "outstanding" || d.status === "partially_paid"
  ) ?? [];

  const paymentLabel = (status: VoucherStatus) => {
    if (status === "paid") return t("vouchers.paid");
    if (status === "partially_paid") return t("vouchers.partiallyPaid");
    if (status === "cancelled") return t("vouchers.cancelled");
    return t("vouchers.unpaid");
  };

  if (isLoading) {
    return (
      <div className="max-w-3xl mx-auto space-y-5">
        <Skeleton className="h-10 w-48" />
        <Skeleton className="h-48" />
      </div>
    );
  }

  const customer = data;
  if (!customer) return <div>{t("customers.customerNotFound")}</div>;

  return (
    <div className="max-w-3xl mx-auto space-y-5">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={() => navigate("/customers")}>
          <ArrowLeft className="w-4 h-4" />
        </Button>
        <div className="flex-1">
          <h1 className="text-2xl font-bold">{customer.name}</h1>
          <p className="text-sm text-muted-foreground font-mono">{customer.code}</p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Card>
          <CardContent className="p-4">
            <p className="text-xs text-muted-foreground">{t("customers.outstandingBalance")}</p>
            <p className="text-lg font-bold text-orange-600">{formatCurrency(customer.credit_balance)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-xs text-muted-foreground">{t("customers.totalVouchers")}</p>
            <p className="text-lg font-bold">{vouchersData?.total ?? "—"}</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-base">{t("customers.customerDetails")}</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
            <div><p className="text-muted-foreground">{t("common.phone")}</p><p className="font-medium">{customer.phone ?? "—"}</p></div>
            <div><p className="text-muted-foreground">{t("common.type")}</p><p className="font-medium">{customer.customer_type}</p></div>
            <div className="sm:col-span-2"><p className="text-muted-foreground">{t("common.address")}</p><p className="font-medium">{customer.address ?? "—"}</p></div>
            <div><p className="text-muted-foreground">{t("customers.joinedDate")}</p><p className="font-medium">{formatDate(customer.created_at)}</p></div>
            {customer.notes && <div className="sm:col-span-2"><p className="text-muted-foreground">{t("common.notes")}</p><p className="font-medium">{customer.notes}</p></div>}
          </div>
        </CardContent>
      </Card>

      {outstandingDebts.length > 0 && (
        <Card className="border-orange-200">
          <CardHeader>
            <CardTitle className="text-base text-orange-700">{t("customers.outstandingDebts")}</CardTitle>
          </CardHeader>
          <CardContent className="p-0 overflow-x-auto">
            <Table className="min-w-[540px]">
              <TableHeader>
                <TableRow>
                  <TableHead>{t("common.date")}</TableHead>
                  <TableHead className="text-right">{t("customers.originalAmount")}</TableHead>
                  <TableHead className="text-right">{t("customers.paidAmount")}</TableHead>
                  <TableHead className="text-right">{t("vouchers.outstanding")}</TableHead>
                  <TableHead>{t("common.status")}</TableHead>
                  {isManager && <TableHead />}
                </TableRow>
              </TableHeader>
              <TableBody>
                {outstandingDebts.map((debt) => (
                  <TableRow key={debt.id}>
                    <TableCell className="text-sm">{formatDate(debt.created_at)}</TableCell>
                    <TableCell className="text-right">{formatCurrency(Number(debt.original_amount))}</TableCell>
                    <TableCell className="text-right">{formatCurrency(Number(debt.paid_amount))}</TableCell>
                    <TableCell className="text-right text-orange-600 font-medium">
                      {formatCurrency(Number(debt.original_amount) - Number(debt.paid_amount))}
                    </TableCell>
                    <TableCell>
                      <Badge variant={debt.status === "outstanding" ? "destructive" : "warning" as "default"}>
                        {debt.status}
                      </Badge>
                    </TableCell>
                    {isManager && (
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-red-600 hover:text-red-700"
                          onClick={() => cancelDebtMutation.mutate(debt.id)}
                          disabled={cancelDebtMutation.isPending}
                        >
                          <Trash2 className="w-4 h-4 mr-1" />
                          {t("customers.writeOff")}
                        </Button>
                      </TableCell>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-y-2">
            <CardTitle className="text-base">{t("customers.voucherHistory")}</CardTitle>
            <Button size="sm" onClick={() => navigate(`/vouchers/new?customer_id=${id}`)}>
              {t("customers.newVoucherForCustomer")}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="p-0 overflow-x-auto">
          {!vouchersData || vouchersData.data.length === 0 ? (
            <p className="text-sm text-muted-foreground p-4">{t("customers.noVouchersYet")}</p>
          ) : (
            <Table className="min-w-[560px]">
              <TableHeader>
                <TableRow>
                  <TableHead>{t("vouchers.voucherNumber")}</TableHead>
                  <TableHead>{t("common.date")}</TableHead>
                  <TableHead>{t("common.status")}</TableHead>
                  <TableHead className="text-right">{t("common.total")}</TableHead>
                  <TableHead className="text-right">{t("vouchers.outstanding")}</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {vouchersData.data.map((v) => (
                  <TableRow key={v.id} className="cursor-pointer" onClick={() => navigate(`/vouchers/${v.id}`)}>
                    <TableCell className="font-mono text-sm">{v.voucher_number}</TableCell>
                    <TableCell>{formatDate(v.sale_date)}</TableCell>
                    <TableCell>
                      <Badge variant={voucherPaymentVariant(v.status) as "default"}>
                        {paymentLabel(v.status)}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right font-medium">{formatCurrency(v.total_amount)}</TableCell>
                    <TableCell className="text-right text-orange-600">{formatCurrency(v.outstanding_amount)}</TableCell>
                    <TableCell>
                      <Button variant="ghost" size="icon" onClick={(e) => { e.stopPropagation(); navigate(`/vouchers/${v.id}`); }}>
                        <Eye className="w-4 h-4" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
