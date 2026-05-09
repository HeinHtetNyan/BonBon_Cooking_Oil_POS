import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation } from "@tanstack/react-query";
import { ArrowLeft, XCircle, Loader2, Pencil, Plus, Trash2, CreditCard } from "lucide-react";
import { useForm, useFieldArray, type Resolver } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { vouchersApi } from "@/api/vouchers";
import { inventoryApi } from "@/api/inventory";
import { customersApi } from "@/api/customers";
import { queryClient } from "@/lib/queryClient";
import { formatCurrency, formatDate, getErrorMessage } from "@/lib/utils";
import { useAuthStore } from "@/store/auth";
import type { CustomerResponse, PaginatedResponse } from "@/types";
import { toast } from "@/hooks/useToast";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from "@/components/ui/alert-dialog";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import type { VoucherStatus } from "@/types";

// labels are now generated inside the component with useTranslation

function paymentStatusVariant(status: VoucherStatus): string {
  if (status === "paid") return "success";
  if (status === "partially_paid") return "warning";
  if (status === "cancelled") return "destructive";
  return "outline";
}

const editSchema = z.object({
  sale_date: z.string().min(1),
  customer_id: z.string().optional(),
  notes: z.string().optional(),
  extra_charges: z.array(z.object({
    description: z.string().min(1, "Required"),
    amount: z.coerce.number().positive("Must be > 0"),
  })).optional(),
  items: z.array(z.object({
    inventory_item_id: z.string().min(1, "Required"),
    quantity: z.coerce.number().positive("Must be > 0"),
    unit: z.string().min(1),
    unit_price: z.coerce.number().min(0),
    discount_percent: z.coerce.number().min(0).max(100).optional(),
  })).min(1, "At least one item required"),
});
type EditForm = z.infer<typeof editSchema>;

const paymentSchema = z.object({
  amount: z.coerce.number().positive("Amount must be > 0"),
  bank_ref: z.string().optional(),
});
type PaymentForm = z.infer<typeof paymentSchema>;

type PaymentMethod = "Cash" | "KPay" | "Bank Transfer";

