import React, { useState, useEffect } from 'react';
import { UserProfile } from '../types';

interface ProfileModalProps {
    isOpen: boolean;
    onClose: () => void;
    profile: UserProfile;
    onSave: (profile: UserProfile) => void;
}

const ProfileModal: React.FC<ProfileModalProps> = ({ isOpen, onClose, profile, onSave }) => {
    const [name, setName] = useState(profile.name);
    const [avatar, setAvatar] = useState(profile.avatar);
    const [isSaving, setIsSaving] = useState(false);

    // Update local state when profile prop changes
    useEffect(() => {
        setName(profile.name);
        setAvatar(profile.avatar);
    }, [profile]);

    if (!isOpen) return null;

    const handleSave = async () => {
        setIsSaving(true);
        // Simulate API delay or actual await if passed async function
        await onSave({ ...profile, name, avatar });
        setIsSaving(false);
        onClose();
    };

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
            {/* Backdrop */}
            <div
                className="absolute inset-0 bg-black/60 backdrop-blur-sm transition-opacity"
                onClick={onClose}
            />

            {/* Modal Content */}
            <div className="relative w-full max-w-md bg-white dark:bg-zinc-900 rounded-3xl overflow-hidden shadow-2xl transform transition-all border border-white/20 dark:border-white/10">

                {/* Header */}
                <div className="px-8 py-6 border-b border-zinc-100 dark:border-zinc-800 bg-zinc-50/50 dark:bg-zinc-900/50">
                    <h2 className="text-xl font-bold text-zinc-900 dark:text-white">Profile Settings</h2>
                    <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-1">Customize your persona</p>
                </div>

                {/* Body */}
                <div className="p-8 space-y-6">

                    {/* Avatar Preview */}
                    <div className="flex justify-center">
                        <div className="relative group">
                            <div className="w-24 h-24 rounded-full overflow-hidden border-4 border-white dark:border-zinc-800 shadow-xl">
                                <img
                                    src={avatar || 'https://api.dicebear.com/7.x/avataaars/svg?seed=Generous'}
                                    alt="Avatar"
                                    className="w-full h-full object-cover"
                                />
                            </div>
                            <div className="absolute inset-0 rounded-full border border-black/10 dark:border-white/10" />
                        </div>
                    </div>

                    {/* Name Input */}
                    <div className="space-y-2">
                        <label className="text-xs font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400">Display Name</label>
                        <input
                            type="text"
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            className="w-full px-4 py-3 rounded-xl bg-zinc-50 dark:bg-black/40 border border-zinc-200 dark:border-white/10 text-zinc-900 dark:text-white focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 outline-none transition-all placeholder:text-zinc-400"
                            placeholder="Enter your name..."
                        />
                    </div>

                    {/* Avatar URL Input */}
                    <div className="space-y-2">
                        <label className="text-xs font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400">Avatar URL</label>
                        <input
                            type="text"
                            value={avatar}
                            onChange={(e) => setAvatar(e.target.value)}
                            className="w-full px-4 py-3 rounded-xl bg-zinc-50 dark:bg-black/40 border border-zinc-200 dark:border-white/10 text-zinc-900 dark:text-white focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 outline-none transition-all placeholder:text-zinc-400 text-sm"
                            placeholder="https://..."
                        />
                        <p className="text-[10px] text-zinc-400 dark:text-zinc-500">
                            Tip: Use <a href="https://dicebear.com" target="_blank" rel="noreferrer" className="underline hover:text-blue-500">DiceBear</a> for cute avatars.
                        </p>
                    </div>
                </div>

                {/* Footer */}
                <div className="px-8 py-5 bg-zinc-50 dark:bg-black/20 flex justify-end gap-3 border-t border-zinc-100 dark:border-white/5">
                    <button
                        onClick={onClose}
                        className="px-5 py-2.5 rounded-xl text-sm font-medium text-zinc-600 dark:text-zinc-400 hover:bg-zinc-200 dark:hover:bg-white/5 transition-colors"
                    >
                        Cancel
                    </button>
                    <button
                        onClick={handleSave}
                        disabled={isSaving}
                        className="px-6 py-2.5 rounded-xl text-sm font-bold text-white bg-gradient-to-r from-blue-600 to-indigo-600 hover:shadow-lg hover:shadow-blue-500/30 active:scale-95 transition-all disabled:opacity-70 disabled:cursor-not-allowed"
                    >
                        {isSaving ? 'Saving...' : 'Save Changes'}
                    </button>
                </div>

            </div>
        </div>
    );
};

export default ProfileModal;
