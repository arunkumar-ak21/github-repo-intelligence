"use client";

import { cn } from "@/lib/utils";
import { 
  LayoutDashboard, GitBranch, ShieldCheck, Box, Settings, 
  Search, Bell, HelpCircle, Plus, Clock, CheckCircle2, 
  XCircle, MessageSquare, Paperclip, MousePointer2,
  ChevronDown, Filter, LayoutGrid, List
} from "lucide-react";
import React from "react";

export function HeroDashboardMockup({ className }: { className?: string }) {
  return (
    <div 
      className={cn("relative flex h-[550px] w-full overflow-hidden rounded-2xl border border-zinc-200/80 bg-white shadow-2xl backdrop-blur-xl animate-fade-in-up-delay-2", className)}
      style={{
        WebkitMaskImage: "linear-gradient(to bottom, black 60%, transparent 100%)",
        maskImage: "linear-gradient(to bottom, black 60%, transparent 100%)"
      }}
    >
      {/* Sidebar */}
      <div className="flex w-[240px] shrink-0 flex-col border-r border-zinc-200/60 bg-zinc-50 p-4 max-md:hidden">
        {/* Logo */}
        <div className="flex items-center gap-2 px-2 py-2">
          <div className="grid size-7 place-items-center rounded bg-zinc-900 text-xs font-bold text-white">RI</div>
          <span className="font-semibold text-zinc-900">Repo Intelligence</span>
        </div>
        
        {/* Workspaces */}
        <div className="mt-6 flex cursor-pointer items-center justify-between rounded-lg border border-zinc-200 bg-white px-3 py-2 shadow-sm transition-colors hover:bg-zinc-50">
          <div className="flex items-center gap-2">
            <div className="size-6 rounded bg-blue-100 flex items-center justify-center text-[10px] font-bold text-blue-700">M</div>
            <div className="flex flex-col">
              <span className="text-xs font-semibold text-zinc-900">Main Workspace</span>
              <span className="text-[10px] text-zinc-500">Enterprise Plan</span>
            </div>
          </div>
          <ChevronDown className="size-4 text-zinc-400" />
        </div>

        {/* Menu */}
        <div className="mt-8 flex flex-col gap-1">
          <span className="mb-2 px-2 text-xs font-semibold uppercase tracking-wider text-zinc-400">Menu</span>
          <NavItem icon={<LayoutDashboard />} label="Overview" />
          <NavItem icon={<GitBranch />} label="Pipelines" active />
          <NavItem icon={<ShieldCheck />} label="Quality Gates" />
          <NavItem icon={<Box />} label="Dependencies" />
        </div>
        
        <div className="mt-auto flex flex-col gap-1">
           <NavItem icon={<Settings />} label="Settings" />
        </div>
      </div>

      {/* Main Content */}
      <div className="flex flex-1 flex-col bg-white relative">
        {/* Topbar */}
        <div className="flex h-16 shrink-0 items-center justify-between border-b border-zinc-200/60 px-6">
          {/* Search */}
          <div className="flex h-9 w-64 items-center gap-2 rounded-md border border-zinc-200 bg-zinc-50 px-3 text-sm text-zinc-400 shadow-sm transition-colors hover:bg-white hover:border-zinc-300">
            <Search className="size-4" />
            <span>Search repositories...</span>
            <span className="ml-auto flex items-center gap-0.5 text-xs">
              <kbd className="rounded border border-zinc-200 bg-white px-1 font-sans">⌘</kbd>
              <kbd className="rounded border border-zinc-200 bg-white px-1 font-sans">F</kbd>
            </span>
          </div>

          {/* Right actions */}
          <div className="flex items-center gap-4">
            <button className="relative text-zinc-400 hover:text-zinc-600">
              <Bell className="size-5" />
              <span className="absolute top-0 right-0 size-2 rounded-full bg-red-500 border-2 border-white"></span>
            </button>
            <button className="text-zinc-400 hover:text-zinc-600">
              <HelpCircle className="size-5" />
            </button>
            <div className="ml-2 size-8 rounded-full bg-gradient-to-tr from-blue-500 to-purple-500 cursor-pointer shadow-sm"></div>
          </div>
        </div>

        {/* Board Header */}
        <div className="flex shrink-0 items-end justify-between px-6 pt-6 pb-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-zinc-900">Frontend Core</h1>
            <div className="mt-1 flex items-center gap-2 text-sm text-zinc-500">
              <span className="font-medium text-zinc-700">arya-technologies / frontend-core</span>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex -space-x-2">
              <div className="size-8 rounded-full border-2 border-white bg-blue-100 flex items-center justify-center text-xs font-medium text-blue-700">JD</div>
              <div className="size-8 rounded-full border-2 border-white bg-green-100 flex items-center justify-center text-xs font-medium text-green-700">AK</div>
              <div className="size-8 rounded-full border-2 border-white bg-purple-100 flex items-center justify-center text-xs font-medium text-purple-700">SM</div>
            </div>
            <button className="flex items-center gap-2 rounded-md bg-zinc-900 px-3 py-2 text-sm font-medium text-white shadow-sm hover:bg-zinc-800 transition-colors">
              <Plus className="size-4" />
              New Run
            </button>
          </div>
        </div>

        {/* Board Filters */}
        <div className="flex shrink-0 items-center gap-4 border-b border-zinc-200/60 px-6 pb-4 text-sm text-zinc-500">
          <div className="flex cursor-pointer items-center gap-2 font-medium hover:text-zinc-900">
            <List className="size-4" />
            <span>List</span>
          </div>
          <div className="flex cursor-pointer items-center gap-2 text-blue-600 border-b-2 border-blue-600 pb-[17px] -mb-[17px] font-medium">
            <LayoutGrid className="size-4" />
            <span>Board</span>
          </div>
          <div className="ml-auto flex items-center gap-4">
            <div className="flex cursor-pointer items-center gap-1 hover:text-zinc-900"><Filter className="size-4" /> Filter</div>
            <div className="flex cursor-pointer items-center gap-1 hover:text-zinc-900 text-blue-600"><span className="text-zinc-300 mr-2">|</span> Group by: <span className="font-medium text-blue-600">Stage</span></div>
          </div>
        </div>

        {/* Kanban Board */}
        <div className="flex-1 overflow-x-auto overflow-y-hidden bg-zinc-50/50 p-6 pb-0 relative">
          <div className="flex h-full gap-4 pb-4">
            {/* Column 1 */}
            <BoardColumn title="Pending" count={2} color="bg-zinc-300">
              <BoardCard title="Docker Build & Push" tag="DEPLOYMENT" tagColor="bg-zinc-900 text-white" />
              <BoardCard title="End-to-End Tests" tag="TESTING" tagColor="bg-zinc-900 text-white" />
            </BoardColumn>

            {/* Column 2 */}
            <BoardColumn title="Running" count={1} color="bg-blue-500">
              <BoardCard title="Static Analysis (SAST)" tag="SECURITY" tagColor="bg-zinc-900 text-white" progress={68} />
            </BoardColumn>

            {/* Column 3 */}
            <BoardColumn title="Failed" count={1} color="bg-red-500">
              <BoardCard title="Dependency Audit" tag="SECURITY" tagColor="bg-zinc-900 text-white" failed />
            </BoardColumn>

            {/* Column 4 */}
            <BoardColumn title="Completed" count={4} color="bg-emerald-500">
              <BoardCard title="Code Quality Gate" tag="ANALYSIS" tagColor="bg-zinc-900 text-white" progress={100} />
              <BoardCard title="Unit Testing (Jest)" tag="TESTING" tagColor="bg-zinc-900 text-white" progress={100} />
            </BoardColumn>
          </div>
        </div>
      </div>

      {/* FLOATING CARD MOCKUP (The "Interactive" element) */}
      <div className="absolute left-[380px] top-[260px] lg:left-[460px] z-20 w-72 -rotate-[4deg] scale-105 rounded-xl border border-zinc-200/80 bg-white/95 p-5 shadow-[0_20px_50px_-12px_rgba(0,0,0,0.2)] backdrop-blur-xl transition-transform hover:rotate-0 hover:scale-110 hover:shadow-[0_30px_60px_-12px_rgba(0,0,0,0.25)]">
        <div className="flex justify-between items-start mb-3">
           <div className="flex gap-2">
             <span className="rounded bg-zinc-900 px-2.5 py-1 text-[13px] font-medium text-white">Code Quality</span>
           </div>
           <div className="size-7 rounded-md bg-zinc-100 flex items-center justify-center text-zinc-900 shadow-sm border border-zinc-200/50">
             <LayoutGrid className="size-3.5" />
           </div>
        </div>
        <h3 className="mt-2 text-[15px] font-bold text-zinc-900 leading-tight">Autonomous PR Review: Feature/Auth</h3>
        <p className="mt-1.5 text-[13px] text-zinc-500 leading-relaxed">Analyzing 12 changed files for security vulnerabilities and code style violations.</p>
        
        <div className="mt-4 flex flex-col gap-2.5">
           <div className="flex items-center gap-2.5 text-[13px] font-medium text-zinc-600">
              <CheckCircle2 className="size-3.5 text-[#047857]" /> No hardcoded secrets found
           </div>
           <div className="flex items-center gap-2.5 text-[13px] font-medium text-zinc-600">
              <CheckCircle2 className="size-3.5 text-[#047857]" /> Typescript strict mode passed
           </div>
           <div className="flex items-center gap-2.5 text-[13px] font-medium text-zinc-400">
              <span className="size-3.5 rounded-full border-2 border-zinc-200 border-t-blue-500 animate-spin"></span> AST Analysis running...
           </div>
        </div>

        <div className="mt-5 flex items-center justify-between border-t border-zinc-100 pt-3">
          <div className="flex gap-3 text-zinc-400">
            <div className="flex items-center gap-1 text-[13px] font-medium"><MessageSquare className="size-3.5" /> 3</div>
            <div className="flex items-center gap-1 text-[13px] font-medium"><Paperclip className="size-3.5" /> 1</div>
          </div>
          <div className="text-[13px] font-bold text-blue-600">45%</div>
        </div>
        
        {/* Fake Cursor */}
        <div className="absolute -bottom-6 -right-3 z-30 drop-shadow-md">
          <MousePointer2 className="size-7 fill-zinc-900 text-white" />
        </div>
      </div>
    </div>
  );
}

function NavItem({ icon, label, active }: { icon: React.ReactNode; label: string; active?: boolean }) {
  return (
    <div className={cn(
      "flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
      active ? "bg-zinc-900 text-white shadow-sm" : "text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900"
    )}>
      <div className={cn("size-4", active ? "text-white" : "text-zinc-400")}>
        {icon}
      </div>
      {label}
    </div>
  );
}

function BoardColumn({ title, count, color, children }: { title: string; count: number; color: string; children: React.ReactNode }) {
  return (
    <div className="flex w-[300px] shrink-0 flex-col gap-3 rounded-xl bg-zinc-100/80 p-3 shadow-sm border border-zinc-200/50 relative z-0">
      <div className="flex items-center justify-between px-1 mb-1">
        <div className="flex items-center gap-2">
          <div className={cn("size-2.5 rounded-sm", color)}></div>
          <span className="text-sm font-bold text-zinc-800">{title}</span>
        </div>
        <div className="flex h-5 min-w-[20px] items-center justify-center rounded-full bg-zinc-200/80 px-1.5 text-xs font-semibold text-zinc-600">{count}</div>
      </div>
      <div className="flex flex-col gap-3 overflow-y-auto pb-4">
        {children}
        <div className="flex cursor-pointer items-center justify-center rounded-lg border-2 border-dashed border-zinc-200 bg-zinc-50/50 py-2.5 text-sm font-medium text-zinc-500 transition-colors hover:border-zinc-300 hover:bg-zinc-100 hover:text-zinc-700">
          <Plus className="mr-1 size-4" /> Add Step
        </div>
      </div>
    </div>
  );
}

