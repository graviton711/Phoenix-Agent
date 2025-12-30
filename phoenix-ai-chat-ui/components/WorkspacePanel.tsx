import React, { useState, useMemo, useEffect, useCallback } from 'react';
import { ThemeColor } from '@/types';
import { getThemeStyles } from '@/utils/theme';
import Editor, { loader } from '@monaco-editor/react';

// Pre-load Monaco loader configuration if needed here
// loader.config({ ... });

interface WorkspacePanelProps {
    files: Record<string, string>;
    projectName: string;
    onClose: () => void;
    buildingFiles?: string[];
    accentColor: ThemeColor;
    isDarkMode: boolean;
    onFixError?: (error: string) => void;
}

// ----------------------------------------------------------------------
// 1. Minimalist File Icon (Google Style)
// ----------------------------------------------------------------------
const FileIcon: React.FC<{ filename: string; className?: string }> = ({ filename, className = "w-4 h-4" }) => {
    const ext = filename.split('.').pop()?.toLowerCase() || '';

    // Simplistic, high-contrast colors
    const icons: Record<string, string> = {
        'tsx': '#3178c6', 'ts': '#3178c6',
        'jsx': '#f7df1e', 'js': '#f7df1e',
        'html': '#e34c26', 'css': '#264de4',
        'json': '#cbcb41', 'md': '#083fa1',
    };
    const color = icons[ext] || '#8b8b8b';

    return (
        <span style={{ color }} className={`${className} flex-shrink-0`}>
            {/* Simple dot or generic file icon could go here if valid svg */}
            <svg viewBox="0 0 24 24" fill="currentColor" className="w-full h-full">
                <path d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z" />
            </svg>
        </span>
    );
};

// ----------------------------------------------------------------------
// 2. Data Structures & File Tree Logic
// ----------------------------------------------------------------------
interface TreeNode {
    name: string;
    path: string;
    isFolder: boolean;
    children: TreeNode[];
}

const buildFileTree = (files: Record<string, string>): TreeNode[] => {
    const root: TreeNode[] = [];
    Object.keys(files).forEach(filePath => {
        const parts = filePath.split('/');
        let current = root;
        parts.forEach((part, index) => {
            const isLast = index === parts.length - 1;
            const existingNode = current.find(n => n.name === part);
            if (existingNode) {
                current = existingNode.children;
            } else {
                const newNode: TreeNode = {
                    name: part,
                    path: parts.slice(0, index + 1).join('/'),
                    isFolder: !isLast,
                    children: []
                };
                current.push(newNode);
                current = newNode.children;
            }
        });
    });

    const sortTree = (nodes: TreeNode[]): TreeNode[] => {
        return nodes
            .sort((a, b) => {
                if (a.isFolder && !b.isFolder) return -1;
                if (!a.isFolder && b.isFolder) return 1;
                return a.name.localeCompare(b.name);
            })
            .map(node => ({ ...node, children: sortTree(node.children) }));
    };
    return sortTree(root);
};

// ----------------------------------------------------------------------
// 3. Components
// ----------------------------------------------------------------------

const FileTreeItem: React.FC<{
    node: TreeNode;
    selectedFile: string;
    onSelect: (path: string) => void;
    expandedFolders: Set<string>;
    onToggleFolder: (path: string) => void;
    depth?: number;
    activeColorClass: string;
    isDarkMode: boolean;
}> = ({ node, selectedFile, onSelect, expandedFolders, onToggleFolder, depth = 0, activeColorClass, isDarkMode }) => {
    const isExpanded = expandedFolders.has(node.path);
    const isSelected = selectedFile === node.path;

    return (
        <div>
            <div
                className={`flex items-center gap-2 px-3 py-1.5 cursor-pointer text-[13px] select-none transition-all duration-200 border-l-[3px]
                    ${isSelected
                        ? `bg-black/10 dark:bg-white/10 font-bold text-zinc-900 dark:text-zinc-100`
                        : 'border-transparent text-zinc-600 dark:text-zinc-300 hover:text-zinc-900 dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/5'
                    }`}
                style={{
                    paddingLeft: `${depth * 16 + 12}px`,
                    borderColor: isSelected ? 'currentColor' : 'transparent'
                }}
                onClick={() => node.isFolder ? onToggleFolder(node.path) : onSelect(node.path)}
            >
                {node.isFolder ? (
                    <span className={`text-zinc-400 transition-transform duration-200 ${isExpanded ? 'rotate-90' : ''} text-[10px] mr-1`}>▶</span>
                ) : (
                    <FileIcon filename={node.name} className="w-4 h-4 mr-1" />
                )}
                <span className="truncate">{node.name}</span>
            </div>

            {node.isFolder && isExpanded && (
                <div>
                    {node.children.map(child => (
                        <FileTreeItem
                            key={child.path}
                            node={child}
                            selectedFile={selectedFile}
                            onSelect={onSelect}
                            expandedFolders={expandedFolders}
                            onToggleFolder={onToggleFolder}
                            depth={depth + 1}
                            activeColorClass={activeColorClass}
                            isDarkMode={isDarkMode}
                        />
                    ))}
                </div>
            )}

        </div>
    );
};

