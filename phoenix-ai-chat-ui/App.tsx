
import React, { useState, useRef, useEffect, useCallback } from 'react';
import Sidebar from './components/Sidebar';
import ChatArea from './components/ChatArea';
import AuroraBackground from './components/AuroraBackground';
import ThemeControls from './components/ThemeControls';
import ProfileModal from './components/ProfileModal';
import SplashScreen from './components/SplashScreen';
import WorkspacePanel from './components/WorkspacePanel';
import ProjectBrowser from './components/ProjectBrowser';
import { ThemeColor, ChatSession, ChatMessage, UserProfile } from './types';
import 'highlight.js/styles/atom-one-dark.css';

// API Base URL
const API_BASE = '/api';

const App: React.FC = () => {
  const [isDarkMode, setIsDarkMode] = useState(true);
  const [accentColor, setAccentColor] = useState<ThemeColor>('amber');
  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  const [isAppReady, setIsAppReady] = useState(false);

  // Chat state
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  // Profile state
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [isProfileOpen, setIsProfileOpen] = useState(false);

  // Project Workspace State
  const [showWorkspace, setShowWorkspace] = useState(false);
  const [projectFiles, setProjectFiles] = useState<Record<string, string>>({});
  const [currentProjectName, setCurrentProjectName] = useState("phoenix_app");
  const [buildingFiles, setBuildingFiles] = useState<string[]>([]);
  const [workspaceWidth, setWorkspaceWidth] = useState(70); // Default 70%
  const [isResizing, setIsResizing] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [showProjectBrowser, setShowProjectBrowser] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // 1. Dark Mode Effect
  useEffect(() => {
    if (isDarkMode) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [isDarkMode]);

  // Sidebar auto-collapse effect
  useEffect(() => {
    if (showWorkspace && workspaceWidth > 50) {
      setIsSidebarCollapsed(true);
    } else if (!showWorkspace) {
      setIsSidebarCollapsed(false);
    }
  }, [showWorkspace, workspaceWidth]);

  // 2. Synchronized Initialization
  useEffect(() => {
    const initializeApp = async () => {
      const startTime = Date.now();

      try {
        const [profileRes, sessionsRes] = await Promise.all([
          fetch(`${API_BASE}/profile`),
          fetch(`${API_BASE}/sessions`)
        ]);

        const profileData = await profileRes.json();
        const sessionsData = await sessionsRes.json();

        if (profileData.profile) {
          const prof = profileData.profile;
          setProfile(prof);
          if (prof.isDarkMode !== undefined) setIsDarkMode(prof.isDarkMode);
          if (prof.accentColor) setAccentColor(prof.accentColor);

          if (prof.avatar) {
            await new Promise((resolve) => {
              const img = new Image();
              img.src = prof.avatar;
              img.onload = resolve;
              img.onerror = resolve;
            });
          }
        }

        if (sessionsData.sessions) {
          setSessions(sessionsData.sessions);
        }
      } catch (error) {
        console.error('Initialization failed:', error);
      }

      const elapsed = Date.now() - startTime;
      const remaining = Math.max(0, 1800 - elapsed);
      setTimeout(() => setIsAppReady(true), remaining);
    };

    initializeApp();
  }, []);

  // 3. Helper Functions
  const fetchSessions = async () => {
    try {
      const response = await fetch(`${API_BASE}/sessions`);
      const data = await response.json();
      setSessions(data.sessions || []);
    } catch (error) {
      console.error('Error fetching sessions:', error);
    }
  };

  const fetchSessionMessages = async (sessionId: string) => {
    try {
      const response = await fetch(`${API_BASE}/sessions/${sessionId}`);
      const data = await response.json();
      setMessages(data.session?.messages || []);
    } catch (error) {
      console.error('Error fetching messages:', error);
      setMessages([]);
    }
  };

  const handleNewChat = async () => {
    try {
      const response = await fetch(`${API_BASE}/sessions/new`, { method: 'POST' });
      const data = await response.json();
      const newSession = data.session;
      setSessions(prev => [newSession, ...prev]);
      setActiveChatId(newSession.id);
      setMessages([]);
      // Reset Workspace State
      setShowWorkspace(false);
      setProjectFiles({});
      setCurrentProjectName("phoenix_app");
    } catch (error) {
      console.error('Error creating new chat:', error);
    }
  };

  const handleDeleteSession = async (sessionId: string) => {
    try {
      await fetch(`${API_BASE}/sessions/${sessionId}`, { method: 'DELETE' });
      setSessions(prev => prev.filter(s => s.id !== sessionId));
      if (activeChatId === sessionId) {
        setActiveChatId(null);
        setMessages([]);
        // Reset Workspace State
        setShowWorkspace(false);
        setProjectFiles({});
      }
    } catch (error) {
      console.error('Error deleting session:', error);
    }
  };

  const handleUpdateProfile = async (newProfile: UserProfile) => {
    try {
      setProfile(newProfile);
      await fetch(`${API_BASE}/profile`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newProfile),
      });
    } catch (error) {
      console.error('Error updating profile:', error);
    }
  };

  const handleSendMessage = useCallback(async (content: string, imageUrl?: string, isRegenerate = false) => {
    if (isLoading) return;

    if (!isRegenerate) {
      // Optimistically add user message
      const userMessage: ChatMessage = {
        id: `temp-${Date.now()}`,
        role: 'user',
        content,
        imageUrl,
        timestamp: new Date().toISOString(),
      };
      setMessages(prev => [...prev, userMessage]);
    }

    setIsLoading(true);

    const assistantMessageId = `assistant-temp-${Date.now()}`;
    const assistantPlaceholder: ChatMessage = {
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      reasoning: '',
      timestamp: new Date().toISOString(),
    };
    setMessages(prev => [...prev, assistantPlaceholder]);

    try {
      // Create AbortController for this request
      abortControllerRef.current = new AbortController();
      const signal = abortControllerRef.current.signal;

      const url = new URL(`${API_BASE}/chat/stream`, window.location.origin);
      url.searchParams.append('message', content);
      if (activeChatId) url.searchParams.append('sessionId', activeChatId);


      const response = await fetch(url.toString(), { signal });
      if (!response.body) throw new Error('No response body');

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let assistantContent = '';
      let assistantReasoning = '';
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmedLine = line.trim();
          if (!trimmedLine || !trimmedLine.startsWith('data: ')) continue;
          try {
            const data = JSON.parse(trimmedLine.slice(6));
            if (data.type === 'start' && data.sessionId && !activeChatId) {
              setActiveChatId(data.sessionId);
            } else if (data.type === 'reasoning') {
              assistantReasoning += data.delta;
              setMessages(prev => prev.map(msg =>
                msg.id === assistantMessageId ? { ...msg, reasoning: assistantReasoning } : msg
              ));
            } else if (data.type === 'content') {
              assistantContent += data.delta;
              setMessages(prev => prev.map(msg =>
                msg.id === assistantMessageId ? { ...msg, content: assistantContent } : msg
              ));
            } else if (data.type === 'execution_result') {
              // Only execution results (from Python tool) go here
              setMessages(prev => prev.map(msg =>
                msg.id === assistantMessageId ? { ...msg, executionResult: (msg.executionResult || '') + data.delta } : msg
              ));
            } else if (data.type === 'build_file_progress') {
              // File is being built - show animation
              setBuildingFiles(prev => [...prev, data.filename]);

              // Open workspace if not already open
              if (!showWorkspace) {
                setShowWorkspace(true);
                setCurrentProjectName(data.projectName || 'phoenix_app');
              }

              // Also add partial file content if streaming
              if (data.content) {
                setProjectFiles(prev => ({ ...prev, [data.filename]: data.content }));
              }
            } else if (data.type === 'tool_build_result') {
              // Explicit event for build success
              setProjectFiles(data.files);
              setCurrentProjectName(data.projectName);
              setShowWorkspace(true);
              setBuildingFiles([]); // Clear building state
            } else if (data.type === 'done') {
              if (data.messageId) {
                setMessages(prev => prev.map(msg =>
                  msg.id === assistantMessageId ? { ...msg, id: data.messageId } : msg
                ));
              }
              fetchSessions();
            }
          } catch (e) { }
        }
      }
    } catch (error: any) {
      // Handle abort gracefully
      if (error?.name === 'AbortError') {
        console.log('Request was cancelled');
        setMessages(prev => prev.map(msg =>
          msg.id === assistantMessageId ? { ...msg, content: msg.content + ' *(Đã hủy)*' } : msg
        ));
      } else {
        console.error('Error sending message:', error);
        setMessages(prev => prev.map(msg =>
          msg.id === assistantMessageId ? { ...msg, content: 'Xin lỗi, đã có lỗi kết nối xảy ra.' } : msg
        ));
      }
    } finally {
      abortControllerRef.current = null;
      setIsLoading(false);
    }
  }, [activeChatId, isLoading, showWorkspace]);

  // Cancel stream handler
  const handleCancelStream = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
  }, []);

  // Resize logic
  const startResizing = useCallback(() => setIsResizing(true), []);
  const stopResizing = useCallback(() => setIsResizing(false), []);
  const resize = useCallback((e: MouseEvent) => {
    if (isResizing && containerRef.current) {
      const containerRect = containerRef.current.getBoundingClientRect();
      const relativeX = e.clientX - containerRect.left;
      const newWidth = ((containerRect.width - relativeX) / containerRect.width) * 100;
      if (newWidth > 15 && newWidth < 85) {
        setWorkspaceWidth(newWidth);
      }
    }
  }, [isResizing]);

  useEffect(() => {
    window.addEventListener('mousemove', resize);
    window.addEventListener('mouseup', stopResizing);
    return () => {
      window.removeEventListener('mousemove', resize);
      window.removeEventListener('mouseup', stopResizing);
    };
  }, [resize, stopResizing]);

  const handleRegenerate = useCallback(() => {
    if (isLoading || messages.length < 2) return;

    // Find the last user message
    const userMessages = messages.filter(m => m.role === 'user');
    if (userMessages.length === 0) return;

    const lastUserMsg = userMessages[userMessages.length - 1];

    // Remove the last turn (typically the last assistant message and potentially partial user message if it were different)
    // Here we just slice up to the last user message
    setMessages(prev => {
      let lastUserIndex = -1;
      for (let i = prev.length - 1; i >= 0; i--) {
        if (prev[i].role === 'user') {
          lastUserIndex = i;
          break;
        }
      }
      if (lastUserIndex === -1) return prev;
      return prev.slice(0, lastUserIndex + 1);
    });

    handleSendMessage(lastUserMsg.content, undefined, true);
  }, [messages, isLoading, handleSendMessage]);

  // 4. Effects for State Sync
  useEffect(() => {
    if (activeChatId && !isLoading) {
      fetchSessionMessages(activeChatId);
    } else if (!activeChatId) {
      setMessages([]);
    }
  }, [activeChatId]);

  useEffect(() => {
    if (!profile) return;
    if (profile.isDarkMode === isDarkMode && profile.accentColor === accentColor) return;
    const timer = setTimeout(() => {
      handleUpdateProfile({ ...profile, isDarkMode, accentColor });
    }, 1000);
    return () => clearTimeout(timer);
  }, [isDarkMode, accentColor, profile]);

  const toggleDarkMode = () => setIsDarkMode(!isDarkMode);

  return (
    <>
      {!isAppReady && <SplashScreen />}

      <div className={`flex h-screen w-full overflow-hidden bg-white dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100 transition-all duration-500 relative ${isAppReady ? 'opacity-100 scale-100' : 'opacity-0 scale-[0.98] pointer-events-none'}`}>
        <AuroraBackground accentColor={accentColor} />
        <div className="flex-1 flex relative overflow-hidden bg-white/50 dark:bg-zinc-950 transition-all duration-500">
          <Sidebar
            activeChatId={activeChatId}
            setActiveChatId={setActiveChatId}
            accentColor={accentColor}
            sessions={sessions}
            onNewChat={handleNewChat}
            onDeleteSession={handleDeleteSession}
            profile={profile!}
            onOpenProfile={() => setIsProfileOpen(true)}
            isCollapsed={isSidebarCollapsed}
            onToggleCollapse={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
          />

          {/* Main Content Area - Responsive Split Screen */}
          <div
            ref={containerRef}
            className={`flex-1 flex ${isResizing ? '' : 'transition-all duration-300'} ease-out relative`}
          >
            {/* Chat Area - Shrinks when workspace is open */}
            <main
              className={`flex flex-col relative overflow-hidden flex-shrink-0 min-w-0 ${isResizing ? '' : 'transition-all duration-300'}`}
              style={{ width: showWorkspace ? `${100 - workspaceWidth}%` : '100%' }}
            >
              <div className="absolute top-6 right-6 z-50">
                <ThemeControls
                  isDarkMode={isDarkMode}
                  toggleDarkMode={toggleDarkMode}
                  accentColor={accentColor}
                  setAccentColor={setAccentColor}
                />
              </div>

              <ChatArea
                accentColor={accentColor}
                messages={messages}
                isLoading={isLoading}
                activeChatId={activeChatId}
                onSendMessage={handleSendMessage}
                onRegenerate={handleRegenerate}
                onCancelStream={handleCancelStream}
              />
            </main>

            {/* Resize Handle */}
            {showWorkspace && (
              <div
                onMouseDown={startResizing}
                className={`absolute top-0 bottom-0 w-1.5 cursor-col-resize z-[100] transition-colors hover:bg-white/20 active:bg-white/30`}
                style={{ right: `${workspaceWidth}%` }}
              >
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[1px] h-20 bg-zinc-300 dark:bg-white/20 rounded-full" />
              </div>
            )}

            {/* Workspace Panel - Slides in from right */}
            {showWorkspace && (
              <div
                className={`h-full relative overflow-hidden min-w-0 flex-shrink-0 ${isResizing ? '' : 'transition-all duration-300'}`}
                style={{ width: `${workspaceWidth}%` }}
              >
                <WorkspacePanel
                  files={projectFiles}
                  projectName={currentProjectName}
                  onClose={() => setShowWorkspace(false)}
                  buildingFiles={buildingFiles}
                  accentColor={accentColor}
                  isDarkMode={isDarkMode}
                  onFixError={(err) => handleSendMessage(err)}
                />
              </div>
            )}

            {/* Re-open Bubble for Workspace */}
            {!showWorkspace && projectFiles && Object.keys(projectFiles).length > 0 && (
              <button
                onClick={() => setShowWorkspace(true)}
                className="fixed bottom-6 right-6 w-14 h-14 rounded-full bg-white dark:bg-zinc-800 shadow-2xl border border-zinc-200 dark:border-zinc-700 flex items-center justify-center z-50 hover:scale-110 transition-all duration-300 group hover:rotate-3"
                title="Open Workspace"
              >
                <div className="absolute inset-0 rounded-full opacity-0 group-hover:opacity-100 transition-opacity duration-500 bg-gradient-to-r from-blue-500/20 to-purple-500/20 blur-xl pointer-events-none" />
                <svg className="w-6 h-6 text-zinc-500 dark:text-zinc-400 group-hover:text-blue-500 transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                </svg>
              </button>
            )}
          </div>
        </div>

        {profile && (
          <ProfileModal
            isOpen={isProfileOpen}
            onClose={() => setIsProfileOpen(false)}
            profile={profile}
            onSave={handleUpdateProfile}
          />
        )}

        {/* Project Browser Modal */}
        {showProjectBrowser && (
          <ProjectBrowser
            onOpenProject={(name, files) => {
              setCurrentProjectName(name);
              setProjectFiles(files);
              setShowWorkspace(true);
              setShowProjectBrowser(false);
            }}
            onClose={() => setShowProjectBrowser(false)}
            accentColor={accentColor}
            isDarkMode={isDarkMode}
          />
        )}

        {/* Browse Projects Button */}
        {!showWorkspace && (
          <button
            onClick={() => setShowProjectBrowser(true)}
            className="fixed bottom-6 right-24 w-12 h-12 rounded-full bg-white dark:bg-zinc-800 shadow-xl border border-zinc-200 dark:border-zinc-700 flex items-center justify-center z-40 hover:scale-110 transition-all duration-300 group"
            title="Browse Projects"
          >
            <svg className="w-5 h-5 text-zinc-500 dark:text-zinc-400 group-hover:text-amber-500 transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
            </svg>
          </button>
        )}
      </div>
    </>
  );
};

export default App;
