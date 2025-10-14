"""
API-Football Service

Handles integration with API-Football API for fetching match, team, and league data.
"""

import logging
import httpx
from typing import Optional, Dict, Any
from datetime import datetime

from app.core.config import settings

logger = logging.getLogger(__name__)


class APIFootballService:
    """
    Service for interacting with API-Football API.
    
    API Documentation: https://www.api-football.com/documentation-v3
    """
    
    BASE_URL = "https://v3.football.api-sports.io"
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize API-Football service.
        
        Args:
            api_key: API-Football API key (defaults to settings.API_FOOTBALL_KEY)
        """
        self.api_key = api_key or settings.API_FOOTBALL_KEY
        if not self.api_key:
            logger.warning("API-Football API key not configured")
    
    def _make_request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        Make a request to API-Football API.
        
        Args:
            endpoint: API endpoint (e.g., "/fixtures")
            params: Query parameters
        
        Returns:
            API response data or None if request fails
        """
        if not self.api_key:
            logger.error("Cannot make API request: API key not configured")
            return None
        
        url = f"{self.BASE_URL}{endpoint}"
        headers = {
            "x-apisports-key": self.api_key
        }
        
        try:
            logger.info(f"Making API-Football request to {endpoint} with params {params}")

            with httpx.Client() as client:
                response = client.get(url, headers=headers, params=params, timeout=10.0)
                response.raise_for_status()

                data = response.json()

                # API-Football returns data in this format:
                # {
                #   "get": "fixtures",
                #   "parameters": {...},
                #   "errors": [],
                #   "results": 1,
                #   "paging": {...},
                #   "response": [...]
                # }

                if data.get("errors"):
                    logger.error(f"API-Football returned errors: {data['errors']}")
                    return None

                return data

        except httpx.HTTPError as e:
            logger.error(f"API-Football request failed: {e}")
            return None
    
    def get_fixture_by_id(self, fixture_id: str) -> Optional[Dict[str, Any]]:
        """
        Get fixture details by ID.
        
        Args:
            fixture_id: API-Football fixture ID
        
        Returns:
            Fixture data or None if not found
        """
        data = self._make_request("/fixtures", params={"id": fixture_id})
        
        if not data or not data.get("response"):
            logger.warning(f"Fixture {fixture_id} not found in API-Football")
            return None
        
        # API-Football returns an array, get first result
        fixture = data["response"][0]
        logger.info(f"Retrieved fixture {fixture_id} from API-Football")
        
        return fixture
    
    def extract_match_data(self, fixture: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract match data from API-Football fixture response.
        
        Args:
            fixture: API-Football fixture object
        
        Returns:
            Normalized match data
        """
        # API-Football fixture structure:
        # {
        #   "fixture": {
        #     "id": 1234,
        #     "date": "2024-01-15T20:00:00+00:00",
        #     "venue": {"name": "...", "city": "..."},
        #     "status": {"short": "NS", "long": "Not Started"}
        #   },
        #   "league": {
        #     "id": 39,
        #     "name": "Premier League",
        #     "country": "England",
        #     "logo": "https://..."
        #   },
        #   "teams": {
        #     "home": {
        #       "id": 33,
        #       "name": "Manchester United",
        #       "logo": "https://..."
        #     },
        #     "away": {
        #       "id": 34,
        #       "name": "Newcastle",
        #       "logo": "https://..."
        #     }
        #   }
        # }
        
        fixture_info = fixture.get("fixture", {})
        league_info = fixture.get("league", {})
        teams_info = fixture.get("teams", {})
        
        return {
            "external_match_id": str(fixture_info.get("id")),
            "match_date": fixture_info.get("date"),
            "venue": fixture_info.get("venue", {}).get("name"),
            "status": fixture_info.get("status", {}).get("short", "NS"),
            "league": {
                "external_id": str(league_info.get("id")),
                "name": league_info.get("name"),
                "country": league_info.get("country"),
                "logo_url": league_info.get("logo")
            },
            "home_team": {
                "external_id": str(teams_info.get("home", {}).get("id")),
                "name": teams_info.get("home", {}).get("name"),
                "logo_url": teams_info.get("home", {}).get("logo")
            },
            "away_team": {
                "external_id": str(teams_info.get("away", {}).get("id")),
                "name": teams_info.get("away", {}).get("name"),
                "logo_url": teams_info.get("away", {}).get("logo")
            }
        }
    
    def get_match_data(self, fixture_id: str) -> Optional[Dict[str, Any]]:
        """
        Get normalized match data by fixture ID.
        
        Args:
            fixture_id: API-Football fixture ID
        
        Returns:
            Normalized match data or None if not found
        """
        fixture = self.get_fixture_by_id(fixture_id)
        
        if not fixture:
            return None
        
        return self.extract_match_data(fixture)

