import React from 'react';
import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { TOOLTIP_STYLE, LEGEND_STYLE, CHART_COLORS } from './chartConfig';

const CAD = (n) =>
  new Intl.NumberFormat('en-CA', { style: 'currency', currency: 'CAD', maximumFractionDigits: 0 }).format(n);

export default function CostBreakdownChart({ data }) {
  return (
    <div className="chart-wrap pie-wrap">
      <h4>Total Cost Breakdown</h4>
      <ResponsiveContainer width="100%" height={290}>
        <PieChart>
          <Pie
            data={data} cx="50%" cy="50%"
            innerRadius={72} outerRadius={112}
            paddingAngle={3} dataKey="value" strokeWidth={0}
          >
            {data.map((_, i) => (
              <Cell key={i} fill={CHART_COLORS.pie[i]} />
            ))}
          </Pie>
          <Tooltip
            formatter={(v) => CAD(v)}
            contentStyle={TOOLTIP_STYLE}
          />
          <Legend
            formatter={(v, e) => `${v}: ${CAD(e.payload.value)}`}
            wrapperStyle={LEGEND_STYLE}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
