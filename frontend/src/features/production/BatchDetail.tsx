import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { useTranslation } from "react-i18next";
import { productionApi } from "@/api/production";
import { inventoryApi } from "@/api/inventory";
import { formatDate, formatNumber } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";

export function BatchDetail() {
  const { t } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data, isLoading } = useQuery({
    queryKey: ["production-batch", id],
    queryFn: () => productionApi.get(id!),
    enabled: !!id,
  });

  const { data: inventoryData } = useQuery({
    queryKey: ["inventory-items-all"],
    queryFn: () => inventoryApi.listItems({ per_page: 500 }),
  });

  if (isLoading) {
    return (
      <div className="max-w-3xl mx-auto space-y-5">
        <Skeleton className="h-10 w-48" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  const batch = data;
  if (!batch) return <div>{t("production.batchNotFound")}</div>;

  const itemNameMap = Object.fromEntries(
    (inventoryData?.data ?? []).map((item) => [item.id, item.name])
  );

  // Use actual outputs if available, otherwise fall back to primary output
  const outputs = batch.outputs && batch.outputs.length > 0
    ? batch.outputs
    : [{ output_item_id: batch.output_item_id, quantity: batch.actual_output ?? batch.expected_output, unit: batch.output_unit }];

  return (
    <div className="max-w-3xl mx-auto space-y-5">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={() => navigate("/production")}>
          <ArrowLeft className="w-4 h-4" />
        </Button>
        <div className="flex-1">
          <h1 className="text-2xl font-bold font-mono">{batch.batch_number}</h1>
          <p className="text-sm text-muted-foreground">{formatDate(batch.start_date)}</p>
        </div>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-base">{t("production.outputItem")}</CardTitle></CardHeader>
        <CardContent className="p-0 overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("production.outputItemLabel")}</TableHead>
                <TableHead className="text-right">{t("common.quantity")}</TableHead>
                <TableHead>{t("common.unit")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {outputs.map((o, i) => (
                <TableRow key={i}>
                  <TableCell className="font-medium">
                    {itemNameMap[(o as any).output_item_id] ?? (o as any).output_item_id}
                  </TableCell>
                  <TableCell className="text-right">{formatNumber((o as any).quantity)}</TableCell>
                  <TableCell className="uppercase">{(o as any).unit}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">{t("production.rawMaterials")}</CardTitle></CardHeader>
        <CardContent className="p-0 overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("production.material")}</TableHead>
                <TableHead className="text-right">{t("common.quantity")}</TableHead>
                <TableHead>{t("common.unit")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {batch.material_usages.map((m) => (
                <TableRow key={m.id}>
                  <TableCell className="font-medium">
                    {itemNameMap[m.material_item_id] ?? <span className="font-mono text-xs">{m.material_item_id}</span>}
                  </TableCell>
                  <TableCell className="text-right">
                    {formatNumber(m.actual_quantity ?? m.planned_quantity)}
                  </TableCell>
                  <TableCell className="uppercase">{m.unit}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {batch.notes && (
        <Card>
          <CardContent className="p-4">
            <p className="text-xs text-muted-foreground mb-1">{t("common.notes")}</p>
            <p className="text-sm">{batch.notes}</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
