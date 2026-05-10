import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Shield, Search, ChevronDown, ChevronUp } from "lucide-react";
import { auditApi } from "@/api/audit";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { AuditLog } from "@/types/audit";

type BadgeVariant = "default" | "success" | "destructive" | "warning";
function statusVariant(code: number | null): BadgeVariant {
  if (!code) return "default";
  if (code < 300) return "success";
  if (code < 400) return "warning";
  return "destructive";
}

function methodBadgeClass(action: string): string {
  const method = action.split(" ")[0];
  switch (method) {
    case "POST":   return "bg-blue-100 text-blue-800";
    case "PUT":
    case "PATCH":  return "bg-yellow-100 text-yellow-800";
    case "DELETE": return "bg-red-100 text-red-800";
    default:       return "bg-gray-100 text-gray-800";
  }
}

function formatPath(action: string): { method: string; path: string } {
  const parts = action.split(" ");
  return { method: parts[0] ?? "", path: parts.slice(1).join(" ") };
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    year: "numeric", month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

function DataDrawer({ data }: { data: Record<string, unknown> | null }) {
  const [open, setOpen] = useState(false);
  if (!data) return <span className="text-muted-foreground text-xs">—</span>;
  return (
    <div>
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1 text-xs text-primary underline-offset-2 hover:underline"
      >
        {open ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
        {open ? "Hide" : "Show"}
      </button>
      {open && (
        <pre className="mt-1 text-[10px] bg-muted rounded p-2 max-w-xs overflow-auto max-h-40">
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  );
}

export function AuditLogPage() {
  const { t } = useTranslation();
  const [page, setPage] = useState(1);
  const [actionFilter, setActionFilter] = useState("");
  const [actorFilter, setActorFilter] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [applied, setApplied] = useState({
    action: "", actor_id: "", start_date: "", end_date: "",
  });

  const { data, isLoading } = useQuery({
    queryKey: ["audit-logs", page, applied],
    queryFn: () =>
      auditApi.list({
        page,
        per_page: 50,
        action: applied.action || undefined,
        actor_id: applied.actor_id || undefined,
        start_date: applied.start_date ? `${applied.start_date}T00:00:00` : undefined,
        end_date: applied.end_date ? `${applied.end_date}T23:59:59` : undefined,
      }),
  });

  function applyFilters() {
    setPage(1);
    setApplied({
      action: actionFilter,
      actor_id: actorFilter,
      start_date: startDate,
      end_date: endDate,
    });
  }

  function clearFilters() {
    setActionFilter("");
    setActorFilter("");
    setStartDate("");
    setEndDate("");
    setPage(1);
    setApplied({ action: "", actor_id: "", start_date: "", end_date: "" });
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-primary/10">
          <Shield className="w-5 h-5 text-primary" />
        </div>
        <div>
          <h1 className="text-2xl font-bold">{t("audit.title")}</h1>
          <p className="text-sm text-muted-foreground">{t("audit.subtitle")}</p>
        </div>
      </div>

      {/* Filters */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium">{t("audit.filters")}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">{t("audit.filterAction")}</label>
              <Input
                placeholder="POST /api/v1/..."
                value={actionFilter}
                onChange={(e) => setActionFilter(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && applyFilters()}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">{t("audit.filterActor")}</label>
              <Input
                placeholder={t("audit.actorIdPlaceholder")}
                value={actorFilter}
                onChange={(e) => setActorFilter(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && applyFilters()}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">{t("common.startDate")}</label>
              <Input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">{t("common.endDate")}</label>
              <Input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
              />
            </div>
          </div>
          <div className="flex gap-2 mt-3">
            <Button size="sm" onClick={applyFilters}>
              <Search className="w-3.5 h-3.5 mr-1.5" />
              {t("common.search")}
            </Button>
            <Button size="sm" variant="outline" onClick={clearFilters}>
              {t("audit.clearFilters")}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Table */}
      <Card>
        <CardContent className="p-0 overflow-x-auto">
          {isLoading ? (
            <div className="p-4 space-y-3">
              {Array.from({ length: 8 }).map((_, i) => (
                <Skeleton key={i} className="h-12" />
              ))}
            </div>
          ) : !data?.data?.length ? (
            <div className="p-8 text-center text-muted-foreground text-sm">
              {t("common.noDataFound")}
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-44">{t("audit.time")}</TableHead>
                  <TableHead>{t("audit.actor")}</TableHead>
                  <TableHead>{t("audit.action")}</TableHead>
                  <TableHead className="w-16">{t("audit.status")}</TableHead>
                  <TableHead className="w-20">{t("audit.duration")}</TableHead>
                  <TableHead>{t("audit.ipAddress")}</TableHead>
                  <TableHead>{t("audit.before")}</TableHead>
                  <TableHead>{t("audit.after")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.data.map((log: AuditLog) => {
                  const { method, path } = formatPath(log.action);
                  return (
                    <TableRow key={log.id}>
                      <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                        {formatTime(log.created_at)}
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-col gap-0.5">
                          <span className="text-sm font-medium">
                            {log.actor_username ?? log.actor_id ?? "—"}
                          </span>
                          {log.actor_role && (
                            <span className="text-[10px] text-muted-foreground uppercase tracking-wide">
                              {t(`roles.${log.actor_role}`, { defaultValue: log.actor_role })}
                            </span>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <span className={cn(
                            "text-[10px] font-bold px-1.5 py-0.5 rounded font-mono",
                            methodBadgeClass(log.action),
                          )}>
                            {method}
                          </span>
                          <span className="text-xs font-mono text-muted-foreground truncate max-w-[220px]" title={path}>
                            {path}
                          </span>
                        </div>
                      </TableCell>
                      <TableCell>
                        {log.status_code ? (
                          <Badge variant={statusVariant(log.status_code)}>
                            {log.status_code}
                          </Badge>
                        ) : "—"}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {log.duration_ms != null ? `${log.duration_ms}ms` : "—"}
                      </TableCell>
                      <TableCell className="text-xs font-mono">
                        {log.ip_address ?? "—"}
                      </TableCell>
                      <TableCell>
                        <DataDrawer data={log.before_data} />
                      </TableCell>
                      <TableCell>
                        <DataDrawer data={log.after_data} />
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Pagination */}
      {data && data.total_pages > 1 && (
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">
            {t("common.total")}: {data.total}
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline" size="sm"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
            >
              {t("common.previous")}
            </Button>
            <span className="flex items-center px-3 text-muted-foreground text-xs">
              {page} / {data.total_pages}
            </span>
            <Button
              variant="outline" size="sm"
              disabled={page >= data.total_pages}
              onClick={() => setPage((p) => p + 1)}
            >
              {t("common.next")}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
