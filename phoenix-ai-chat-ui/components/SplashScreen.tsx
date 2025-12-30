
import React, { useEffect, useState } from 'react';

interface SplashScreenProps {
  onAnimationEnd?: () => void;
  minDuration?: number;
}

const SplashScreen: React.FC<SplashScreenProps> = ({ 
  onAnimationEnd, 
  minDuration = 1500 
}) => {
  const [isVisible, setIsVisible] = useState(true);
  const [isExiting, setIsExiting] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => {
      setIsExiting(true);
      // Wait for exit animation to complete
      const exitTimer = setTimeout(() => {
        setIsVisible(false);
        if (onAnimationEnd) onAnimationEnd();
      }, 800); // matches CSS duration
      return () => clearTimeout(exitTimer);
    }, minDuration);

    return () => clearTimeout(timer);
  }, [minDuration, onAnimationEnd]);

  if (!isVisible) return null;

  return (
    <div className={`fixed inset-0 z-[9999] flex items-center justify-center bg-white dark:bg-zinc-950 transition-transform duration-700 ease-in-out ${isExiting ? 'translate-y-[-100%]' : 'translate-y-0'}`}>
      <div className="relative flex flex-col items-center">
        {/* Animated Phoenix Logo */}
        <div className="relative w-32 h-32 mb-8 group">
          {/* Outer glow aura */}
          <div className="absolute inset-0 bg-amber-500/20 blur-3xl rounded-full animate-pulse-subtle"></div>
          
          {/* The Phoenix Fire Icon */}
          <div className={`relative z-10 w-full h-full flex items-center justify-center transition-all duration-1000 ${isExiting ? 'scale-75 opacity-0 rotate-12' : 'scale-100 opacity-100 rotate-0'}`}>
             <svg viewBox="0 0 24 24" fill="none" className="w-24 h-24 drop-shadow-[0_0_15px_rgba(245,158,11,0.6)]">
                <path d="M17.657 18.657A8 8 0 016.343 7.343S7 9 9 10c0-2 .5-5 2.986-7C14 5 16.09 5.777 17.656 7.343A7.975 7.975 0 0120 13a7.975 7.975 0 01-2.343 5.657z" 
                      fill="url(#phoenix-gradient)" 
                      className="animate-liquid" />
                <path d="M9.879 16.121A3 3 0 1012.015 11L11 14H9c0 .768.293 1.536.879 2.121z" 
                      fill="white" 
                      className="opacity-90" />
                <defs>
                  <linearGradient id="phoenix-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stopColor="#f59e0b" />
                    <stop offset="100%" stopColor="#ef4444" />
                  </linearGradient>
                </defs>
             </svg>
          </div>

          {/* Luxury Shimmer Effect */}
          <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/10 to-transparent w-[200%] animate-glint -skew-x-12"></div>
        </div>

        {/* Text Loader */}
        <div className="flex flex-col items-center gap-3">
          <h1 className={`text-4xl font-bold tracking-tight text-zinc-900 dark:text-white transition-all duration-700 delay-200 ${isExiting ? 'translate-y-4 opacity-0' : 'translate-y-0 opacity-100'}`}>
            Phoenix <span className="text-amber-500">AI</span>
          </h1>
          
          <div className="flex items-center gap-1.5 h-1">
             <div className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-[bounce_1s_infinite_0ms]"></div>
             <div className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-[bounce_1s_infinite_200ms]"></div>
             <div className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-[bounce_1s_infinite_400ms]"></div>
          </div>
          
          <p className={`text-zinc-500 dark:text-zinc-400 text-sm font-medium tracking-widest uppercase transition-all duration-700 delay-300 ${isExiting ? 'translate-y-4 opacity-0' : 'translate-y-0 opacity-100'}`}>
             Initializing System
          </p>
        </div>
      </div>
    </div>
  );
};

export default SplashScreen;
