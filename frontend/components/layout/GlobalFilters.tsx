"use client";
import CalendarMonthOutlinedIcon from "@mui/icons-material/CalendarMonthOutlined";
import CheckIcon from "@mui/icons-material/Check";
import {
  Box,
  Button,
  Divider,
  ListItemIcon,
  ListItemText,
  Menu,
  MenuItem,
  Select,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from "@mui/material";
import { useMemo, useState } from "react";
import { useGlobalFilters } from "@/hooks/useGlobalFilters";
import { useFilterOptions } from "@/services/queries";

const PRESET_GROUPS: { label: string; values: string[] }[] = [
  { label: "Days", values: ["today", "yesterday", "last_7_days", "last_30_days", "last_90_days"] },
  { label: "Calendar", values: ["week_to_date", "previous_week", "month_to_date", "previous_month", "quarter_to_date", "previous_quarter", "year_to_date", "previous_year"] },
];

const LABELS: Record<string, string> = {
  today: "Today",
  yesterday: "Yesterday",
  last_7_days: "Last 7 days",
  last_30_days: "Last 30 days",
  last_90_days: "Last 90 days",
  week_to_date: "Week-to-date",
  previous_week: "Previous week",
  month_to_date: "Month-to-date",
  previous_month: "Previous month",
  quarter_to_date: "Quarter-to-date",
  previous_quarter: "Previous quarter",
  year_to_date: "Year-to-date",
  previous_year: "Previous year",
  custom: "Custom range",
};

export function presetLabel(p: string, start?: string, end?: string) {
  if (p === "custom" && start && end) return `${start} → ${end}`;
  return LABELS[p] ?? p;
}

export function DateRangeControl({ disabled }: { disabled?: boolean }) {
  const { filters, setFilters } = useGlobalFilters();
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const [start, setStart] = useState(filters.start);
  const [end, setEnd] = useState(filters.end);
  return (
    <>
      <Tooltip title={disabled ? "This page uses fixed periods" : "Reporting period (anchored to the latest available billing date)"}>
        <span>
          <Button
            variant="outlined"
            color="inherit"
            disabled={disabled}
            startIcon={<CalendarMonthOutlinedIcon fontSize="small" />}
            onClick={(e) => setAnchor(e.currentTarget)}
            sx={{ bgcolor: "#fff", borderColor: "divider", fontWeight: 600, minWidth: 150, justifyContent: "flex-start" }}
            data-testid="date-range"
          >
            {presetLabel(filters.preset, filters.start, filters.end)}
          </Button>
        </span>
      </Tooltip>
      <Menu anchorEl={anchor} open={!!anchor} onClose={() => setAnchor(null)} slotProps={{ paper: { sx: { width: 280 } } }}>
        {PRESET_GROUPS.map((g, gi) => [
          gi > 0 && <Divider key={`d${gi}`} />,
          <Typography key={g.label} variant="overline" sx={{ px: 2, color: "text.secondary" }}>
            {g.label}
          </Typography>,
          ...g.values.map((v) => (
            <MenuItem
              key={v}
              selected={filters.preset === v}
              onClick={() => {
                setFilters({ preset: v, start: "", end: "" });
                setAnchor(null);
              }}
            >
              <ListItemIcon sx={{ minWidth: 28 }}>{filters.preset === v && <CheckIcon sx={{ fontSize: 16 }} />}</ListItemIcon>
              <ListItemText primary={LABELS[v]} />
            </MenuItem>
          )),
        ])}
        <Divider />
        <Box sx={{ px: 2, py: 1 }}>
          <Typography variant="overline" color="text.secondary">
            Custom range
          </Typography>
          <Stack direction="row" spacing={1} sx={{ mt: 0.5 }}>
            <TextField type="date" label="From" value={start} onChange={(e) => setStart(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} fullWidth />
            <TextField type="date" label="To" value={end} onChange={(e) => setEnd(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} fullWidth />
          </Stack>
          <Button
            fullWidth
            variant="contained"
            sx={{ mt: 1 }}
            disabled={!start || !end || end < start}
            onClick={() => {
              setFilters({ preset: "custom", start, end });
              setAnchor(null);
            }}
          >
            Apply custom range
          </Button>
        </Box>
      </Menu>
    </>
  );
}

export function GlobalFilterBar({ dateRange = true }: { dateRange?: boolean }) {
  const { filters, setFilters } = useGlobalFilters();
  const opts = useFilterOptions();
  const o = opts.data;
  const subs = useMemo(() => {
    if (!o) return [];
    const envCodes = filters.env ? o.environments.filter((e) => e.group === filters.env || e.code === filters.env).map((e) => e.code) : null;
    return o.subscriptions.filter((s) => (!filters.app || String(s.application_id) === filters.app) && (!envCodes || (s.environment && envCodes.includes(s.environment))));
  }, [o, filters.app, filters.env]);
  const selectSx = { minWidth: 150, bgcolor: "#fff", "& .MuiSelect-select": { py: "5px", fontWeight: 600 } };
  return (
    <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap data-testid="global-filters">
      <Select value={filters.app} displayEmpty onChange={(e) => setFilters({ app: e.target.value, sub: "" })} sx={selectSx} inputProps={{ "aria-label": "Application" }} data-testid="filter-application">
        <MenuItem value="">All applications</MenuItem>
        {o?.applications.map((a) => (
          <MenuItem key={a.id} value={String(a.id)}>
            {a.name}
          </MenuItem>
        ))}
        <Divider />
        <MenuItem value="shared">Shared Services</MenuItem>
        <MenuItem value="unallocated">Unallocated</MenuItem>
      </Select>
      <Select value={filters.env} displayEmpty onChange={(e) => setFilters({ env: e.target.value, sub: "" })} sx={selectSx} inputProps={{ "aria-label": "Environment" }} data-testid="filter-environment">
        <MenuItem value="">All environments</MenuItem>
        {o?.environment_groups.map((g) => (
          <MenuItem key={g.code} value={g.code}>
            {g.name}
          </MenuItem>
        ))}
      </Select>
      <Select value={filters.sub} displayEmpty onChange={(e) => setFilters({ sub: e.target.value })} sx={{ ...selectSx, minWidth: 190, maxWidth: 260 }} inputProps={{ "aria-label": "Subscription" }} data-testid="filter-subscription">
        <MenuItem value="">All subscriptions</MenuItem>
        {subs.map((s) => (
          <MenuItem key={s.subscription_id} value={s.subscription_id}>
            <ListItemText primary={s.subscription_name} secondary={s.subscription_id} slotProps={{ secondary: { sx: { fontSize: 10.5 } } }} />
          </MenuItem>
        ))}
      </Select>
      <DateRangeControl disabled={!dateRange} />
      <ToggleButtonGroup size="small" exclusive value={filters.cost} onChange={(_, v) => v && setFilters({ cost: v })} aria-label="Cost type" sx={{ bgcolor: "#fff" }}>
        {/* Tooltips must not wrap ToggleButtons (the group injects props into direct children) */}
        <ToggleButton value="actual" data-testid="cost-actual" title="Actual cost: charges as billed (purchases on the purchase date)">
          Actual
        </ToggleButton>
        <ToggleButton value="amortized" data-testid="cost-amortized" title="Amortized cost: reservation / savings-plan purchases spread over their term">
          Amortized
        </ToggleButton>
      </ToggleButtonGroup>
      {o && o.currencies.length > 1 && (
        <Select value={filters.cur} displayEmpty onChange={(e) => setFilters({ cur: e.target.value })} sx={{ ...selectSx, minWidth: 100 }} inputProps={{ "aria-label": "Currency" }}>
          <MenuItem value="">{o.default_currency} (default)</MenuItem>
          {o.currencies.map((c) => (
            <MenuItem key={c} value={c}>
              {c}
            </MenuItem>
          ))}
        </Select>
      )}
    </Stack>
  );
}