import { SandpackProvider, SandpackLayout, SandpackPreview, useSandpackConsole } from "@codesandbox/sandpack-react";
import { atomDark } from "@codesandbox/sandpack-themes";

// Helper to track console errors in real-time
const ConsoleTracker: React.FC<{ onError: (msg: string) => void }> = ({ onError }) => {
    const { logs } = useSandpackConsole({ resetOnPreviewRestart: true });

    useEffect(() => {
        const errorLogs = logs.filter(log => log.method === 'error');
        if (errorLogs.length > 0) {
            const lastLog = errorLogs[errorLogs.length - 1];
            // Safe string conversion
            const msg = lastLog.data?.map(d => (typeof d === 'object' ? JSON.stringify(d) : String(d))).join(' ') || 'Unknown Runtime Error';
            onError(msg);
        }
    }, [logs, onError]);

    return null;
};

const PreviewPanel: React.FC<{
    files: Record<string, string>;
    isDarkMode: boolean;
    onErrorDetected?: (msg: string) => void;
}> = ({ files, isDarkMode, onErrorDetected }) => {
    // Convert files to Sandpack format
    const sandpackFiles = useMemo(() => {
        const mappedFiles: Record<string, any> = {};

        // Check if we have an App.tsx in src/
        const hasSrcApp = Object.keys(files).some(k => k === 'src/App.tsx' || k === '/src/App.tsx');

        Object.entries(files).forEach(([path, content]) => {
            // Ensure path starts with / for Sandpack
            let normalizedPath = path.startsWith('/') ? path : `/${path}`;
            mappedFiles[normalizedPath] = content;

            // If there's src/App.tsx, also map it to /App.tsx to override Sandpack default
            if (normalizedPath === '/src/App.tsx' && hasSrcApp) {
                // Create a re-export at root level
                mappedFiles['/App.tsx'] = `export { default } from './src/App';\nexport * from './src/App';`;
            }
        });

        // Ensure we have an index.tsx that imports from /App.tsx
        if (!mappedFiles['/index.tsx'] && !mappedFiles['/src/index.tsx']) {
            mappedFiles['/index.tsx'] = `import React from 'react';\nimport ReactDOM from 'react-dom/client';\nimport App from './App';\n\nReactDOM.createRoot(document.getElementById('root')!).render(\n  <React.StrictMode>\n    <App />\n  </React.StrictMode>\n);`;
        }

        return mappedFiles;
    }, [files]);

    return (
        <div className="h-full w-full bg-zinc-100 dark:bg-zinc-900 overflow-hidden rounded-md border border-zinc-200 dark:border-zinc-800 shadow-inner">
            <SandpackProvider
                template="react-ts"
                files={sandpackFiles}
                theme={isDarkMode ? atomDark : 'light'}
                options={{
                    externalResources: ["https://cdn.tailwindcss.com"],
                    activeFile: "/App.tsx",
                    visibleFiles: ["/App.tsx"],
                    classes: {
                        "sp-layout": "!h-full !rounded-none !border-none !bg-transparent",
                        "sp-preview": "!h-full",
                        "sp-wrapper": "!h-full",
                    }
                }}
                customSetup={{
                    dependencies: JSON.parse(files['package.json'] || files['/package.json'] || '{}').dependencies
                }}
            >
                <SandpackLayout className="!h-full !block !bg-white dark:!bg-zinc-950">
                    {/* Listen for errors */}
                    {onErrorDetected && <ConsoleTracker onError={onErrorDetected} />}

                    <SandpackPreview
                        showNavigator={false}
                        showOpenInCodeSandbox={false}
                        showRefreshButton={true}
                        className="!h-full"
                    />
                </SandpackLayout>
            </SandpackProvider>
        </div>
    );
};

// ----------------------------------------------------------------------
// 4. Main Panel
// ----------------------------------------------------------------------

