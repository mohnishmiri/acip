"use client";
/** Email delivery status, test email and per-notification email preview. */
import MailOutlineIcon from "@mui/icons-material/MailOutline";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import SendOutlinedIcon from "@mui/icons-material/SendOutlined";
import { zodResolver } from "@hookform/resolvers/zod";
import { Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, LinearProgress, Stack, ToggleButton, ToggleButtonGroup, Tooltip, Typography } from "@mui/material";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { StatusChip } from "@/components/common/StatusChip";
import { api, apiText } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { useApi } from "@/services/queries";
import { surface } from "@/styles/tokens";
import { errorMessage, FormDialog, RhfText, useCan, useToast } from "@/features/admin/ui";

export interface EmailSettings {
  provider: "disabled" | "smtp" | "graph";
  enabled: boolean;
  from_address: string;
  from_name: string;
  reply_to: string | null;
  smtp_host: string | null;
  smtp_port: number | null;
  smtp_security: string | null;
  smtp_auth: boolean | null;
  graph_sender: string | null;
  public_url: string;
  local_catcher: boolean;
  deliveries: Record<string, number>;
}

export interface Delivery {
  id: number;
  channel: string;
  status: "pending" | "sent" | "failed" | "skipped";
  recipients: string[];
  attempts: number;
  last_error: string | null;
  sent_at: string | null;
  subject: string | null;
}

export const EMAIL_SPLIT = /[\s,;]+/;
export const EMAIL_RE = /^[^@\s<>"']+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$/;

export function parseRecipients(text: string): string[] {
  return Array.from(new Set(text.split(EMAIL_SPLIT).map((x) => x.trim().toLowerCase()).filter(Boolean)));
}

const testSchema = z.object({
  recipients: z
    .string()
    .trim()
    .min(1, "Enter at least one email address")
    .refine((v) => parseRecipients(v).every((e) => EMAIL_RE.test(e)), "One or more addresses are not valid")
    .refine((v) => parseRecipients(v).length <= 10, "At most 10 recipients"),
});
type TestValues = z.infer<typeof testSchema>;

function providerText(s: EmailSettings): string {
  if (s.provider === "smtp") return `SMTP · ${s.smtp_host}:${s.smtp_port}${s.smtp_security && s.smtp_security !== "none" ? ` (${s.smtp_security.toUpperCase()})` : ""}${s.smtp_auth ? " · authenticated" : ""}`;
  if (s.provider === "graph") return `Microsoft Graph · mailbox ${s.graph_sender}`;
  return "Disabled";
}

export function EmailDeliveryPanel() {
  const q = useApi<EmailSettings>("/notifications/email-settings", undefined, { refetchInterval: 30_000 });
  const canManage = useCan("manage_alerts");
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const form = useForm<TestValues>({ resolver: zodResolver(testSchema), defaultValues: { recipients: "" } });
  const s = q.data;
  const d = s?.deliveries ?? {};
  return (
    <Box sx={{ border: `1px solid ${surface.border}`, borderRadius: 1, bgcolor: "#fff", p: 2 }} data-testid="email-delivery-panel">
      <Stack direction={{ xs: "column", md: "row" }} spacing={2} alignItems={{ md: "center" }}>
        <Box sx={{ width: 40, height: 40, borderRadius: 1, bgcolor: "#ebf3fc", color: "primary.main", display: "grid", placeItems: "center", flexShrink: 0 }} aria-hidden>
          <MailOutlineIcon />
        </Box>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Stack direction="row" spacing={1} alignItems="center">
            <Typography variant="subtitle1">Email delivery</Typography>
            {s && (s.enabled ? <StatusChip value="ok" label={s.local_catcher ? "Enabled · local mail catcher" : "Enabled"} /> : <StatusChip value="disabled" label="Disabled" />)}
          </Stack>
          {s ? (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25 }}>
              From <b>{s.from_name}</b> &lt;{s.from_address}&gt; · {providerText(s)}
              {s.reply_to ? ` · replies to ${s.reply_to}` : ""}
            </Typography>
          ) : (
            <Typography variant="body2" color="text.secondary">Loading…</Typography>
          )}
          <Typography variant="caption" component="div" sx={{ mt: 0.5 }}>
            Sent {d.sent ?? 0} · pending {d.pending ?? 0} · failed {d.failed ?? 0} · skipped {d.skipped ?? 0}. Each new alert is emailed once to the recipients of its rule; ongoing issues are not re-sent.
          </Typography>
        </Box>
        {s?.local_catcher && (
          <Button variant="text" href="http://localhost:8025" target="_blank" rel="noopener" endIcon={<OpenInNewIcon fontSize="small" />}>
            Open local inbox
          </Button>
        )}
        {canManage && (
          <Button variant="outlined" startIcon={<SendOutlinedIcon fontSize="small" />} disabled={!s?.enabled} onClick={() => { setError(null); form.reset({ recipients: "" }); setOpen(true); }} data-testid="email-test-open">
            Send test email
          </Button>
        )}
      </Stack>
      {s && !s.enabled && (
        <Alert severity="info" sx={{ mt: 1.5 }}>
          Email is disabled. Set <code>EMAIL_PROVIDER</code> to <code>smtp</code> (e.g. Office 365 or your SMTP relay) or <code>graph</code> (Microsoft Graph) and restart the services. Notifications are still recorded in-app.
        </Alert>
      )}
      {s?.local_catcher && (
        <Alert severity="success" variant="outlined" sx={{ mt: 1.5, bgcolor: "#fff" }}>
          Local development: emails are delivered to the Mailpit catcher at <b>http://localhost:8025</b> and never leave this machine. Configure <code>SMTP_*</code> or Microsoft Graph to send real mail.
        </Alert>
      )}
      <FormDialog
        open={open}
        title="Send a test email"
        onClose={() => setOpen(false)}
        busy={form.formState.isSubmitting}
        error={error}
        submitLabel="Send test email"
        testId="email-test-dialog"
        onSubmit={form.handleSubmit(async (v) => {
          setError(null);
          try {
            const r = await api<{ recipients: string[] }>("/notifications/test-email", { method: "POST", body: { recipients: parseRecipients(v.recipients) } });
            toast(`Test email sent to ${r.recipients.join(", ")}`);
            setOpen(false);
            q.refetch();
          } catch (e) {
            setError(errorMessage(e));
          }
        })}
      >
        <Typography variant="body2" color="text.secondary">
          Sends a sample alert email immediately using the configured provider, to confirm delivery and formatting.
        </Typography>
        <RhfText control={form.control} name="recipients" label="Recipients" required helperText="One or more addresses, separated by commas or new lines" multiline testId="email-test-recipients" />
      </FormDialog>
    </Box>
  );
}

export function EmailStatusChip({ delivery }: { delivery?: Delivery }) {
  if (!delivery) return <Typography variant="caption">—</Typography>;
  const label = { sent: "Emailed", pending: "Queued", failed: "Failed", skipped: "Not sent" }[delivery.status] ?? delivery.status;
  const tip = [
    `Recipients: ${delivery.recipients.join(", ") || "none"}`,
    delivery.sent_at ? `Sent ${dateTime(delivery.sent_at)}` : `Attempts: ${delivery.attempts}`,
    delivery.last_error ? `Reason: ${delivery.last_error}` : null,
  ].filter(Boolean).join("\n");
  const tone = delivery.status === "sent" ? "good" : delivery.status === "failed" ? "critical" : delivery.status === "pending" ? "info" : "neutral";
  return (
    <Tooltip title={<span style={{ whiteSpace: "pre-line" }}>{tip}</span>}>
      <span>
        <StatusChip value={delivery.status} label={label} tone={tone} />
      </span>
    </Tooltip>
  );
}

export function EmailPreviewDialog({ notificationId, onClose }: { notificationId: number | null; onClose: () => void }) {
  const [format, setFormat] = useState<"html" | "text">("html");
  const [body, setBody] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (notificationId === null) return;
    setBody(null);
    setError(null);
    apiText(`/notifications/${notificationId}/email-preview`, { format })
      .then(setBody)
      .catch((e) => setError(errorMessage(e)));
  }, [notificationId, format]);
  return (
    <Dialog open={notificationId !== null} onClose={onClose} maxWidth="md" fullWidth data-testid="email-preview-dialog">
      <DialogTitle sx={{ display: "flex", alignItems: "center", gap: 2 }}>
        <Box sx={{ flex: 1 }}>Email preview</Box>
        <ToggleButtonGroup size="small" exclusive value={format} onChange={(_, v) => v && setFormat(v)} aria-label="Preview format">
          <ToggleButton value="html">HTML</ToggleButton>
          <ToggleButton value="text">Plain text</ToggleButton>
        </ToggleButtonGroup>
      </DialogTitle>
      <DialogContent dividers sx={{ p: 0, bgcolor: "#f2f4f7" }}>
        {error && <Alert severity="error" sx={{ m: 2 }}>{error}</Alert>}
        {!body && !error && <LinearProgress />}
        {body && format === "html" && (
          // sandbox without permissions: no scripts, no navigation from inside the preview
          <iframe title="Email preview" sandbox="" srcDoc={body} style={{ width: "100%", height: "70vh", border: 0, display: "block" }} data-testid="email-preview-frame" />
        )}
        {body && format === "text" && (
          <Box component="pre" sx={{ m: 0, p: 2, fontSize: 12.5, whiteSpace: "pre-wrap", fontFamily: "Consolas, 'Courier New', monospace", bgcolor: "#fff", minHeight: "40vh" }}>
            {body}
          </Box>
        )}
      </DialogContent>
      <DialogActions>
        <Typography variant="caption" sx={{ flex: 1, px: 1 }}>
          Exactly what recipients receive (rendered from the current record).
        </Typography>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}
