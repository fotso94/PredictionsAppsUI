import React, { useState } from 'react';
import { Database, Cloud, Shield, Cpu, HardDrive, Activity, Users, Brain, Lock, Globe, Zap } from 'lucide-react';

const ArchitectureDiagram = () => {
  const [activeLayer, setActiveLayer] = useState('all');

  const layers = {
    client: { name: 'Client Layer', color: 'bg-blue-500' },
    gateway: { name: 'Gateway Layer', color: 'bg-purple-500' },
    application: { name: 'Application Layer', color: 'bg-green-500' },
    data: { name: 'Data Layer', color: 'bg-orange-500' },
    support: { name: 'Support Services', color: 'bg-pink-500' }
  };

  const shouldShow = (layer) => activeLayer === 'all' || activeLayer === layer;

  return (
    <div className="w-full h-full bg-slate-900 text-white p-8 overflow-auto">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold mb-2">Soccer Predictions Platform</h1>
          <p className="text-slate-400">Multi-Profile Cloud Architecture - AWS Production Environment</p>
        </div>

        {/* Layer Filter */}
        <div className="flex gap-2 mb-8 flex-wrap">
          <button
            onClick={() => setActiveLayer('all')}
            className={`px-4 py-2 rounded ${activeLayer === 'all' ? 'bg-slate-600' : 'bg-slate-700'} hover:bg-slate-600 transition-colors`}
          >
            All Layers
          </button>
          {Object.entries(layers).map(([key, layer]) => (
            <button
              key={key}
              onClick={() => setActiveLayer(key)}
              className={`px-4 py-2 rounded ${activeLayer === key ? layer.color : 'bg-slate-700'} hover:opacity-80 transition-opacity`}
            >
              {layer.name}
            </button>
          ))}
        </div>

        {/* Architecture Diagram */}
        <div className="space-y-6">
          
          {/* Client Layer */}
          {shouldShow('client') && (
            <div className="border-2 border-blue-500 rounded-lg p-6 bg-slate-800">
              <div className="flex items-center gap-2 mb-4">
                <Globe className="text-blue-400" />
                <h2 className="text-xl font-bold text-blue-400">Client Layer</h2>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="bg-slate-700 p-4 rounded border-l-4 border-blue-400">
                  <Users className="mb-2" size={20} />
                  <h3 className="font-semibold mb-1">Regular Users</h3>
                  <p className="text-sm text-slate-300">Prediction consumption, personal tracking</p>
                </div>
                <div className="bg-slate-700 p-4 rounded border-l-4 border-purple-400">
                  <Brain className="mb-2" size={20} />
                  <h3 className="font-semibold mb-1">Expert Users</h3>
                  <p className="text-sm text-slate-300">ML review, manual predictions, analytics tools</p>
                </div>
                <div className="bg-slate-700 p-4 rounded border-l-4 border-red-400">
                  <Shield className="mb-2" size={20} />
                  <h3 className="font-semibold mb-1">Admin Users</h3>
                  <p className="text-sm text-slate-300">System management, oversight, approvals</p>
                </div>
              </div>
              <div className="mt-4 bg-slate-700 p-4 rounded">
                <div className="flex items-center gap-2 mb-2">
                  <Cloud size={20} className="text-blue-300" />
                  <span className="font-semibold">React Frontend (S3 + CloudFront)</span>
                </div>
                <p className="text-sm text-slate-300">TypeScript, Vite, Tailwind CSS, React Query</p>
              </div>
            </div>
          )}

          {/* Gateway Layer */}
          {shouldShow('gateway') && (
            <div className="border-2 border-purple-500 rounded-lg p-6 bg-slate-800">
              <div className="flex items-center gap-2 mb-4">
                <Zap className="text-purple-400" />
                <h2 className="text-xl font-bold text-purple-400">Gateway & Load Balancing Layer</h2>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="bg-slate-700 p-4 rounded">
                  <h3 className="font-semibold mb-2">Route 53</h3>
                  <p className="text-sm text-slate-300">DNS routing, health checks, failover</p>
                </div>
                <div className="bg-slate-700 p-4 rounded">
                  <h3 className="font-semibold mb-2">Application Load Balancer</h3>
                  <p className="text-sm text-slate-300">Multi-AZ, SSL termination, path-based routing</p>
                </div>
              </div>
            </div>
          )}

          {/* Application Layer */}
          {shouldShow('application') && (
            <div className="border-2 border-green-500 rounded-lg p-6 bg-slate-800">
              <div className="flex items-center gap-2 mb-4">
                <Cpu className="text-green-400" />
                <h2 className="text-xl font-bold text-green-400">Application Layer (ECS Fargate)</h2>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="bg-slate-700 p-4 rounded border-l-4 border-blue-400">
                  <h3 className="font-semibold mb-2">Public API Service</h3>
                  <p className="text-sm text-slate-300 mb-3">FastAPI - Regular users</p>
                  <div className="text-xs space-y-1 text-slate-400">
                    <div>CPU: 512, RAM: 1GB</div>
                    <div>Instances: 2-10</div>
                    <div>Auto-scale: 70% CPU</div>
                  </div>
                </div>
                <div className="bg-slate-700 p-4 rounded border-l-4 border-purple-400">
                  <h3 className="font-semibold mb-2">Expert API Service</h3>
                  <p className="text-sm text-slate-300 mb-3">FastAPI - Expert tools</p>
                  <div className="text-xs space-y-1 text-slate-400">
                    <div>CPU: 1024, RAM: 2GB</div>
                    <div>Instances: 1-5</div>
                    <div>Auto-scale: 60% CPU</div>
                  </div>
                </div>
                <div className="bg-slate-700 p-4 rounded border-l-4 border-red-400">
                  <h3 className="font-semibold mb-2">Admin API Service</h3>
                  <p className="text-sm text-slate-300 mb-3">FastAPI - Admin ops</p>
                  <div className="text-xs space-y-1 text-slate-400">
                    <div>CPU: 512, RAM: 1GB</div>
                    <div>Instances: 1-3</div>
                    <div>Auto-scale: 50% CPU</div>
                  </div>
                </div>
                <div className="bg-slate-700 p-4 rounded border-l-4 border-green-400">
                  <h3 className="font-semibold mb-2">ML Worker Service</h3>
                  <p className="text-sm text-slate-300 mb-3">Python - Predictions</p>
                  <div className="text-xs space-y-1 text-slate-400">
                    <div>CPU: 2048, RAM: 4GB</div>
                    <div>Instances: 1-8</div>
                    <div>Auto-scale: Queue depth</div>
                  </div>
                </div>
              </div>
              <div className="mt-4 bg-slate-700 p-4 rounded">
                <h3 className="font-semibold mb-2">Hybrid Prediction Engine</h3>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-green-300">ML Baseline:</span> Automated predictions with confidence scores
                  </div>
                  <div>
                    <span className="text-purple-300">Expert Override:</span> Manual review and adjustment system
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Data Layer */}
          {shouldShow('data') && (
            <div className="border-2 border-orange-500 rounded-lg p-6 bg-slate-800">
              <div className="flex items-center gap-2 mb-4">
                <Database className="text-orange-400" />
                <h2 className="text-xl font-bold text-orange-400">Data Layer</h2>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="bg-slate-700 p-4 rounded">
                  <h3 className="font-semibold mb-2">RDS PostgreSQL</h3>
                  <p className="text-sm text-slate-300 mb-2">Primary database - Multi-AZ</p>
                  <ul className="text-xs text-slate-400 space-y-1">
                    <li>• db.r6g.xlarge (4 vCPU, 32GB)</li>
                    <li>• Multi-schema architecture</li>
                    <li>• Read replicas for analytics</li>
                    <li>• Automated backups (30 days)</li>
                  </ul>
                </div>
                <div className="bg-slate-700 p-4 rounded">
                  <h3 className="font-semibold mb-2">ElastiCache Redis</h3>
                  <p className="text-sm text-slate-300 mb-2">Caching layer - Multi-AZ</p>
                  <ul className="text-xs text-slate-400 space-y-1">
                    <li>• Session management</li>
                    <li>• Prediction caching</li>
                    <li>• Expert tools cache</li>
                    <li>• Real-time data</li>
                  </ul>
                </div>
                <div className="bg-slate-700 p-4 rounded">
                  <h3 className="font-semibold mb-2">Amazon SQS</h3>
                  <p className="text-sm text-slate-300 mb-2">Message queuing</p>
                  <ul className="text-xs text-slate-400 space-y-1">
                    <li>• ML job queue</li>
                    <li>• Expert notifications</li>
                    <li>• Async processing</li>
                    <li>• Event distribution</li>
                  </ul>
                </div>
              </div>
            </div>
          )}

          {/* Support Services */}
          {shouldShow('support') && (
            <div className="border-2 border-pink-500 rounded-lg p-6 bg-slate-800">
              <div className="flex items-center gap-2 mb-4">
                <HardDrive className="text-pink-400" />
                <h2 className="text-xl font-bold text-pink-400">Support Services</h2>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="bg-slate-700 p-4 rounded">
                  <h3 className="font-semibold mb-2">S3 Storage</h3>
                  <ul className="text-sm text-slate-300 space-y-1">
                    <li>• ML models</li>
                    <li>• Audit logs</li>
                    <li>• Expert data</li>
                    <li>• User assets</li>
                  </ul>
                </div>
                <div className="bg-slate-700 p-4 rounded">
                  <Activity size={20} className="mb-2" />
                  <h3 className="font-semibold mb-2">CloudWatch</h3>
                  <ul className="text-sm text-slate-300 space-y-1">
                    <li>• Logs aggregation</li>
                    <li>• Performance metrics</li>
                    <li>• Custom dashboards</li>
                    <li>• Alerting</li>
                  </ul>
                </div>
                <div className="bg-slate-700 p-4 rounded">
                  <Lock size={20} className="mb-2" />
                  <h3 className="font-semibold mb-2">Secrets Manager</h3>
                  <ul className="text-sm text-slate-300 space-y-1">
                    <li>• API keys</li>
                    <li>• DB credentials</li>
                    <li>• Encryption keys</li>
                    <li>• Certificates</li>
                  </ul>
                </div>
                <div className="bg-slate-700 p-4 rounded">
                  <Zap size={20} className="mb-2" />
                  <h3 className="font-semibold mb-2">EventBridge</h3>
                  <ul className="text-sm text-slate-300 space-y-1">
                    <li>• Scheduled tasks</li>
                    <li>• Event routing</li>
                    <li>• Workflow triggers</li>
                    <li>• Integration hub</li>
                  </ul>
                </div>
              </div>
            </div>
          )}

          {/* Security & Compliance */}
          <div className="border-2 border-yellow-500 rounded-lg p-6 bg-slate-800">
            <div className="flex items-center gap-2 mb-4">
              <Shield className="text-yellow-400" />
              <h2 className="text-xl font-bold text-yellow-400">Security & Compliance</h2>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="bg-slate-700 p-4 rounded">
                <h3 className="font-semibold mb-2">IAM & RBAC</h3>
                <p className="text-sm text-slate-300">Role-based access control for Expert, Admin, and Regular users</p>
              </div>
              <div className="bg-slate-700 p-4 rounded">
                <h3 className="font-semibold mb-2">VPC Security</h3>
                <p className="text-sm text-slate-300">Private subnets, security groups, network isolation</p>
              </div>
              <div className="bg-slate-700 p-4 rounded">
                <h3 className="font-semibold mb-2">Audit Trail</h3>
                <p className="text-sm text-slate-300">Comprehensive logging of all predictions and user actions</p>
              </div>
            </div>
          </div>

          {/* Data Flow */}
          <div className="border-2 border-cyan-500 rounded-lg p-6 bg-slate-800">
            <div className="flex items-center gap-2 mb-4">
              <Activity className="text-cyan-400" />
              <h2 className="text-xl font-bold text-cyan-400">Prediction Flow</h2>
            </div>
            <div className="space-y-3">
              <div className="flex items-center gap-3 text-sm">
                <div className="bg-green-600 text-white px-3 py-1 rounded">1</div>
                <div>Match data input triggers ML prediction generation</div>
              </div>
              <div className="flex items-center gap-3 text-sm">
                <div className="bg-green-600 text-white px-3 py-1 rounded">2</div>
                <div>ML Engine generates baseline prediction with confidence score</div>
              </div>
              <div className="flex items-center gap-3 text-sm">
                <div className="bg-purple-600 text-white px-3 py-1 rounded">3</div>
                <div>Low confidence predictions routed to Expert review</div>
              </div>
              <div className="flex items-center gap-3 text-sm">
                <div className="bg-purple-600 text-white px-3 py-1 rounded">4</div>
                <div>Expert can accept, modify, or override ML prediction</div>
              </div>
              <div className="flex items-center gap-3 text-sm">
                <div className="bg-red-600 text-white px-3 py-1 rounded">5</div>
                <div>High-stakes matches require Admin approval (optional)</div>
              </div>
              <div className="flex items-center gap-3 text-sm">
                <div className="bg-blue-600 text-white px-3 py-1 rounded">6</div>
                <div>Final prediction published with source attribution and audit trail</div>
              </div>
            </div>
          </div>

          {/* Key Metrics */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="bg-slate-800 border border-slate-700 p-4 rounded">
              <div className="text-2xl font-bold text-blue-400">99.9%</div>
              <div className="text-sm text-slate-400">Target Availability</div>
            </div>
            <div className="bg-slate-800 border border-slate-700 p-4 rounded">
              <div className="text-2xl font-bold text-green-400">2 hours</div>
              <div className="text-sm text-slate-400">RTO (Recovery Time)</div>
            </div>
            <div className="bg-slate-800 border border-slate-700 p-4 rounded">
              <div className="text-2xl font-bold text-purple-400">15 min</div>
              <div className="text-sm text-slate-400">RPO (Data Loss)</div>
            </div>
            <div className="bg-slate-800 border border-slate-700 p-4 rounded">
              <div className="text-2xl font-bold text-orange-400">$2.5-4K</div>
              <div className="text-sm text-slate-400">Est. Monthly Cost</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ArchitectureDiagram;