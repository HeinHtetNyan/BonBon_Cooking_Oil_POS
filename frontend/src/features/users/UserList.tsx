import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useTranslation } from "react-i18next";
import { usersApi } from "@/api/users";
import { queryClient } from "@/lib/queryClient";
import { getErrorMessage } from "@/lib/utils";
import { toast } from "@/hooks/useToast";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Skeleton } from "@/components/ui/skeleton";
import type { UserRole } from "@/types";

const createSchema = z.object({
  username: z.string().min(3),
  email: z.string().email(),
  full_name: z.string().min(1),
  phone: z.string().optional(),
  role: z.enum(["super_admin", "admin", "manager", "cashier", "warehouse"]),
  password: z.string().min(8).regex(/[A-Z]/, "Must have uppercase").regex(/[0-9]/, "Must have digit"),
});
type CreateForm = z.infer<typeof createSchema>;

export function UserList() {
  const { t } = useTranslation();
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["users", page],
    queryFn: () => usersApi.list(page),
  });

  const { register, handleSubmit, reset, formState: { errors, isSubmitting } } = useForm<CreateForm>({
    resolver: zodResolver(createSchema),
    defaultValues: { role: "cashier" },
  });

  const mutation = useMutation({
    mutationFn: (d: CreateForm) => usersApi.create(d),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      toast({ title: t("users.newUser"), variant: "success" as "default" });
      setOpen(false);
      reset();
    },
    onError: (e) => setError(getErrorMessage(e)),
  });

  const roleVariant: Record<UserRole, string> = {
    super_admin: "destructive",
    admin: "destructive",
    manager: "purple",
    cashier: "info",
    warehouse: "warning",
  };

  const roleLabel = (r: string) => t(`roles.${r}`, { defaultValue: r });

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-y-3">
        <div>
          <h1 className="text-2xl font-bold">{t("users.title")}</h1>
          <p className="text-sm text-muted-foreground">{t("users.subtitle")}</p>
        </div>
        <Button onClick={() => setOpen(true)}>
          <Plus className="w-4 h-4 mr-2" /> {t("users.newUser")}
        </Button>
      </div>

      <Card>
        <CardContent className="p-0 overflow-x-auto">
          {isLoading ? (
            <div className="p-4 space-y-3">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-12" />)}</div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("users.userCol")}</TableHead>
                  <TableHead>{t("users.usernameCol")}</TableHead>
                  <TableHead>{t("users.roleCol")}</TableHead>
                  <TableHead>{t("users.statusCol")}</TableHead>
                  <TableHead>{t("users.lastLogin")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data?.data.map((u) => {
                  const initials = u.full_name.split(" ").map((n) => n[0]).join("").toUpperCase().slice(0, 2);
                  return (
                    <TableRow key={u.id}>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <Avatar className="w-8 h-8">
                            <AvatarFallback className="bg-primary text-white text-xs">{initials}</AvatarFallback>
                          </Avatar>
                          <p className="font-medium text-sm">{u.full_name}</p>
                        </div>
                      </TableCell>
                      <TableCell className="font-mono text-sm">{u.username}</TableCell>
                      <TableCell>
                        <Badge variant={roleVariant[u.role] as "default"}>{roleLabel(u.role)}</Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant="success">{t("users.activeStatus")}</Badge>
                      </TableCell>
                      <TableCell className="text-muted-foreground text-sm">—</TableCell>
                    </TableRow>
                  );
                })}
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

      <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) { reset(); setError(null); } }}>
        <DialogContent>
          <DialogHeader><DialogTitle>{t("users.newUser")}</DialogTitle></DialogHeader>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <form onSubmit={handleSubmit((d) => mutation.mutate(d))} className="space-y-3" autoComplete="off">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>{t("users.fullName")}</Label>
                <Input {...register("full_name")} />
                {errors.full_name && <p className="text-xs text-destructive">{errors.full_name.message}</p>}
              </div>
              <div className="space-y-1.5">
                <Label>{t("users.usernameLabel")}</Label>
                <Input {...register("username")} />
                {errors.username && <p className="text-xs text-destructive">{errors.username.message}</p>}
              </div>
              <div className="space-y-1.5">
                <Label>{t("users.emailLabel")}</Label>
                <Input type="email" {...register("email")} />
                {errors.email && <p className="text-xs text-destructive">{errors.email.message}</p>}
              </div>
              <div className="space-y-1.5">
                <Label>{t("users.phoneLabel")}</Label>
                <Input {...register("phone")} />
              </div>
              <div className="space-y-1.5">
                <Label>{t("users.roleLabel")}</Label>
                <select className="flex h-9 w-full rounded-md border border-input bg-input px-3 py-1 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" {...register("role")}>
                  {(["super_admin","admin","manager","cashier","warehouse"] as const).map((r) => (
                    <option key={r} value={r}>{roleLabel(r)}</option>
                  ))}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label>{t("users.passwordLabel")}</Label>
                <Input type="password" {...register("password")} />
                {errors.password && <p className="text-xs text-destructive">{errors.password.message}</p>}
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setOpen(false)}>{t("common.cancel")}</Button>
              <Button type="submit" disabled={isSubmitting}>{t("users.createUser")}</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
