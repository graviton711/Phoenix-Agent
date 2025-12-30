import React from 'react';
import { ThemeColor } from '../types';
import { getThemeStyles } from '../utils/theme';

interface ConfirmModalProps {
    isOpen: boolean;
    onClose: () => void;
    onConfirm: () => void;
    title: string;
    message: string;
    confirmText?: string;
    cancelText?: string;
    accentColor: ThemeColor;
    isDarkMode: boolean;
    variant?: 'danger' | 'warning' | 'info';
}

const ConfirmModal: React.FC<ConfirmModalProps> = ({
    isOpen,
    onClose,
    onConfirm,
    title,
    message,
    confirmText = 'Confirm',
    cancelText = 'Cancel',
    accentColor,
    isDarkMode,
    variant = 'danger',
}) => {
    if (!isOpen) return null;

    const theme = getThemeStyles(accentColor) as any;

    const getVariantStyles = () => {
        switch (variant) {
            case 'danger':
                return {
                    icon: (
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    ),
                    button: 'bg-red-500 hover:bg-red-600 shadow-red-500/20',
                    border: 'border-red-500/20',
                    bg: 'bg-red-500/10',
                    text: 'text-red-500',
                };
            case 'warning':
                return {
                    icon: (
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    ),
                    button: 'bg-amber-500 hover:bg-amber-600 shadow-amber-500/20',
                    border: 'border-amber-500/20',
                    bg: 'bg-amber-500/10',
                    text: 'text-amber-500',
                };
            default:
                return {
                    icon: (
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    ),
                    button: theme.primary,
                    border: 'border-blue-500/20',
                    bg: 'bg-blue-500/10',
                    text: 'text-blue-500',
                };
        }
    };

    const v = getVariantStyles();

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
            {/* Backdrop */}
            <div
                className="absolute inset-0 bg-black/60 backdrop-blur-md animate-fadeIn"
                onClick={onClose}
            />

            {/* Modal */}
            <div className={`relative w-full max-w-sm rounded-[2.5rem] overflow-hidden shadow-2xl animate-scaleIn border ${isDarkMode ? 'bg-zinc-950/80 border-white/5' : 'bg-white/90 border-black/5'
                }`}>
                <div className="absolute inset-0 bg-gradient-to-b from-white/5 to-transparent pointer-events-none" />

                <div className="p-8">
                    <div className={`w-14 h-14 rounded-2xl flex items-center justify-center mb-6 ${v.bg} ${v.border} border`}>
                        <svg className={`w-7 h-7 ${v.text}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            {v.icon}
                        </svg>
                    </div>

                    <h3 className={`text-2xl font-bold mb-3 tracking-tight ${isDarkMode ? 'text-white' : 'text-zinc-900'}`}>
                        {title}
                    </h3>

                    <p className={`text-[15px] leading-relaxed mb-8 ${isDarkMode ? 'text-zinc-400' : 'text-zinc-500'}`}>
                        {message}
                    </p>

                    <div className="flex flex-col gap-3">
                        <button
                            onClick={onConfirm}
                            className={`w-full py-4 rounded-2xl text-white font-bold tracking-wide transition-all active:scale-95 shadow-lg ${v.button}`}
                        >
                            {confirmText}
                        </button>
                        <button
                            onClick={onClose}
                            className={`w-full py-4 rounded-2xl font-bold tracking-wide transition-all active:scale-95 border ${isDarkMode
                                    ? 'bg-white/5 border-white/10 text-zinc-300 hover:bg-white/10'
                                    : 'bg-black/5 border-black/10 text-zinc-600 hover:bg-black/10'
                                }`}
                        >
                            {cancelText}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default ConfirmModal;
