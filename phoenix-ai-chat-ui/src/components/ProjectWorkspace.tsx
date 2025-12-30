import React, { useMemo } from 'react';
import {
    SandpackProvider,
    SandpackLayout,
    SandpackFileExplorer,
    SandpackCodeEditor,
    SandpackPreview
} from "@codesandbox/sandpack-react";

interface ProjectWorkspaceProps {
    files: Record<string, string>; // Format: { "App.tsx": "code...", "index.html": "code..." }
    projectName: string;
    onClose: () => void;
}

const ProjectWorkspace: React.FC<ProjectWorkspaceProps> = ({ files, projectName, onClose }) => {
    // Convert files to Sandpack format (keys must start with "/")
    const sandpackFiles = useMemo(() => {
        if (!files || Object.keys(files).length === 0) {
            return {
                "/App.tsx": "export default function App() { return <div>No files generated</div>; }",
                "/index.html": "<!DOCTYPE html><html><body><div id='root'></div></body></html>"
            };
        }

        const converted: Record<string, string> = {};
        for (const [filename, content] of Object.entries(files)) {
            // Ensure all keys start with "/"
            const key = filename.startsWith("/") ? filename : `/${filename}`;
            converted[key] = content;
        }
        return converted;
    }, [files]);

    return (
        <div className="fixed inset-0 z-50 flex flex-col bg-gray-900 animate-in fade-in zoom-in-95 duration-200">
            {/* HEADER */}
            <div className="h-12 border-b border-gray-700 flex items-center justify-between px-4 bg-[#1e1e1e]">
                <div className="flex items-center space-x-2">
                    <span className="text-blue-400 font-bold">Phoenix Studio</span>
                    <span className="text-gray-500">/</span>
                    <span className="text-gray-200 font-mono text-sm">{projectName}</span>
                </div>
                <button
                    onClick={onClose}
                    className="text-gray-400 hover:text-white px-3 py-1 rounded hover:bg-red-600 transition-colors"
                >
                    Close Workspace
                </button>
            </div>

            {/* SANDPACK CORE */}
            <div className="flex-1 overflow-hidden">
                <SandpackProvider
                    files={sandpackFiles}
                    theme="dark"
                    template="react"
                    options={{
                        externalResources: ["https://cdn.tailwindcss.com"] // Auto inject Tailwind
                    }}
                >
                    <SandpackLayout className="h-full !rounded-none !border-none">
                        {/* 3 PANELS: Explorer - Editor - Preview */}
                        <SandpackFileExplorer style={{ height: "100%" }} />
                        <SandpackCodeEditor
                            showTabs
                            showLineNumbers
                            showInlineErrors
                            wrapContent
                            closableTabs
                            style={{ height: "100%" }}
                        />
                        <SandpackPreview
                            showNavigator
                            showRefreshButton
                            style={{ height: "100%" }}
                        />
                    </SandpackLayout>
                </SandpackProvider>
            </div>
        </div>
    );
};

export default ProjectWorkspace;

