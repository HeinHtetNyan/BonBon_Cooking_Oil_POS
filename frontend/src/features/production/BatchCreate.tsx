import { useNavigate } from "react-router-dom";
import { useQuery, useMutation } from "@tanstack/react-query";
import { ArrowLeft, Plus, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useForm, useFieldArray, type Resolver } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { productionApi } from "@/api/production";
import { inventoryApi } from "@/api/inventory";
import { getErrorMessage } from "@/lib/utils";
import { WEIGHT_UNITS } from "@/lib/constants";
import { toast } from "@/hooks/useToast";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const materialSchema = z.object({
  material_item_id: z.string().uuid("Select a material"),
  quantity: z.coerce.number().positive("Must be > 0"),
  unit: z.enum(["viss", "tical", "kg", "liter", "unit"]),
});

const outputSchema = z.object({
  output_item_id: z.string().uuid("Select an output item"),
  output_amount: z.coerce.number().positive("Must be > 0"),
  output_unit: z.enum(["viss", "tical", "kg", "liter", "unit"]),
});

const createSchema = z.object({
  production_date: z.string().min(1, "Required"),
  notes: z.string().optional(),
  outputs: z.array(outputSchema).min(1, "Add at least one output item"),
  materials: z.array(materialSchema).min(1, "Add at least one raw material"),
});

type CreateForm = z.infer<typeof createSchema>;

