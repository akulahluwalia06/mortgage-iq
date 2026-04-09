const TICK_STYLE = {
  fill: '#B0A498',
  fontSize: 10,
  fontFamily: 'IBM Plex Mono, monospace',
};

export const GRID_PROPS = {
  strokeDasharray: '2 4',
  stroke: 'rgba(0,0,0,0.06)',
  vertical: false,
};

export const X_AXIS_PROPS = {
  tick: TICK_STYLE,
  tickFormatter: (v) => `Y${v}`,
  axisLine: false,
  tickLine: false,
};

export const Y_AXIS_PROPS = {
  tick: TICK_STYLE,
  tickFormatter: (v) => `$${(v / 1000).toFixed(0)}k`,
  axisLine: false,
  tickLine: false,
};

export const TOOLTIP_CURSOR_BAR  = { fill: 'rgba(0,0,0,0.03)' };
export const TOOLTIP_CURSOR_LINE = { stroke: 'rgba(0,0,0,0.1)' };

export const TOOLTIP_STYLE = {
  background: '#fff',
  border: '1px solid #E0D8CE',
  borderRadius: 6,
  fontSize: 12,
  fontFamily: 'IBM Plex Mono, monospace',
};

export const LEGEND_STYLE = {
  fontSize: 12,
  color: '#7A6E64',
  fontFamily: 'IBM Plex Mono, monospace',
};

export const CHART_COLORS = {
  principal: '#1A3F6F',
  interest:  '#C8102E',
  balance:   '#1A3F6F',
  pie:       ['#C8102E', '#1A3F6F', '#B45309'],
};
