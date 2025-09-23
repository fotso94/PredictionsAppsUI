import React from 'react'
import clsx from 'clsx'

interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({ 
  size = 'md', 
  className 
}) => {
  const sizeClasses = {
    sm: 'h-4 w-4',
    md: 'h-8 w-8',
    lg: 'h-12 w-12',
  }

  return (
    <div className={clsx('spinner', sizeClasses[size], className)} />
  )
}

interface LoadingSkeletonProps {
  className?: string
  lines?: number
}

const LoadingSkeleton: React.FC<LoadingSkeletonProps> = ({ 
  className, 
  lines = 1 
}) => {
  return (
    <div className="space-y-2">
      {Array.from({ length: lines }).map((_, index) => (
        <div
          key={index}
          className={clsx('skeleton h-4', className)}
        />
      ))}
    </div>
  )
}

interface LoadingStateProps {
  loading: boolean
  error?: string
  children: React.ReactNode
}

const LoadingState: React.FC<LoadingStateProps> = ({ 
  loading, 
  error, 
  children 
}) => {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="text-center py-12">
        <div className="text-danger-400 mb-2">Error</div>
        <div className="text-secondary-400">{error}</div>
      </div>
    )
  }

  return <>{children}</>
}

export { LoadingSpinner, LoadingSkeleton, LoadingState }