export function VoucherDetail() {
  const { t } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuthStore();

  const paymentStatusLabel = (status: VoucherStatus) => {
    if (status === "paid") return t("vouchers.paid");
    if (status === "partially_paid") return t("vouchers.partiallyPaid");
    if (status === "cancelled") return t("vouchers.cancelled");
    return t("vouchers.unpaid");
  };
  const isAdmin = user?.role === "admin" || user?.role === "super_admin";
  const [voidReason, setVoidReason] = useState("");
  const [editOpen, setEditOpen] = useState(false);
  const [paymentOpen, setPaymentOpen] = useState(false);
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["voucher", id],
    queryFn: () => vouchersApi.get(id!),
    enabled: !!id,
  });

  const { data: inventoryData } = useQuery({
    queryKey: ["inventory-items-all"],
    queryFn: () => inventoryApi.listItems({ per_page: 500 }),
  });

  const { data: customersData } = useQuery<PaginatedResponse<CustomerResponse>>({
    queryKey: ["customers-all"],
    queryFn: () => customersApi.list({ per_page: 500 }),
  });

  const { data: voucherCustomer } = useQuery({
    queryKey: ["customer", data?.customer_id],
    queryFn: () => customersApi.get(data!.customer_id!),
    enabled: !!data?.customer_id,
  });

  const itemNameMap = Object.fromEntries(
    (inventoryData?.data ?? []).map((item) => [item.id, item.name])
  );
  const customerNameMap = Object.fromEntries(
    (customersData?.data ?? []).map((c: CustomerResponse) => [c.id, c.name])
  );

  const confirmMutation = useMutation({
    mutationFn: () => vouchersApi.confirm(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["voucher", id] });
      queryClient.invalidateQueries({ queryKey: ["vouchers"] });
      queryClient.invalidateQueries({ queryKey: ["inventory-items"] });
      toast({ title: t("vouchers.voucherDetails"), variant: "success" as "default" });
    },
    onError: (e) => toast({ title: "Error", description: getErrorMessage(e), variant: "destructive" }),
  });

  const voidMutation = useMutation({
    mutationFn: () =>
      vouchersApi.void(id!, { reason: voidReason, expected_version: data?.version_number }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["voucher", id] });
      queryClient.invalidateQueries({ queryKey: ["vouchers"] });
      toast({ title: t("vouchers.cancelVoucher") });
    },
    onError: (e) => toast({ title: "Error", description: getErrorMessage(e), variant: "destructive" }),
  });

  const { register: regEdit, control: ctrlEdit, handleSubmit: handleEdit, reset: resetEdit, formState: { isSubmitting: editSubmitting } } = useForm<EditForm>({
    resolver: zodResolver(editSchema) as Resolver<EditForm>,
  });

  const { fields: extraFields, append: appendExtra, remove: removeExtra } = useFieldArray({
    control: ctrlEdit,
    name: "extra_charges",
  });

  const { fields: itemFields, append: appendItem, remove: removeItem } = useFieldArray({
    control: ctrlEdit,
    name: "items",
  });

  const editMutation = useMutation({
    mutationFn: async (d: EditForm) => {
      await vouchersApi.updateItems(id!, d.items.map((it) => ({
        inventory_item_id: it.inventory_item_id,
        quantity: it.quantity,
        unit: it.unit as import("@/types").WeightUnit,
        unit_price: it.unit_price,
        discount_percent: it.discount_percent ?? 0,
      })));
      return vouchersApi.update(id!, {
        notes: d.notes,
        customer_id: d.customer_id || undefined,
        sale_date: d.sale_date,
        extra_charges: d.extra_charges,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["voucher", id] });
      queryClient.invalidateQueries({ queryKey: ["vouchers"] });
      toast({ title: t("vouchers.editVoucher"), variant: "success" as "default" });
      setEditOpen(false);
    },
    onError: (e) => toast({ title: "Error", description: getErrorMessage(e), variant: "destructive" }),
  });

  const { register: regPay, handleSubmit: handlePay, reset: resetPay, formState: { isSubmitting: paySubmitting, errors: payErrors } } = useForm<PaymentForm>({
    resolver: zodResolver(paymentSchema) as Resolver<PaymentForm>,
  });

  const codeMap: Record<PaymentMethod, string> = {
    Cash: "CASH",
    KPay: "KBZ_PAY",
    "Bank Transfer": "BANK_TRANSFER",
  };

  const paymentMutation = useMutation({
    mutationFn: (d: PaymentForm) => {
      const method = paymentMethod ?? "Cash";
      return vouchersApi.recordPayment(id!, {
        payment_method_code: codeMap[method],
        amount: d.amount,
        reference_number: method === "Bank Transfer" && d.bank_ref?.trim() ? d.bank_ref.trim() : undefined,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["voucher", id] });
      queryClient.invalidateQueries({ queryKey: ["vouchers"] });
      queryClient.invalidateQueries({ queryKey: ["customers"] });
      toast({ title: t("vouchers.recordPayment"), variant: "success" as "default" });
      setPaymentOpen(false);
      setPaymentMethod("Cash");
      resetPay();
    },
    onError: (e) => toast({ title: "Error", description: getErrorMessage(e), variant: "destructive" }),
  });

  function openEdit() {
    if (!voucher) return;
    resetEdit({
      sale_date: voucher.sale_date,
      customer_id: voucher.customer_id ?? "",
      notes: voucher.notes ?? "",
      extra_charges: voucher.extra_charges ?? [],
      items: voucher.items.map((it) => ({
        inventory_item_id: it.inventory_item_id,
        quantity: Number(it.quantity),
        unit: it.unit,
        unit_price: Number(it.unit_price),
        discount_percent: Number(it.discount_percent),
      })),
    });
    setEditOpen(true);
  }

  const voucher = data;

  if (isLoading) {
    return (
      <div className="max-w-3xl mx-auto space-y-5">
        <Skeleton className="h-10 w-48" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  if (!voucher) return <div>{t("vouchers.voucherNotFound")}</div>;

  const customerName = voucher.customer_id ? customerNameMap[voucher.customer_id] : null;

  return (
    <div className="max-w-3xl mx-auto space-y-5">
      <div className="flex flex-wrap items-start gap-3">
        <Button variant="ghost" size="icon" onClick={() => navigate("/vouchers")} className="shrink-0">
          <ArrowLeft className="w-4 h-4" />
        </Button>
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-xl sm:text-2xl font-bold font-mono">{voucher.voucher_number}</h1>
            <Badge variant={paymentStatusVariant(voucher.status) as "default"}>
              {paymentStatusLabel(voucher.status)}
            </Badge>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground mt-0.5">
            <span>{formatDate(voucher.sale_date)}</span>
            {customerName && (
              <>
                <span>·</span>
                <span
                  className="text-primary cursor-pointer hover:underline"
                  onClick={() => navigate(`/customers/${voucher.customer_id}`)}
                >
                  {customerName}
                </span>
              </>
            )}
            {!customerName && <span>· {t("vouchers.walkIn")}</span>}
          </div>
        </div>

        <div className="flex flex-wrap gap-2 shrink-0">
          {voucher.status === "draft" && (
            <Button
              variant="default"
              size="sm"
              onClick={() => confirmMutation.mutate()}
              disabled={confirmMutation.isPending}
            >
              {confirmMutation.isPending ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : null}
              {t("vouchers.confirmVoucher")}
            </Button>
          )}
          {(voucher.status === "confirmed" || voucher.status === "partially_paid") && (
            <Button variant="outline" size="sm" onClick={() => {
              resetPay({ amount: voucher.outstanding_amount });
              setPaymentMethod("Cash");
              setPaymentOpen(true);
            }}>
              <CreditCard className="w-4 h-4 mr-1" /> {t("vouchers.recordPayment")}
            </Button>
          )}
          {isAdmin && (
            <Button variant="outline" size="sm" onClick={openEdit}>
              <Pencil className="w-4 h-4 mr-1" /> {t("common.edit")}
            </Button>
          )}
          {voucher.status !== "cancelled" && isAdmin && (
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="destructive" size="sm">
                  <XCircle className="w-4 h-4 mr-1" /> {t("common.cancel")}
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>{t("vouchers.cancelVoucher")}</AlertDialogTitle>
                  <AlertDialogDescription>{t("vouchers.cancelWarning")}</AlertDialogDescription>
                </AlertDialogHeader>
                <Input
                  placeholder={t("vouchers.cancelReason")}
                  value={voidReason}
                  onChange={(e) => setVoidReason(e.target.value)}
                />
                <AlertDialogFooter>
                  <AlertDialogCancel>{t("vouchers.back")}</AlertDialogCancel>
                  <AlertDialogAction
                    className="bg-destructive text-white hover:bg-destructive/90"
                    onClick={() => voidMutation.mutate()}
                    disabled={!voidReason.trim() || voidMutation.isPending}
                  >
                    {voidMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : t("vouchers.cancelVoucher")}
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          )}
        </div>
      </div>

      {/* Draft warning */}
      {voucher.status === "draft" && (
        <div className="rounded-md bg-yellow-50 border border-yellow-300 p-3 text-sm text-yellow-800">
          {t("vouchers.draftWarning")}
        </div>
      )}

      {/* Summary */}
      <div className="grid grid-cols-3 gap-3">
        <Card>
          <CardContent className="p-4">
            <p className="text-xs text-muted-foreground">{t("vouchers.totalAmount")}</p>
            <p className="text-lg font-bold">{formatCurrency(voucher.total_amount)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-xs text-muted-foreground">{t("vouchers.paid")}</p>
            <p className="text-lg font-bold text-green-600">{formatCurrency(voucher.paid_amount)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-xs text-muted-foreground">{t("vouchers.outstanding")}</p>
            <p className="text-lg font-bold text-orange-600">{formatCurrency(voucher.outstanding_amount)}</p>
          </CardContent>
        </Card>
      </div>

      {/* Items */}
      <Card>
        <CardHeader><CardTitle className="text-base">{t("vouchers.lineItems")}</CardTitle></CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("vouchers.item")}</TableHead>
                <TableHead className="text-right">{t("vouchers.qty")}</TableHead>
                <TableHead>{t("common.unit")}</TableHead>
                <TableHead className="text-right">{t("vouchers.unitPrice")}</TableHead>
                <TableHead className="text-right">{t("vouchers.discountPct")}</TableHead>
                <TableHead className="text-right">{t("vouchers.lineTotal")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {voucher.items.map((item) => (
                <TableRow key={item.id}>
                  <TableCell className="font-medium">
                    {itemNameMap[item.inventory_item_id] ?? <span className="text-muted-foreground font-mono text-xs">{item.inventory_item_id}</span>}
                  </TableCell>
                  <TableCell className="text-right">{item.quantity}</TableCell>
                  <TableCell className="uppercase">{item.unit}</TableCell>
                  <TableCell className="text-right">{formatCurrency(item.unit_price)}</TableCell>
                  <TableCell className="text-right">{item.discount_percent}%</TableCell>
                  <TableCell className="text-right font-medium">{formatCurrency(item.line_total)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          </div>

          <div className="p-4 border-t space-y-1.5">
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">{t("vouchers.itemsSubtotal")}</span>
              <span>{formatCurrency(voucher.subtotal)}</span>
            </div>
            {voucher.discount_amount > 0 && (
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">{t("vouchers.discount")}</span>
                <span className="text-destructive">-{formatCurrency(voucher.discount_amount)}</span>
              </div>
            )}
            {voucher.extra_charges?.map((ec, i) => (
              <div key={i} className="flex justify-between text-sm">
                <span className="text-muted-foreground">{ec.description}</span>
                <span>{formatCurrency(ec.amount)}</span>
              </div>
            ))}
            <Separator />
            <div className="flex justify-between font-semibold">
              <span>{t("common.total")}</span>
              <span>{formatCurrency(voucher.total_amount)}</span>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Payments */}
      {voucher.payments.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-base">{t("vouchers.payments")}</CardTitle></CardHeader>
          <CardContent className="p-0 overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("common.amount")}</TableHead>
                  <TableHead>{t("vouchers.reference")}</TableHead>
                  <TableHead>{t("common.date")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {voucher.payments.map((p) => (
                  <TableRow key={p.id}>
                    <TableCell className="font-medium">{formatCurrency(p.amount)}</TableCell>
                    <TableCell>{p.reference_number ?? "—"}</TableCell>
                    <TableCell>{formatDate(p.created_at)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* Record Payment Dialog */}
      <Dialog open={paymentOpen} onOpenChange={(v) => { setPaymentOpen(v); if (!v) { resetPay(); setPaymentMethod("Cash"); } }}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>{t("vouchers.recordPayment")}</DialogTitle></DialogHeader>
          <form onSubmit={handlePay((d) => paymentMutation.mutate(d))} className="space-y-4" autoComplete="off" noValidate>
            <div className="space-y-1.5">
              <Label>{t("vouchers.outstandingLabel")} <span className="font-semibold text-orange-600">{formatCurrency(voucher.outstanding_amount)}</span></Label>
            </div>
            {voucherCustomer && Number(voucherCustomer.credit_balance) > voucher.outstanding_amount && (
              <div className="rounded-md bg-orange-50 border border-orange-200 p-2">
                <p className="text-xs text-orange-700">
                  {t("vouchers.customerTotalOutstanding")}: <span className="font-bold">{formatCurrency(Number(voucherCustomer.credit_balance))}</span>
                </p>
              </div>
            )}
            <div className="space-y-1.5">
              <Label>{t("vouchers.amountKyats")}</Label>
              <Input type="number" step="1" placeholder="0" {...regPay("amount")} />
              {payErrors.amount && <p className="text-xs text-destructive">{payErrors.amount.message}</p>}
            </div>
            <div className="space-y-2">
              <Label>{t("vouchers.paymentMethod")}</Label>
              <div className="flex gap-2">
                {(["Cash", "KPay", "Bank Transfer"] as PaymentMethod[]).map((m) => (
                  <Button
                    key={m}
                    type="button"
                    variant={paymentMethod === m ? "default" : "outline"}
                    size="sm"
                    className="flex-1"
                    onClick={() => setPaymentMethod(paymentMethod === m ? null : m)}
                  >
                    {m === "Cash" ? t("vouchers.cash") : m === "KPay" ? t("vouchers.kpay") : t("vouchers.bankTransfer")}
                  </Button>
                ))}
              </div>
            </div>
            {paymentMethod === "Bank Transfer" && (
              <div className="space-y-1.5">
                <Label>{t("vouchers.bankRef")}</Label>
                <Input placeholder="e.g. TXN123456" {...regPay("bank_ref")} />
              </div>
            )}
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setPaymentOpen(false)}>{t("common.cancel")}</Button>
              <Button type="submit" disabled={paySubmitting}>{t("vouchers.savePayment")}</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Admin Edit Dialog */}
      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>{t("vouchers.editVoucher")}</DialogTitle></DialogHeader>
          <form onSubmit={handleEdit((d) => editMutation.mutate(d))} className="space-y-4" autoComplete="off">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>{t("vouchers.saleDate")}</Label>
                <Input type="date" {...regEdit("sale_date")} />
              </div>
              <div className="space-y-1.5">
                <Label>{t("vouchers.customer")}</Label>
                <select
                  className="flex h-9 w-full rounded-md border border-input bg-input px-3 py-1 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  {...regEdit("customer_id")}
                >
                  <option value="">{t("vouchers.noCustomerShort")}</option>
                  {customersData?.data?.map((c: CustomerResponse) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>
              <div className="col-span-2 space-y-1.5">
                <Label>{t("common.notes")}</Label>
                <Input {...regEdit("notes")} placeholder="Notes" />
              </div>
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label className="font-semibold">{t("vouchers.lineItems")}</Label>
                <Button type="button" variant="ghost" size="sm" onClick={() => appendItem({ inventory_item_id: "", quantity: 1, unit: "viss", unit_price: 0, discount_percent: 0 })}>
                  <Plus className="w-3 h-3 mr-1" /> {t("vouchers.addItem")}
                </Button>
              </div>
              {itemFields.map((f, i) => (
                <div key={f.id} className="rounded-md border sm:border-0 p-2.5 sm:p-0 space-y-2 sm:space-y-0 sm:grid sm:grid-cols-12 sm:gap-2 sm:items-center">
                  <div className="sm:col-span-4">
                    <select className="flex h-9 w-full rounded-md border border-input bg-input px-3 py-1 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" {...regEdit(`items.${i}.inventory_item_id`)}>
                      <option value="">— {t("vouchers.item")} —</option>
                      {(inventoryData?.data ?? []).map((item) => (
                        <option key={item.id} value={item.id}>{item.name}</option>
                      ))}
                    </select>
                  </div>
                  <div className="grid grid-cols-4 gap-2 sm:contents">
                    <div className="sm:col-span-2">
                      <Input type="number" step="0.001" placeholder={t("vouchers.qty")} {...regEdit(`items.${i}.quantity`)} />
                    </div>
                    <div className="sm:col-span-2">
                      <select className="flex h-9 w-full rounded-md border border-input bg-input px-3 py-1 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" {...regEdit(`items.${i}.unit`)}>
                        <option value="viss">Viss</option>
                        <option value="tical">Tical</option>
                        <option value="kg">KG</option>
                        <option value="liter">Liter</option>
                        <option value="unit">Unit</option>
                      </select>
                    </div>
                    <div className="sm:col-span-2">
                      <Input type="number" step="1" placeholder={t("vouchers.unitPrice")} {...regEdit(`items.${i}.unit_price`)} />
                    </div>
                    <div className="sm:col-span-1">
                      <Input type="number" step="0.01" placeholder={t("vouchers.discountPct")} {...regEdit(`items.${i}.discount_percent`)} />
                    </div>
                  </div>
                  <div className="sm:col-span-1 flex justify-end sm:justify-center">
                    <Button type="button" variant="ghost" size="icon" disabled={itemFields.length <= 1} onClick={() => removeItem(i)}>
                      <Trash2 className="w-4 h-4 text-destructive" />
                    </Button>
                  </div>
                </div>
              ))}
              <p className="text-xs text-muted-foreground hidden sm:block">{t("vouchers.columnHint")}</p>
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label>{t("vouchers.extraCharges")}</Label>
                <Button type="button" variant="ghost" size="sm" onClick={() => appendExtra({ description: "", amount: 0 })}>
                  <Plus className="w-3 h-3 mr-1" /> {t("common.add")}
                </Button>
              </div>
              {extraFields.map((f, i) => (
                <div key={f.id} className="flex gap-2 items-center">
                  <Input className="flex-1" placeholder={t("common.description")} {...regEdit(`extra_charges.${i}.description`)} />
                  <Input className="w-32" type="number" step="1" placeholder={t("common.amount")} {...regEdit(`extra_charges.${i}.amount`)} />
                  <Button type="button" variant="ghost" size="icon" onClick={() => removeExtra(i)}>
                    <Trash2 className="w-4 h-4 text-destructive" />
                  </Button>
                </div>
              ))}
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setEditOpen(false)}>{t("common.cancel")}</Button>
              <Button type="submit" disabled={editSubmitting}>{t("common.saveChanges")}</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
