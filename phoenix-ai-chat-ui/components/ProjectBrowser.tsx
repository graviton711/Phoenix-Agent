import React, { useState, useEffect } from 'react';
import { ThemeColor } from '@/types';
import { getThemeStyles } from '@/utils/theme';
import ConfirmModal from './ConfirmModal';

interface Project {
    name: string;
    file_count: number;
    created_at: number;
}

interface ProjectBrowserProps {
    onOpenProject: (projectName: string, files: Record<string, string>) => void;
    onClose: () => void;
    accentColor: ThemeColor;
    isDarkMode: boolean;
}

const ProjectBrowser: React.FC<ProjectBrowserProps> = ({ onOpenProject, onClose, accentColor, isDarkMode }) => {
    const [projects, setProjects] = useState<Project[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [loadingProject, setLoadingProject] = useState<string | null>(null);
    const [projectToDelete, setProjectToDelete] = useState<string | null>(null);

    const theme = getThemeStyles(accentColor) as any;

    useEffect(() => {
        fetchProjects();
    }, []);

    const fetchProjects = async () => {
        try {
            const res = await fetch('/api/projects');
            const data = await res.json();
            setProjects(data.projects || []);
            setError(null);
        } catch (e) {
            setError('Failed to load projects');
        } finally {
            setLoading(false);
        }
    };

    const handleOpenProject = async (name: string) => {
        setLoadingProject(name);
        try {
            const res = await fetch(`/api/projects/${name}`);
            if (!res.ok) throw new Error('Project not found');
            const data = await res.json();
            onOpenProject(data.project_name, data.files);
        } catch (e) {
            setError('Failed to load project files');
        } finally {
            setLoadingProject(null);
        }
    };

    const handleDeleteProject = (name: string, e: React.MouseEvent) => {
        e.stopPropagation();
        setProjectToDelete(name);
    };

    const confirmDelete = async () => {
        if (!projectToDelete) return;
        const name = projectToDelete;
        try {
            await fetch(`/api/projects/${name}`, { method: 'DELETE' });
            setProjects(projects.filter(p => p.name !== name));
            setProjectToDelete(null);
        } catch (e) {
            setError('Failed to delete project');
        }
    };

    const formatDate = (timestamp: number) => {
        return new Date(timestamp * 1000).toLocaleDateString('vi-VN', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    };

    return (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className={`w-full max-w-lg rounded-2xl shadow-2xl ${isDarkMode ? 'bg-zinc-900 border border-zinc-800' : 'bg-white border border-zinc-200'}`}>
                {/* Header */}
                <div className="flex items-center justify-between p-4 border-b border-zinc-700/50">
                    <h2 className={`text-lg font-semibold ${isDarkMode ? 'text-white' : 'text-zinc-900'}`}>
                        Built Projects
                    </h2>
                    <button
                        onClick={onClose}
                        className="p-2 rounded-full hover:bg-zinc-700/50 transition-colors"
                    >
                        <svg className="w-5 h-5 text-zinc-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                </div>

                {/* Content */}
                <div className="p-4 max-h-96 overflow-y-auto">
                    {loading ? (
                        <div className="flex items-center justify-center py-8">
                            <div className="animate-spin rounded-full h-8 w-8 border-2 border-zinc-600 border-t-transparent" />
                        </div>
                    ) : error ? (
                        <div className="text-center py-8 text-red-400">{error}</div>
                    ) : projects.length === 0 ? (
                        <div className="text-center py-8 text-zinc-500">
                            No projects yet. Build something!
                        </div>
                    ) : (
                        <div className="space-y-2">
                            {projects.map(project => (
                                <div
                                    key={project.name}
                                    onClick={() => handleOpenProject(project.name)}
                                    className={`group flex items-center justify-between p-3 rounded-xl cursor-pointer transition-all ${isDarkMode
                                        ? 'hover:bg-zinc-800 border border-zinc-800'
                                        : 'hover:bg-zinc-100 border border-zinc-200'
                                        } ${loadingProject === project.name ? 'opacity-50' : ''}`}
                                >
                                    <div className="flex items-center gap-3">
                                        <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${theme.bgLight}`}>
                                            <svg className={`w-5 h-5 ${theme.text}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                                            </svg>
                                        </div>
                                        <div>
                                            <div className={`font-medium ${isDarkMode ? 'text-white' : 'text-zinc-900'}`}>
                                                {project.name}
                                            </div>
                                            <div className="text-xs text-zinc-500">
                                                {project.file_count} files • {formatDate(project.created_at)}
                                            </div>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        {loadingProject === project.name ? (
                                            <div className="animate-spin rounded-full h-5 w-5 border-2 border-zinc-600 border-t-transparent" />
                                        ) : (
                                            <>
                                                <button
                                                    onClick={(e) => handleDeleteProject(project.name, e)}
                                                    className="p-2 rounded-lg opacity-0 group-hover:opacity-100 hover:bg-red-500/20 text-red-400 transition-all"
                                                    title="Delete"
                                                >
                                                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                                    </svg>
                                                </button>
                                                <svg className={`w-5 h-5 ${theme.text}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                                                </svg>
                                            </>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
                <ConfirmModal
                    isOpen={!!projectToDelete}
                    onClose={() => setProjectToDelete(null)}
                    onConfirm={confirmDelete}
                    title="Xóa dự án?"
                    message={`Bạn có chắc muốn xóa vĩnh viễn dự án "${projectToDelete}"? Hành động này sẽ xóa toàn bộ thư mục và không thể hoàn tác.`}
                    confirmText="Xóa vĩnh viễn"
                    cancelText="Hủy"
                    accentColor={accentColor}
                    isDarkMode={isDarkMode}
                />
            </div>
        </div>
    );
};

export default ProjectBrowser;
