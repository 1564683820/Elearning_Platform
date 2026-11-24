// Light green theme — 浅绿色主题，统一简洁
// Monochrome core + green color-block sections, pill CTAs, clean typography

// ─── Green accent palette (theme-wide) ──────────────
export const green = {
  strong: '#2d7d46',
  mid: '#3d7a4e',
  primary: '#5B9E6F',
  soft: '#88c8a0',
  bg: '#e6f7e6',
  bg2: '#d4edda',
  bg3: '#e8f5e9',
} as const;

// ─── Colors ───────────────────────────────────────────
export const colors = {
  // Brand core — green as primary, keep black/white for structure
  primary: green.primary,
  'on-primary': '#ffffff',
  canvas: '#ffffff',
  'inverse-canvas': '#1a2e1a',
  'surface-soft': '#f5f5f5',
  hairline: '#e5e5e5',
  'hairline-soft': '#f0f0f0',
  ink: '#000000',
  'inverse-ink': '#ffffff',
  'on-inverse-soft': 'rgba(255,255,255,0.16)',

  // Pastel color blocks — all green shades only
  'block-lime': green.bg,
  'block-lilac': green.bg2,
  'block-cream': green.bg3,
  'block-mint': '#d1fae5',
  'block-pink': '#dcfce7',
  'block-coral': '#c8e6c9',
  'block-navy': '#1a3d2e',

  // Semantic — keep for UX clarity
  success: green.strong,
  danger: '#dc2626',
  warning: '#d97706',
  info: green.mid,

  // Text
  'text-primary': '#000000',
  'text-secondary': '#6b7280',
  'text-tertiary': '#9ca3af',
  'text-inverse': '#ffffff',

  // Misc
  overlay: 'rgba(0,0,0,0.5)',
} as const;

// ─── Typography ──────────────────────────────────────
export const typography = {
  'display-xl': { fontSize: 42, fontWeight: 340, lineHeight: 1.1, letterSpacing: '-1.2px' },
  'display-lg': { fontSize: 32, fontWeight: 340, lineHeight: 1.15, letterSpacing: '-0.8px' },
  headline: { fontSize: 24, fontWeight: 540, lineHeight: 1.35, letterSpacing: '-0.26px' },
  subhead: { fontSize: 20, fontWeight: 340, lineHeight: 1.35, letterSpacing: '-0.2px' },
  'card-title': { fontSize: 18, fontWeight: 700, lineHeight: 1.4, letterSpacing: '0' },
  body: { fontSize: 15, fontWeight: 400, lineHeight: 1.5, letterSpacing: '0' },
  'body-sm': { fontSize: 13, fontWeight: 400, lineHeight: 1.45, letterSpacing: '0' },
  caption: { fontSize: 11, fontWeight: 500, lineHeight: 1.3, letterSpacing: '0.4px' },
  button: { fontSize: 15, fontWeight: 500, lineHeight: 1.4, letterSpacing: '0' },
  eyebrow: { fontSize: 13, fontWeight: 500, lineHeight: 1.3, letterSpacing: '0.5px' },
} as const;

// ─── Spacing ────────────────────────────────────────
export const space = {
  hair: 1,
  xxs: 4,
  xs: 8,
  sm: 12,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
  section: 64,
} as const;

// ─── Radius ──────────────────────────────────────────
export const radius = {
  sm: 6,
  md: 8,
  lg: 16,
  xl: 24,
  pill: 50,
  full: 9999,
} as const;

// ─── Shadows ──────────────────────────────────────────
export const shadows = {
  none: 'none',
  hairline: `0 0 0 1px ${colors.hairline}`,
  soft: '0 2px 8px rgba(0,0,0,0.06)',
  elevated: '0 4px 16px rgba(0,0,0,0.1)',
  modal: '0 8px 32px rgba(0,0,0,0.15)',
} as const;

// ─── Component Mixins ────────────────────────────────
// These are helper styles to be spread via { ...btnPrimary }

export const btnPrimary: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  gap: 8,
  padding: '10px 24px',
  background: colors.primary,
  color: colors['on-primary'],
  border: 'none',
  borderRadius: radius.pill,
  fontSize: typography.button.fontSize,
  fontWeight: typography.button.fontWeight,
  lineHeight: typography.button.lineHeight,
  cursor: 'pointer',
  transition: 'opacity 0.15s',
  whiteSpace: 'nowrap',
  textDecoration: 'none',
};

export const btnSecondary: React.CSSProperties = {
  ...btnPrimary,
  background: colors.canvas,
  color: colors.ink,
  border: `1px solid ${colors.hairline}`,
};

export const btnDanger: React.CSSProperties = {
  ...btnPrimary,
  background: colors.canvas,
  color: colors.danger,
  border: `1px solid ${colors.danger}30`,
};

