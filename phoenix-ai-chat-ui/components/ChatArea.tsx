
import React, { useState, useRef, useEffect } from 'react';
import ReactMarkdown, { Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import hljs from 'highlight.js';
import { THEME_PALETTES } from '../constants';
import { ThemeColor, ChatMessage } from '../types';
import { getThemeStyles } from '../utils/theme';

interface ChatAreaProps {
  accentColor: ThemeColor;
  messages: ChatMessage[];
  isLoading: boolean;
  onSendMessage: (message: string) => void;
  onRegenerate?: () => void;
  onCancelStream?: () => void;
}

// Helper to parse content that might be a JSON string
const parseMessageContent = (message: ChatMessage) => {
  let content = message.content;
  let reasoning = message.reasoning || '';

  if (content.trim().startsWith('{') && content.trim().endsWith('}')) {
    try {
      const parsed = JSON.parse(content);
      if (parsed.content || parsed.reasoning) {
        content = parsed.content || '';
        reasoning = parsed.reasoning || '';
      }
    } catch (e) {
      // Keep original
    }
  }
  return { content, reasoning };
};

// Component SearchBlock để hiển thị quá trình tìm kiếm thời gian thực
const SearchBlock: React.FC<{ reasoning: string; isStreaming?: boolean }> = ({ reasoning, isStreaming }) => {
  const [isExpanded, setIsExpanded] = useState(true);

  // Tách dòng linh hoạt (xử lý cả \n thật và escaped \n từ JSON)
  const lines = reasoning.split(/\n|\\n/);
  const links: { url: string; title: string }[] = [];
  const statusLines: string[] = [];

  for (const line of lines) {
    const trimmedLine = line.trim();
    if (trimmedLine.startsWith('LINK:') || trimmedLine.startsWith('FOUND:')) {
      const isFound = trimmedLine.startsWith('FOUND:');
      const parts = trimmedLine.substring(isFound ? 6 : 5).split('|');
      if (parts.length >= 2) {
        const url = parts[0].trim();
        const title = parts.slice(1).join('|').trim();
        if (url && !links.some(l => l.url === url)) {
          links.push({ url, title: title || url });
        }
      }
    } else if (trimmedLine && !trimmedLine.startsWith('>')) {
      statusLines.push(trimmedLine);
    }
  }

  if (statusLines.length === 0 && links.length === 0 && !isStreaming) return null;

  const currentStatus = statusLines[statusLines.length - 1] || 'Đang tìm kiếm...';

  return (
    <div className="mb-6 animate-slideIn">
      <div
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-center gap-3 px-5 py-3 rounded-2xl bg-blue-500/5 border border-blue-500/10 cursor-pointer hover:bg-blue-500/10 transition-all group"
      >
        <span className="text-[11px] font-bold uppercase tracking-widest text-blue-500/80 flex-1">
          {isStreaming ? currentStatus : 'Đã hoàn tất tìm kiếm'}
        </span>
      </div>

      {isExpanded && (links.length > 0 || isStreaming) && (
        <div className="mt-4 ml-4 pl-6 border-l-2 border-blue-500/10 space-y-3 animate-fadeIn">
          {links.map((link, idx) => (
            <div key={idx} className="relative group/link animate-slideIn">
              <div className="flex items-center gap-3">
                <a
                  href={link.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="relative overflow-hidden block px-3 py-1.5 rounded-lg text-[13px] text-zinc-500 hover:text-blue-500 transition-all bg-white/5 border border-transparent hover:border-blue-500/20 truncate max-w-sm"
                >
                  {/* Shimmer/Glint Effect */}
                  {isStreaming && (
                    <div className="absolute inset-0 w-full h-full bg-gradient-to-r from-transparent via-white/10 to-transparent -translate-x-full animate-glint" />
                  )}
                  {link.title || link.url}
                </a>
              </div>
            </div>
          ))}
          {isStreaming && (
            <div className="flex items-center gap-3 p-3 rounded-lg bg-zinc-500/5 border border-dashed border-zinc-500/20 animate-pulse">
              <div className="h-2 w-32 bg-zinc-500/20 rounded-full" />
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// Component ThinkingBlock với hiệu ứng Luxury Glass
const ThinkingBlock: React.FC<{ reasoning: string; isStreaming?: boolean }> = ({ reasoning, isStreaming }) => {
  const [isExpanded, setIsExpanded] = useState(false);

  if (!reasoning && !isStreaming) return null;

  // Detect if this is a Search process
  const isSearch = reasoning.includes('LINK:') || reasoning.includes('FOUND:');

  if (isSearch) {
    return <SearchBlock reasoning={reasoning} isStreaming={isStreaming} />;
  }

  return (
    <div className="mb-5 animate-slideIn">
      <div className="relative group inline-block">
        {/* Shadow Layer */}
        <div className="absolute inset-0 rounded-full shadow-[0_4px_20px_-4px_rgba(0,0,0,0.1)] group-hover:shadow-[0_8px_30px_-4px_rgba(0,0,0,0.15)] transition-all duration-700" />

        {/* Content Layer */}
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="relative z-10 overflow-hidden inline-flex items-center px-6 py-2.5 rounded-full text-[11px] font-black uppercase tracking-[0.2em]
                     bg-white/5 dark:bg-white/5 backdrop-blur-[40px] border border-white/20 dark:border-white/10
                     text-zinc-500 hover:text-zinc-900 dark:hover:text-white transition-all duration-700"
        >
          {/* Luxury Glint Effect */}
          <div className="absolute inset-0 w-full h-full bg-gradient-to-r from-transparent via-white/20 to-transparent -translate-x-full group-hover:animate-glint" />

          <span className={`italic ${isStreaming ? 'animate-pulse' : ''}`}>
            {isStreaming ? 'Thinking is an art...' : (isExpanded ? 'Hide logic' : 'Thinking...')}
          </span>
        </button>
      </div>

      {(isExpanded || (isStreaming && reasoning)) && (
        <div
          className="mt-4 px-7 py-5 rounded-[2rem] text-[13px] leading-loose text-zinc-500/70 dark:text-zinc-400/50 
                     bg-white/5 dark:bg-black/20 backdrop-blur-3xl border border-white/5
                     animate-fadeIn max-w-[95%] shadow-inner italic"
          style={{ opacity: isExpanded ? 1 : 0.6 }}
        >
          {reasoning.split('\n').filter(l => !l.startsWith('LINK:')).join('\n')}
          {isStreaming && <span className="inline-block w-1 h-3 ml-1 bg-zinc-500/20 animate-pulse" />}
        </div>
      )}
    </div>
  );
};

// Component ExecutionBlock (Terminal/Sandbox output)
const ExecutionBlock: React.FC<{ output: string }> = ({ output }) => {
  if (!output) return null;
  return (
    <div className="mb-6 animate-fadeIn">
      <div className="flex items-center gap-2 mb-2 px-4">
        <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
        <span className="text-[10px] font-black uppercase tracking-widest text-emerald-500/70">Execution Result</span>
      </div>
      <div className="bg-zinc-950 rounded-3xl p-6 border border-emerald-500/20 shadow-2xl shadow-emerald-500/5 overflow-hidden">
        <pre className="font-mono text-[13px] leading-relaxed text-emerald-400 overflow-x-auto no-scrollbar whitespace-pre-wrap break-all">
          {output}
        </pre>
      </div>
    </div>
  );
};

// CodeBlock Component
const CodeBlock: React.FC<{ code: string; language?: string }> = ({ code, language }) => {
  const [copied, setCopied] = useState(false);
  const [view, setView] = useState<'code' | 'preview'>('code');
  const codeRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (codeRef.current && view === 'code') {
      hljs.highlightElement(codeRef.current);
    }
  }, [code, language, view]);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) { }
  };

  const isHtml = language?.toLowerCase() === 'html' || language?.toLowerCase() === 'xml';

  return (
    <div className="relative my-6 rounded-[1.5rem] overflow-hidden bg-[#1e1e1e] border border-zinc-800/80 shadow-[0_20px_40px_-10px_rgba(0,0,0,0.4)] group/code">
      <div className="flex items-center justify-between px-5 py-3 bg-[#252526] border-b border-white/5">
        <div className="flex items-center gap-4">
          <div className="flex gap-1.5 mr-2">
            <div className="w-2.5 h-2.5 rounded-full bg-red-500/20 group-hover/code:bg-red-500 transition-colors" />
            <div className="w-2.5 h-2.5 rounded-full bg-amber-500/20 group-hover/code:bg-amber-500 transition-colors" />
            <div className="w-2.5 h-2.5 rounded-full bg-emerald-500/20 group-hover/code:bg-emerald-500 transition-colors" />
          </div>
          {isHtml && (
            <div className="flex bg-black/20 rounded-lg p-0.5">
              <button
                onClick={() => setView('code')}
                className={`px-3 py-1 rounded-md text-[10px] font-bold transition-all ${view === 'code' ? 'bg-white/10 text-white shadow-sm' : 'text-zinc-500 hover:text-zinc-300'}`}
              >
                CODE
              </button>
              <button
                onClick={() => setView('preview')}
                className={`px-3 py-1 rounded-md text-[10px] font-bold transition-all ${view === 'preview' ? 'bg-white/10 text-white shadow-sm' : 'text-zinc-500 hover:text-zinc-300'}`}
              >
                PREVIEW
              </button>
            </div>
          )}
          {!isHtml && <span className="text-[10px] uppercase tracking-[0.2em] text-zinc-500 font-bold">{language || 'text'}</span>}
        </div>
        <button
          onClick={handleCopy}
          className="text-[10px] uppercase tracking-widest text-zinc-500 hover:text-white transition-all font-bold opacity-0 group-hover/code:opacity-100"
        >
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>

      {view === 'code' ? (
        <pre className="!m-0 !p-6 overflow-x-auto no-scrollbar">
          <code ref={codeRef} className={`!bg-transparent !p-0 font-mono text-[13px] leading-relaxed ${language ? `language-${language}` : ''}`}>
            {code}
          </code>
        </pre>
      ) : (
        <div className="w-full h-[400px] overflow-hidden rounded-b-[1.5rem] bg-gradient-to-b from-white to-zinc-50 relative group/preview">
          <iframe
            srcDoc={`
              <!DOCTYPE html>
              <html>
                <head>
                  <style>
                    ::-webkit-scrollbar {
                      width: 8px;
                      height: 8px;
                    }
                    ::-webkit-scrollbar-track {
                      background: transparent;
                    }
                    ::-webkit-scrollbar-thumb {
                      background: rgba(0, 0, 0, 0.1);
                      border-radius: 10px;
                      border: 2px solid transparent;
                      background-clip: content-box;
                    }
                    ::-webkit-scrollbar-thumb:hover {
                      background: rgba(0, 0, 0, 0.2);
                      background-clip: content-box;
                    }
                    body { 
                      margin: 0; 
                      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                    }
                  </style>
                </head>
                <body>${code}</body>
              </html>
            `}
            title="preview"
            className="w-full h-full border-none rounded-b-[1.5rem]"
            sandbox="allow-scripts"
            style={{ colorScheme: 'light' }}
          />
        </div>
      )}
    </div>
  );
};

// Custom Markdown Components
const MarkdownComponents: Components = {
  code({ node, inline, className, children, ...props }: any) {
    const match = /language-(\w+)/.exec(className || '');
    const codeContent = String(children).replace(/\n$/, '');

    return !inline && match ? (
      <CodeBlock language={match[1]} code={codeContent} />
    ) : (
      <code className={`${className} bg-black/10 dark:bg-white/10 px-1.5 py-0.5 rounded text-sm font-mono text-pink-600 dark:text-pink-400`} {...props}>
        {children}
      </code>
    );
  },
  p: ({ children }) => <p className="mb-4 last:mb-0 leading-relaxed">{children}</p>,
  ul: ({ children }) => <ul className="list-disc pl-4 mb-4 space-y-1">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal pl-4 mb-4 space-y-1">{children}</ol>,
  li: ({ children }) => <li className="pl-1 marker:text-zinc-400">{children}</li>,
  h1: ({ children }) => <h1 className="text-2xl font-bold mb-4 mt-6">{children}</h1>,
  h2: ({ children }) => <h2 className="text-xl font-bold mb-3 mt-5">{children}</h2>,
  h3: ({ children }) => <h3 className="text-lg font-bold mb-2 mt-4">{children}</h3>,
  blockquote: ({ children }) => <blockquote className="border-l-2 border-zinc-300 dark:border-zinc-700 pl-4 py-1.5 italic text-zinc-500 dark:text-zinc-400 my-4 bg-zinc-50/50 dark:bg-white/5 rounded-r-lg">{children}</blockquote>,
  a: ({ children, href }) => <a href={href} target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline">{children}</a>,
};

const MessageActions: React.FC<{
  role: 'user' | 'assistant';
  content: string;
  onRegenerate?: () => void;
  showRegenerate?: boolean;
}> = ({ role, content, onRegenerate, showRegenerate }) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) { }
  };

  return (
    <div className={`absolute bottom-[-40px] ${role === 'user' ? 'right-4' : 'left-4'} flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-all duration-300 z-50`}>
      <button
        onClick={handleCopy}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white/10 dark:bg-black/20 backdrop-blur-md border border-white/10 text-[10px] font-bold uppercase tracking-widest text-zinc-500 hover:text-zinc-900 dark:hover:text-white transition-all shadow-sm"
      >
        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
        </svg>
        {copied ? 'Copied' : 'Copy'}
      </button>

      {role === 'assistant' && showRegenerate && onRegenerate && (
        <button
          onClick={onRegenerate}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white/10 dark:bg-black/20 backdrop-blur-md border border-white/10 text-[10px] font-bold uppercase tracking-widest text-zinc-500 hover:text-blue-500 transition-all shadow-sm"
        >
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          Regenerate
        </button>
      )}
    </div>
  );
};

const ChatArea: React.FC<ChatAreaProps> = ({ accentColor, messages, isLoading, onSendMessage, onRegenerate, onCancelStream }) => {
  const [inputValue, setInputValue] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const theme = getThemeStyles(accentColor) as any;
  const isPreset = theme.type === 'preset';

  // Scroll only when a NEW message is added, not on every token update
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length]);

  // Focus input when loading finishes
  useEffect(() => {
    if (!isLoading) {
      inputRef.current?.focus();
    }
  }, [isLoading]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (inputValue.trim() && !isLoading) {
      onSendMessage(inputValue.trim());
      setInputValue('');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const hasMessages = messages.length > 0;

  return (
    <div className="flex-1 flex flex-col items-center justify-between px-8 pt-8 pb-2 h-full relative overflow-hidden bg-transparent">
      <div className="flex-1 flex flex-col w-full max-w-4xl overflow-y-auto no-scrollbar pb-10 px-6">
        {!hasMessages ? (
          <div className="flex-1 flex flex-col items-center justify-center animate-fadeIn group">
            <div
              className={`w-32 h-32 rounded-[3.5rem] flex items-center justify-center shadow-2xl shadow-current/30 mb-10 transition-all duration-1000 group-hover:rotate-[360deg] active:scale-95 animate-float ${theme.type === 'preset' ? theme.primary : ''}`}
              style={theme.type === 'custom' ? theme.primaryStyle : {}}
            >
              <svg className="w-14 h-14 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 18.657A8 8 0 016.343 7.343S7 9 9 10c0-2 .5-5 2.986-7C14 5 16.09 5.777 17.656 7.343A7.975 7.975 0 0120 13a7.975 7.975 0 01-2.343 5.657z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.879 16.121A3 3 0 1012.015 11L11 14H9c0 .768.293 1.536.879 2.121z" />
              </svg>
            </div>
            <h2 className="text-7xl font-bold tracking-tighter sm:text-9xl bg-clip-text text-transparent bg-gradient-to-r from-violet-500 via-fuchsia-500 to-amber-500 text-center animate-titleReveal font-cursive py-4">
              Phoenix
            </h2>
            <p className="text-zinc-500 dark:text-zinc-400 text-lg text-center max-w-lg font-medium mt-6 opacity-60">
              The apex of artificial intelligence, forged for precision and elegance.
            </p>
          </div>
        ) : (
          <div className="flex-1 space-y-8 py-10">
            {messages.map((message, index) => {
              const { content, reasoning } = parseMessageContent(message);

              // Extract Sources if present
              const sourcesRegex = /##\s*(Nguồn tham khảo|Sources)([\s\S]*)/i;
              const globalMatch = content.match(sourcesRegex);

              let mainContent = content;
              let sourcesContent = '';

              if (globalMatch) {
                mainContent = content.substring(0, globalMatch.index).trim();
                sourcesContent = globalMatch[2].trim();
              }

              const isLast = index === messages.length - 1;
              const isStreaming = isLast && isLoading && message.role === 'assistant';

              return (
                <div key={message.id} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'} animate-messageSlideIn w-full`}>
                  <div className={`${message.role === 'user' ? 'max-w-[65%]' : 'max-w-[85%] w-full'}`}>
                    {message.role === 'assistant' && (reasoning || isStreaming) && (
                      <ThinkingBlock reasoning={reasoning} isStreaming={isStreaming} />
                    )}
                    {message.role === 'assistant' && message.executionResult && (
                      <ExecutionBlock output={message.executionResult} />
                    )}
                    <div className="relative group rounded-[2.5rem] mb-6">
                      {/* Action Buttons */}
                      <MessageActions
                        role={message.role as any}
                        content={mainContent}
                        onRegenerate={onRegenerate}
                        showRegenerate={isLast}
                      />

                      {/* LAYER 1: Shadow (Unclipped, Behind) */}
                      <div className="absolute inset-0 rounded-[2.5rem] shadow-[0_8px_30px_rgb(0,0,0,0.04)] group-hover:shadow-[0_8px_30px_rgb(0,0,0,0.08)] transition-shadow duration-500" />

                      {/* LAYER 2: Visuals - Background, Border & Blur (Strictly Clipped) */}
                      <div className="absolute inset-0 rounded-[2.5rem] overflow-hidden border border-white/20 dark:border-white/5 isolate">
                        {isStreaming && (
                          <div className="absolute -inset-[150%] animate-spin-slow bg-[conic-gradient(from_0deg,transparent_0_340deg,#0ea5e9_360deg)] dark:bg-[conic-gradient(from_0deg,transparent_0_340deg,#fff_360deg)] opacity-60 blur-2xl" />
                        )}
                        <div className={`absolute inset-0 ${message.role === 'user'
                          ? (theme.type === 'preset' ? theme.primary : '')
                          : isStreaming
                            ? 'bg-zinc-100/50 dark:bg-white/5 backdrop-blur-[50px]'
                            : 'bg-zinc-100/80 dark:bg-white/5 backdrop-blur-[50px]'
                          }`}
                          style={message.role === 'user' && theme.type === 'custom' ? theme.primaryStyle : {}}
                        />
                      </div>

                      {/* LAYER 3: Content (Text Only) */}
                      <div
                        className={`relative z-10 ${message.role === 'user' ? 'px-5 py-2.5' : 'px-7 py-4'} text-[14.5px] leading-relaxed ${message.role === 'user' ? 'text-white' : 'text-zinc-900 dark:text-zinc-100'
                          }`}
                      >
                        {message.role === 'assistant' ? (
                          <div className="markdown-content">
                            <ReactMarkdown
                              remarkPlugins={[remarkGfm, remarkMath]}
                              rehypePlugins={[rehypeKatex]}
                              components={MarkdownComponents}
                            >
                              {mainContent + (isStreaming && !sourcesContent ? '▍' : '')}
                            </ReactMarkdown>

                            {/* Collapsible Sources Section */}
                            {(sourcesContent) && (
                              <div className="mt-6 pt-4 border-t border-black/5 dark:border-white/5">
                                <details className="group/sources">
                                  <summary className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-zinc-500 cursor-pointer hover:text-zinc-800 dark:hover:text-zinc-300 transition-colors select-none list-none">
                                    <div className="w-4 h-4 rounded-full bg-blue-500/10 flex items-center justify-center group-open/sources:bg-blue-500/20 text-blue-600 transition-all">
                                      <svg className="w-2.5 h-2.5 transform group-open/sources:rotate-90 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M9 5l7 7-7 7" />
                                      </svg>
                                    </div>
                                    Nguồn tham khảo ({sourcesContent.split('\n').filter(l => l.trim().startsWith('-')).length})
                                  </summary>
                                  <div className="mt-3 pl-2 text-sm text-zinc-600 dark:text-zinc-400 bg-black/5 dark:bg-white/5 rounded-xl p-3">
                                    <ReactMarkdown
                                      remarkPlugins={[remarkGfm, remarkMath]}
                                      rehypePlugins={[rehypeKatex]}
                                      components={MarkdownComponents}
                                    >
                                      {sourcesContent}
                                    </ReactMarkdown>
                                  </div>
                                </details>
                              </div>
                            )}
                          </div>
                        ) : content}
                      </div>

                    </div>
                  </div>
                </div>
              );
            })}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      <div className="w-full max-w-3xl pt-2 animate-slideUp">
        <form onSubmit={handleSubmit} className="relative group mx-auto w-full">
          <div
            className={`absolute -inset-4 rounded-[4rem] bg-gradient-to-r opacity-0 group-focus-within:opacity-20 transition-all duration-1000 blur-[60px] ${theme.type === 'preset' ? theme.glow : ''}`}
            style={theme.type === 'custom' ? theme.glowStyle : {}}
          />
          <div className="relative flex items-end gap-3 p-5 rounded-[4rem] border border-white/20 dark:border-white/5 bg-white/10 dark:bg-black/40 backdrop-blur-[60px] shadow-[0_20px_40px_-12px_rgba(0,0,0,0.12)]">
            <button type="button" className="p-4 text-zinc-500 hover:text-blue-500 transition-all transform hover:scale-110 active:scale-95">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
              </svg>
            </button>
            <textarea
              ref={inputRef}
              rows={1}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Elevate your thoughts..."
              disabled={isLoading}
              className="flex-1 bg-transparent border-none outline-none focus:ring-0 text-zinc-800 dark:text-zinc-100 placeholder-zinc-500/30 py-4 resize-none max-h-48 text-[16px] overflow-hidden"
              style={{ boxShadow: 'none' }}
              onInput={(e) => {
                const target = e.target as HTMLTextAreaElement;
                target.style.height = 'auto';
                target.style.height = `${target.scrollHeight}px`;
              }}
            />
            {/* Cancel Button - Shows when loading */}
            {isLoading && onCancelStream && (
              <button
                type="button"
                onClick={onCancelStream}
                className="p-4 rounded-full bg-red-500 text-white hover:bg-red-600 transition-all shadow-2xl active:scale-90 animate-pulse"
                title="Dừng phản hồi"
              >
                <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            )}
            {/* Submit Button - Shows when not loading */}
            {!isLoading && (
              <button
                type="submit"
                disabled={!inputValue.trim()}
                className={`p-4 rounded-full text-white hover:brightness-125 transition-all shadow-2xl disabled:opacity-5 disabled:grayscale active:scale-90 ${isPreset ? theme.primary : ''}`}
                style={!isPreset ? theme.primaryStyle : {}}
              >
                <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                </svg>
              </button>
            )}
          </div>
        </form>
        <p className="text-[10px] text-zinc-500/30 text-center uppercase tracking-[0.5em] font-black mt-8 mb-4 cursor-default">
          Phoenix AI • Transcendence
        </p>
      </div>
    </div>
  );
};

export default ChatArea;