export function BatchCreate() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const { data: outputItems } = useQuery({
    queryKey: ["inventory-items", "finished_oil"],
    queryFn: () => inventoryApi.listItems({ item_type: "finished_oil", per_page: 200 }),
  });

  const { data: rawMaterials } = useQuery({
    queryKey: ["inventory-items", "raw_material"],
    queryFn: () => inventoryApi.listItems({ item_type: "raw_material", per_page: 200 }),
  });

  const {
    register,
    handleSubmit,
    control,
    formState: { errors, isSubmitting },
  } = useForm<CreateForm>({
    resolver: zodResolver(createSchema) as Resolver<CreateForm>,
    defaultValues: {
      production_date: new Date().toISOString().split("T")[0],
      outputs: [{ output_item_id: "", output_amount: 0, output_unit: "viss" }],
      materials: [{ material_item_id: "", quantity: 0, unit: "viss" }],
    },
  });

  const { fields: outputFields, append: appendOutput, remove: removeOutput } = useFieldArray({ control, name: "outputs" });
  const { fields: materialFields, append: appendMaterial, remove: removeMaterial } = useFieldArray({ control, name: "materials" });

  const mutation = useMutation({
    mutationFn: async (d: CreateForm) => {
      const primary = d.outputs[0];

      // Step 1: Create batch (uses first output as primary)
      const createResp = await productionApi.create({
        output_item_id: primary.output_item_id,
        expected_output: primary.output_amount,
        output_unit: primary.output_unit as import("@/types").WeightUnit,
        start_date: d.production_date,
        notes: d.notes,
        material_usages: d.materials.map((m) => ({
          material_item_id: m.material_item_id,
          planned_quantity: m.quantity,
          unit: m.unit as import("@/types").WeightUnit,
        })),
      });
      // Interceptor unwraps { success, data } → data directly
      const createdBatch = (createResp as any).id ? createResp as any : (createResp as any).data;

      // Step 2: Start — response includes material_usages with DB-assigned IDs
      const startResp = await productionApi.start(createdBatch.id);
      const startedBatch = (startResp as any).id ? startResp as any : (startResp as any).data;

      const materialUsages: Array<{ usage_id: string; actual_quantity: number }> =
        (startedBatch.material_usages ?? []).map((mu: any) => ({
          usage_id: mu.id,
          actual_quantity: Number(mu.planned_quantity),
        }));

      console.debug("[BatchCreate] material_usages for complete:", materialUsages);

      // Step 3: Complete with ALL outputs
      await productionApi.complete(createdBatch.id, {
        actual_material_usages: materialUsages,
        outputs: d.outputs.map((o) => ({
          output_item_id: o.output_item_id,
          quantity: o.output_amount,
          unit: o.output_unit as import("@/types").WeightUnit,
        })),
        labour_cost: 0,
        overhead_cost: 0,
      });

      return createdBatch;
    },
    onSuccess: (batch) => {
      toast({ title: t("production.recordProduction"), variant: "success" as "default" });
      navigate(`/production/${batch.id}`);
    },
    onError: (e) => toast({ title: getErrorMessage(e), variant: "destructive" }),
  });

  return (
    <div className="space-y-5 max-w-3xl">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={() => navigate("/production")}>
          <ArrowLeft className="w-4 h-4" />
        </Button>
        <div>
          <h1 className="text-2xl font-bold">{t("production.newRun")}</h1>
          <p className="text-sm text-muted-foreground">{t("production.subtitle")}</p>
        </div>
      </div>

      <form onSubmit={handleSubmit((d) => mutation.mutate(d))} className="space-y-5" autoComplete="off">
        {/* General info */}
        <Card>
          <CardContent className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-5">
            <div className="space-y-1.5">
              <Label>{t("production.productionDate")}</Label>
              <Input type="date" {...register("production_date")} />
              {errors.production_date && <p className="text-xs text-destructive">{errors.production_date.message}</p>}
            </div>
            <div className="space-y-1.5">
              <Label>{t("common.notes")}</Label>
              <Input {...register("notes")} placeholder="Optional notes" />
            </div>
          </CardContent>
        </Card>

        {/* Output items */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">{t("production.outputItem")}</CardTitle>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => appendOutput({ output_item_id: "", output_amount: 0, output_unit: "viss" })}
            >
              <Plus className="w-4 h-4 mr-1" /> {t("production.addOutput")}
            </Button>
          </CardHeader>
          <CardContent className="space-y-3">
            {errors.outputs?.root && (
              <p className="text-xs text-destructive">{errors.outputs.root.message}</p>
            )}
            {outputFields.map((field, i) => (
              <div key={field.id} className="rounded-md border sm:border-0 p-3 sm:p-0 space-y-2 sm:space-y-0 sm:grid sm:grid-cols-12 sm:gap-2 sm:items-end">
                <div className="sm:col-span-6 space-y-1">
                  {i === 0 && <Label className="text-xs">{t("production.outputItemLabel")} *</Label>}
                  <select
                    className="flex h-9 w-full rounded-md border border-input bg-input px-3 py-1 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    {...register(`outputs.${i}.output_item_id`)}
                  >
                    <option value="">— Select finished oil item —</option>
                    {outputItems?.data.map((item) => (
                      <option key={item.id} value={item.id}>{item.name}</option>
                    ))}
                  </select>
                  {errors.outputs?.[i]?.output_item_id && (
                    <p className="text-xs text-destructive">{errors.outputs[i]?.output_item_id?.message}</p>
                  )}
                </div>
                <div className="grid grid-cols-2 gap-2 sm:contents">
                  <div className="sm:col-span-3 space-y-1">
                    {i === 0 && <Label className="text-xs">{t("production.outputAmountLabel")} *</Label>}
                    <Input type="number" step="0.01" {...register(`outputs.${i}.output_amount`)} />
                    {errors.outputs?.[i]?.output_amount && (
                      <p className="text-xs text-destructive">{errors.outputs[i]?.output_amount?.message}</p>
                    )}
                  </div>
                  <div className="sm:col-span-2 space-y-1">
                    {i === 0 && <Label className="text-xs">{t("production.outputUnit")} *</Label>}
                    <select
                      className="flex h-9 w-full rounded-md border border-input bg-input px-3 py-1 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      {...register(`outputs.${i}.output_unit`)}
                    >
                      {Object.entries(WEIGHT_UNITS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                    </select>
                  </div>
                </div>
                <div className="sm:col-span-1 flex justify-end sm:justify-center">
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    disabled={outputFields.length === 1}
                    onClick={() => removeOutput(i)}
                  >
                    <Trash2 className="w-4 h-4 text-destructive" />
                  </Button>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        {/* Raw materials */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">{t("production.rawMaterials")}</CardTitle>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => appendMaterial({ material_item_id: "", quantity: 0, unit: "viss" })}
            >
              <Plus className="w-4 h-4 mr-1" /> {t("production.addMaterial")}
            </Button>
          </CardHeader>
          <CardContent className="space-y-3">
            {errors.materials?.root && (
              <p className="text-xs text-destructive">{errors.materials.root.message}</p>
            )}
            {materialFields.map((field, i) => (
              <div key={field.id} className="rounded-md border sm:border-0 p-3 sm:p-0 space-y-2 sm:space-y-0 sm:grid sm:grid-cols-12 sm:gap-2 sm:items-end">
                <div className="sm:col-span-6 space-y-1">
                  {i === 0 && <Label className="text-xs">{t("production.material")} *</Label>}
                  <select
                    className="flex h-9 w-full rounded-md border border-input bg-input px-3 py-1 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    {...register(`materials.${i}.material_item_id`)}
                  >
                    <option value="">— Select —</option>
                    {rawMaterials?.data.map((item) => (
                      <option key={item.id} value={item.id}>{item.name}</option>
                    ))}
                  </select>
                  {errors.materials?.[i]?.material_item_id && (
                    <p className="text-xs text-destructive">{errors.materials[i]?.material_item_id?.message}</p>
                  )}
                </div>
                <div className="grid grid-cols-2 gap-2 sm:contents">
                  <div className="sm:col-span-3 space-y-1">
                    {i === 0 && <Label className="text-xs">{t("common.quantity")} *</Label>}
                    <Input type="number" step="0.01" {...register(`materials.${i}.quantity`)} />
                    {errors.materials?.[i]?.quantity && (
                      <p className="text-xs text-destructive">{errors.materials[i]?.quantity?.message}</p>
                    )}
                  </div>
                  <div className="sm:col-span-2 space-y-1">
                    {i === 0 && <Label className="text-xs">{t("common.unit")} *</Label>}
                    <select
                      className="flex h-9 w-full rounded-md border border-input bg-input px-3 py-1 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      {...register(`materials.${i}.unit`)}
                    >
                      {Object.entries(WEIGHT_UNITS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                    </select>
                  </div>
                </div>
                <div className="sm:col-span-1 flex justify-end sm:justify-center">
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    disabled={materialFields.length === 1}
                    onClick={() => removeMaterial(i)}
                  >
                    <Trash2 className="w-4 h-4 text-destructive" />
                  </Button>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={() => navigate("/production")}>{t("common.cancel")}</Button>
          <Button type="submit" disabled={isSubmitting}>{t("production.recordProduction")}</Button>
        </div>
      </form>
    </div>
  );
}