export const btnSmall: React.CSSProperties = {
  ...btnPrimary,
  padding: '6px 16px',
  fontSize: 13,
};

export const btnSmallSecondary: React.CSSProperties = {
  ...btnSmall,
  background: colors.canvas,
  color: colors['text-secondary'],
  border: `1px solid ${colors.hairline}`,
};

// ─── Card styles ─────────────────────────────────────
export const cardStyle: React.CSSProperties = {
  background: colors.canvas,
  borderRadius: radius.lg,
  padding: space.lg,
  boxShadow: shadows.soft,
  border: `1px solid ${colors.hairline}`,
};

export const colorBlockLime: React.CSSProperties = {
  background: colors['block-lime'],
  borderRadius: radius.lg,
  padding: space.xxl,
};

export const colorBlockLilac: React.CSSProperties = {
  background: colors['block-lilac'],
  borderRadius: radius.lg,
  padding: space.xxl,
};

export const colorBlockCoral: React.CSSProperties = {
  background: colors['block-coral'],
  borderRadius: radius.lg,
  padding: space.xxl,
};

// ─── Input styles ────────────────────────────────────
export const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '10px 14px',
  border: `1px solid ${colors.hairline}`,
  borderRadius: radius.md,
  fontSize: typography.body.fontSize,
  color: colors['text-primary'],
  background: colors.canvas,
  outline: 'none',
  boxSizing: 'border-box',
  transition: 'border-color 0.15s',
};

export const labelStyle: React.CSSProperties = {
  display: 'block',
  marginBottom: 6,
  fontSize: typography['body-sm'].fontSize,
  fontWeight: 500,
  color: colors['text-secondary'],
  letterSpacing: typography.eyebrow.letterSpacing,
  textTransform: 'uppercase',
};

// ─── Filter chips ────────────────────────────────────
export function chipStyle(active: boolean): React.CSSProperties {
  return {
    padding: '6px 18px',
    borderRadius: radius.pill,
    border: `1px solid ${active ? colors.primary : colors.hairline}`,
    background: active ? colors.primary : colors.canvas,
    color: active ? colors['on-primary'] : colors['text-secondary'],
    cursor: 'pointer',
    fontSize: 13,
    fontWeight: active ? 500 : 400,
    transition: 'all 0.15s',
  };
}

// ─── SVG Icons (inline components) ────────────────────
// Simple SVG icons to replace emoji throughout the app.
// Each is a minimal 16x16 or 20x20 viewBox.

export function IconFile({ size = 16, color = '#000' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10 1H4a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V4l-3-3z" />
      <path d="M10 1v3h3" />
    </svg>
  );
}

export function IconFolder({ size = 16, color = '#000' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1 4a1 1 0 0 1 1-1h4l2 2h5a1 1 0 0 1 1 1v6a1 1 0 0 1-1 1H2a1 1 0 0 1-1-1V4z" />
    </svg>
  );
}

export function IconPlus({ size = 16, color = '#fff' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round">
      <line x1="8" y1="3" x2="8" y2="13" />
      <line x1="3" y1="8" x2="13" y2="8" />
    </svg>
  );
}

export function IconTrash({ size = 16, color = '#dc2626' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 4h12" /><path d="M5 4V2a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" /><path d="M3 4v9a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V4" />
    </svg>
  );
}

export function IconEdit({ size = 16, color = '#000' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M11 1l3 3-9 9H2v-3l9-9z" />
    </svg>
  );
}

export function IconBack({ size = 16, color = '#000' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10 3L5 8l5 5" />
    </svg>
  );
}

export function IconCheck({ size = 16, color = '#2d7d46' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 8l3 3 7-7" />
    </svg>
  );
}

export function IconX({ size = 16, color = '#dc2626' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round">
      <line x1="3" y1="3" x2="13" y2="13" /><line x1="13" y1="3" x2="3" y2="13" />
    </svg>
  );
}

export function IconSearch({ size = 16, color = '#6b7280' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="7" cy="7" r="4" /><path d="M10 10l3 3" />
    </svg>
  );
}

export function IconGrid({ size = 16, color = '#000' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke={color} strokeWidth="1.2" strokeLinecap="round">
      <rect x="1" y="1" width="6" height="6" rx="1" /><rect x="9" y="1" width="6" height="6" rx="1" />
      <rect x="1" y="9" width="6" height="6" rx="1" /><rect x="9" y="9" width="6" height="6" rx="1" />
    </svg>
  );
}

export function IconUsers({ size = 16, color = '#000' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5.5 6a2 2 0 1 0 0-4 2 2 0 0 0 0 4z" /><path d="M1 14v-1a3 3 0 0 1 3-3h3a3 3 0 0 1 3 3v1" />
      <path d="M11 7l2 2 2-2" /><path d="M13 9V1" />
    </svg>
  );
}

