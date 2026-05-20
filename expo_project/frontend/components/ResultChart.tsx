"use client";

import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  Tooltip,
  Legend,
} from "chart.js";
import { Bar, Line, Pie, Scatter } from "react-chartjs-2";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, BarElement, ArcElement, Tooltip, Legend);

type Props = {
  rows: Record<string, any>[];
  chartType: "bar" | "line" | "pie" | "scatter" | "area";
  labelKey?: string;
  valueKey?: string;
};

export default function ResultChart({ rows, chartType, labelKey: inputLabelKey, valueKey: inputValueKey }: Props) {
  if (!rows.length) return null;
  const keys = Object.keys(rows[0]);
  if (keys.length < 2) return <p className="text-sm text-red-600">Need at least 2 columns for charting.</p>;

  const labelKey = inputLabelKey && keys.includes(inputLabelKey) ? inputLabelKey : keys[0];
  const valueKey = inputValueKey && keys.includes(inputValueKey) ? inputValueKey : keys[1];
  const labels = rows.map((r) => String(r[labelKey]));
  const values = rows.map((r) => Number(r[valueKey]) || 0);

  const neonPalette = [
    "rgba(123,97,255,0.8)",
    "rgba(34,211,238,0.78)",
    "rgba(163,255,18,0.72)",
    "rgba(147,127,255,0.75)",
    "rgba(82,223,244,0.74)",
  ];

  const options = {
    responsive: true,
    plugins: {
      legend: {
        labels: {
          color: "#9CA3AF",
        },
      },
      tooltip: {
        backgroundColor: "rgba(17,24,39,0.98)",
        borderColor: "rgba(31,41,55,1)",
        borderWidth: 1,
        titleColor: "#E5E7EB",
        bodyColor: "#9CA3AF",
      },
    },
    scales: {
      x: {
        ticks: { color: "#9CA3AF" },
        grid: { color: "rgba(148,163,184,0.12)" },
      },
      y: {
        ticks: { color: "#9CA3AF" },
        grid: { color: "rgba(148,163,184,0.1)" },
      },
    },
  } as const;

  const data = {
    labels,
    datasets: [
      {
        label: valueKey,
        data: values,
        backgroundColor: "rgba(34,211,238,0.22)",
        borderColor: "rgba(123,97,255,1)",
        pointBackgroundColor: "rgba(163,255,18,0.95)",
        pointBorderColor: "rgba(17,24,39,0.95)",
        pointRadius: 4,
        pointHoverRadius: 6,
        borderWidth: 2,
      },
    ],
  };

  if (chartType === "bar") return <Bar data={data} options={options} />;
  if (chartType === "line") return <Line data={data} options={options} />;
  if (chartType === "area") {
    return (
      <Line
        data={{
          ...data,
          datasets: data.datasets.map((dataset) => ({ ...dataset, fill: true })),
        }}
        options={options}
      />
    );
  }
  if (chartType === "pie") {
    return (
      <Pie
        data={{
          labels,
          datasets: [
            {
              label: valueKey,
              data: values,
              backgroundColor: labels.map((_, i) => neonPalette[i % neonPalette.length]),
              borderColor: "rgba(17,24,39,0.95)",
              borderWidth: 1,
            },
          ],
        }}
        options={options}
      />
    );
  }
  return (
    <Scatter
      data={{
        datasets: [
          {
            label: valueKey,
            data: rows.map((r, i) => ({ x: i + 1, y: Number(r[valueKey]) || 0 })),
            backgroundColor: "rgba(123,97,255,0.85)",
            borderColor: "rgba(34,211,238,0.95)",
            pointRadius: 5,
          },
        ],
      }}
      options={options}
    />
  );
}
