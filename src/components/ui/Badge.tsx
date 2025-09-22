import React from 'react';
import { clsx } from 'clsx';

interface BadgeProps {
  children: React.ReactNode;
  variant?: 'primary' | 'secondary' | 'success' | 'danger' | 'warning' | 'info';
  size?: 'sm' | 'md' | 'lg';
  rounded?: boolean;
  className?: string;
}

const Badge: React.FC<BadgeProps> = ({
  children,
  variant = 'primary',
  size = 'md',
  rounded = false,
  className,
}) => {
  const baseClasses = 'inline-flex items-center font-medium';

  const variantClasses = {
    primary: 'bg-primary-600/20 text-primary-400 border border-primary-600/30',
    secondary: 'bg-dark-700 text-dark-300 border border-dark-600',
    success: 'bg-success-600/20 text-success-400 border border-success-600/30',
    danger: 'bg-danger-600/20 text-danger-400 border border-danger-600/30',
    warning: 'bg-yellow-600/20 text-yellow-400 border border-yellow-600/30',
    info: 'bg-blue-600/20 text-blue-400 border border-blue-600/30',
  };

  const sizeClasses = {
    sm: 'px-2 py-0.5 text-xs',
    md: 'px-2.5 py-1 text-sm',
    lg: 'px-3 py-1.5 text-base',
  };

  return (
    <span
      className={clsx(
        baseClasses,
        variantClasses[variant],
        sizeClasses[size],
        rounded ? 'rounded-full' : 'rounded',
        className
      )}
    >
      {children}
    </span>
  );
};

interface StatusBadgeProps {
  status: 'online' | 'offline' | 'away' | 'busy';
  showText?: boolean;
  className?: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({
  status,
  showText = false,
  className,
}) => {
  const statusConfig = {
    online: { color: 'bg-success-500', text: 'Online' },
    offline: { color: 'bg-dark-500', text: 'Offline' },
    away: { color: 'bg-yellow-500', text: 'Away' },
    busy: { color: 'bg-danger-500', text: 'Busy' },
  };

  const config = statusConfig[status];

  return (
    <div className={clsx('flex items-center', className)}>
      <div className={clsx('w-2 h-2 rounded-full', config.color)} />
      {showText && (
        <span className="ml-2 text-sm text-dark-300">{config.text}</span>
      )}
    </div>
  );
};

interface ConfidenceBadgeProps {
  confidence: number;
  className?: string;
}

export const ConfidenceBadge: React.FC<ConfidenceBadgeProps> = ({
  confidence,
  className,
}) => {
  const getVariant = (confidence: number) => {
    if (confidence >= 80) return 'success';
    if (confidence >= 60) return 'warning';
    return 'danger';
  };

  const getLabel = (confidence: number) => {
    if (confidence >= 80) return 'High';
    if (confidence >= 60) return 'Medium';
    return 'Low';
  };

  return (
    <Badge
      variant={getVariant(confidence)}
      size="sm"
      className={className}
    >
      {confidence}% {getLabel(confidence)}
    </Badge>
  );
};

export default Badge;
