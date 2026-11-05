"use client";
/**
 * Reusable data table (TanStack Table + MUI).
 * Sorting (client or server), multi-column sort (shift-click), server-side pagination,
 * column visibility (persisted per user in localStorage), column resizing, sticky header,
 * horizontal scrolling, expandable rows and loading / empty / error states.
 */
import ViewColumnOutlinedIcon from "@mui/icons-material/ViewColumnOutlined";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import KeyboardArrowRightIcon from "@mui/icons-material/KeyboardArrowRight";
import {
  Box,
  Button,
  Checkbox,
  FormControlLabel,
  IconButton,
  LinearProgress,
  Menu,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  TableSortLabel,
  Typography,
} from "@mui/material";
import {
  flexRender,
  getCoreRowModel,
  getExpandedRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  type ColumnDef,
  type Row,
  type SortingState,
  type VisibilityState,
  useReactTable,
} from "@tanstack/react-table";
import { Fragment, type ReactNode, useEffect, useMemo, useState } from "react";
import { surface } from "@/styles/tokens";

export interface ColumnMeta {
  align?: "left" | "right" | "center";
  numeric?: boolean;
  label?: string; // name in the column picker
}

export interface ServerPaging {
  page: number; // 1-based
  pageSize: number;
  total: number;
  onChange: (page: number, pageSize: number) => void;
}

export interface DataTableProps<T> {
  data: T[];
  columns: ColumnDef<T, unknown>[];
  loading?: boolean;
  error?: string | null;
  emptyMessage?: string;
  onRowClick?: (row: T) => void;
  getRowId?: (row: T, index: number) => string;
  selectedRowId?: string | null;
  initialSorting?: SortingState;
  serverSorting?: { sorting: SortingState; onChange: (s: SortingState) => void };
  serverPaging?: ServerPaging;
  clientPageSize?: number;
  defaultHidden?: string[];
  storageKey?: string;
  maxHeight?: number | string;
  toolbar?: ReactNode;
  renderSubRow?: (row: T) => ReactNode;
  footer?: ReactNode;
  testId?: string;
  dense?: boolean;
  /** Hide the toolbar row (search/column picker) for small evidence tables. */
  hideToolbar?: boolean;
}

function loadVisibility(key: string | undefined, hidden: string[]): VisibilityState {
  const base: VisibilityState = Object.fromEntries(hidden.map((h) => [h, false]));
  if (!key || typeof window === "undefined") return base;
  try {
    return { ...base, ...JSON.parse(window.localStorage.getItem(`acip.cols.${key}`) ?? "{}") };
  } catch {
    return base;
  }
}

