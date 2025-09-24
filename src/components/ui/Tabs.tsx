import React, { useState, createContext, useContext } from 'react';
import { clsx } from 'clsx';

interface TabsContextType {
  activeTab: string;
  setActiveTab: (tab: string) => void;
}

const TabsContext = createContext<TabsContextType | undefined>(undefined);

const useTabsContext = () => {
  const context = useContext(TabsContext);
  if (!context) {
    throw new Error('Tabs components must be used within a Tabs provider');
  }
  return context;
};

interface TabsProps {
  children: React.ReactNode;
  defaultValue: string;
  value?: string;
  onChange?: (value: string) => void;
  className?: string;
}

const Tabs: React.FC<TabsProps> = ({
  children,
  defaultValue,
  value,
  onChange,
  className,
}) => {
  const [internalActiveTab, setInternalActiveTab] = useState(defaultValue);
  
  const activeTab = value !== undefined ? value : internalActiveTab;
  
  const setActiveTab = (tab: string) => {
    if (value === undefined) {
      setInternalActiveTab(tab);
    }
    onChange?.(tab);
  };

  return (
    <TabsContext.Provider value={{ activeTab, setActiveTab }}>
      <div className={clsx('w-full', className)}>
        {children}
      </div>
    </TabsContext.Provider>
  );
};

interface TabsListProps {
  children: React.ReactNode;
  className?: string;
}

export const TabsList: React.FC<TabsListProps> = ({ children, className }) => {
  return (
    <div className={clsx(
      'flex space-x-1 bg-dark-800 p-1 rounded-lg border border-dark-700',
      className
    )}>
      {children}
    </div>
  );
};

interface TabsTriggerProps {
  children: React.ReactNode;
  value: string;
  className?: string;
  disabled?: boolean;
}

export const TabsTrigger: React.FC<TabsTriggerProps> = ({
  children,
  value,
  className,
  disabled = false,
}) => {
  const { activeTab, setActiveTab } = useTabsContext();
  const isActive = activeTab === value;

  return (
    <button
      onClick={() => !disabled && setActiveTab(value)}
      disabled={disabled}
      className={clsx(
        'px-3 py-2 text-sm font-medium rounded-md transition-all duration-200',
        'focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 focus:ring-offset-dark-800',
        isActive
          ? 'bg-primary-600 text-white shadow-sm'
          : 'text-dark-300 hover:text-white hover:bg-dark-700',
        disabled && 'opacity-50 cursor-not-allowed',
        className
      )}
    >
      {children}
    </button>
  );
};

interface TabsContentProps {
  children: React.ReactNode;
  value: string;
  className?: string;
}

export const TabsContent: React.FC<TabsContentProps> = ({
  children,
  value,
  className,
}) => {
  const { activeTab } = useTabsContext();
  
  if (activeTab !== value) {
    return null;
  }

  return (
    <div className={clsx('mt-4', className)}>
      {children}
    </div>
  );
};

export default Tabs;
