import { useState, useEffect } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Plus, Pencil, Trash2, PackagePlus } from "lucide-react";
import { useForm, type Resolver } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useTranslation } from "react-i18next";
import { inventoryApi } from "@/api/inventory";
import { queryClient } from "@/lib/queryClient";
import { formatNumber, getErrorMessage } from "@/lib/utils";
import { INVENTORY_ITEM_TYPES, WEIGHT_UNITS } from "@/lib/constants";
import { toast } from "@/hooks/useToast";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import type { InventoryItemType, InventoryItemResponse } from "@/types";

const createSchema = z.object({
  name: z.string().min(1),
  item_type: z.enum(["raw_material", "finished_oil", "packaging"]),
  unit: z.enum(["viss", "tical", "kg", "liter", "unit"]),
  description: z.string().optional(),
  initial_quantity: z.coerce.number().positive().optional().or(z.literal("")),
  unit_cost: z.coerce.number().min(0).optional().or(z.literal("")),
});
type CreateForm = z.infer<typeof createSchema>;

const editSchema = z.object({
  name: z.string().min(1),
  purchase_date: z.string().optional(),
  description: z.string().optional(),
  reorder_level: z.coerce.number().min(0).optional().or(z.literal("")),
  reorder_quantity: z.coerce.number().min(0).optional().or(z.literal("")),
});
type EditForm = z.infer<typeof editSchema>;

const stockSchema = z.object({
  quantity: z.coerce.number().positive(),
  unit_price: z.coerce.number().min(0).optional().or(z.literal("")),
  transaction_date: z.string().min(1),
  notes: z.string().optional(),
});
type StockForm = z.infer<typeof stockSchema>;

