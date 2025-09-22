import React from 'react';

interface PerformanceChartProps {
  data?: {
    labels: string[];
    datasets: {
      label: string;
      data: number[];
      borderColor: string;
      backgroundColor: string;
    }[];
  };
  height?: number;
}

const PerformanceChart: React.FC<PerformanceChartProps> = ({ 
  data, 
  height = 300 
}) => {
  // Mock data for demonstration
  const mockData = {
    labels: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'],
    datasets: [
      {
        label: 'Win Rate %',
        data: [65, 68, 72, 70, 75, 78],
        borderColor: '#10b981',
        backgroundColor: 'rgba(16, 185, 129, 0.1)',
      },
      {
        label: 'ROI %',
        data: [12, 15, 18, 16, 20, 22],
        borderColor: '#8b5cf6',
        backgroundColor: 'rgba(139, 92, 246, 0.1)',
      }
    ]
  };

  const chartData = data || mockData;

  return (
    <div className="w-full" style={{ height }}>
      <div className="flex items-center justify-center h-full bg-dark-700/30 rounded-lg border-2 border-dashed border-dark-600">
        <div className="text-center">
          <div className="text-4xl mb-4">📊</div>
          <h3 className="text-lg font-semibold text-white mb-2">Performance Chart</h3>
          <p className="text-sm text-dark-400 mb-4">
            Chart.js integration ready
          </p>
          <div className="text-xs text-dark-500 space-y-1">
            <div>Mock Data Available:</div>
            <div>• Win Rate: {chartData.datasets[0].data.join('%, ')}%</div>
            <div>• ROI: {chartData.datasets[1].data.join('%, ')}%</div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default PerformanceChart;
