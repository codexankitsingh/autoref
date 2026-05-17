'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';

const navItems = [
  { href: '/', icon: '✨', label: 'New Outreach' },
  { href: '/dashboard', icon: '📊', label: 'Dashboard' },
  { href: '/settings', icon: '⚙️', label: 'Settings' },
];

export default function Sidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="sidebar-logo">
          <div className="sidebar-logo-icon">A</div>
          <span className="sidebar-logo-text">AutoRef</span>
        </div>
      </div>

      <nav className="sidebar-nav">
        {navItems.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`sidebar-link ${pathname === item.href ? 'active' : ''}`}
          >
            <span className="sidebar-link-icon">{item.icon}</span>
            {item.label}
          </Link>
        ))}

        {/* Admin link — only for admins */}
        {user?.is_admin && (
          <Link
            href="/admin"
            className={`sidebar-link ${pathname === '/admin' ? 'active' : ''}`}
          >
            <span className="sidebar-link-icon">🛡️</span>
            Admin Panel
          </Link>
        )}
      </nav>

      <div className="sidebar-footer">
        {user && (
          <div className="sidebar-user">
            <div className="sidebar-user-info">
              {user.avatar_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={user.avatar_url}
                  alt={user.name}
                  className="sidebar-user-avatar"
                />
              ) : (
                <div className="sidebar-user-avatar sidebar-user-avatar-placeholder">
                  {user.name.charAt(0).toUpperCase()}
                </div>
              )}
              <div className="sidebar-user-details">
                <div className="sidebar-user-name">{user.name}</div>
                <div className="sidebar-user-email">{user.email}</div>
              </div>
            </div>
            <button
              className="btn btn-sm"
              onClick={logout}
              style={{
                marginTop: '8px',
                width: '100%',
                background: 'rgba(239, 68, 68, 0.1)',
                color: 'var(--accent-danger)',
                border: '1px solid rgba(239, 68, 68, 0.2)',
                fontSize: '12px',
              }}
            >
              🚪 Logout
            </button>
          </div>
        )}
        <span className="sidebar-version" style={{ marginTop: '8px', display: 'block' }}>
          AutoRef v1.0.0
        </span>
      </div>
    </aside>
  );
}
