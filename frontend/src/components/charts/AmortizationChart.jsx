import React from 'react';
import {
  BarChart, Bar, AreaChart, Area,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import ChartTooltip from './ChartTooltip';
import {
  GRID_PROPS, X_AXIS_PROPS, Y_AXIS_PROPS,
  TOOLTIP_CURSOR_BAR, TOOLTIP_CURSOR_LINE,
  LEGEND_STYLE, CHART_COLORS,
} from './chartConfig';

export default function AmortizationChart({ data }) {
  return (
    <>
      <div className="chart-wrap">
        <h4>Annual Principal vs Interest</h4>
        <ResponsiveContainer width="100%" height={250}>
          <BarChart data={data} barSize={12} barGap={2}>
            <CartesianGrid {...GRID_PROPS} />
            <XAxis dataKey="year" {...X_AXIS_PROPS} />
            <YAxis {...Y_AXIS_PROPS} />
            <Tooltip content={<ChartTooltip />} cursor={TOOLTIP_CURSOR_BAR} />
            <Legend wrapperStyle={LEGEND_STYLE} />
            <Bar dataKey="Principal" fill={CHART_COLORS.principal} radius={[3, 3, 0, 0]} opacity={0.9} />
            <Bar dataKey="Interest"  fill={CHART_COLORS.interest}  radius={[3, 3, 0, 0]} opacity={0.9} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="chart-wrap">
        <h4>Remaining Balance</h4>
        <ResponsiveContainer width="100%" height={210}>
          <AreaChart data={data}>
            <defs>
              <linearGradient id="balGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor={CHART_COLORS.balance} stopOpacity={0.2} />
                <stop offset="95%" stopColor={CHART_COLORS.balance} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid {...GRID_PROPS} />
            <XAxis dataKey="year" {...X_AXIS_PROPS} />
            <YAxis {...Y_AXIS_PROPS} />
            <Tooltip content={<ChartTooltip />} cursor={TOOLTIP_CURSOR_LINE} />
            <Area
              type="monotone" dataKey="Balance"
              stroke={CHART_COLORS.balance} fill="url(#balGrad)"
              strokeWidth={2} dot={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </>
  );
}
