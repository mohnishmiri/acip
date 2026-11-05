"use client";
import FileDownloadOutlinedIcon from "@mui/icons-material/FileDownloadOutlined";
import { Button, ListItemText, Menu, MenuItem, Snackbar } from "@mui/material";
import { useState } from "react";
import { download, type Params } from "@/lib/api";

/** Server-side export: the file respects the applied filters and states period, currency and cost type. */
export function ExportMenu({ params, view, label = "Export" }: { params: Params; view: string; label?: string }) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const run = async (format: "csv" | "xlsx") => {
    setAnchor(null);
    try {
      await download("/costs/export", { ...params, view, format, page: undefined, page_size: undefined });
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Export failed");
    }
  };
  return (
    <>
      <Button variant="outlined" color="inherit" startIcon={<FileDownloadOutlinedIcon fontSize="small" />} onClick={(e) => setAnchor(e.currentTarget)} data-testid={`export-${view}`}>
        {label}
      </Button>
      <Menu anchorEl={anchor} open={!!anchor} onClose={() => setAnchor(null)}>
        <MenuItem onClick={() => run("csv")}>
          <ListItemText primary="CSV" secondary="Comma-separated, with report context header" />
        </MenuItem>
        <MenuItem onClick={() => run("xlsx")}>
          <ListItemText primary="Excel (.xlsx)" secondary="Formatted workbook" />
        </MenuItem>
      </Menu>
      <Snackbar open={!!msg} autoHideDuration={5000} onClose={() => setMsg(null)} message={msg} />
    </>
  );
}
