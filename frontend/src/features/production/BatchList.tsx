import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Plus, Eye } from "lucide-react";
import { useTranslation } from "react-i18next";
import { productionApi } from "@/api/production";
import { formatDate, formatNumber } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export function BatchList() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery({
    queryKey: ["production-batches", page],
    queryFn: () => productionApi.list({ page, per_page: 25 }),
  });

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-y-3">
        <div>
          <h1 className="text-2xl font-bold">{t("production.title")}</h1>
          <p className="text-sm text-muted-foreground">{t("production.subtitle")}</p>
        </div>
        <Button onClick={() => navigate("/production/new")}>
          <Plus className="w-4 h-4 mr-2" /> {t("production.newRun")}
        </Button>
      </div>

      <Card>
        <CardContent className="p-0 overflow-x-auto">
          {isLoading ? (
            <div className="p-4 space-y-3">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-12" />)}</div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("production.batchNumber")}</TableHead>
                  <TableHead>{t("common.date")}</TableHead>
                  <TableHead>{t("production.outputItem")}</TableHead>
                  <TableHead className="text-right">{t("production.outputAmount")}</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {data?.data.map((b) => (
                  <TableRow key={b.id} className="cursor-pointer" onClick={() => navigate(`/production/${b.id}`)}>
                    <TableCell className="font-mono text-sm">{b.batch_number}</TableCell>
                    <TableCell>{formatDate(b.start_date)}</TableCell>
                    <TableCell>{b.output_item_id}</TableCell>
                    <TableCell className="text-right font-medium">
                      {b.actual_output != null
                        ? `${formatNumber(b.actual_output)} ${b.output_unit}`
                        : `${formatNumber(b.expected_output)} ${b.output_unit}`}
                    </TableCell>
                    <TableCell>
                      <Button variant="ghost" size="icon"><Eye className="w-4 h-4" /></Button>
                    </TableCell>
                  </TableRow>
                ))}
                {data?.data.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={5} className="text-center py-8 text-muted-foreground">{t("production.noRunsFound")}</TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {data && data.total_pages > 1 && (
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">{t("common.total")}: {data.total}</span>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>{t("common.previous")}</Button>
            <Button variant="outline" size="sm" disabled={page >= data.total_pages} onClick={() => setPage((p) => p + 1)}>{t("common.next")}</Button>
          </div>
        </div>
      )}
    </div>
  );
}
