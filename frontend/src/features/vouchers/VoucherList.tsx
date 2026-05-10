import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Plus, Search, Eye } from "lucide-react";
import { useTranslation } from "react-i18next";
import { vouchersApi } from "@/api/vouchers";
import { formatCurrency, formatDate } from "@/lib/utils";
import type { VoucherStatus } from "@/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

function paymentStatusVariant(status: VoucherStatus): string {
  if (status === "paid") return "success";
  if (status === "partially_paid") return "warning";
  if (status === "cancelled") return "destructive";
  return "outline";
}

export function VoucherList() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");

  const paymentLabel = (status: VoucherStatus) => {
    if (status === "paid") return t("vouchers.paid");
    if (status === "partially_paid") return t("vouchers.partiallyPaid");
    if (status === "cancelled") return t("vouchers.cancelled");
    return t("vouchers.unpaid");
  };

  const { data, isLoading } = useQuery({
    queryKey: ["vouchers", page],
    queryFn: () => vouchersApi.list({ page, per_page: 25 }),
  });

  const filtered = data?.data.filter((v) =>
    !search || v.voucher_number.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-y-3">
        <div>
          <h1 className="text-2xl font-bold">{t("vouchers.title")}</h1>
          <p className="text-sm text-muted-foreground">{t("vouchers.subtitle")}</p>
        </div>
        <Button onClick={() => navigate("/vouchers/new")}>
          <Plus className="w-4 h-4 mr-2" /> {t("vouchers.newVoucher")}
        </Button>
      </div>

      <Card>
        <CardContent className="p-4">
          <div className="relative max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              className="pl-9"
              placeholder={t("vouchers.searchPlaceholder")}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0 overflow-x-auto">
          {isLoading ? (
            <div className="p-4 space-y-3">
              {Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-12" />)}
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("vouchers.voucherNumber")}</TableHead>
                  <TableHead>{t("common.date")}</TableHead>
                  <TableHead>{t("vouchers.payment")}</TableHead>
                  <TableHead className="text-right">{t("common.total")}</TableHead>
                  <TableHead className="text-right">{t("vouchers.paid")}</TableHead>
                  <TableHead className="text-right">{t("vouchers.outstanding")}</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {(filtered ?? []).map((v) => (
                  <TableRow key={v.id} className="cursor-pointer" onClick={() => navigate(`/vouchers/${v.id}`)}>
                    <TableCell className="font-mono text-sm">{v.voucher_number}</TableCell>
                    <TableCell>{formatDate(v.sale_date)}</TableCell>
                    <TableCell>
                      <Badge variant={paymentStatusVariant(v.status) as "default"}>
                        {paymentLabel(v.status)}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right font-medium">{formatCurrency(v.total_amount)}</TableCell>
                    <TableCell className="text-right text-green-600">{formatCurrency(v.paid_amount)}</TableCell>
                    <TableCell className="text-right text-orange-600">{formatCurrency(Math.max(0, Number(v.outstanding_amount)))}</TableCell>
                    <TableCell>
                      <Button variant="ghost" size="icon" onClick={(e) => { e.stopPropagation(); navigate(`/vouchers/${v.id}`); }}>
                        <Eye className="w-4 h-4" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
                {(filtered ?? []).length === 0 && (
                  <TableRow>
                    <TableCell colSpan={7} className="text-center py-8 text-muted-foreground">{t("vouchers.noVouchersFound")}</TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {data && data.total_pages > 1 && (
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">
            {t("common.showing")} {(page - 1) * 25 + 1}–{Math.min(page * 25, data.total)} {t("common.of")} {data.total}
          </span>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>{t("common.previous")}</Button>
            <Button variant="outline" size="sm" disabled={page >= data.total_pages} onClick={() => setPage((p) => p + 1)}>{t("common.next")}</Button>
          </div>
        </div>
      )}
    </div>
  );
}
