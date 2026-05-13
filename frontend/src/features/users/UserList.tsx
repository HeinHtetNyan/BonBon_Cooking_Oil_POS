import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Plus, Pencil, KeyRound, Trash2, Ban, CheckCircle } from "lucide-react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useTranslation } from "react-i18next";
import { usersApi } from "@/api/users";
import { queryClient } from "@/lib/queryClient";
import { getErrorMessage } from "@/lib/utils";
import { toast } from "@/hooks/useToast";
import { useAuthStore } from "@/store/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel,
  AlertDialogContent, AlertDialogDescription, AlertDialogFooter,
  AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import type { UserRole, UserStatus, UserSummary } from "@/types";

const ROLES = ["super_admin", "admin", "manager", "cashier", "warehouse"] as const;

const createSchema = z.object({
  username: z.string().min(3),
  email: z.string().email(),
  full_name: z.string().min(1),
  phone: z.string().optional(),
  role: z.enum(["super_admin", "admin", "manager", "cashier", "warehouse"]),
  password: z.string().min(8).regex(/[A-Z]/, "Must have uppercase").regex(/[0-9]/, "Must have digit"),
});
type CreateForm = z.infer<typeof createSchema>;

const editSchema = z.object({
  full_name: z.string().min(1),
  phone: z.string().optional(),
  role: z.enum(["super_admin", "admin", "manager", "cashier", "warehouse"]),
  status: z.enum(["active", "inactive", "suspended", "pending_verification"]),
});
type EditForm = z.infer<typeof editSchema>;

const passwordSchema = z.object({
  new_password: z.string().min(8).regex(/[A-Z]/, "Must have uppercase").regex(/[0-9]/, "Must have digit"),
  confirm_password: z.string(),
}).refine((d) => d.new_password === d.confirm_password, {
  message: "Passwords do not match",
  path: ["confirm_password"],
});
type PasswordForm = z.infer<typeof passwordSchema>;

