
import React, { useState } from 'react';
import { THEME_PALETTES } from '../constants';
import { ThemeColor } from '../types';

interface ThemeControlsProps {
  isDarkMode: boolean;
  toggleDarkMode: () => void;
  accentColor: ThemeColor;
  setAccentColor: (color: ThemeColor) => void;
}

const ThemeControls: React.FC<ThemeControlsProps> = ({
  isDarkMode,
  toggleDarkMode,
  accentColor,
  setAccentColor
}) => {
  const [showPalette, setShowPalette] = useState(false);

  return (
    <div className="flex items-center gap-2 bg-white/80 dark:bg-zinc-900/80 backdrop-blur-md p-1.5 rounded-2xl shadow-lg border border-zinc-200 dark:border-zinc-800">
      {/* Palette Trigger */}
      <div className="relative">
        <button
          onClick={() => setShowPalette(!showPalette)}
          className={`p-2 rounded-xl transition-colors ${showPalette ? 'bg-zinc-100 dark:bg-zinc-800' : 'hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-600 dark:text-zinc-400'}`}
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.172-1.172a4 4 0 115.656 5.656L15 13.657M7 14v4" />
          </svg>
        </button>

        {showPalette && (
          <div className="absolute top-full right-0 mt-2 p-3 bg-white dark:bg-zinc-900 rounded-xl shadow-2xl border border-zinc-200 dark:border-zinc-800 flex flex-col gap-3 animate-in fade-in slide-in-from-top-1 w-48">
            <p className="text-xs font-semibold text-zinc-500 uppercase">Chọn màu chủ đạo</p>
            <div className="flex items-center gap-3">
              <input
                type="color"
                value={accentColor.startsWith('#') ? accentColor : '#9333ea'} // Fallback if preset
                onChange={(e) => setAccentColor(e.target.value)}
                className="w-10 h-10 rounded cursor-pointer border-0 p-0 overflow-hidden"
              />
              <span className="text-xs font-mono text-zinc-600 dark:text-zinc-400">{accentColor}</span>
            </div>

            <div className="grid grid-cols-5 gap-1 pt-2 border-t border-zinc-100 dark:border-zinc-800">
              {/* Quick Presets */}
              {Object.keys(THEME_PALETTES).map((color) => (
                <button
                  key={color}
                  onClick={() => setAccentColor(color)}
                  className={`w-6 h-6 rounded-full ${THEME_PALETTES[color as keyof typeof THEME_PALETTES].primary} hover:scale-110 transition-transform`}
                  title={color}
                />
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="w-px h-6 bg-zinc-200 dark:bg-zinc-800 mx-1" />

      {/* Dark Mode Toggle */}
      <button
        onClick={toggleDarkMode}
        className="p-2 rounded-xl hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-600 dark:text-zinc-400 transition-colors"
      >
        {isDarkMode ? (
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
          </svg>
        ) : (
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
          </svg>
        )}
      </button>
    </div>
  );
};

export default ThemeControls;