export function InventoryList() {
  const { t } = useTranslation();
  const [page, setPage] = useState(1);
  const [typeFilter, setTypeFilter] = useState<InventoryItemType | "all">("all");
  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<InventoryItemResponse | null>(null);
  const [stockTarget, setStockTarget] = useState<InventoryItemResponse | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<InventoryItemResponse | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [editError, setEditError] = useState<string | null>(null);
  const [stockError, setStockError] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["inventory-items", page, typeFilter],
    queryFn: () =>
      inventoryApi.listItems({
        page,
        per_page: 25,
        item_type: typeFilter === "all" ? undefined : typeFilter,
      }),
  });

  const {
    register, handleSubmit, reset,
    formState: { errors, isSubmitting },
  } = useForm<CreateForm>({
    resolver: zodResolver(createSchema) as Resolver<CreateForm>,
    defaultValues: { item_type: "raw_material", unit: "viss" },
  });

  const {
    register: regEdit, handleSubmit: submitEdit, reset: resetEdit,
    formState: { errors: errEdit, isSubmitting: isEditing },
  } = useForm<EditForm>({
    resolver: zodResolver(editSchema) as Resolver<EditForm>,
  });

  const {
    register: regStock, handleSubmit: submitStock, reset: resetStock,
    formState: { errors: errStock, isSubmitting: isAddingStock },
  } = useForm<StockForm>({
    resolver: zodResolver(stockSchema) as Resolver<StockForm>,
  });

  useEffect(() => {
    if (editTarget) {
      resetEdit({
        name: editTarget.name,
        purchase_date: editTarget.purchase_date ?? "",
        description: editTarget.description ?? "",
        reorder_level: editTarget.reorder_level ?? "",
        reorder_quantity: editTarget.reorder_quantity ?? "",
      });
      setEditError(null);
    }
  }, [editTarget]);

  useEffect(() => {
    if (stockTarget) {
      resetStock({ transaction_date: new Date().toISOString().split("T")[0] });
      setStockError(null);
    }
  }, [stockTarget]);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["inventory-items"] });

  const createMutation = useMutation({
    mutationFn: (d: CreateForm) => inventoryApi.createItem({
      ...d,
      initial_quantity: d.initial_quantity === "" ? undefined : d.initial_quantity as number | undefined,
      unit_cost: d.unit_cost === "" ? undefined : d.unit_cost as number | undefined,
    }),
    onSuccess: () => {
      invalidate();
      toast({ title: t("inventory.newInventoryItem"), variant: "success" as "default" });
      setCreateOpen(false);
      reset();
    },
    onError: (e) => setCreateError(getErrorMessage(e)),
  });

  const editMutation = useMutation({
    mutationFn: (d: EditForm) => inventoryApi.updateItem(editTarget!.id, {
      name: d.name,
      purchase_date: d.purchase_date || undefined,
      description: d.description || undefined,
      reorder_level: d.reorder_level === "" ? undefined : d.reorder_level as number | undefined,
      reorder_quantity: d.reorder_quantity === "" ? undefined : d.reorder_quantity as number | undefined,
    }),
    onSuccess: () => {
      invalidate();
      toast({ title: t("inventory.itemUpdated"), variant: "success" as "default" });
      setEditTarget(null);
    },
    onError: (e) => setEditError(getErrorMessage(e)),
  });

  const stockMutation = useMutation({
    mutationFn: (d: StockForm) => inventoryApi.createMovement({
      item_id: stockTarget!.id,
      movement_type: "purchase_in",
      quantity: d.quantity,
      unit: stockTarget!.unit,
      unit_price: d.unit_price === "" ? undefined : d.unit_price as number | undefined,
      transaction_date: d.transaction_date,
      notes: d.notes || undefined,
    }),
    onSuccess: () => {
      invalidate();
      toast({ title: t("inventory.stockAdded"), variant: "success" as "default" });
      setStockTarget(null);
    },
    onError: (e) => setStockError(getErrorMessage(e)),
  });

  const deleteMutation = useMutation({
    mutationFn: () => inventoryApi.deleteItem(deleteTarget!.id),
    onSuccess: () => {
      invalidate();
      toast({ title: t("inventory.itemDeleted"), variant: "success" as "default" });
      setDeleteTarget(null);
    },
    onError: (e) => setDeleteError(getErrorMessage(e)),
  });

  const itype = (k: string) => t(`inventoryItemTypes.${k}`, { defaultValue: k });

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-y-3">
        <div>
          <h1 className="text-2xl font-bold">{t("inventory.title")}</h1>
          <p className="text-sm text-muted-foreground">{t("inventory.subtitle")}</p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="w-4 h-4 mr-2" /> {t("inventory.newItem")}
        </Button>
      </div>

      <Card>
        <CardContent className="p-4">
          <Select value={typeFilter} onValueChange={(v) => setTypeFilter(v as InventoryItemType | "all")}>
            <SelectTrigger className="w-full sm:w-44">
              <SelectValue placeholder={t("inventory.allTypes")} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t("inventory.allTypes")}</SelectItem>
              {Object.entries(INVENTORY_ITEM_TYPES).map(([k]) => (
                <SelectItem key={k} value={k}>{itype(k)}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0 overflow-x-auto">
          {isLoading ? (
            <div className="p-4 space-y-3">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-12" />)}</div>
          ) : (
            <Table className="min-w-[560px]">
              <TableHeader>
                <TableRow>
                  <TableHead>{t("common.code")}</TableHead>
                  <TableHead>{t("common.name")}</TableHead>
                  <TableHead>{t("common.type")}</TableHead>
                  <TableHead className="text-right">{t("common.quantity")}</TableHead>
                  <TableHead>{t("common.unit")}</TableHead>
                  <TableHead className="w-28" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {data?.data.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell className="font-mono text-sm">{item.code}</TableCell>
                    <TableCell className="font-medium">{item.name}</TableCell>
                    <TableCell>{itype(item.item_type)}</TableCell>
                    <TableCell className="text-right font-medium">{formatNumber(item.current_balance)}</TableCell>
                    <TableCell className="uppercase">{item.unit}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1 justify-end">
                        <Button
                          variant="ghost" size="icon" className="h-8 w-8"
                          title={t("inventory.addStock")}
                          onClick={() => setStockTarget(item)}
                        >
                          <PackagePlus className="w-4 h-4" />
                        </Button>
                        <Button
                          variant="ghost" size="icon" className="h-8 w-8"
                          title={t("common.edit")}
                          onClick={() => setEditTarget(item)}
                        >
                          <Pencil className="w-4 h-4" />
                        </Button>
                        <Button
                          variant="ghost" size="icon" className="h-8 w-8 text-destructive hover:text-destructive"
                          title={t("common.delete")}
                          onClick={() => { setDeleteTarget(item); setDeleteError(null); }}
                        >
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
                {data?.data.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center py-8 text-muted-foreground">{t("inventory.noItemsFound")}</TableCell>
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

      {/* Create Dialog */}
      <Dialog open={createOpen} onOpenChange={(v) => { setCreateOpen(v); if (!v) { reset(); setCreateError(null); } }}>
        <DialogContent>
          <DialogHeader><DialogTitle>{t("inventory.newInventoryItem")}</DialogTitle></DialogHeader>
          {createError && <p className="text-sm text-destructive">{createError}</p>}
          <form onSubmit={handleSubmit((d) => createMutation.mutate(d))} className="space-y-3" autoComplete="off">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="sm:col-span-2 space-y-1.5">
                <Label>{t("common.name")} *</Label>
                <Input {...register("name")} />
                {errors.name && <p className="text-xs text-destructive">{errors.name.message}</p>}
              </div>
              <div className="space-y-1.5">
                <Label>{t("common.type")} *</Label>
                <select className="flex h-9 w-full rounded-md border border-input bg-input px-3 py-1 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" {...register("item_type")}>
                  {Object.entries(INVENTORY_ITEM_TYPES).map(([k]) => (
                    <option key={k} value={k}>{itype(k)}</option>
                  ))}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label>{t("common.unit")} *</Label>
                <select className="flex h-9 w-full rounded-md border border-input bg-input px-3 py-1 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" {...register("unit")}>
                  {Object.entries(WEIGHT_UNITS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label>{t("inventory.openingStock")}</Label>
                <Input type="number" min="0" step="any" placeholder="0" {...register("initial_quantity")} />
              </div>
              <div className="space-y-1.5">
                <Label>{t("inventory.unitCost")}</Label>
                <Input type="number" min="0" step="any" placeholder="0" {...register("unit_cost")} />
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setCreateOpen(false)}>{t("common.cancel")}</Button>
              <Button type="submit" disabled={isSubmitting}>{t("common.create")}</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Edit Dialog */}
      <Dialog open={!!editTarget} onOpenChange={(v) => { if (!v) setEditTarget(null); }}>
        <DialogContent>
          <DialogHeader><DialogTitle>{t("inventory.editItem")}</DialogTitle></DialogHeader>
          {editError && <p className="text-sm text-destructive">{editError}</p>}
          <form onSubmit={submitEdit((d) => editMutation.mutate(d))} className="space-y-3" autoComplete="off">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="sm:col-span-2 space-y-1.5">
                <Label>{t("common.name")} *</Label>
                <Input {...regEdit("name")} />
                {errEdit.name && <p className="text-xs text-destructive">{errEdit.name.message}</p>}
              </div>
              <div className="space-y-1.5">
                <Label>{t("inventory.purchaseDate")}</Label>
                <Input type="date" {...regEdit("purchase_date")} />
              </div>
              <div className="space-y-1.5">
                <Label>{t("common.notes")}</Label>
                <Input {...regEdit("description")} />
              </div>
              <div className="space-y-1.5">
                <Label>{t("inventory.reorderLevel")}</Label>
                <Input type="number" min="0" step="any" {...regEdit("reorder_level")} />
              </div>
              <div className="space-y-1.5">
                <Label>{t("inventory.reorderQuantity")}</Label>
                <Input type="number" min="0" step="any" {...regEdit("reorder_quantity")} />
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setEditTarget(null)}>{t("common.cancel")}</Button>
              <Button type="submit" disabled={isEditing}>{t("common.saveChanges")}</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Add Stock Dialog */}
      <Dialog open={!!stockTarget} onOpenChange={(v) => { if (!v) setStockTarget(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("inventory.addStock")}</DialogTitle>
            {stockTarget && (
              <p className="text-sm text-muted-foreground mt-1">
                {stockTarget.name} — {t("inventory.currentBalance")}: {formatNumber(stockTarget.current_balance)} {stockTarget.unit}
              </p>
            )}
          </DialogHeader>
          {stockError && <p className="text-sm text-destructive">{stockError}</p>}
          <form onSubmit={submitStock((d) => stockMutation.mutate(d))} className="space-y-3" autoComplete="off">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>{t("common.date")} *</Label>
                <Input type="date" {...regStock("transaction_date")} />
                {errStock.transaction_date && <p className="text-xs text-destructive">{errStock.transaction_date.message}</p>}
              </div>
              <div className="space-y-1.5">
                <Label>{t("common.quantity")} ({stockTarget?.unit}) *</Label>
                <Input type="number" min="0.001" step="any" {...regStock("quantity")} />
                {errStock.quantity && <p className="text-xs text-destructive">{errStock.quantity.message}</p>}
              </div>
              <div className="space-y-1.5">
                <Label>{t("inventory.unitCostShort")}</Label>
                <Input type="number" min="0" step="any" placeholder="0" {...regStock("unit_price")} />
              </div>
              <div className="space-y-1.5">
                <Label>{t("common.notes")}</Label>
                <Input {...regStock("notes")} />
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setStockTarget(null)}>{t("common.cancel")}</Button>
              <Button type="submit" disabled={isAddingStock}>{t("inventory.addStock")}</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Delete Confirm Dialog */}
      <Dialog open={!!deleteTarget} onOpenChange={(v) => { if (!v) setDeleteTarget(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("common.delete")} — {deleteTarget?.name}</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">{t("inventory.deleteWarning")}</p>
          {deleteError && <p className="text-sm text-destructive">{deleteError}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setDeleteTarget(null)}>{t("common.cancel")}</Button>
            <Button
              variant="destructive"
              onClick={() => deleteMutation.mutate()}
              disabled={deleteMutation.isPending}
            >
              {t("common.delete")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
