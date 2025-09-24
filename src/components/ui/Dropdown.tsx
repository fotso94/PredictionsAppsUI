import React, { useState, useRef, useEffect } from 'react';
import { clsx } from 'clsx';
import { ChevronDownIcon } from '@heroicons/react/24/outline';

interface DropdownOption {
  value: string;
  label: string;
  icon?: React.ReactNode;
  disabled?: boolean;
}

interface DropdownProps {
  options: DropdownOption[];
  value?: string;
  placeholder?: string;
  onChange: (value: string) => void;
  className?: string;
  disabled?: boolean;
  fullWidth?: boolean;
  searchable?: boolean;
}

const Dropdown: React.FC<DropdownProps> = ({
  options,
  value,
  placeholder = 'Select an option',
  onChange,
  className,
  disabled = false,
  fullWidth = false,
  searchable = false,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const dropdownRef = useRef<HTMLDivElement>(null);

  const selectedOption = options.find(option => option.value === value);

  const filteredOptions = searchable
    ? options.filter(option =>
        option.label.toLowerCase().includes(searchTerm.toLowerCase())
      )
    : options;

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
        setSearchTerm('');
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSelect = (optionValue: string) => {
    onChange(optionValue);
    setIsOpen(false);
    setSearchTerm('');
  };

  return (
    <div
      ref={dropdownRef}
      className={clsx('relative', fullWidth && 'w-full', className)}
    >
      <button
        type="button"
        onClick={() => !disabled && setIsOpen(!isOpen)}
        disabled={disabled}
        className={clsx(
          'flex items-center justify-between w-full px-3 py-2 text-left bg-dark-800 border border-dark-600 rounded-lg transition-colors duration-200',
          'hover:border-dark-500 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent',
          disabled && 'opacity-50 cursor-not-allowed',
          isOpen && 'border-primary-500 ring-2 ring-primary-500'
        )}
      >
        <div className="flex items-center">
          {selectedOption?.icon && (
            <span className="mr-2 w-5 h-5 text-dark-400">
              {selectedOption.icon}
            </span>
          )}
          <span className={clsx(
            selectedOption ? 'text-white' : 'text-dark-400'
          )}>
            {selectedOption?.label || placeholder}
          </span>
        </div>
        <ChevronDownIcon
          className={clsx(
            'w-5 h-5 text-dark-400 transition-transform duration-200',
            isOpen && 'transform rotate-180'
          )}
        />
      </button>

      {isOpen && (
        <div className="absolute z-10 w-full mt-1 bg-dark-800 border border-dark-600 rounded-lg shadow-lg max-h-60 overflow-auto">
          {searchable && (
            <div className="p-2 border-b border-dark-700">
              <input
                type="text"
                placeholder="Search..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full px-3 py-2 bg-dark-700 border border-dark-600 rounded text-white placeholder-dark-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            </div>
          )}
          
          <div className="py-1">
            {filteredOptions.length === 0 ? (
              <div className="px-3 py-2 text-dark-400 text-sm">
                No options found
              </div>
            ) : (
              filteredOptions.map((option) => (
                <button
                  key={option.value}
                  onClick={() => !option.disabled && handleSelect(option.value)}
                  disabled={option.disabled}
                  className={clsx(
                    'flex items-center w-full px-3 py-2 text-left transition-colors duration-200',
                    option.disabled
                      ? 'text-dark-500 cursor-not-allowed'
                      : 'text-white hover:bg-dark-700',
                    value === option.value && 'bg-primary-600/20 text-primary-400'
                  )}
                >
                  {option.icon && (
                    <span className="mr-2 w-5 h-5">
                      {option.icon}
                    </span>
                  )}
                  {option.label}
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default Dropdown;
