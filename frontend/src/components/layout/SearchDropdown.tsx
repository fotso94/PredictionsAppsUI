import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { MagnifyingGlassIcon, XMarkIcon } from '@heroicons/react/24/outline';
import searchService, { SearchResults } from '@/services/search.service';
import clsx from 'clsx';

interface SearchDropdownProps {
  className?: string;
}

const SearchDropdown: React.FC<SearchDropdownProps> = ({ className }) => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResults>({ teams: [], leagues: [] });
  const [isLoading, setIsLoading] = useState(false);
  const [isOpen, setIsOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  
  const searchRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  // Debounce search
  useEffect(() => {
    if (query.length < 3) {
      setResults({ teams: [], leagues: [] });
      setIsOpen(false);
      setError(null);
      return;
    }

    setIsLoading(true);
    setError(null);
    
    const timeoutId = setTimeout(async () => {
      try {
        const searchResults = await searchService.search(query);
        setResults(searchResults);
        setIsOpen(true);
        setSelectedIndex(-1);
      } catch (err) {
        console.error('Search error:', err);
        setError('Failed to search. Please try again.');
        setResults({ teams: [], leagues: [] });
      } finally {
        setIsLoading(false);
      }
    }, 400); // 400ms debounce

    return () => clearTimeout(timeoutId);
  }, [query]);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Handle keyboard navigation
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    const totalResults = results.teams.length + results.leagues.length;
    
    if (e.key === 'Escape') {
      setIsOpen(false);
      inputRef.current?.blur();
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex(prev => (prev < totalResults - 1 ? prev + 1 : prev));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex(prev => (prev > 0 ? prev - 1 : -1));
    } else if (e.key === 'Enter' && selectedIndex >= 0) {
      e.preventDefault();
      handleSelectResult(selectedIndex);
    }
  }, [results, selectedIndex]);

  const handleSelectResult = (index: number) => {
    const teamCount = results.teams.length;
    
    if (index < teamCount) {
      // Team selected
      const team = results.teams[index];
      navigate(`/teams/${team.id}`);
    } else {
      // League selected
      const league = results.leagues[index - teamCount];
      navigate(`/leagues/${league.id}`);
    }
    
    // Clear search and close dropdown
    setQuery('');
    setIsOpen(false);
    inputRef.current?.blur();
  };

  const handleClearSearch = () => {
    setQuery('');
    setResults({ teams: [], leagues: [] });
    setIsOpen(false);
    setError(null);
    inputRef.current?.focus();
  };

  const totalResults = results.teams.length + results.leagues.length;
  const hasResults = totalResults > 0;
  const showDropdown = isOpen && (hasResults || isLoading || error || query.length >= 3);

  return (
    <div ref={searchRef} className={clsx('relative', className)}>
      {/* Search Input */}
      <div className="relative">
        <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
          <MagnifyingGlassIcon className="h-5 w-5 text-secondary-400" aria-hidden="true" />
        </div>
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => query.length >= 3 && setIsOpen(true)}
          placeholder="Search teams, leagues..."
          className="block w-full rounded-lg border-0 bg-dark-800 py-2 pl-10 pr-10 text-white placeholder:text-secondary-400 focus:ring-2 focus:ring-primary-500 sm:text-sm"
        />
        {query && (
          <button
            onClick={handleClearSearch}
            className="absolute inset-y-0 right-0 flex items-center pr-3 text-secondary-400 hover:text-white"
          >
            <XMarkIcon className="h-5 w-5" />
          </button>
        )}
      </div>

      {/* Search Results Dropdown */}
      {showDropdown && (
        <div className="absolute z-50 mt-2 w-full min-w-[320px] max-w-md rounded-lg bg-dark-800 shadow-xl ring-1 ring-dark-700 overflow-hidden">
          {/* Loading State */}
          {isLoading && (
            <div className="px-4 py-8 text-center">
              <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-primary-500 border-r-transparent"></div>
              <p className="mt-2 text-sm text-secondary-400">Searching...</p>
            </div>
          )}

          {/* Error State */}
          {error && !isLoading && (
            <div className="px-4 py-6 text-center">
              <p className="text-sm text-red-400">{error}</p>
            </div>
          )}

          {/* No Results */}
          {!isLoading && !error && query.length >= 3 && !hasResults && (
            <div className="px-4 py-6 text-center">
              <p className="text-sm text-secondary-400">No results found for "{query}"</p>
              <p className="mt-1 text-xs text-secondary-500">Try a different search term</p>
            </div>
          )}

          {/* Results */}
          {!isLoading && !error && hasResults && (
            <div className="max-h-96 overflow-y-auto">
              {/* Teams Section */}
              {results.teams.length > 0 && (
                <div className="border-b border-dark-700">
                  <div className="px-4 py-2 bg-dark-900">
                    <h3 className="text-xs font-semibold text-secondary-400 uppercase tracking-wider">
                      Teams ({results.teams.length})
                    </h3>
                  </div>
                  <div className="py-1">
                    {results.teams.map((team, index) => (
                      <button
                        key={team.id}
                        onClick={() => handleSelectResult(index)}
                        className={clsx(
                          'w-full px-4 py-3 flex items-center space-x-3 hover:bg-dark-700 transition-colors',
                          selectedIndex === index && 'bg-dark-700'
                        )}
                      >
                        <img
                          src={team.logo}
                          alt={team.name}
                          className="h-8 w-8 rounded-full object-cover bg-white"
                          onError={(e) => {
                            (e.target as HTMLImageElement).src = 'https://via.placeholder.com/32?text=T';
                          }}
                        />
                        <div className="flex-1 text-left">
                          <p className="text-sm font-medium text-white">{team.name}</p>
                          <p className="text-xs text-secondary-400">{team.country}</p>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Leagues Section */}
              {results.leagues.length > 0 && (
                <div>
                  <div className="px-4 py-2 bg-dark-900">
                    <h3 className="text-xs font-semibold text-secondary-400 uppercase tracking-wider">
                      Leagues ({results.leagues.length})
                    </h3>
                  </div>
                  <div className="py-1">
                    {results.leagues.map((league, index) => (
                      <button
                        key={league.id}
                        onClick={() => handleSelectResult(results.teams.length + index)}
                        className={clsx(
                          'w-full px-4 py-3 flex items-center space-x-3 hover:bg-dark-700 transition-colors',
                          selectedIndex === results.teams.length + index && 'bg-dark-700'
                        )}
                      >
                        <img
                          src={league.logo}
                          alt={league.name}
                          className="h-8 w-8 rounded-full object-cover bg-white"
                          onError={(e) => {
                            (e.target as HTMLImageElement).src = 'https://via.placeholder.com/32?text=L';
                          }}
                        />
                        <div className="flex-1 text-left">
                          <p className="text-sm font-medium text-white">{league.name}</p>
                          <p className="text-xs text-secondary-400">
                            {league.country} • {league.type}
                          </p>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Keyboard Hint */}
          {hasResults && !isLoading && (
            <div className="px-4 py-2 bg-dark-900 border-t border-dark-700">
              <p className="text-xs text-secondary-500">
                Use ↑↓ to navigate, Enter to select, Esc to close
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default SearchDropdown;

