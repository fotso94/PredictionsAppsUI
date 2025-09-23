import React from 'react'
import clsx from 'clsx'
import { ConfidenceLevel } from '@/types'

interface BadgeProps {
  children: React.ReactNode
  variant?: 'success' | 'warning' | 'danger' | 'info' | 'secondary'
  className?: string
}

interface ConfidenceBadgeProps {
  level: ConfidenceLevel
  className?: string
}

const Badge: React.FC<BadgeProps> = ({ 
  children, 
  variant = 'secondary', 
  className 
}) => {
  const variantClasses = {
    success: 'badge-success',
    warning: 'badge-warning',
    danger: 'badge-danger',
    info: 'badge-info',
    secondary: 'badge-secondary',
  }

  return (
    <span className={clsx('badge', variantClasses[variant], className)}>
      {children}
    </span>
  )
}

const ConfidenceBadge: React.FC<ConfidenceBadgeProps> = ({ level, className }) => {
  const confidenceClasses = {
    low: 'confidence-low',
    medium: 'confidence-medium',
    high: 'confidence-high',
    'very-high': 'confidence-very-high',
  }

  const confidenceLabels = {
    low: 'Low',
    medium: 'Medium',
    high: 'High',
    'very-high': 'Very High',
  }

  return (
    <span className={clsx(confidenceClasses[level], className)}>
      {confidenceLabels[level]}
    </span>
  )
}

export { Badge, ConfidenceBadge }
