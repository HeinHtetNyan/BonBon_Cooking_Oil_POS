import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useForm, useFieldArray, type Resolver } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Plus, Trash2, ArrowLeft, Loader2, X } from "lucide-react";
import { vouchersApi } from "@/api/vouchers";
import { inventoryApi } from "@/api/inventory";
import { customersApi } from "@/api/customers";
import { queryClient } from "@/lib/queryClient";
import { getErrorMessage, generateIdempotencyKey, formatCurrency } from "@/lib/utils";
import { WEIGHT_UNITS } from "@/lib/constants";
import { toast } from "@/hooks/useToast";
import { apiClient } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Alert, AlertDescription } from "@/components/ui/alert";
import type { CustomerResponse, PaginatedResponse, VoucherCreate, WeightUnit } from "@/types";

type PaymentMethod = "Cash" | "KPay" | "Bank Transfer";

const itemSchema = z.object({
  inventory_item_id: z.string().min(1, "Required"),
  quantity: z.coerce.number().positive("Must be positive"),
  unit: z.string().min(1, "Required"),
  unit_price: z.coerce.number().min(0, "Must be >= 0"),
  discount_percent: z.coerce.number().min(0).max(100).optional(),
  notes: z.string().optional(),
});

const extraChargeSchema = z.object({
  description: z.string().min(1, "Required"),
  amount: z.coerce.number().positive("Must be > 0"),
});

const voucherSchema = z.object({
  customer_id: z.string().optional(),
  sale_date: z.string().min(1, "Required"),
  voucher_type: z.enum(["sale", "return"]),
  notes: z.string().optional(),
  items: z.array(itemSchema).min(1, "At least one item required"),
  extra_charges: z.array(extraChargeSchema).optional(),
});

type FormValues = z.infer<typeof voucherSchema>;

function calcLineTotal(qty: number, price: number, discPct: number): number {
  const gross = qty * price;
  return Math.round(gross * (1 - discPct / 100));
}

