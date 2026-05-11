import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Plus, Pencil } from "lucide-react";
import { useForm, type Resolver } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useTranslation } from "react-i18next";
import { expensesApi } from "@/api/expenses";
import { queryClient } from "@/lib/queryClient";
import { formatCurrency, formatDate, getErrorMessage } from "@/lib/utils";
import { useAuthStore } from "@/store/auth";
import { toast } from "@/hooks/useToast";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import type { ExpenseResponse } from "@/types";

const CATEGORY_KEYS = ["labour", "utilities", "transport", "maintenance", "packaging", "administrative", "marketing", "rent", "other"] as const;
type CategoryKey = typeof CATEGORY_KEYS[number];

const editSchema = z.object({
  description: z.string().min(1),
  category: z.enum(CATEGORY_KEYS),
  amount: z.coerce.number().positive(),
  expense_date: z.string().min(1),
});

const createSchema = z.object({
  category: z.enum(CATEGORY_KEYS),
  description: z.string().min(1),
  amount: z.coerce.number().positive(),
  expense_date: z.string().min(1),
});
type CreateForm = z.infer<typeof createSchema>;
type EditForm = z.infer<typeof editSchema>;

export function ExpenseList() {
  const { t } = useTranslation();
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<ExpenseResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { user } = useAuthStore();
  const canEdit = user?.role === "manager" || user?.role === "admin" || user?.role === "super_admin";

  const { data, isLoading } = useQuery({
    queryKey: ["expenses", page],
    queryFn: () => expensesApi.list({ page, per_page: 25 }),
  });

  const { register, handleSubmit, reset, formState: { errors, isSubmitting } } = useForm<CreateForm>({
    resolver: zodResolver(createSchema) as Resolver<CreateForm>,
    defaultValues: {
      category: "other",
      expense_date: new Date().toISOString().split("T")[0],
    },
  });

  const mutation = useMutation({
    mutationFn: (d: CreateForm) => expensesApi.create(d),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["expenses"] });
      toast({ title: t("expenses.recordExpense"), variant: "success" as "default" });
      setOpen(false);
      reset();
    },
    onError: (e) => setError(getErrorMessage(e)),
  });

  const { register: regEdit, handleSubmit: handleEdit, reset: resetEdit, formState: { isSubmitting: editSubmitting } } = useForm<EditForm>({
    resolver: zodResolver(editSchema) as Resolver<EditForm>,
  });

  const editMutation = useMutation({
    mutationFn: (d: EditForm) => expensesApi.update(editTarget!.id, d),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["expenses"] });
      toast({ title: t("expenses.editExpense"), variant: "success" as "default" });
      setEditTarget(null);
    },
    onError: (e) => toast({ title: "Error", description: getErrorMessage(e), variant: "destructive" }),
  });

  function openEdit(expense: ExpenseResponse) {
    resetEdit({
      description: expense.description,
      category: expense.category as CategoryKey,
      amount: Number(expense.amount),
      expense_date: expense.expense_date,
    });
    setEditTarget(expense);
  }

  const catLabel = (k: string) => t(`expenseCategories.${k}`, { defaultValue: k });

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-y-3">
        <div>
          <h1 className="text-2xl font-bold">{t("expenses.title")}</h1>
          <p className="text-sm text-muted-foreground">{t("expenses.subtitle")}</p>
        </div>
        <Button onClick={() => setOpen(true)}>
          <Plus className="w-4 h-4 mr-2" /> {t("expenses.recordExpense")}
        </Button>
      </div>

      <Card>
        <CardContent className="p-0 overflow-x-auto">
          {isLoading ? (
            <div className="p-4 space-y-3">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-12" />)}</div>
          ) : (
            <Table className="min-w-[560px]">
              <TableHeader>
                <TableRow>
                  <TableHead>{t("common.ref")}</TableHead>
                  <TableHead>{t("common.date")}</TableHead>
                  <TableHead>{t("common.category")}</TableHead>
                  <TableHead>{t("common.description")}</TableHead>
                  <TableHead className="text-right">{t("common.amount")}</TableHead>
                  {canEdit && <TableHead />}
                </TableRow>
              </TableHeader>
              <TableBody>
                {data?.data.map((e) => (
                  <TableRow key={e.id}>
                    <TableCell className="font-mono text-sm">{e.reference_number}</TableCell>
                    <TableCell>{formatDate(e.expense_date)}</TableCell>
                    <TableCell>{catLabel(e.category)}</TableCell>
                    <TableCell className="max-w-48 truncate">{e.description}</TableCell>
                    <TableCell className="text-right font-medium">{formatCurrency(e.amount)}</TableCell>
                    {canEdit && (
                      <TableCell>
                        <Button variant="ghost" size="icon" onClick={() => openEdit(e)}>
                          <Pencil className="w-4 h-4" />
                        </Button>
                      </TableCell>
                    )}
                  </TableRow>
                ))}
                {data?.data.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={canEdit ? 6 : 5} className="text-center py-8 text-muted-foreground">{t("expenses.noExpensesFound")}</TableCell>
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

      {/* Create dialog */}
      <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) { reset(); setError(null); } }}>
        <DialogContent>
          <DialogHeader><DialogTitle>{t("expenses.recordExpense")}</DialogTitle></DialogHeader>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <form onSubmit={handleSubmit((d) => mutation.mutate(d))} className="space-y-3" autoComplete="off">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>{t("common.category")} *</Label>
                <select className="flex h-9 w-full rounded-md border border-input bg-input px-3 py-1 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" {...register("category")}>
                  {CATEGORY_KEYS.map((k) => <option key={k} value={k}>{catLabel(k)}</option>)}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label>{t("common.date")} *</Label>
                <Input type="date" {...register("expense_date")} />
                {errors.expense_date && <p className="text-xs text-destructive">{errors.expense_date.message}</p>}
              </div>
              <div className="sm:col-span-2 space-y-1.5">
                <Label>{t("common.description")} *</Label>
                <Input {...register("description")} />
                {errors.description && <p className="text-xs text-destructive">{errors.description.message}</p>}
              </div>
              <div className="sm:col-span-2 space-y-1.5">
                <Label>{t("expenses.amountKyats")}</Label>
                <Input type="number" step="1" {...register("amount")} />
                {errors.amount && <p className="text-xs text-destructive">{errors.amount.message}</p>}
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setOpen(false)}>{t("common.cancel")}</Button>
              <Button type="submit" disabled={isSubmitting}>{t("common.save")}</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Edit dialog */}
      <Dialog open={!!editTarget} onOpenChange={(v) => { if (!v) setEditTarget(null); }}>
        <DialogContent>
          <DialogHeader><DialogTitle>{t("expenses.editExpense")}</DialogTitle></DialogHeader>
          <form onSubmit={handleEdit((d) => editMutation.mutate(d))} className="space-y-3" autoComplete="off">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>{t("common.category")} *</Label>
                <select className="flex h-9 w-full rounded-md border border-input bg-input px-3 py-1 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" {...regEdit("category")}>
                  {CATEGORY_KEYS.map((k) => <option key={k} value={k}>{catLabel(k)}</option>)}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label>{t("common.date")} *</Label>
                <Input type="date" {...regEdit("expense_date")} />
              </div>
              <div className="sm:col-span-2 space-y-1.5">
                <Label>{t("common.description")} *</Label>
                <Input {...regEdit("description")} />
              </div>
              <div className="sm:col-span-2 space-y-1.5">
                <Label>{t("expenses.amountKyats")}</Label>
                <Input type="number" step="1" {...regEdit("amount")} />
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setEditTarget(null)}>{t("common.cancel")}</Button>
              <Button type="submit" disabled={editSubmitting}>{t("common.save")}</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
