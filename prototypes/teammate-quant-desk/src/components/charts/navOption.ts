import * as echarts from "echarts";
import type { EChartsOption } from "echarts";
import type { NavPoint } from "@/data/mock";

const AXIS_LABEL = {
  color: "#566173",
  fontSize: 10,
  fontFamily: "JetBrains Mono",
};

/** 净值曲线 + 回撤曲线：同一实例双 grid，共享 X 轴与十字准星 */
export function buildNavOption(data: NavPoint[], benchName: string): EChartsOption {
  const dates = data.map((p) => p.date);
  const strategy = data.map((p) => +p.strategy.toFixed(4));
  const benchmark = data.map((p) => +p.benchmark.toFixed(4));
  const dd = data.map((p) => +(p.drawdown * 100).toFixed(2));
  const minDd = Math.min(...dd);
  const minIdx = dd.indexOf(minDd);

  return {
    animationDuration: 900,
    animationEasing: "cubicOut",
    axisPointer: {
      link: [{ xAxisIndex: "all" }],
      lineStyle: { color: "rgba(148,163,184,0.35)", width: 1 },
      label: {
        show: false,
      },
    },
    grid: [
      { left: 52, right: 18, top: 34, height: "52%" },
      { left: 52, right: 18, top: "72%", height: "17%" },
    ],
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(13,18,25,0.96)",
      borderColor: "rgba(148,163,184,0.16)",
      borderWidth: 1,
      padding: [10, 14],
      textStyle: { color: "#E2E8F0", fontSize: 11, fontFamily: "JetBrains Mono" },
      formatter: (params) => {
        const list = params as { dataIndex: number }[];
        const p = data[list[0].dataIndex];
        const row = (color: string, label: string, value: string) =>
          `<div style="display:flex;align-items:center;gap:8px;margin-top:5px">
            <span style="width:8px;height:8px;border-radius:2px;background:${color}"></span>
            <span style="color:#8B94A7">${label}</span>
            <span style="margin-left:auto;padding-left:20px;font-weight:600">${value}</span>
          </div>`;
        return `<div style="min-width:190px">
          <div style="font-weight:700;letter-spacing:0.04em">${p.date}</div>
          ${row("#22D3EE", "策略净值", p.strategy.toFixed(4))}
          ${row("#64748B", benchName, p.benchmark.toFixed(4))}
          ${row("#F43F5E", "当日收益", `${p.ret >= 0 ? "+" : ""}${(p.ret * 100).toFixed(2)}%`)}
          ${row("#F43F5E", "回撤", `${(p.drawdown * 100).toFixed(2)}%`)}
        </div>`;
      },
    },
    xAxis: [
      {
        type: "category",
        gridIndex: 0,
        data: dates,
        show: false,
        boundaryGap: false,
      },
      {
        type: "category",
        gridIndex: 1,
        data: dates,
        boundaryGap: false,
        axisLine: { lineStyle: { color: "rgba(148,163,184,0.12)" } },
        axisTick: { show: false },
        axisLabel: { ...AXIS_LABEL, hideOverlap: true, margin: 10 },
      },
    ],
    yAxis: [
      {
        type: "value",
        gridIndex: 0,
        scale: true,
        name: "净值",
        nameTextStyle: { color: "#566173", fontSize: 10, align: "left" },
        splitLine: { lineStyle: { color: "rgba(148,163,184,0.07)" } },
        axisLabel: { ...AXIS_LABEL, formatter: (v: number) => v.toFixed(2) },
      },
      {
        type: "value",
        gridIndex: 1,
        scale: true,
        splitNumber: 2,
        name: "回撤",
        nameTextStyle: { color: "#566173", fontSize: 10, align: "left" },
        splitLine: { show: false },
        axisLabel: { ...AXIS_LABEL, formatter: "{value}%" },
      },
    ],
    series: [
      {
        name: "策略净值",
        type: "line",
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: strategy,
        showSymbol: false,
        smooth: 0.12,
        z: 3,
        lineStyle: { width: 2, color: "#22D3EE" },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: "rgba(34,211,238,0.24)" },
            { offset: 1, color: "rgba(34,211,238,0)" },
          ]),
        },
        emphasis: { disabled: true },
      },
      {
        name: benchName,
        type: "line",
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: benchmark,
        showSymbol: false,
        smooth: 0.12,
        z: 2,
        lineStyle: { width: 1, type: "dashed", color: "#64748B" },
        emphasis: { disabled: true },
      },
      {
        name: "回撤",
        type: "line",
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: dd,
        showSymbol: false,
        lineStyle: { width: 1, color: "#F43F5E" },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: "rgba(244,63,94,0)" },
            { offset: 1, color: "rgba(244,63,94,0.38)" },
          ]),
        },
        markPoint: {
          symbol: "circle",
          symbolSize: 6,
          itemStyle: { color: "#F43F5E", borderColor: "#0A0E14", borderWidth: 1.5 },
          label: {
            show: true,
            formatter: `最大回撤 ${minDd.toFixed(2)}%`,
            position: "top",
            distance: 6,
            color: "#F43F5E",
            fontSize: 10,
            fontFamily: "JetBrains Mono",
          },
          data: [{ name: "最大回撤", coord: [dates[minIdx], minDd] }],
        },
        emphasis: { disabled: true },
      },
    ],
  };
}
