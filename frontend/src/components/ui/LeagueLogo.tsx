import React from 'react'
import { getLeagueLogoUrl, handleLogoError } from '@/utils/logoUtils'

interface LeagueLogoProps {
  leagueId: string
  leagueName: string
  logoUrl?: string
  size?: 'sm' | 'md' | 'lg' | 'xl'
  className?: string
}

const LeagueLogo: React.FC<LeagueLogoProps> = ({
  leagueId,
  leagueName,
  logoUrl,
  size = 'sm',
  className = ''
}) => {
  const sizeClasses = {
    sm: 'h-4 w-4',
    md: 'h-8 w-8',
    lg: 'h-12 w-12',
    xl: 'h-16 w-16'
  }

  return (
    <img
      src={getLeagueLogoUrl(leagueId, logoUrl)}
      alt={`${leagueName} logo`}
      className={`${sizeClasses[size]} object-contain ${className}`}
      onError={(e) => handleLogoError(e, 'league', leagueId)}
      loading="lazy"
    />
  )
}

export default LeagueLogo
