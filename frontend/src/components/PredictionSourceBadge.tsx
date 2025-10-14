/**
 * Prediction Source Badge Component
 * Displays prediction source with icon and color (KAN-155)
 */

import React from 'react';
import { getPredictionSourceInfo, PredictionSource } from '../types/expert';

interface PredictionSourceBadgeProps {
  source: string | PredictionSource;
  showLabel?: boolean;
  showIcon?: boolean;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

/**
 * Badge component to display prediction source
 * Shows icon (👤 Expert, 🤖 LLM, ⭐ API-Football, etc.) and optional label
 */
export const PredictionSourceBadge: React.FC<PredictionSourceBadgeProps> = ({
  source,
  showLabel = true,
  showIcon = true,
  size = 'md',
  className = '',
}) => {
  const sourceInfo = getPredictionSourceInfo(source as string);

  // Size classes
  const sizeClasses = {
    sm: 'text-xs px-2 py-0.5',
    md: 'text-sm px-2.5 py-1',
    lg: 'text-base px-3 py-1.5',
  };

  const iconSizeClasses = {
    sm: 'text-sm',
    md: 'text-base',
    lg: 'text-lg',
  };

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full bg-gray-100 dark:bg-gray-800 ${sizeClasses[size]} ${className}`}
      title={sourceInfo.description}
    >
      {showIcon && (
        <span className={iconSizeClasses[size]} role="img" aria-label={sourceInfo.label}>
          {sourceInfo.icon}
        </span>
      )}
      {showLabel && (
        <span className={`font-medium ${sourceInfo.color}`}>
          {sourceInfo.label}
        </span>
      )}
    </span>
  );
};

interface PredictionPriorityBadgeProps {
  priority: number;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

/**
 * Badge component to display prediction priority level
 */
export const PredictionPriorityBadge: React.FC<PredictionPriorityBadgeProps> = ({
  priority,
  size = 'md',
  className = '',
}) => {
  // Determine color based on priority
  const getColorClass = (priority: number): string => {
    if (priority >= 90) return 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200';
    if (priority >= 50) return 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200';
    if (priority >= 25) return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200';
    return 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200';
  };

  const sizeClasses = {
    sm: 'text-xs px-2 py-0.5',
    md: 'text-sm px-2.5 py-1',
    lg: 'text-base px-3 py-1.5',
  };

  return (
    <span
      className={`inline-flex items-center rounded-full font-medium ${getColorClass(priority)} ${sizeClasses[size]} ${className}`}
      title={`Priority Level: ${priority}`}
    >
      Priority {priority}
    </span>
  );
};

interface PredictionStatusBadgeProps {
  status: string;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

/**
 * Badge component to display prediction status
 */
export const PredictionStatusBadge: React.FC<PredictionStatusBadgeProps> = ({
  status,
  size = 'md',
  className = '',
}) => {
  // Determine color based on status
  const getColorClass = (status: string): string => {
    switch (status.toLowerCase()) {
      case 'published':
        return 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200';
      case 'approved':
        return 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200';
      case 'pending':
      case 'under_review':
        return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200';
      case 'rejected':
        return 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200';
      case 'archived':
        return 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200';
      default:
        return 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200';
    }
  };

  const sizeClasses = {
    sm: 'text-xs px-2 py-0.5',
    md: 'text-sm px-2.5 py-1',
    lg: 'text-base px-3 py-1.5',
  };

  return (
    <span
      className={`inline-flex items-center rounded-full font-medium ${getColorClass(status)} ${sizeClasses[size]} ${className}`}
    >
      {status.charAt(0).toUpperCase() + status.slice(1).replace('_', ' ')}
    </span>
  );
};

interface ConfidenceBadgeProps {
  confidence: number;
  size?: 'sm' | 'md' | 'lg';
  showPercentage?: boolean;
  className?: string;
}

/**
 * Badge component to display confidence score
 */
export const ConfidenceBadge: React.FC<ConfidenceBadgeProps> = ({
  confidence,
  size = 'md',
  showPercentage = true,
  className = '',
}) => {
  // Determine color based on confidence
  const getColorClass = (confidence: number): string => {
    if (confidence >= 0.85) return 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200';
    if (confidence >= 0.70) return 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200';
    if (confidence >= 0.50) return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200';
    return 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200';
  };

  const getLabel = (confidence: number): string => {
    if (confidence >= 0.85) return 'Very High';
    if (confidence >= 0.70) return 'High';
    if (confidence >= 0.50) return 'Medium';
    return 'Low';
  };

  const sizeClasses = {
    sm: 'text-xs px-2 py-0.5',
    md: 'text-sm px-2.5 py-1',
    lg: 'text-base px-3 py-1.5',
  };

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full font-medium ${getColorClass(confidence)} ${sizeClasses[size]} ${className}`}
      title={`Confidence: ${(confidence * 100).toFixed(1)}%`}
    >
      <span>{getLabel(confidence)}</span>
      {showPercentage && (
        <span className="opacity-75">
          ({(confidence * 100).toFixed(0)}%)
        </span>
      )}
    </span>
  );
};

export default PredictionSourceBadge;

