"use client";
/**
 * Thin ECharts wrapper: tree-shaken registration, resize observer, click events,
 * and an accessible label. Every chart sits next to an equivalent table view.
 */
import { Box } from "@mui/material";
import { BarChart, LineChart, PieChart, TreemapChart, CustomChart } from "echarts/charts";
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  MarkAreaComponent,
  TooltipComponent,
  AriaComponent,
  TitleComponent,
} from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { useEffect, useRef } from "react";

echarts.use([BarChart, LineChart, PieChart, TreemapChart, CustomChart, GridComponent, LegendComponent, TooltipComponent, DataZoomComponent, MarkLineComponent, MarkAreaComponent, AriaComponent, TitleComponent, CanvasRenderer]);

export type EChartsOption = echarts.EChartsCoreOption;

export interface EChartProps {
  option: EChartsOption;
  height?: number | string;
  ariaLabel: string;
  onClick?: (params: { name: string; seriesName?: string; dataIndex: number; data: unknown; seriesIndex?: number }) => void;
  testId?: string;
}

export default function EChart({ option, height = 320, ariaLabel, onClick, testId }: EChartProps) {
  const ref = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  const clickRef = useRef(onClick);
  clickRef.current = onClick;

  useEffect(() => {
    if (!ref.current) return;
    const c = echarts.init(ref.current, undefined, { renderer: "canvas" });
    chart.current = c;
    c.on("click", (p) => clickRef.current?.(p as never));
    const ro = new ResizeObserver(() => c.resize());
    ro.observe(ref.current);
    return () => {
      ro.disconnect();
      c.dispose();
      chart.current = null;
    };
  }, []);

  useEffect(() => {
    chart.current?.setOption({ aria: { enabled: true, label: { description: ariaLabel } }, ...option }, { notMerge: true });
  }, [option, ariaLabel]);

  return <Box ref={ref} role="img" aria-label={ariaLabel} data-testid={testId} sx={{ width: "100%", height, cursor: onClick ? "pointer" : "default" }} />;
}
