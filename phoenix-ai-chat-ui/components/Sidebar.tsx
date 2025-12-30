
import React from 'react';
import { THEME_PALETTES } from '../constants';
import { ThemeColor, ChatSession, UserProfile } from '../types';
import { getThemeStyles } from '../utils/theme';

interface SidebarProps {
  activeChatId: string | null;
  setActiveChatId: (id: string) => void;
  accentColor: ThemeColor;
  sessions: ChatSession[];
  onNewChat: () => void;
  onDeleteSession: (id: string) => void;
  profile: UserProfile | null;
  onOpenProfile: () => void;
  isCollapsed: boolean;
  onToggleCollapse: () => void;
}

const Sidebar: React.FC<SidebarProps> = ({
  activeChatId,
  setActiveChatId,
  accentColor,
  sessions,
  onNewChat,
  onDeleteSession,
  profile,
  onOpenProfile,
  isCollapsed,
  onToggleCollapse
}) => {
  const theme = getThemeStyles(accentColor) as any;
  const isPreset = theme.type === 'preset';

  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Vừa xong';
    if (diffMins < 60) return `${diffMins} phút trước`;
    if (diffHours < 24) return `${diffHours} giờ trước`;
    if (diffDays < 7) return `${diffDays} ngày trước`;
    return date.toLocaleDateString('vi-VN');
  };

  return (
    <aside className={`${isCollapsed ? 'w-20' : 'w-72'} h-full border-r border-zinc-200 dark:border-zinc-800 bg-white/50 dark:bg-zinc-900/50 backdrop-blur-xl flex flex-col transition-all duration-500 relative group/sidebar`}>
      {/* Collapse Toggle Button */}
      <button
        onClick={onToggleCollapse}
        className="absolute -right-3 top-24 w-6 h-6 rounded-full bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 flex items-center justify-center shadow-md z-50 hover:scale-110 transition-all opacity-0 group-hover/sidebar:opacity-100"
      >
        <svg className={`w-3 h-3 text-zinc-500 transition-transform duration-500 ${isCollapsed ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M15 19l-7-7 7-7" />
        </svg>
      </button>

      {/* Brand */}
      <div className={`p-6 flex items-center ${isCollapsed ? 'justify-center' : 'gap-3'}`}>
        <div className="w-10 h-10 rounded-xl flex-shrink-0 flex items-center justify-center shadow-lg shadow-zinc-500/20 bg-gradient-to-br from-violet-500 via-fuchsia-500 to-amber-500">
          <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 18.657A8 8 0 016.343 7.343S7 9 9 10c0-2 .5-5 2.986-7C14 5 16.09 5.777 17.656 7.343A7.975 7.975 0 0120 13a7.975 7.975 0 01-2.343 5.657z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.879 16.121A3 3 0 1012.015 11L11 14H9c0 .768.293 1.536.879 2.121z" />
          </svg>
        </div>
        {!isCollapsed && <h1 className="text-3xl font-bold bg-gradient-to-r from-violet-500 via-fuchsia-500 to-amber-500 bg-clip-text text-transparent font-cursive py-2 whitespace-nowrap overflow-hidden animate-fadeIn">Phoenix AI</h1>}
      </div>

      {/* New Chat Button */}
      <div className="px-4 mb-6">
        <button
          onClick={onNewChat}
          className={`group relative w-full h-12 rounded-xl overflow-hidden shadow-lg transition-all active:scale-95 flex items-center ${isCollapsed ? 'justify-center' : 'px-4'}`}
          title={isCollapsed ? "Đoạn chat mới" : ""}
        >
          <div className="absolute inset-0 bg-gradient-to-r from-violet-600 via-fuchsia-500 to-amber-500 animate-gradient-xy opacity-90 group-hover:opacity-100" />
          <div className="relative flex items-center justify-center gap-2 text-white font-bold text-sm tracking-widest uppercase">
            <svg className="w-5 h-5 flex-shrink-0 transition-transform group-hover:rotate-12 group-hover:scale-110" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-7.714 2.143L11 21l-2.286-6.857L1 12l7.714-2.143L11 3z" />
            </svg>
            {!isCollapsed && <span className="whitespace-nowrap overflow-hidden animate-fadeIn">Đoạn chat mới</span>}
          </div>
        </button>
      </div>

      {/* Chat History */}
      <div className="flex-1 overflow-y-auto px-2 space-y-1 no-scrollbar">
        {!isCollapsed && sessions.length > 0 && (
          <div className="px-4 py-2 text-xs font-semibold text-zinc-500 uppercase tracking-wider animate-fadeIn">
            Gần đây
          </div>
        )}
        {sessions.map((chat) => (
          <div
            key={chat.id}
            className={`group relative w-full text-left rounded-lg transition-all cursor-pointer flex items-center ${isCollapsed ? 'justify-center p-3' : 'px-4 py-3'} 
              ${activeChatId === chat.id
                ? 'bg-zinc-100 dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100'
                : 'hover:bg-zinc-50 dark:hover:bg-zinc-800/50 text-zinc-600 dark:text-zinc-400'
              }`}
            onClick={() => setActiveChatId(chat.id)}
            title={isCollapsed ? chat.title : ""}
          >
            {isCollapsed ? (
              <div className="w-8 h-8 rounded-full bg-zinc-200 dark:bg-zinc-700 flex items-center justify-center text-[10px] font-bold uppercase overflow-hidden">
                {chat.title.substring(0, 2)}
              </div>
            ) : (
              <div className="flex-1 min-w-0 pr-8 animate-fadeIn">
                <div className="text-sm font-medium truncate">{chat.title}</div>
                <div className="text-xs opacity-60 truncate flex items-center justify-between">
                  <span className="truncate">{chat.lastMessage || 'Chưa có tin nhắn'}</span>
                  <span className="text-[10px] ml-2 flex-shrink-0">{formatTimestamp(chat.timestamp)}</span>
                </div>
              </div>
            )}

            {activeChatId === chat.id && (
              <div
                className={`absolute ${isCollapsed ? 'right-1 top-1' : 'right-10 top-1/2 -translate-y-1/2'} w-1.5 h-1.5 rounded-full ${isPreset ? theme.primary : ''}`}
                style={!isPreset ? theme.primaryStyle : {}}
              />
            )}

            {!isCollapsed && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDeleteSession(chat.id);
                }}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-zinc-200 dark:hover:bg-zinc-700 transition-all animate-fadeIn"
                title="Xóa đoạn chat"
              >
                <svg className="w-4 h-4 text-zinc-500 hover:text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            )}
          </div>
        ))}

        {sessions.length === 0 && !isCollapsed && (
          <div className="px-4 py-8 text-center text-zinc-400 text-sm animate-fadeIn">
            Chưa có đoạn chat nào.<br />
            Hãy bắt đầu cuộc trò chuyện mới!
          </div>
        )}
      </div>

      {/* Profile Section */}
      <div className="p-4 border-t border-zinc-200 dark:border-zinc-800">
        <div
          onClick={onOpenProfile}
          className={`flex items-center gap-3 p-2 rounded-xl hover:bg-zinc-100 dark:hover:bg-zinc-800 cursor-pointer transition-colors group ${isCollapsed ? 'justify-center' : ''}`}
          title={isCollapsed ? "Cài đặt" : ""}
        >
          <img
            src={profile?.avatar || "https://api.dicebear.com/7.x/avataaars/svg?seed=Felix"}
            alt="User avatar"
            className="w-10 h-10 rounded-full object-cover ring-2 ring-zinc-200 dark:ring-zinc-700 group-hover:ring-blue-500 transition-all flex-shrink-0"
          />
          {!isCollapsed && (
            <>
              <div className="flex-1 min-w-0 animate-fadeIn">
                <p className="text-sm font-semibold truncate text-zinc-900 dark:text-zinc-100">{profile?.name || "Loading..."}</p>
                <p className="text-xs text-zinc-500 truncate">Settings</p>
              </div>
              <button className="text-zinc-400 group-hover:text-blue-500 transition-colors flex-shrink-0 animate-fadeIn">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
              </button>
            </>
          )}
        </div>
      </div>
    </aside>
  );
};

export default Sidebar;