export function UserList() {
  const { t } = useTranslation();
  const { user: currentUser } = useAuthStore();
  const isSuperAdmin = currentUser?.role === "super_admin";

  const [page, setPage] = useState(1);
  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<UserSummary | null>(null);
  const [passwordTarget, setPasswordTarget] = useState<UserSummary | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<UserSummary | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [editError, setEditError] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["users", page],
    queryFn: () => usersApi.list(page),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["users"] });

  // Create
  const createForm = useForm<CreateForm>({
    resolver: zodResolver(createSchema),
    defaultValues: { role: "cashier" },
  });
  const createMutation = useMutation({
    mutationFn: (d: CreateForm) => usersApi.create(d),
    onSuccess: () => { invalidate(); toast({ title: t("users.newUser"), variant: "success" as "default" }); setCreateOpen(false); createForm.reset(); },
    onError: (e) => setCreateError(getErrorMessage(e)),
  });

  // Edit
  const editForm = useForm<EditForm>({ resolver: zodResolver(editSchema) });
  const editMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: EditForm }) => usersApi.update(id, data),
    onSuccess: () => { invalidate(); toast({ title: "User updated", variant: "success" as "default" }); setEditTarget(null); },
    onError: (e) => setEditError(getErrorMessage(e)),
  });

  function openEdit(u: UserSummary) {
    setEditError(null);
    editForm.reset({ full_name: u.full_name, phone: undefined, role: u.role, status: u.status });
    setEditTarget(u);
  }

  // Password
  const passwordForm = useForm<PasswordForm>({ resolver: zodResolver(passwordSchema) });
  const passwordMutation = useMutation({
    mutationFn: ({ id, new_password }: { id: string; new_password: string }) => usersApi.setPassword(id, new_password),
    onSuccess: () => { toast({ title: "Password updated", variant: "success" as "default" }); setPasswordTarget(null); passwordForm.reset(); },
    onError: (e) => setPasswordError(getErrorMessage(e)),
  });

  // Toggle disable
  const toggleMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: UserStatus }) => usersApi.update(id, { status }),
    onSuccess: (_, vars) => { invalidate(); toast({ title: vars.status === "active" ? "User enabled" : "User disabled", variant: "success" as "default" }); },
    onError: (e) => toast({ title: getErrorMessage(e), variant: "destructive" }),
  });

  // Delete
  const deleteMutation = useMutation({
    mutationFn: (id: string) => usersApi.delete(id),
    onSuccess: () => { invalidate(); toast({ title: "User deleted", variant: "success" as "default" }); setDeleteTarget(null); },
    onError: (e) => toast({ title: getErrorMessage(e), variant: "destructive" }),
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
        <Button onClick={() => { setCreateError(null); createForm.reset({ role: "cashier" }); setCreateOpen(true); }}>
          <Plus className="w-4 h-4 mr-2" /> {t("users.newUser")}
        </Button>
      </div>

      <Card>
        <CardContent className="p-0 overflow-x-auto">
          {isLoading ? (
            <div className="p-4 space-y-3">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-12" />)}</div>
          ) : (
            <Table className="min-w-[520px]">
              <TableHeader>
                <TableRow>
                  <TableHead>{t("users.userCol")}</TableHead>
                  <TableHead>{t("users.usernameCol")}</TableHead>
                  <TableHead>{t("users.roleCol")}</TableHead>
                  <TableHead>{t("users.statusCol")}</TableHead>
                  <TableHead>{t("users.lastLogin")}</TableHead>
                  {isSuperAdmin && <TableHead className="text-right">Actions</TableHead>}
                </TableRow>
              </TableHeader>
              <TableBody>
                {data?.data.map((u) => {
                  const initials = u.full_name.split(" ").map((n) => n[0]).join("").toUpperCase().slice(0, 2);
                  const isActive = u.status === "active";
                  const isSelf = u.id === currentUser?.id;
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
                        <Badge variant={isActive ? "success" : "secondary"}>
                          {isActive ? t("users.activeStatus") : u.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-muted-foreground text-sm">—</TableCell>
                      {isSuperAdmin && (
                        <TableCell className="text-right">
                          <div className="flex items-center justify-end gap-1">
                            <Button size="icon" variant="ghost" className="h-8 w-8" title="Edit" onClick={() => openEdit(u)}>
                              <Pencil className="w-3.5 h-3.5" />
                            </Button>
                            <Button size="icon" variant="ghost" className="h-8 w-8" title="Set Password" onClick={() => { setPasswordError(null); passwordForm.reset(); setPasswordTarget(u); }}>
                              <KeyRound className="w-3.5 h-3.5" />
                            </Button>
                            {!isSelf && (
                              <>
                                <Button
                                  size="icon" variant="ghost"
                                  className={`h-8 w-8 ${isActive ? "text-orange-500 hover:text-orange-600" : "text-green-600 hover:text-green-700"}`}
                                  title={isActive ? "Disable" : "Enable"}
                                  disabled={toggleMutation.isPending}
                                  onClick={() => toggleMutation.mutate({ id: u.id, status: isActive ? "inactive" : "active" })}
                                >
                                  {isActive ? <Ban className="w-3.5 h-3.5" /> : <CheckCircle className="w-3.5 h-3.5" />}
                                </Button>
                                <Button size="icon" variant="ghost" className="h-8 w-8 text-destructive hover:text-destructive" title="Delete" onClick={() => setDeleteTarget(u)}>
                                  <Trash2 className="w-3.5 h-3.5" />
                                </Button>
                              </>
                            )}
                          </div>
                        </TableCell>
                      )}
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

      {/* Create Dialog */}
      <Dialog open={createOpen} onOpenChange={(v) => { setCreateOpen(v); if (!v) { createForm.reset(); setCreateError(null); } }}>
        <DialogContent>
          <DialogHeader><DialogTitle>{t("users.newUser")}</DialogTitle></DialogHeader>
          {createError && <p className="text-sm text-destructive">{createError}</p>}
          <form onSubmit={createForm.handleSubmit((d) => createMutation.mutate(d))} className="space-y-3" autoComplete="off">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>{t("users.fullName")}</Label>
                <Input {...createForm.register("full_name")} />
                {createForm.formState.errors.full_name && <p className="text-xs text-destructive">{createForm.formState.errors.full_name.message}</p>}
              </div>
              <div className="space-y-1.5">
                <Label>{t("users.usernameLabel")}</Label>
                <Input {...createForm.register("username")} />
                {createForm.formState.errors.username && <p className="text-xs text-destructive">{createForm.formState.errors.username.message}</p>}
              </div>
              <div className="space-y-1.5">
                <Label>{t("users.emailLabel")}</Label>
                <Input type="email" {...createForm.register("email")} />
                {createForm.formState.errors.email && <p className="text-xs text-destructive">{createForm.formState.errors.email.message}</p>}
              </div>
              <div className="space-y-1.5">
                <Label>{t("users.phoneLabel")}</Label>
                <Input {...createForm.register("phone")} />
              </div>
              <div className="space-y-1.5">
                <Label>{t("users.roleLabel")}</Label>
                <select className="flex h-9 w-full rounded-md border border-input bg-input px-3 py-1 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" {...createForm.register("role")}>
                  {ROLES.map((r) => <option key={r} value={r}>{roleLabel(r)}</option>)}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label>{t("users.passwordLabel")}</Label>
                <Input type="password" {...createForm.register("password")} />
                {createForm.formState.errors.password && <p className="text-xs text-destructive">{createForm.formState.errors.password.message}</p>}
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setCreateOpen(false)}>{t("common.cancel")}</Button>
              <Button type="submit" disabled={createForm.formState.isSubmitting}>{t("users.createUser")}</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Edit Dialog */}
      <Dialog open={!!editTarget} onOpenChange={(v) => { if (!v) setEditTarget(null); }}>
        <DialogContent>
          <DialogHeader><DialogTitle>Edit User — {editTarget?.username}</DialogTitle></DialogHeader>
          {editError && <p className="text-sm text-destructive">{editError}</p>}
          <form onSubmit={editForm.handleSubmit((d) => editMutation.mutate({ id: editTarget!.id, data: d }))} className="space-y-3" autoComplete="off">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="space-y-1.5 sm:col-span-2">
                <Label>{t("users.fullName")}</Label>
                <Input {...editForm.register("full_name")} />
                {editForm.formState.errors.full_name && <p className="text-xs text-destructive">{editForm.formState.errors.full_name.message}</p>}
              </div>
              <div className="space-y-1.5">
                <Label>{t("users.phoneLabel")}</Label>
                <Input {...editForm.register("phone")} />
              </div>
              <div className="space-y-1.5">
                <Label>{t("users.roleLabel")}</Label>
                <select className="flex h-9 w-full rounded-md border border-input bg-input px-3 py-1 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" {...editForm.register("role")}>
                  {ROLES.map((r) => <option key={r} value={r}>{roleLabel(r)}</option>)}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label>Status</Label>
                <select className="flex h-9 w-full rounded-md border border-input bg-input px-3 py-1 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" {...editForm.register("status")}>
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                  <option value="suspended">Suspended</option>
                  <option value="pending_verification">Pending Verification</option>
                </select>
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setEditTarget(null)}>{t("common.cancel")}</Button>
              <Button type="submit" disabled={editMutation.isPending}>Save Changes</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Set Password Dialog */}
      <Dialog open={!!passwordTarget} onOpenChange={(v) => { if (!v) { setPasswordTarget(null); passwordForm.reset(); setPasswordError(null); } }}>
        <DialogContent>
          <DialogHeader><DialogTitle>Set Password — {passwordTarget?.username}</DialogTitle></DialogHeader>
          {passwordError && <p className="text-sm text-destructive">{passwordError}</p>}
          <form onSubmit={passwordForm.handleSubmit((d) => passwordMutation.mutate({ id: passwordTarget!.id, new_password: d.new_password }))} className="space-y-3" autoComplete="off">
            <div className="space-y-1.5">
              <Label>New Password</Label>
              <Input type="password" {...passwordForm.register("new_password")} />
              {passwordForm.formState.errors.new_password && <p className="text-xs text-destructive">{passwordForm.formState.errors.new_password.message}</p>}
            </div>
            <div className="space-y-1.5">
              <Label>Confirm Password</Label>
              <Input type="password" {...passwordForm.register("confirm_password")} />
              {passwordForm.formState.errors.confirm_password && <p className="text-xs text-destructive">{passwordForm.formState.errors.confirm_password.message}</p>}
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setPasswordTarget(null)}>{t("common.cancel")}</Button>
              <Button type="submit" disabled={passwordMutation.isPending}>Update Password</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <AlertDialog open={!!deleteTarget} onOpenChange={(v) => { if (!v) setDeleteTarget(null); }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete User</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete <strong>{deleteTarget?.full_name}</strong> ({deleteTarget?.username})? This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => deleteMutation.mutate(deleteTarget!.id)}
              disabled={deleteMutation.isPending}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
