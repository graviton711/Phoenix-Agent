
import React from 'react';
import { ThemeColor } from '../types';

interface AuroraBackgroundProps {
  accentColor: ThemeColor;
}

const AuroraBackground: React.FC<AuroraBackgroundProps> = ({ accentColor }) => {
  const getColorHex = (color: ThemeColor, intensity: number) => {
    switch (color) {
      case 'blue': return intensity === 1 ? 'bg-blue-400' : 'bg-cyan-300';
      case 'purple': return intensity === 1 ? 'bg-purple-400' : 'bg-indigo-300';
      case 'rose': return intensity === 1 ? 'bg-rose-400' : 'bg-pink-300';
      case 'emerald': return intensity === 1 ? 'bg-emerald-400' : 'bg-teal-300';
      case 'amber': return intensity === 1 ? 'bg-amber-400' : 'bg-orange-300';
      default: return 'bg-purple-400';
    }
  };

  return (
    <div className="absolute inset-0 pointer-events-none overflow-hidden opacity-40 dark:opacity-20 transition-opacity duration-1000">
      <div 
        className={`aurora-blob w-[600px] h-[600px] top-[-10%] left-[-10%] ${getColorHex(accentColor, 1)}`}
        style={{ animation: 'aurora-1 15s ease-in-out infinite' }}
      />
      <div 
        className={`aurora-blob w-[500px] h-[500px] bottom-[-10%] right-[-5%] ${getColorHex(accentColor, 2)}`}
        style={{ animation: 'aurora-2 20s ease-in-out infinite' }}
      />
      <div 
        className={`aurora-blob w-[450px] h-[450px] top-[20%] right-[10%] ${getColorHex(accentColor, 1)}`}
        style={{ animation: 'aurora-3 18s ease-in-out infinite' }}
      />
    </div>
  );
};

export default AuroraBackground;
