
import React from 'react';
import { ThemeColor } from './types';

export const THEME_PALETTES: Record<ThemeColor, { primary: string; secondary: string; glow: string }> = {
  blue: {
    primary: 'bg-blue-600',
    secondary: 'text-blue-600',
    glow: 'from-blue-500/20 to-cyan-500/20'
  },
  purple: {
    primary: 'bg-purple-600',
    secondary: 'text-purple-600',
    glow: 'from-purple-500/20 to-pink-500/20'
  },
  rose: {
    primary: 'bg-rose-600',
    secondary: 'text-rose-600',
    glow: 'from-rose-500/20 to-orange-500/20'
  },
  emerald: {
    primary: 'bg-emerald-600',
    secondary: 'text-emerald-600',
    glow: 'from-emerald-500/20 to-teal-500/20'
  },
  amber: {
    primary: 'bg-amber-600',
    secondary: 'text-amber-600',
    glow: 'from-amber-500/20 to-yellow-500/20'
  }
};

