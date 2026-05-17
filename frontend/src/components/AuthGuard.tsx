'use client';

import { useAuth } from '@/contexts/AuthContext';
import { useRouter } from 'next/navigation';
import { useEffect } from 'react';

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isApproved, isLoading, user } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [isLoading, isAuthenticated, router]);

  if (isLoading) {
    return (
      <div className="auth-page">
        <div className="auth-card" style={{ textAlign: 'center', padding: '60px 40px' }}>
          <div className="spinner spinner-lg" style={{ margin: '0 auto 16px' }} />
          <p style={{ color: 'var(--text-secondary)' }}>Loading...</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return null; // Will redirect in useEffect
  }

  // Show pending approval message
  if (!isApproved) {
    return (
      <div className="auth-page">
        <div className="auth-card" style={{ textAlign: 'center', maxWidth: '480px' }}>
          <div style={{ fontSize: '64px', marginBottom: '20px' }}>⏳</div>
          <h2 style={{ fontSize: '22px', fontWeight: 700, marginBottom: '12px', color: 'var(--text-primary)' }}>
            Account Pending Approval
          </h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '15px', lineHeight: 1.6, marginBottom: '24px' }}>
            Welcome, <strong>{user?.name}</strong>! Your account has been created but requires admin approval before you can access AutoRef.
          </p>
          <p style={{ color: 'var(--text-tertiary)', fontSize: '13px', marginBottom: '24px' }}>
            You&apos;ll be able to use the platform once an administrator approves your account.
          </p>
          <button className="btn btn-secondary" onClick={() => window.location.reload()}>
            🔄 Check Status
          </button>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
