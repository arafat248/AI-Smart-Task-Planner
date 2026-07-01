import {
  LayoutDashboard, CheckSquare, Calendar, Brain, Bell, Settings,
  Tag, FolderOpen, TrendingUp, LogOut, ChevronLeft, ChevronRight,
  CalendarRange, Layers,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { useNotifications } from '../hooks/useNotifications';

export type View =
  | 'dashboard'
  | 'tasks'
  | 'calendar'
  | 'weekly'
  | 'ai-planner'
  | 'analytics'
  | 'categories'
  | 'tags'
  | 'notifications'
  | 'settings'
  | 'architecture';

interface SidebarProps {
  view: View;
  onView: (v: View) => void;
  collapsed: boolean;
  onCollapse: (v: boolean) => void;
}

const NAV = [
  { label: 'Dashboard', icon: LayoutDashboard, view: 'dashboard' as View },
  { label: 'Tasks', icon: CheckSquare, view: 'tasks' as View },
  { label: 'Calendar', icon: Calendar, view: 'calendar' as View },
  { label: 'Weekly Plan', icon: CalendarRange, view: 'weekly' as View },
  { label: 'AI Planner', icon: Brain, view: 'ai-planner' as View },
  { label: 'Analytics', icon: TrendingUp, view: 'analytics' as View },
];

const SECONDARY = [
  { label: 'Categories', icon: FolderOpen, view: 'categories' as View },
  { label: 'Tags', icon: Tag, view: 'tags' as View },
  { label: 'Notifications', icon: Bell, view: 'notifications' as View },
  { label: 'Settings', icon: Settings, view: 'settings' as View },
  { label: 'Architecture', icon: Layers, view: 'architecture' as View },
];

export default function Sidebar({ view, onView, collapsed, onCollapse }: SidebarProps) {
  const { user, profile, signOut } = useAuth();
  const { unreadCount } = useNotifications();

  const initials = (profile?.display_name ?? user?.email ?? '?')
    .split(' ')
    .map((p) => p[0]?.toUpperCase())
    .slice(0, 2)
    .join('');

  return (
    <aside
      className={`relative flex flex-col bg-white border-r border-gray-100 transition-all duration-300 ${
        collapsed ? 'w-[68px]' : 'w-[230px]'
      } min-h-screen shrink-0`}
    >
      {/* Header */}
      <div className="flex items-center gap-3 h-16 px-4 border-b border-gray-100">
        <div className="w-8 h-8 bg-blue-600 rounded-xl flex items-center justify-center shrink-0">
          <Brain size={16} className="text-white" />
        </div>
        {!collapsed && (
          <span className="font-bold text-gray-900 text-base tracking-tight">TaskAI</span>
        )}
      </div>

      {/* Collapse toggle */}
      <button
        onClick={() => onCollapse(!collapsed)}
        className="absolute -right-3 top-[72px] w-6 h-6 bg-white border border-gray-200 rounded-full flex items-center justify-center shadow-sm hover:bg-gray-50 transition-colors z-10"
      >
        {collapsed ? <ChevronRight size={12} /> : <ChevronLeft size={12} />}
      </button>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto scrollbar-thin">
        {NAV.map(({ label, icon: Icon, view: v }) => (
          <button
            key={v}
            onClick={() => onView(v)}
            title={collapsed ? label : undefined}
            className={`sidebar-link w-full ${view === v ? 'active' : ''} ${
              collapsed ? 'justify-center px-2' : ''
            }`}
          >
            <Icon size={18} className="shrink-0" />
            {!collapsed && <span>{label}</span>}
          </button>
        ))}

        <div className={`my-3 border-t border-gray-100 ${collapsed ? 'mx-1' : 'mx-0'}`} />

        {SECONDARY.map(({ label, icon: Icon, view: v }) => (
          <button
            key={v}
            onClick={() => onView(v)}
            title={collapsed ? label : undefined}
            className={`sidebar-link w-full relative ${view === v ? 'active' : ''} ${
              collapsed ? 'justify-center px-2' : ''
            }`}
          >
            <Icon size={18} className="shrink-0" />
            {!collapsed && <span>{label}</span>}
            {v === 'notifications' && unreadCount > 0 && (
              <span className={`${collapsed ? 'absolute -top-0.5 -right-0.5' : 'ml-auto'} min-w-[18px] h-[18px] bg-red-500 text-white text-xs font-bold rounded-full flex items-center justify-center px-1`}>
                {unreadCount > 9 ? '9+' : unreadCount}
              </span>
            )}
          </button>
        ))}
      </nav>

      {/* User section */}
      <div className={`px-3 py-4 border-t border-gray-100 ${collapsed ? 'flex justify-center' : ''}`}>
        {collapsed ? (
          <button
            onClick={signOut}
            title="Sign Out"
            className="w-9 h-9 flex items-center justify-center rounded-xl hover:bg-gray-100 transition-colors"
          >
            <LogOut size={16} className="text-gray-500" />
          </button>
        ) : (
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-blue-700 rounded-lg flex items-center justify-center text-white text-xs font-bold shrink-0">
              {initials}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-semibold text-gray-900 truncate">
                {profile?.display_name ?? 'User'}
              </p>
              <p className="text-xs text-gray-400 truncate">{user?.email}</p>
            </div>
            <button
              onClick={signOut}
              title="Sign Out"
              className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors"
            >
              <LogOut size={14} />
            </button>
          </div>
        )}
      </div>
    </aside>
  );
}
