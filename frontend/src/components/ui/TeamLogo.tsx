import React from 'react'
import { getTeamLogoUrl, handleLogoError } from '@/utils/logoUtils'

interface TeamLogoProps {
  teamId: string
  teamName: string
  logoUrl?: string
  size?: 'sm' | 'md' | 'lg' | 'xl'
  className?: string
}

const TeamLogo: React.FC<TeamLogoProps> = ({
  teamId,
  teamName,
  logoUrl,
  size = 'md',
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
      src={getTeamLogoUrl(teamId, logoUrl)}
      alt={`${teamName} logo`}
      className={`${sizeClasses[size]} object-contain ${className}`}
      onError={(e) => handleLogoError(e, 'team', teamId)}
      loading="lazy"
    />
  )
}

export default TeamLogo
