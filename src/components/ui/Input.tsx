import React, { forwardRef } from 'react';
import { clsx } from 'clsx';

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
  icon?: React.ReactNode;
  iconPosition?: 'left' | 'right';
  fullWidth?: boolean;
}

const Input = forwardRef<HTMLInputElement, InputProps>(({
  label,
  error,
  helperText,
  icon,
  iconPosition = 'left',
  fullWidth = false,
  className,
  id,
  ...props
}, ref) => {
  const inputId = id || `input-${Math.random().toString(36).substr(2, 9)}`;

  const baseClasses = 'bg-dark-800 border text-white rounded-lg px-3 py-2 transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed';

  const borderClasses = error 
    ? 'border-danger-500 focus:ring-danger-500' 
    : 'border-dark-600 hover:border-dark-500';

  return (
    <div className={clsx('space-y-1', fullWidth && 'w-full')}>
      {label && (
        <label 
          htmlFor={inputId}
          className="block text-sm font-medium text-dark-300"
        >
          {label}
        </label>
      )}
      
      <div className="relative">
        {icon && iconPosition === 'left' && (
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
            <span className="text-dark-400 w-5 h-5">
              {icon}
            </span>
          </div>
        )}
        
        <input
          ref={ref}
          id={inputId}
          className={clsx(
            baseClasses,
            borderClasses,
            icon && iconPosition === 'left' && 'pl-10',
            icon && iconPosition === 'right' && 'pr-10',
            fullWidth && 'w-full',
            className
          )}
          {...props}
        />
        
        {icon && iconPosition === 'right' && (
          <div className="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none">
            <span className="text-dark-400 w-5 h-5">
              {icon}
            </span>
          </div>
        )}
      </div>
      
      {error && (
        <p className="text-sm text-danger-500">
          {error}
        </p>
      )}
      
      {helperText && !error && (
        <p className="text-sm text-dark-400">
          {helperText}
        </p>
      )}
    </div>
  );
});

Input.displayName = 'Input';

export default Input;
