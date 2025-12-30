
import { THEME_PALETTES } from '../constants';
import { ThemeColor } from '../types';

// Helper to convert hex to RGB
export const hexToRgb = (hex: string): string => {
    // Expand shorthand form (e.g. "03F") to full form (e.g. "0033FF")
    var shorthandRegex = /^#?([a-f\d])([a-f\d])([a-f\d])$/i;
    hex = hex.replace(shorthandRegex, function (m, r, g, b) {
        return r + r + g + g + b + b;
    });

    var result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    return result ? `${parseInt(result[1], 16)} ${parseInt(result[2], 16)} ${parseInt(result[3], 16)}` : '0 0 0';
}

// Get styles (handling both Preset Names and Hex Codes)
export const getThemeStyles = (color: string) => {
    // If it's a preset name (e.g. 'purple')
    if (color in THEME_PALETTES) {
        return {
            type: 'preset',
            ...THEME_PALETTES[color as ThemeColor]
        };
    }

    // If it's a Hex Code (or assume it is)
    const rgb = hexToRgb(color);
    return {
        type: 'custom',
        // We return CSS class-like objects or inline styles
        primaryClass: `bg-[${color}]`, // Tailwind arbitrary value rely on JIT, might be flaky if dynamic. Better to use inline style.
        primaryStyle: { backgroundColor: color },
        secondaryStyle: { color: color },
        glowStyle: { backgroundImage: `linear-gradient(to bottom right, rgba(${rgb}, 0.2), rgba(${rgb}, 0.1))` },
        borderStyle: { borderColor: `rgba(${rgb}, 0.2)` }
    };
};
