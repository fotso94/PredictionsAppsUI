import React from 'react';
import { clsx } from 'clsx';

interface ContainerProps {
  children: React.ReactNode;
  size?: 'sm' | 'md' | 'lg' | 'xl' | 'full';
  className?: string;
  padding?: boolean;
}

const Container: React.FC<ContainerProps> = ({
  children,
  size = 'xl',
  className,
  padding = true,
}) => {
  const sizeClasses = {
    sm: 'max-w-2xl',
    md: 'max-w-4xl',
    lg: 'max-w-6xl',
    xl: 'max-w-7xl',
    full: 'max-w-full',
  };

  return (
    <div
      className={clsx(
        'mx-auto',
        sizeClasses[size],
        padding && 'px-4 sm:px-6 lg:px-8',
        className
      )}
    >
      {children}
    </div>
  );
};

interface SectionProps {
  children: React.ReactNode;
  className?: string;
  padding?: 'none' | 'sm' | 'md' | 'lg' | 'xl';
  background?: 'transparent' | 'dark' | 'darker';
}

export const Section: React.FC<SectionProps> = ({
  children,
  className,
  padding = 'lg',
  background = 'transparent',
}) => {
  const paddingClasses = {
    none: '',
    sm: 'py-8',
    md: 'py-12',
    lg: 'py-16',
    xl: 'py-24',
  };

  const backgroundClasses = {
    transparent: '',
    dark: 'bg-dark-800',
    darker: 'bg-dark-900',
  };

  return (
    <section
      className={clsx(
        paddingClasses[padding],
        backgroundClasses[background],
        className
      )}
    >
      {children}
    </section>
  );
};

export default Container;