export function IconRefresh({ size = 16, color = '#000' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 8a6 6 0 0 1-11.6 2.4" /><path d="M2 8a6 6 0 0 1 11.6-2.4" /><path d="M14 2v4h-4" />
    </svg>
  );
}

export function IconArrowRight({ size = 16, color = '#000' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M6 3l5 5-5 5" />
    </svg>
  );
}

export function IconExternal({ size = 16, color = '#000' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10 1h5v5" /><path d="M15 1L8 8" /><path d="M13 9v4a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h4" />
    </svg>
  );
}

export function IconBook({ size = 16, color = '#000' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke={color} strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 2v12a1 1 0 0 0 1 1h3a2 2 0 0 0 2-2 2 2 0 0 0 2 2h3a1 1 0 0 0 1-1V2a1 1 0 0 0-1-1h-3a2 2 0 0 0-2 2 2 2 0 0 0-2-2H3a1 1 0 0 0-1 1z" />
    </svg>
  );
}

export function IconChart({ size = 16, color = '#000' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="1" y="10" width="3" height="5" rx="0.5" /><rect x="6.5" y="6" width="3" height="9" rx="0.5" /><rect x="12" y="2" width="3" height="13" rx="0.5" />
    </svg>
  );
}

export function IconShield({ size = 16, color = '#000' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke={color} strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M8 1l6 2v4c0 4-3 7-6 8-3-1-6-4-6-8V3l6-2z" />
    </svg>
  );
}

export function IconClock({ size = 16, color = '#000' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="8" cy="8" r="6" /><path d="M8 4.5V8l2.5 1.5" />
    </svg>
  );
}

export function IconDocument({ size = 16, color = '#000' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke={color} strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 1h5l4 4v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1z" /><path d="M9 1v4h4" /><line x1="5" y1="8" x2="11" y2="8" /><line x1="5" y1="11" x2="9" y2="11" />
    </svg>
  );
}

export function IconPpt({ size = 16, color = '#000' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke={color} strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="1" width="12" height="14" rx="1.5" /><path d="M5 5h6" /><path d="M5 8h4" /><path d="M5 11h5" />
    </svg>
  );
}

export function IconGraduation({ size = 16, color = '#000' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke={color} strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M8 2L1 6l7 4 7-4-7-4z" /><path d="M1 6v4" /><path d="M13 8v3a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8" />
    </svg>
  );
}

export function IconSpeaker({ size = 16, color = '#000' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 5.5h2l3-3v11l-3-3H2a1 1 0 0 1-1-1v-3a1 1 0 0 1 1-1z" /><path d="M10 5.5a3 3 0 0 1 0 5" /><path d="M12 3.5a5 5 0 0 1 0 9" />
    </svg>
  );
}

export function IconBulb({ size = 16, color = '#000' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke={color} strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M6 13h4" /><path d="M8 1C5.5 1 3.5 3 3.5 5.5c0 2 1.5 3 2.5 4v1.5h4V9.5c1-1 2.5-2 2.5-4C12.5 3 10.5 1 8 1z" />
    </svg>
  );
}

export function IconMic({ size = 16, color = '#000' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 2.5a3 3 0 0 1 6 0v4a3 3 0 0 1-6 0v-4z" />
      <path d="M2.5 7.5v.5a5.5 5.5 0 0 0 11 0v-.5" />
      <line x1="8" y1="13" x2="8" y2="15" />
      <line x1="5" y1="15" x2="11" y2="15" />
    </svg>
  );
}

export function IconPlay({ size = 16, color = '#000' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 2l10 6-10 6V2z" />
    </svg>
  );
}

export function IconStop({ size = 16, color = '#000' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="10" height="10" rx="1.5" />
    </svg>
  );
}

export function IconPause({ size = 16, color = '#000' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="2" width="3.5" height="12" rx="1" />
      <rect x="9.5" y="2" width="3.5" height="12" rx="1" />
    </svg>
  );
}

export function IconDownload({ size = 16, color = '#2d7d46' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M8 1v10" /><path d="M3 7l5 5 5-5" /><path d="M1 13h14" />
    </svg>
  );
}

export function IconActivity({ size = 16, color = '#000' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1 8h2l2-5 2 10 2-7 2 4 2-2h2" />
    </svg>
  );
}

// ─── Progress bar helper ─────────────────────────────
export function progressBarStyle(percent: number, color = colors.success): React.CSSProperties {
  return {
    height: 8,
    background: colors['surface-soft'],
    borderRadius: radius.pill,
    overflow: 'hidden',
  };
}

export function progressBarFill(percent: number, color = colors.success): React.CSSProperties {
  return {
    height: '100%',
    width: `${Math.min(100, Math.max(0, percent))}%`,
    background: color,
    borderRadius: radius.pill,
    transition: 'width 0.5s ease',
  };
}