export function VoucherCreate() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const preselectedCustomerId = searchParams.get("customer_id") ?? undefined;
  const [error, setError] = useState<string | null>(null);
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod | null>(null);
  const [paymentAmount, setPaymentAmount] = useState<string>("");
  const [bankRef, setBankRef] = useState("");

  function handlePaymentMethodToggle(m: PaymentMethod) {
    if (paymentMethod === m) {
      setPaymentMethod(null);
      setPaymentAmount("");
    } else {
      setPaymentMethod(m);
    }
  }

  const { data: inventoryData } = useQuery({
    queryKey: ["inventory-items", "finished_oil"],
    queryFn: () => inventoryApi.listItems({ item_type: "finished_oil", per_page: 500 }),
  });

  const { data: customersData } = useQuery<PaginatedResponse<CustomerResponse>>({
    queryKey: ["customers-all"],
    queryFn: () => customersApi.list({ per_page: 500 }),
  });

  const { register, control, handleSubmit, watch, setValue, formState: { errors } } = useForm<FormValues>({
    resolver: zodResolver(voucherSchema) as Resolver<FormValues>,
    defaultValues: {
      customer_id: preselectedCustomerId ?? "",
      sale_date: new Date().toISOString().split("T")[0],
      voucher_type: "sale",
      items: [{ inventory_item_id: "", quantity: 1, unit: "viss", unit_price: 0 }],
      extra_charges: [],
    },
  });

  const { fields, append, remove } = useFieldArray({ control, name: "items" });
  const { fields: extraFields, append: appendExtra, remove: removeExtra } = useFieldArray({
    control,
    name: "extra_charges",
  });

  const watchedItems = watch("items");
  const watchedExtras = watch("extra_charges") ?? [];
  const watchedCustomerId = watch("customer_id");

  const itemsSubtotal = watchedItems.reduce((sum, item) => {
    return sum + calcLineTotal(item.quantity || 0, item.unit_price || 0, item.discount_percent || 0);
  }, 0);

  const extraTotal = watchedExtras.reduce((sum, ec) => sum + Math.round(ec.amount || 0), 0);
  const grandTotal = itemsSubtotal + extraTotal;

  const selectedCustomer = customersData?.data?.find((c: CustomerResponse) => c.id === watchedCustomerId);
  const previousDebt = selectedCustomer ? Number(selectedCustomer.total_debt) : 0;

  const mutation = useMutation({
    mutationFn: async (data: FormValues) => {
      const key = generateIdempotencyKey();
      apiClient.defaults.headers.common["Idempotency-Key"] = key;
      const payload: VoucherCreate = {
        ...data,
        customer_id: data.customer_id || undefined,
        items: data.items.map((item) => ({
          ...item,
          unit: item.unit as WeightUnit,
        })),
        extra_charges: data.extra_charges?.map((ec) => ({
          description: ec.description,
          amount: ec.amount,
        })),
        auto_confirm: true,
      };
      const res = await vouchersApi.create(payload);
      delete apiClient.defaults.headers.common["Idempotency-Key"];

      // Record payment if a method was selected (voucher is already confirmed)
      if (paymentMethod) {
        const codeMap: Record<PaymentMethod, string> = {
          Cash: "CASH",
          KPay: "KBZ_PAY",
          "Bank Transfer": "BANK_TRANSFER",
        };
        const amountToRecord = paymentAmount !== "" && Number(paymentAmount) > 0
          ? Number(paymentAmount)
          : Number(res.total_amount);
        try {
          await vouchersApi.recordPayment(res.id, {
            payment_method_code: codeMap[paymentMethod],
            amount: amountToRecord,
            reference_number: paymentMethod === "Bank Transfer" && bankRef.trim() ? bankRef.trim() : undefined,
          });
        } catch (payErr) {
          toast({
            title: "Payment not recorded",
            description: getErrorMessage(payErr),
            variant: "destructive",
          });
        }
      }

      return res;
    },
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ["vouchers"] });
      queryClient.invalidateQueries({ queryKey: ["customers"] });
      queryClient.invalidateQueries({ queryKey: ["inventory-items"] });
      toast({ title: t("vouchers.newVoucher"), description: `${res.voucher_number}`, variant: "success" as "default" });
      navigate(`/vouchers/${res.id}`);
    },
    onError: (e) => setError(getErrorMessage(e)),
  });

  return (
    <div className="max-w-3xl mx-auto space-y-5">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={() => navigate("/vouchers")}>
          <ArrowLeft className="w-4 h-4" />
        </Button>
        <div>
          <h1 className="text-2xl font-bold">{t("vouchers.newVoucher")}</h1>
          <p className="text-sm text-muted-foreground">{t("vouchers.autoNumber")}</p>
        </div>
      </div>

      {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}

      <form onSubmit={handleSubmit((d) => mutation.mutate(d))} className="space-y-5" autoComplete="off" noValidate>
        <Card>
          <CardHeader><CardTitle className="text-base">{t("vouchers.voucherDetails")}</CardTitle></CardHeader>
          <CardContent className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label>{t("vouchers.saleDate")}</Label>
              <Input type="date" {...register("sale_date")} />
              {errors.sale_date && <p className="text-xs text-destructive">{errors.sale_date.message}</p>}
            </div>
            <div className="space-y-1.5">
              <Label>{t("vouchers.voucherType")}</Label>
              <select className="flex h-9 w-full rounded-md border border-input bg-input px-3 py-1 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" {...register("voucher_type")}>
                <option value="sale">{t("vouchers.sale")}</option>
                <option value="return">{t("vouchers.return")}</option>
              </select>
            </div>
            <div className="sm:col-span-2 space-y-1.5">
              <Label>{t("vouchers.customerOptional")}</Label>
              <div className="flex gap-2 items-center">
                <select
                  className="flex h-9 w-full rounded-md border border-input bg-input px-3 py-1 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  value={watchedCustomerId}
                  onChange={(e) => setValue("customer_id", e.target.value)}
                >
                  <option value="">{t("vouchers.noCustomer")}</option>
                  {customersData?.data?.map((c: CustomerResponse) => (
                    <option key={c.id} value={c.id}>{c.name} ({c.code})</option>
                  ))}
                </select>
                {watchedCustomerId && (
                  <Button type="button" variant="ghost" size="icon" onClick={() => setValue("customer_id", "")}>
                    <X className="w-4 h-4" />
                  </Button>
                )}
              </div>
              <p className="text-xs text-muted-foreground">{t("vouchers.customerDebtTracking")}</p>
              {previousDebt > 0 && (
                <div className="rounded-md bg-orange-50 border border-orange-200 p-3 space-y-1">
                  <p className="text-sm text-orange-800">
                    {t("vouchers.previousOutstanding")}: <span className="font-semibold">{formatCurrency(previousDebt)}</span>
                  </p>
                  <p className="text-sm font-bold text-orange-900">
                    {t("vouchers.totalOwed")}: {formatCurrency(grandTotal + previousDebt)}
                  </p>
                </div>
              )}
            </div>
            <div className="sm:col-span-2 space-y-1.5">
              <Label>{t("vouchers.notesOptional")}</Label>
              <Input {...register("notes")} placeholder="Additional notes" autoComplete="off" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle className="text-base">{t("vouchers.lineItems")}</CardTitle>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => append({ inventory_item_id: "", quantity: 1, unit: "viss", unit_price: 0 })}
            >
              <Plus className="w-4 h-4 mr-1" />
              {t("vouchers.addItem")}
            </Button>
          </CardHeader>
          <CardContent className="space-y-3">
            {errors.items?.root && <p className="text-xs text-destructive">{errors.items.root.message}</p>}
            {fields.map((field, idx) => (
              <div key={field.id} className="rounded-md border sm:border-0 p-3 sm:p-0 space-y-2 sm:space-y-0 sm:grid sm:grid-cols-12 sm:gap-2 sm:items-end">
                {/* Item selector — full width on mobile, 4 cols on desktop */}
                <div className="sm:col-span-4 space-y-1">
                  {idx === 0 && <Label className="text-xs hidden sm:block">{t("vouchers.item")}</Label>}
                  <Label className="text-xs sm:hidden text-muted-foreground">{t("vouchers.item")} {idx + 1}</Label>
                  <select className="flex h-9 w-full rounded-md border border-input bg-input px-3 py-1 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" {...register(`items.${idx}.inventory_item_id`)}>
                    <option value="">Select item...</option>
                    {inventoryData?.data.map((item) => (
                      <option key={item.id} value={item.id}>{item.name}</option>
                    ))}
                  </select>
                  {errors.items?.[idx]?.inventory_item_id && <p className="text-xs text-destructive">{errors.items[idx]?.inventory_item_id?.message}</p>}
                </div>
                {/* Qty, Unit, Price, Disc%, Delete — 2-row on mobile, inline on desktop */}
                <div className="grid grid-cols-4 gap-2 sm:contents">
                  <div className="sm:col-span-2 space-y-1">
                    {idx === 0 && <Label className="text-xs hidden sm:block">{t("vouchers.qty")}</Label>}
                    <Label className="text-xs sm:hidden text-muted-foreground">{t("vouchers.qty")}</Label>
                    <Input type="number" step="0.01" {...register(`items.${idx}.quantity`)} />
                  </div>
                  <div className="sm:col-span-2 space-y-1">
                    {idx === 0 && <Label className="text-xs hidden sm:block">{t("common.unit")}</Label>}
                    <Label className="text-xs sm:hidden text-muted-foreground">{t("common.unit")}</Label>
                    <select className="flex h-9 w-full rounded-md border border-input bg-input px-3 py-1 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" {...register(`items.${idx}.unit`)}>
                      {Object.entries(WEIGHT_UNITS).map(([k, v]) => (
                        <option key={k} value={k}>{v}</option>
                      ))}
                    </select>
                  </div>
                  <div className="sm:col-span-2 space-y-1">
                    {idx === 0 && <Label className="text-xs hidden sm:block">{t("vouchers.unitPrice")}</Label>}
                    <Label className="text-xs sm:hidden text-muted-foreground">{t("vouchers.unitPrice")}</Label>
                    <Input type="number" step="1" {...register(`items.${idx}.unit_price`)} />
                  </div>
                  <div className="sm:col-span-1 space-y-1">
                    {idx === 0 && <Label className="text-xs hidden sm:block">{t("vouchers.discountPct")}</Label>}
                    <Label className="text-xs sm:hidden text-muted-foreground">{t("vouchers.discountPct")}</Label>
                    <Input type="number" step="0.1" max="100" {...register(`items.${idx}.discount_percent`)} />
                  </div>
                </div>
                <div className="sm:col-span-1 flex justify-end sm:justify-center">
                  {fields.length > 1 && (
                    <Button type="button" variant="ghost" size="icon" onClick={() => remove(idx)}>
                      <Trash2 className="w-4 h-4 text-destructive" />
                    </Button>
                  )}
                </div>
              </div>
            ))}

            <Separator />

            {/* Extra Charges */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-muted-foreground">{t("vouchers.extraCharges")}</p>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => appendExtra({ description: "", amount: 0 })}
                >
                  <Plus className="w-3 h-3 mr-1" /> {t("vouchers.addCharge")}
                </Button>
              </div>
              {extraFields.map((field, idx) => (
                <div key={field.id} className="flex gap-2 items-end">
                  <div className="flex-1 space-y-1">
                    {idx === 0 && <Label className="text-xs">{t("common.description")}</Label>}
                    <Input placeholder="e.g. Delivery fee" {...register(`extra_charges.${idx}.description`)} autoComplete="off" />
                    {errors.extra_charges?.[idx]?.description && <p className="text-xs text-destructive">{errors.extra_charges[idx]?.description?.message}</p>}
                  </div>
                  <div className="w-24 sm:w-32 shrink-0 space-y-1">
                    {idx === 0 && <Label className="text-xs">{t("vouchers.amountKyats")}</Label>}
                    <Input type="number" step="1" {...register(`extra_charges.${idx}.amount`)} />
                    {errors.extra_charges?.[idx]?.amount && <p className="text-xs text-destructive">{errors.extra_charges[idx]?.amount?.message}</p>}
                  </div>
                  <Button type="button" variant="ghost" size="icon" onClick={() => removeExtra(idx)}>
                    <Trash2 className="w-4 h-4 text-destructive" />
                  </Button>
                </div>
              ))}
            </div>

            <Separator />
            <div className="flex justify-end">
              <div className="text-right space-y-1 w-full sm:min-w-48 sm:w-auto">
                <div className="flex justify-between text-sm text-muted-foreground">
                  <span>{t("vouchers.itemsSubtotal")}</span>
                  <span>{formatCurrency(itemsSubtotal)}</span>
                </div>
                {extraTotal > 0 && (
                  <div className="flex justify-between text-sm text-muted-foreground">
                    <span>{t("vouchers.extraChargesLabel")}</span>
                    <span>{formatCurrency(extraTotal)}</span>
                  </div>
                )}
                {previousDebt > 0 && (
                  <div className="flex justify-between text-sm text-orange-600 pt-1">
                    <span>+ {t("vouchers.previousOutstanding")}</span>
                    <span>{formatCurrency(previousDebt)}</span>
                  </div>
                )}
                <div className="flex justify-between text-lg font-bold pt-1 border-t">
                  <span>{t("common.total")}</span>
                  <span>{formatCurrency(grandTotal + previousDebt)}</span>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Payment Method */}
        <Card>
          <CardHeader><CardTitle className="text-base">{t("vouchers.paymentMethodOptional")}</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <div className="flex gap-2">
              {(["Cash", "KPay", "Bank Transfer"] as PaymentMethod[]).map((m) => (
                <Button
                  key={m}
                  type="button"
                  variant={paymentMethod === m ? "default" : "outline"}
                  className="flex-1"
                  onClick={() => handlePaymentMethodToggle(m)}
                >
                  {m === "Cash" ? t("vouchers.cash") : m === "KPay" ? t("vouchers.kpay") : t("vouchers.bankTransfer")}
                </Button>
              ))}
            </div>
            {paymentMethod && (
              <div className="space-y-1.5">
                <Label className="text-sm">{t("vouchers.paymentAmountOptional")}</Label>
                <Input
                  type="number"
                  step="1"
                  value={paymentAmount}
                  placeholder={String(grandTotal)}
                  onChange={(e) => setPaymentAmount(e.target.value)}
                  autoComplete="off"
                />
                <p className="text-xs text-muted-foreground">{t("vouchers.paymentAmountHint")}</p>
                {paymentAmount !== "" && Number(paymentAmount) > 0 && Number(paymentAmount) < grandTotal && (
                  <p className="text-xs text-orange-600">
                    {t("vouchers.outstandingLabel")} {formatCurrency(grandTotal - Number(paymentAmount))}
                  </p>
                )}
              </div>
            )}
            {paymentMethod === "Bank Transfer" && (
              <div className="space-y-1.5">
                <Label className="text-sm">{t("vouchers.bankRef")}</Label>
                <Input
                  placeholder="e.g. TXN123456"
                  value={bankRef}
                  onChange={(e) => setBankRef(e.target.value)}
                  autoComplete="off"
                />
              </div>
            )}
          </CardContent>
        </Card>

        <div className="flex gap-3 justify-end">
          <Button type="button" variant="outline" onClick={() => navigate("/vouchers")}>{t("common.cancel")}</Button>
          <Button type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />{t("vouchers.creating")}</> : t("vouchers.createVoucher")}
          </Button>
        </div>
      </form>
    </div>
  );
}
