'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Sidebar from '@/components/Sidebar';
import AuthGuard from '@/components/AuthGuard';
import { api } from '@/lib/api';

interface ScrapedJob {
  id: number;
  title: string;
  company: string;
  location: string;
  source: string;
  match_score: number | null;
  status: string;
  scraped_at: string;
  job_url: string;
  required_skills: string; // JSON string
}

export default function JobsPage() {
  const router = useRouter();
  const [jobs, setJobs] = useState<ScrapedJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);
  const [minScore, setMinScore] = useState(60);

  useEffect(() => {
    fetchJobs();
  }, [minScore]);

  const fetchJobs = async () => {
    setLoading(true);
    try {
      const data = await api.getJobs(minScore);
      setJobs(data);
    } catch (error) {
      console.error('Failed to fetch jobs:', error);
    } finally {
      setLoading(false);
    }
  };

  const handlePursue = async (id: number) => {
    try {
      await api.pursueJob(id);
      // Remove from list or show success
      setJobs(jobs.filter(j => j.id !== id));
      
      // We could redirect to the "Generate" page with this JD, but for now 
      // just removing it from this view is fine.
    } catch (error) {
      console.error('Failed to pursue job:', error);
      alert('Failed to pursue job');
    }
  };

  const handleTriggerScrape = async () => {
    setTriggering(true);
    try {
      await api.triggerScrape();
      alert('Scrape triggered in background. Check back in a few minutes.');
    } catch (error: any) {
      alert(error.message || 'Failed to trigger scrape');
    } finally {
      setTriggering(false);
    }
  };

  const getScoreColor = (score: number | null) => {
    if (score === null) return '#6b7280';
    if (score >= 80) return '#10b981'; // Green
    if (score >= 60) return '#f59e0b'; // Yellow
    return '#ef4444'; // Red
  };

  return (
    <AuthGuard>
      <div className="app-layout">
        <Sidebar />
        
        <main className="main-content">
          <div className="page-header flex justify-between items-center">
            <div>
              <h1 className="page-title">Job Discovery</h1>
              <p className="page-subtitle">AI-scored jobs from LinkedIn, Indeed, and Glassdoor</p>
            </div>
            <button 
              className="btn btn-secondary" 
              onClick={handleTriggerScrape}
              disabled={triggering}
            >
              {triggering ? 'Triggering...' : 'Force Scrape Now'}
            </button>
          </div>

          <div className="card mb-24">
            <div className="flex items-center gap-16">
              <label className="form-label" style={{ marginBottom: 0 }}>Min Match Score:</label>
              <input 
                type="range" 
                min="0" 
                max="100" 
                step="10"
                value={minScore} 
                onChange={(e) => setMinScore(Number(e.target.value))}
                style={{ width: '200px' }}
              />
              <span className="text-primary font-bold">{minScore}</span>
            </div>
          </div>

          <div className="table-container">
            {loading ? (
              <div className="flex justify-center py-40"><div className="spinner spinner-lg"></div></div>
            ) : jobs.length === 0 ? (
              <div className="empty-state">
                <div className="empty-state-icon">🔍</div>
                <h3 className="empty-state-title">No jobs found</h3>
                <p className="empty-state-text">We couldn't find any jobs matching your criteria. Try lowering the minimum match score or triggering a new scrape.</p>
              </div>
            ) : (
              <table className="table">
                <thead>
                  <tr>
                    <th>Score</th>
                    <th>Role</th>
                    <th>Company</th>
                    <th>Location</th>
                    <th>Source</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((job) => (
                    <tr key={job.id}>
                      <td>
                        <div style={{ 
                          display: 'flex', 
                          alignItems: 'center', 
                          justifyContent: 'center',
                          width: '40px', 
                          height: '40px', 
                          borderRadius: '50%', 
                          background: `${getScoreColor(job.match_score)}20`,
                          color: getScoreColor(job.match_score),
                          fontWeight: 'bold',
                          fontSize: '14px'
                        }}>
                          {job.match_score || '-'}
                        </div>
                      </td>
                      <td>
                        <div style={{ fontWeight: 500 }}>{job.title}</div>
                        <div style={{ fontSize: '12px', color: 'var(--text-tertiary)', marginTop: '4px' }}>
                          {new Date(job.scraped_at).toLocaleDateString()}
                        </div>
                      </td>
                      <td>{job.company}</td>
                      <td>{job.location}</td>
                      <td>
                        <span className="badge badge-draft">{job.source}</span>
                      </td>
                      <td>
                        <div className="flex gap-8">
                          <a href={job.job_url} target="_blank" rel="noopener noreferrer" className="btn btn-secondary btn-sm">
                            View
                          </a>
                          <button 
                            className="btn btn-primary btn-sm"
                            onClick={() => handlePursue(job.id)}
                          >
                            Pursue
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </main>
      </div>
    </AuthGuard>
  );
}
