import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Eye } from "lucide-react";
import { useTranslation } from "react-i18next";
import { customersApi } from "@/api/customers";
import { vouchersApi } from "@/api/vouchers";
import { formatCurrency, formatDate } from "@/lib/utils";
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
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div><p className="text-muted-foreground">{t("common.phone")}</p><p className="font-medium">{customer.phone ?? "—"}</p></div>
            <div><p className="text-muted-foreground">{t("common.type")}</p><p className="font-medium">{customer.customer_type}</p></div>
            <div className="col-span-2"><p className="text-muted-foreground">{t("common.address")}</p><p className="font-medium">{customer.address ?? "—"}</p></div>
            <div><p className="text-muted-foreground">{t("customers.joinedDate")}</p><p className="font-medium">{formatDate(customer.created_at)}</p></div>
            {customer.notes && <div className="col-span-2"><p className="text-muted-foreground">{t("common.notes")}</p><p className="font-medium">{customer.notes}</p></div>}
          </div>
        </CardContent>
      </Card>

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
            <Table>
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
