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
  /**
   * Where the level came from. An expert publishes a confidence score; a model forecast does not,
   * so its badge is only the strength of the probability itself. Labelling a derived bucket as the
   * model's confidence would attribute a judgement the model never made.
   */
  basis?: 'published' | 'derived'
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

const ConfidenceBadge: React.FC<ConfidenceBadgeProps> = ({ level, className, basis = 'published' }) => {
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

  const title = basis === 'derived'
    ? `${confidenceLabels[level]} probability. This source publishes no confidence score, so this `
      + 'reflects how strong the probability is, not how confident the source claims to be.'
    : `${confidenceLabels[level]} confidence, as published by the source.`

  return (
    <span
      className={clsx(confidenceClasses[level], className)}
      title={title}
      data-basis={basis}
    >
      {confidenceLabels[level]}
    </span>
  )
}

export { Badge, ConfidenceBadge }