export default function DataTable<T>(props: DataTableProps<T>) {
  const { data, columns, loading, error, serverPaging, serverSorting, storageKey } = props;
  const [sorting, setSorting] = useState<SortingState>(props.initialSorting ?? []);
  const [visibility, setVisibility] = useState<VisibilityState>(() => loadVisibility(storageKey, props.defaultHidden ?? []));
  const [expanded, setExpanded] = useState({});
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);

  useEffect(() => {
    if (storageKey && typeof window !== "undefined") window.localStorage.setItem(`acip.cols.${storageKey}`, JSON.stringify(visibility));
  }, [visibility, storageKey]);

  const table = useReactTable({
    data,
    columns,
    state: {
      sorting: serverSorting ? serverSorting.sorting : sorting,
      columnVisibility: visibility,
      expanded,
      ...(serverPaging ? {} : {}),
    },
    getRowId: props.getRowId,
    onSortingChange: (u) => {
      const next = typeof u === "function" ? u(serverSorting ? serverSorting.sorting : sorting) : u;
      if (serverSorting) serverSorting.onChange(next);
      else setSorting(next);
    },
    onColumnVisibilityChange: setVisibility,
    onExpandedChange: setExpanded,
    getRowCanExpand: () => !!props.renderSubRow,
    manualSorting: !!serverSorting,
    manualPagination: !!serverPaging,
    enableMultiSort: true,
    isMultiSortEvent: (e) => (e as MouseEvent).shiftKey,
    columnResizeMode: "onChange",
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getExpandedRowModel: getExpandedRowModel(),
    getPaginationRowModel: serverPaging ? undefined : getPaginationRowModel(),
    initialState: { pagination: { pageSize: props.clientPageSize ?? 25 } },
  });

  const rows = table.getRowModel().rows;
  const colCount = table.getVisibleLeafColumns().length + (props.renderSubRow ? 1 : 0);
  const hideable = useMemo(() => table.getAllLeafColumns().filter((c) => c.getCanHide()), [table]);

  return (
    <Box data-testid={props.testId}>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ px: 1.5, py: 1, borderBottom: `1px solid ${surface.border}`, minHeight: 44, display: props.hideToolbar ? "none" : "flex" }}>
        <Box sx={{ flex: 1, display: "flex", gap: 1, alignItems: "center", flexWrap: "wrap" }}>{props.toolbar}</Box>
        <Button size="small" variant="text" color="inherit" startIcon={<ViewColumnOutlinedIcon fontSize="small" />} onClick={(e) => setAnchor(e.currentTarget)} aria-label="Choose columns">
          Columns
        </Button>
        <Menu anchorEl={anchor} open={!!anchor} onClose={() => setAnchor(null)} slotProps={{ paper: { sx: { maxHeight: 420, px: 1.5, py: 0.5 } } }}>
          {hideable.map((c) => (
            <Box key={c.id}>
              <FormControlLabel
                control={<Checkbox size="small" checked={c.getIsVisible()} onChange={c.getToggleVisibilityHandler()} />}
                label={<Typography variant="body2">{(c.columnDef.meta as ColumnMeta | undefined)?.label ?? (typeof c.columnDef.header === "string" ? c.columnDef.header : c.id)}</Typography>}
              />
            </Box>
          ))}
        </Menu>
      </Stack>
      <Box sx={{ position: "relative" }}>
        {loading && <LinearProgress sx={{ position: "absolute", top: 0, left: 0, right: 0, zIndex: 3, height: 2 }} />}
        <TableContainer sx={{ maxHeight: props.maxHeight ?? 560, overflowX: "auto" }}>
          <Table stickyHeader size="small" sx={{ tableLayout: "fixed", width: table.getTotalSize() + (props.renderSubRow ? 36 : 0), minWidth: "100%" }}>
            <TableHead>
              {table.getHeaderGroups().map((hg) => (
                <TableRow key={hg.id}>
                  {props.renderSubRow && <TableCell sx={{ width: 36 }} />}
                  {hg.headers.map((h) => {
                    const meta = h.column.columnDef.meta as ColumnMeta | undefined;
                    const sortDir = h.column.getIsSorted();
                    return (
                      <TableCell key={h.id} align={meta?.align ?? (meta?.numeric ? "right" : "left")} sx={{ width: h.getSize(), position: "relative", userSelect: "none", zIndex: 2 }}>
                        {h.isPlaceholder ? null : h.column.getCanSort() ? (
                          <TableSortLabel active={!!sortDir} direction={sortDir || "desc"} onClick={h.column.getToggleSortingHandler()} sx={{ flexDirection: meta?.numeric ? "row-reverse" : "row" }}>
                            {flexRender(h.column.columnDef.header, h.getContext())}
                          </TableSortLabel>
                        ) : (
                          flexRender(h.column.columnDef.header, h.getContext())
                        )}
                        {h.column.getCanResize() && (
                          <Box
                            onMouseDown={h.getResizeHandler()}
                            onTouchStart={h.getResizeHandler()}
                            onDoubleClick={() => h.column.resetSize()}
                            sx={{ position: "absolute", right: 0, top: 6, bottom: 6, width: 5, cursor: "col-resize", borderRight: `2px solid ${h.column.getIsResizing() ? "#0f6cbd" : "transparent"}`, "&:hover": { borderRightColor: surface.borderStrong } }}
                          />
                        )}
                      </TableCell>
                    );
                  })}
                </TableRow>
              ))}
            </TableHead>
            <TableBody>
              {error ? (
                <TableRow>
                  <TableCell colSpan={colCount} sx={{ py: 5, textAlign: "center", color: "error.main" }}>
                    {error}
                  </TableCell>
                </TableRow>
              ) : rows.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={colCount} sx={{ py: 5, textAlign: "center", color: "text.secondary" }}>
                    {loading ? "Loading…" : (props.emptyMessage ?? "No data for the selected filters.")}
                  </TableCell>
                </TableRow>
              ) : (
                rows.map((row: Row<T>) => {
                  const selected = props.selectedRowId && row.id === props.selectedRowId;
                  return (
                    <Fragment key={row.id}>
                      <TableRow
                        hover
                        selected={!!selected}
                        onClick={props.onRowClick ? () => props.onRowClick?.(row.original) : undefined}
                        sx={{ cursor: props.onRowClick ? "pointer" : "default", "&.Mui-selected": { backgroundColor: surface.selected } }}
                      >
                        {props.renderSubRow && (
                          <TableCell sx={{ width: 36, px: 0.5 }}>
                            <IconButton
                              aria-label={row.getIsExpanded() ? "Collapse row" : "Expand row"}
                              onClick={(e) => {
                                e.stopPropagation();
                                row.toggleExpanded();
                              }}
                            >
                              {row.getIsExpanded() ? <KeyboardArrowDownIcon fontSize="small" /> : <KeyboardArrowRightIcon fontSize="small" />}
                            </IconButton>
                          </TableCell>
                        )}
                        {row.getVisibleCells().map((cell) => {
                          const meta = cell.column.columnDef.meta as ColumnMeta | undefined;
                          return (
                            <TableCell
                              key={cell.id}
                              align={meta?.align ?? (meta?.numeric ? "right" : "left")}
                              className={meta?.numeric ? "num" : undefined}
                              sx={{ width: cell.column.getSize(), overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                            >
                              {flexRender(cell.column.columnDef.cell, cell.getContext())}
                            </TableCell>
                          );
                        })}
                      </TableRow>
                      {row.getIsExpanded() && props.renderSubRow && (
                        <TableRow>
                          <TableCell colSpan={colCount} sx={{ backgroundColor: surface.subtle, py: 1.5 }}>
                            {props.renderSubRow(row.original)}
                          </TableCell>
                        </TableRow>
                      )}
                    </Fragment>
                  );
                })
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </Box>
      {props.footer}
      {serverPaging ? (
        <TablePagination
          component="div"
          count={serverPaging.total}
          page={serverPaging.page - 1}
          rowsPerPage={serverPaging.pageSize}
          rowsPerPageOptions={[25, 50, 100, 250]}
          onPageChange={(_, p) => serverPaging.onChange(p + 1, serverPaging.pageSize)}
          onRowsPerPageChange={(e) => serverPaging.onChange(1, Number(e.target.value))}
          sx={{ borderTop: `1px solid ${surface.border}` }}
        />
      ) : data.length > (props.clientPageSize ?? 25) ? (
        <TablePagination
          component="div"
          count={data.length}
          page={table.getState().pagination.pageIndex}
          rowsPerPage={table.getState().pagination.pageSize}
          rowsPerPageOptions={[10, 25, 50, 100]}
          onPageChange={(_, p) => table.setPageIndex(p)}
          onRowsPerPageChange={(e) => table.setPageSize(Number(e.target.value))}
          sx={{ borderTop: `1px solid ${surface.border}` }}
        />
      ) : null}
    </Box>
  );
}