function BoardCard({ title, tag, tagColor, progress, failed }: { title: string; tag: string; tagColor: string; progress?: number; failed?: boolean }) {
  return (
    <div className={cn(
      "flex flex-col gap-3 rounded-xl border bg-white p-4 shadow-sm transition-all hover:shadow-md cursor-pointer",
      failed ? "border-red-200" : "border-zinc-200/80 hover:border-blue-300"
    )}>
      <div className="flex justify-between items-center">
        <span className={cn("rounded-md px-2.5 py-1.5 text-[10px] font-medium tracking-wide uppercase", tagColor)}>{tag}</span>
        {failed && <XCircle className="size-4 text-red-500" />}
      </div>
      <span className="text-[15px] font-bold text-zinc-800 tracking-tight">{title}</span>
      {progress !== undefined && (
        <div className="flex items-center gap-2.5 mt-1">
          <div className="h-1.5 flex-1 rounded-full bg-zinc-100 overflow-hidden">
            <div className={cn("h-full rounded-full", progress === 100 ? "bg-[#10b981]" : "bg-[#3b82f6]")} style={{ width: `${progress}%` }}></div>
          </div>
          <span className="text-xs font-bold text-zinc-500">{progress}%</span>
        </div>
      )}
      {failed && (
        <div className="mt-1 flex items-center gap-2 rounded-md bg-red-50 px-2 py-1.5 text-xs font-medium text-red-600">
           <AlertCircle className="size-3" /> Step failed at dependency resolution.
        </div>
      )}
      <div className="flex items-center justify-between pt-2 border-t border-zinc-50 mt-1">
        <div className="flex gap-3 text-zinc-400">
          <div className="flex items-center gap-1 text-xs font-medium hover:text-zinc-600 transition-colors"><MessageSquare className="size-3" /> {failed ? 2 : 0}</div>
          <div className="flex items-center gap-1 text-xs font-medium hover:text-zinc-600 transition-colors"><Paperclip className="size-3" /> {progress === 100 ? 1 : 0}</div>
        </div>
        <div className="size-5 rounded-full bg-zinc-200 text-[9px] font-bold flex items-center justify-center text-zinc-500">JD</div>
      </div>
    </div>
  );
}

function AlertCircle(props: any) {
  return <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
}
