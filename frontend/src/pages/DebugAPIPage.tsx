import React, { useState } from 'react'
import Card from '@/components/ui/Card'
import Button from '@/components/ui/Button'
import { footballDataService } from '@/services/football-data.service'
import apiFootballService from '@/services/api-football.service'

const DebugAPIPage: React.FC = () => {
  const [output, setOutput] = useState<string>('')
  const [loading, setLoading] = useState(false)

  const addOutput = (message: string) => {
    setOutput(prev => prev + '\n' + message)
    console.log(message)
  }

  const testGetTopLeagues = async () => {
    try {
      setLoading(true)
      setOutput('=== Testing getTopLeagues() ===')

      addOutput('Step 1: Checking footballDataService object...')
      addOutput(`footballDataService type: ${typeof footballDataService}`)
      addOutput(`footballDataService: ${JSON.stringify(Object.keys(footballDataService))}`)

      addOutput('\nStep 2: Calling footballDataService.getTopLeagues()...')
      const startTime = Date.now()
      const leagues = await footballDataService.getTopLeagues()
      const endTime = Date.now()

      addOutput(`\nStep 3: Response received in ${endTime - startTime}ms`)
      addOutput(`✅ Success! Received ${leagues.length} leagues`)

      if (leagues.length === 0) {
        addOutput('\n⚠️ WARNING: API returned 0 leagues!')
        addOutput('This might be a season data issue.')
        addOutput('Check browser console for detailed logs from FootballDataService')
      } else {
        addOutput(`\nLeagues data: ${JSON.stringify(leagues, null, 2)}`)

        leagues.forEach((league, index) => {
          addOutput(`\nLeague ${index + 1}:`)
          addOutput(`  ID: ${league.id}`)
          addOutput(`  Name: ${league.name}`)
          addOutput(`  Country: ${league.country}`)
          addOutput(`  Logo: ${league.logo}`)
          addOutput(`  Season: ${league.season}`)
        })
      }
    } catch (error) {
      addOutput(`\n❌ Error: ${error instanceof Error ? error.message : String(error)}`)
      addOutput(`Stack: ${error instanceof Error ? error.stack : 'N/A'}`)
      addOutput('\nCheck browser console for more details')
    } finally {
      setLoading(false)
    }
  }

  const testGetTodayFixtures = async () => {
    try {
      setLoading(true)
      setOutput('=== Testing getTodayFixtures() ===')
      
      addOutput('Calling footballDataService.getTodayFixtures()...')
      const matches = await footballDataService.getTodayFixtures()
      
      addOutput(`✅ Success! Received ${matches.length} matches`)
      
      if (matches.length > 0) {
        addOutput(`\nFirst match:`)
        addOutput(`  ID: ${matches[0].id}`)
        addOutput(`  Home: ${matches[0].homeTeam.name}`)
        addOutput(`  Away: ${matches[0].awayTeam.name}`)
        addOutput(`  League: ${matches[0].league.name}`)
      }
    } catch (error) {
      addOutput(`❌ Error: ${error instanceof Error ? error.message : String(error)}`)
    } finally {
      setLoading(false)
    }
  }

  const testGetTomorrowFixtures = async () => {
    try {
      setLoading(true)
      setOutput('=== Testing getTomorrowFixtures() ===')
      
      addOutput('Calling footballDataService.getTomorrowFixtures()...')
      const matches = await footballDataService.getTomorrowFixtures()
      
      addOutput(`✅ Success! Received ${matches.length} matches`)
      
      if (matches.length > 0) {
        addOutput(`\nFirst match:`)
        addOutput(`  ID: ${matches[0].id}`)
        addOutput(`  Home: ${matches[0].homeTeam.name}`)
        addOutput(`  Away: ${matches[0].awayTeam.name}`)
        addOutput(`  League: ${matches[0].league.name}`)
      }
    } catch (error) {
      addOutput(`❌ Error: ${error instanceof Error ? error.message : String(error)}`)
    } finally {
      setLoading(false)
    }
  }

  const testGetTeamsByLeague = async () => {
    try {
      setLoading(true)
      setOutput('=== Testing getTeamsByLeague(39) - Premier League ===')
      
      addOutput('Calling footballDataService.getTeamsByLeague(39)...')
      const teams = await footballDataService.getTeamsByLeague(39)
      
      addOutput(`✅ Success! Received ${teams.length} teams`)
      
      if (teams.length > 0) {
        addOutput(`\nFirst 5 teams:`)
        teams.slice(0, 5).forEach((team, index) => {
          addOutput(`  ${index + 1}. ${team.name} (ID: ${team.id})`)
        })
      }
    } catch (error) {
      addOutput(`❌ Error: ${error instanceof Error ? error.message : String(error)}`)
    } finally {
      setLoading(false)
    }
  }

  const testGetFixturesByLeague = async () => {
    try {
      setLoading(true)
      setOutput('=== Testing getFixturesByLeague(39) - Premier League ===')
      
      addOutput('Calling footballDataService.getFixturesByLeague(39, undefined, { next: 5 })...')
      const matches = await footballDataService.getFixturesByLeague(39, undefined, { next: 5 })
      
      addOutput(`✅ Success! Received ${matches.length} matches`)
      
      if (matches.length > 0) {
        addOutput(`\nUpcoming matches:`)
        matches.forEach((match, index) => {
          addOutput(`  ${index + 1}. ${match.homeTeam.name} vs ${match.awayTeam.name}`)
        })
      }
    } catch (error) {
      addOutput(`❌ Error: ${error instanceof Error ? error.message : String(error)}`)
    } finally {
      setLoading(false)
    }
  }

  const testRawAPI = async () => {
    try {
      setLoading(true)
      setOutput('=== Testing Raw API (Premier League) ===')

      addOutput('Testing direct API call to api-football.service')
      addOutput('Endpoint: /leagues?id=39&season=2023')
      addOutput('Note: Free plan only has access to seasons 2021-2023')

      const response = await apiFootballService.getLeagues({ id: 39, season: 2023 })

      addOutput(`\n✅ Raw API Response:`)
      addOutput(`Results: ${response.results}`)
      addOutput(`Response length: ${response.response.length}`)
      addOutput(`\nFull response: ${JSON.stringify(response, null, 2)}`)

      if (response.response.length > 0) {
        const league = response.response[0]
        addOutput(`\nLeague data:`)
        addOutput(`  ID: ${league.league.id}`)
        addOutput(`  Name: ${league.league.name}`)
        addOutput(`  Country: ${league.country.name}`)
        addOutput(`  Logo: ${league.league.logo}`)
        addOutput(`  Seasons: ${league.seasons.length}`)
      } else {
        addOutput('\n⚠️ WARNING: API returned empty response!')
        addOutput('The API might not have data for season 2024')
      }
    } catch (error) {
      addOutput(`\n❌ Error: ${error instanceof Error ? error.message : String(error)}`)
      addOutput(`Stack: ${error instanceof Error ? error.stack : 'N/A'}`)
    } finally {
      setLoading(false)
    }
  }

  const clearOutput = () => {
    setOutput('')
  }

  return (
    <div className="min-h-screen bg-dark-950 py-8">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-white">API Debug Page</h1>
          <p className="text-secondary-400">Test all API service methods</p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Controls */}
          <Card>
            <Card.Header>
              <h2 className="text-xl font-semibold text-white">Test Controls</h2>
            </Card.Header>
            <Card.Body className="space-y-3">
              <div className="text-yellow-400 text-sm mb-4 p-3 bg-dark-900 rounded border border-yellow-600">
                <strong>⚠️ API Limitation:</strong> Free plan only has access to seasons 2021-2023. Using season 2023 for testing.
              </div>

              <Button
                onClick={testRawAPI}
                disabled={loading}
                className="w-full"
                variant="primary"
              >
                🔍 Test Raw API (Premier League 2023)
              </Button>

              <div className="border-t border-dark-700 my-2"></div>

              <Button
                onClick={testGetTopLeagues}
                disabled={loading}
                className="w-full"
              >
                Test getTopLeagues()
              </Button>

              <Button
                onClick={testGetTodayFixtures}
                disabled={loading}
                className="w-full"
              >
                Test getTodayFixtures()
              </Button>

              <Button
                onClick={testGetTomorrowFixtures}
                disabled={loading}
                className="w-full"
              >
                Test getTomorrowFixtures()
              </Button>

              <Button
                onClick={testGetTeamsByLeague}
                disabled={loading}
                className="w-full"
              >
                Test getTeamsByLeague(39)
              </Button>

              <Button
                onClick={testGetFixturesByLeague}
                disabled={loading}
                className="w-full"
              >
                Test getFixturesByLeague(39)
              </Button>

              <div className="border-t border-dark-700 my-2"></div>

              <Button
                onClick={clearOutput}
                variant="secondary"
                className="w-full"
              >
                Clear Output
              </Button>
            </Card.Body>
          </Card>

          {/* Output */}
          <Card>
            <Card.Header>
              <h2 className="text-xl font-semibold text-white">Output</h2>
            </Card.Header>
            <Card.Body>
              {loading && (
                <div className="text-center py-4">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500 mx-auto mb-2"></div>
                  <div className="text-secondary-400 text-sm">Testing...</div>
                </div>
              )}
              
              <pre className="bg-dark-900 p-4 rounded-lg text-xs text-secondary-300 overflow-auto max-h-[600px] font-mono whitespace-pre-wrap">
                {output || 'Click a button to test an API method...'}
              </pre>
            </Card.Body>
          </Card>
        </div>

        {/* Instructions */}
        <Card className="mt-6">
          <Card.Header>
            <h2 className="text-xl font-semibold text-white">Instructions</h2>
          </Card.Header>
          <Card.Body>
            <div className="text-secondary-300 space-y-2">
              <p>1. Open browser console (F12) to see detailed logs</p>
              <p>2. Click each test button to verify API methods work correctly</p>
              <p>3. Check the output panel for results</p>
              <p>4. If errors occur, check the error message and stack trace</p>
              <p>5. Compare results with what you see on the actual pages</p>
            </div>
          </Card.Body>
        </Card>
      </div>
    </div>
  )
}

export default DebugAPIPage