const ExplorerToggle: React.FC<{ isCollapsed: boolean; onToggle: () => void; activeColorClass: string }> = ({ isCollapsed, onToggle, activeColorClass }) => {
    return (
        <button
            onClick={onToggle}
            className={`flex items-center justify-center p-2 rounded-xl transition-all duration-300 hover:bg-black/5 dark:hover:bg-white/10 ${isCollapsed ? activeColorClass : 'text-zinc-600 hover:text-zinc-900 dark:text-zinc-300 dark:hover:text-white'}`}
            title={isCollapsed ? "Expand Explorer" : "Collapse Explorer"}
        >
            <svg className={`w-5 h-5 transition-transform duration-500 ${isCollapsed ? '' : 'rotate-180'}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
            </svg>
        </button>
    );
};

const WorkspacePanel: React.FC<WorkspacePanelProps> = ({ files, projectName, onClose, buildingFiles = [], accentColor, isDarkMode, onFixError }) => {
    const theme = getThemeStyles(accentColor) as any;

    // State to catch errors from the preview
    const [capturedError, setCapturedError] = useState<string | null>(null);

    // State
    const [selectedFile, setSelectedFile] = useState<string>('');
    useEffect(() => {
        if (!selectedFile) {
            const keys = Object.keys(files);
            const app = keys.find(k => k.includes('App'));
            if (app) setSelectedFile(app);
            else if (keys.length > 0) setSelectedFile(keys[0]);
        }
    }, [files]);

    const [activeTab, setActiveTab] = useState<'code' | 'preview'>('code');
    const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set(['src', 'components', 'public']));
    const [localFiles, setLocalFiles] = useState(files);

    useEffect(() => { setLocalFiles(files); }, [files]);

    const fileTree = useMemo(() => buildFileTree(localFiles), [localFiles]);

    const handleToggleFolder = (path: string) => {
        setExpandedFolders(prev => {
            const newSet = new Set(prev);
            if (newSet.has(path)) newSet.delete(path);
            else newSet.add(path);
            return newSet;
        });
    };

    const handleSelectFile = (path: string) => {
        setSelectedFile(path);
        // Only switch to code tab if we are in preview
        if (activeTab === 'preview') setActiveTab('code');
    };

    const handleEditorChange = (value: string | undefined) => {
        if (value !== undefined) {
            setLocalFiles(prev => ({ ...prev, [selectedFile]: value }));
        }
    };

    // Resize Logic
    const [explorerWidth, setExplorerWidth] = useState(240);
    const [isResizingExplorer, setIsResizingExplorer] = useState(false);

    const startResizing = useCallback(() => setIsResizingExplorer(true), []);
    const stopResizing = useCallback(() => setIsResizingExplorer(false), []);
    const resize = useCallback((mouseMoveEvent: MouseEvent) => {
        if (isResizingExplorer) {
            setExplorerWidth(prev => {
                const newW = prev + mouseMoveEvent.movementX;
                return Math.max(150, Math.min(newW, 600));
            });
        }
    }, [isResizingExplorer]);

    useEffect(() => {
        if (isResizingExplorer) {
            window.addEventListener('mousemove', resize);
            window.addEventListener('mouseup', stopResizing);
        } else {
            window.removeEventListener('mousemove', resize);
            window.removeEventListener('mouseup', stopResizing);
        }
        return () => {
            window.removeEventListener('mousemove', resize);
            window.removeEventListener('mouseup', stopResizing);
        };
    }, [isResizingExplorer, resize, stopResizing]);

    const activeColorClass = theme.primaryText || 'text-amber-500';

    const handleAutoFix = () => {
        if (!onFixError) return;

        if (capturedError) {
            onFixError(`I found a Runtime Error in the preview:\n"${capturedError}"\n\nPlease analyze the code, identify the cause, and fix it. Return ONLY the modified file(s). Do not rewrite unchanged files.`);
        } else {
            onFixError("Please analyze the current project files for any logical or syntax errors. If found, fix them and return ONLY the modified file(s).");
        }
    };

    return (
        <div className="h-full flex flex-col min-w-0 bg-white/80 dark:bg-black/80 backdrop-blur-xl border-l border-white/20 dark:border-white/5 shadow-2xl relative">

            {/* Header - Minimalist & Clean */}
            <div className="h-16 flex items-center justify-between px-6 border-b border-black/5 dark:border-white/5 flex-shrink-0 bg-white/50 dark:bg-black/20 backdrop-blur-md">
                <div className="flex items-center gap-4">
                    {/* Just the Explorer Toggle, kept clean as requested */}
                    <ExplorerToggle
                        isCollapsed={false}
                        onToggle={() => { }}
                        activeColorClass={activeColorClass}
                    />
                </div>

                {/* Center Tabs - Pill Style */}
                <div className="absolute left-1/2 -translate-x-1/2 flex bg-black/5 dark:bg-white/10 rounded-full p-1 border border-black/5 dark:border-white/5">
                    <button
                        onClick={() => setActiveTab('code')}
                        className={`px-6 py-1.5 rounded-full text-xs font-bold transition-all duration-300 ${activeTab === 'code'
                            ? 'bg-white dark:bg-zinc-800 shadow-sm text-zinc-900 dark:text-white'
                            : 'text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200'}`}
                    >
                        Code
                    </button>
                    <button
                        onClick={() => setActiveTab('preview')}
                        className={`px-6 py-1.5 rounded-full text-xs font-bold transition-all duration-300 ${activeTab === 'preview'
                            ? 'bg-white dark:bg-zinc-800 shadow-sm text-zinc-900 dark:text-white'
                            : 'text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200'}`}
                    >
                        Preview
                    </button>
                </div>

                <div className="flex items-center gap-2">
                    <button
                        onClick={handleAutoFix}
                        className={`w-8 h-8 rounded-full flex items-center justify-center transition-all duration-300 hover:bg-black/5 dark:hover:bg-white/10 bg-transparent ${capturedError ? 'text-red-500 animate-pulse' : 'text-amber-500'}`}
                        title={capturedError ? "Fix Detected Error!" : "Auto Check & Fix"}
                    >
                        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                        </svg>
                    </button>
                    <button
                        onClick={onClose}
                        className="w-8 h-8 rounded-full flex items-center justify-center hover:bg-black/5 dark:hover:bg-white/10 bg-transparent text-zinc-500 dark:text-zinc-400 transition-colors"
                    >
                        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                </div>
            </div>

            {/* Split Body */}
            <div className="flex-1 flex overflow-hidden">
                {/* Explorer Sidebar - Resizable */}
                {activeTab === 'code' && (
                    <div
                        className="flex-shrink-0 flex flex-col border-r border-black/5 dark:border-white/5 bg-zinc-50/50 dark:bg-black/20 backdrop-blur-sm relative"
                        style={{ width: explorerWidth }}
                    >
                        <div className="px-4 py-3 text-[11px] font-bold text-zinc-400 uppercase tracking-wider mb-2 select-none">Explorer</div>
                        <div className="flex-1 px-2 overflow-y-auto">
                            {fileTree.map(node => (
                                <FileTreeItem
                                    key={node.path}
                                    node={node}
                                    selectedFile={selectedFile}
                                    onSelect={handleSelectFile}
                                    expandedFolders={expandedFolders}
                                    onToggleFolder={handleToggleFolder}
                                    isDarkMode={isDarkMode}
                                    activeColorClass={activeColorClass}
                                />
                            ))}
                        </div>
                        {/* Drag Handle */}
                        <div
                            className="absolute top-0 right-0 w-1 h-full cursor-col-resize hover:bg-blue-500/50 transition-colors z-10"
                            onMouseDown={startResizing}
                        />
                    </div>
                )}

                {/* Main Content Area */}
                <div className="flex-1 overflow-hidden relative bg-white dark:bg-[#1e1e1e]">
                    {activeTab === 'code' ? (
                        <div className="h-full w-full flex flex-col">
                            {/* File Name Header inside Editor */}
                            <div className="h-9 flex items-center px-4 border-b border-zinc-200 dark:border-zinc-800 bg-white dark:bg-[#1e1e1e] flex-shrink-0">
                                <FileIcon filename={selectedFile} className="w-3.5 h-3.5 mr-2 opacity-70" />
                                <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400">{selectedFile}</span>
                            </div>

                            <div className="flex-1 relative overflow-hidden">
                                {selectedFile && (
                                    <Editor
                                        height="100%"
                                        language={selectedFile.endsWith('json') ? 'json' : selectedFile.endsWith('css') ? 'css' : selectedFile.endsWith('html') ? 'html' : 'typescript'}
                                        value={localFiles[selectedFile]}
                                        theme={isDarkMode ? 'vs-dark' : 'light'}
                                        onChange={handleEditorChange}
                                        options={{
                                            fontSize: 14,
                                            fontFamily: "'Fira Code', 'Roboto Mono', monospace",
                                            minimap: { enabled: false },
                                            scrollBeyondLastLine: false,
                                            smoothScrolling: true,
                                            cursorBlinking: 'smooth',
                                            cursorSmoothCaretAnimation: 'on',
                                            renderLineHighlight: 'all',
                                            padding: { top: 16, bottom: 16 },
                                            roundedSelection: true,
                                        }}
                                        loading={<div className="p-4 text-zinc-500 font-mono text-xs">Initializing Editor...</div>}
                                    />
                                )}
                            </div>
                        </div>
                    ) : (
                        <div className="h-full w-full bg-zinc-100 dark:bg-zinc-900 p-4">
                            <PreviewPanel files={localFiles} isDarkMode={isDarkMode} onErrorDetected={setCapturedError} />
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default WorkspacePanel;

