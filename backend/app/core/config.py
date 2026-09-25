"""
Application Configuration
Centralized settings management using Pydantic BaseSettings
"""

from typing import Any, List, Optional, Union
from pydantic import field_validator, ValidationInfo
from pydantic_settings import BaseSettings
import secrets
import json


class Settings(BaseSettings):
    """Application settings"""

    # Project Information
    PROJECT_NAME: str = "Soccer Predictions Platform API"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"

    # Environment
    ENVIRONMENT: str = "development"  # development, staging, production
    DEBUG: bool = True

    # Security
    SECRET_KEY: str = secrets.token_urlsafe(32)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 30  # 30 days
    ALGORITHM: str = "HS256"

    # CORS
    # The browser sends an Origin the moment the interface talks to this API cross-origin, and
    # anything not listed here is refused before the endpoint is reached - which the reader sees
    # as a sign-in button that does nothing rather than as an error. 3100 is the port the frontend
    # dev server binds (--port 3100 --strictPort) and the one e2e/live drives, so leaving it out
    # makes the whole live suite fail on sign-in while every API-level check still passes.
    BACKEND_CORS_ORIGINS: Union[List[str], str] = [
        "http://localhost:3000",  # React frontend
        "http://localhost:3100",  # Vite dev server, the port this project actually uses
        "http://localhost:5173",  # Vite default, for a dev server started without --port
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3100",
        "http://127.0.0.1:5173",
    ]

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            # Try to parse as JSON first
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except (json.JSONDecodeError, ValueError):
                pass
            # Otherwise split by comma
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, list):
            return v
        raise ValueError(f"Invalid CORS origins format: {v}")
    
    # Allowed Hosts (for production)
    ALLOWED_HOSTS: List[str] = ["localhost", "127.0.0.1"]
    
    # Database - PostgreSQL
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres123"
    POSTGRES_DB: str = "soccer_predictions"
    DATABASE_URL: Optional[str] = None
    
    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_db_connection(cls, v: Optional[str], info: ValidationInfo) -> str:
        if isinstance(v, str):
            return v
        return (
            f"postgresql://{info.data.get('POSTGRES_USER')}:"
            f"{info.data.get('POSTGRES_PASSWORD')}@"
            f"{info.data.get('POSTGRES_SERVER')}:"
            f"{info.data.get('POSTGRES_PORT')}/"
            f"{info.data.get('POSTGRES_DB')}"
        )
    
    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0  # Default database for sessions
    REDIS_PASSWORD: Optional[str] = None
    REDIS_URL: Optional[str] = None
    
    @field_validator("REDIS_URL", mode="before")
    @classmethod
    def assemble_redis_connection(cls, v: Optional[str], info: ValidationInfo) -> str:
        if isinstance(v, str):
            return v
        password = info.data.get('REDIS_PASSWORD')
        if password:
            return (
                f"redis://:{password}@"
                f"{info.data.get('REDIS_HOST')}:"
                f"{info.data.get('REDIS_PORT')}/"
                f"{info.data.get('REDIS_DB')}"
            )
        return (
            f"redis://{info.data.get('REDIS_HOST')}:"
            f"{info.data.get('REDIS_PORT')}/"
            f"{info.data.get('REDIS_DB')}"
        )
    
    # Redis Database Allocation (from KAN-30)
    REDIS_DB_SESSIONS: int = 0  # User sessions and authentication
    REDIS_DB_PREDICTIONS: int = 1  # Prediction caching
    REDIS_DB_EXPERT_TOOLS: int = 2  # Expert tools cache
    REDIS_DB_ML_MODELS: int = 3  # ML model predictions cache
    REDIS_DB_MATCH_DATA: int = 4  # Real-time match data
    REDIS_DB_RATE_LIMIT: int = 5  # API rate limiting
    
    # Email Configuration
    # Email Provider: smtp, sendgrid, ses
    EMAIL_PROVIDER: str = "smtp"
    EMAIL_ENABLED: bool = True

    # SMTP Configuration
    SMTP_TLS: bool = True
    SMTP_PORT: int = 587
    SMTP_HOST: Optional[str] = None
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None

    # Email Sender Information
    EMAILS_FROM_EMAIL: Optional[str] = None
    EMAILS_FROM_NAME: str = "Soccer Predictions Platform"

    # SendGrid Configuration (for future use)
    SENDGRID_API_KEY: Optional[str] = None

    # AWS SES Configuration (for future use)
    AWS_SES_REGION: Optional[str] = None
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None

    # Email Templates
    EMAIL_TEMPLATES_DIR: str = "app/templates/emails"

    # Frontend URL (for email links)
    FRONTEND_URL: str = "http://localhost:3000"
    
    # External APIs (retained integrations)
    API_FOOTBALL_KEY: Optional[str] = None
    THESPORTSDB_KEY: Optional[str] = None  # optional; used by the retained TheSportsDB fallback provider

    # ------------------------------------------------------------------
    # Match-data and prediction providers (Phase 1 integrations)
    # ------------------------------------------------------------------
    # Active match-data provider: livescore | api_football | thesportsdb | sample
    DATA_PROVIDER: str = "livescore"
    # Comma-separated providers tried in order when the active one fails (e.g. "api_football,thesportsdb")
    DATA_PROVIDER_FALLBACKS: str = ""
    # Active prediction provider: gameforecast | api_football | none | sample
    PREDICTION_PROVIDER: str = "gameforecast"
    # Canonical competition keys covered by the product (see app/services/providers/competitions.py)
    COVERED_COMPETITIONS: str = "premier_league,la_liga,serie_a,bundesliga,ligue_1,champions_league"
    # National-team competitions, added to the club set above rather than replacing any of it.
    # Accepts explicit keys ("fifa_world_cup,uefa_nations_league"), `active` (every national-team
    # competition Live Score still schedules, 29 today), `all` (those plus the five dormant ones), or
    # nothing.
    #
    # `active`, because the scheduler now pays for these by the fixture rather than by the
    # competition. Asking all 35 covered competitions on every pass is what used to make this
    # unaffordable - 35 x 3 days x 4 fixture passes = 420/day, and the results task at its
    # half-hourly interval 35 x 2 x 48 = 3,360/day, some four times the whole 1,200/day Live Score
    # plan. Three rules replace that, and each is bounded by a setting below:
    #
    #   - the results task asks only for the competitions an unsettled match is actually IN
    #     (`MatchDataService.pending_result_keys`), capped per pass;
    #   - the fixtures task asks for a national-team competition only on days its coverage calendar
    #     says it plays, capped per pass; the club six are always asked for, exactly as before;
    #   - those calendars are bought one request at a time by a rotation that refreshes the stalest
    #     first and re-reads a dormant competition at most once a fortnight.
    #
    # A dormant tournament therefore costs nothing until it schedules something, and an
    # international break is picked up within a day with nobody touching a setting.
    COVERED_NATIONAL_TEAM_COMPETITIONS: str = "active"

    # Live Score API (https://live-score-api.com) — key + secret from the account profile
    LIVESCORE_API_KEY: Optional[str] = None
    LIVESCORE_API_SECRET: Optional[str] = None
    LIVESCORE_API_BASE_URL: str = "https://livescore-api.com/api-client"
    # Trial allows 1,500 requests/day; keep headroom for retries and manual checks
    LIVESCORE_DAILY_REQUEST_BUDGET: int = 1200
    # Optional override of competition ids, e.g. "premier_league=2,la_liga=3"; otherwise resolved by name
    LIVESCORE_COMPETITION_IDS: Optional[str] = None

    # GameForecastAPI (https://www.gameforecastapi.com, served through RapidAPI)
    GAMEFORECAST_API_KEY: Optional[str] = None
    GAMEFORECAST_API_HOST: str = "game-forecast-api.p.rapidapi.com"
    GAMEFORECAST_API_BASE_URL: str = "https://game-forecast-api.p.rapidapi.com"
    # Free plan allows 10 requests/day (10/hour); Pro 5,000/month. Keep a small margin.
    GAMEFORECAST_DAILY_REQUEST_BUDGET: int = 8
    # Optional override of league ids, e.g. "premier_league=15"; otherwise resolved by name (1 request per league)
    GAMEFORECAST_LEAGUE_IDS: Optional[str] = None
    GAMEFORECAST_SYNC_DAYS_AHEAD: int = 7
    # Minimum hours between two forecast syncs of the same competition
    GAMEFORECAST_SYNC_INTERVAL_HOURS: int = 24

    # Forecasts older than this (since the provider generated them) are reported as stale, never as current
    FORECAST_MAX_AGE_HOURS: int = 72

    # ------------------------------------------------------------------
    # Background synchronisation (app/services/sync_scheduler.py)
    # ------------------------------------------------------------------
    # Without this the app only refreshes when somebody happens to load a page with refresh on, so
    # "last updated" is whatever the last visitor paid for. The scheduler makes that explicit.
    # One line in .env turns the whole thing off:  SYNC_SCHEDULER_ENABLED=false
    SYNC_SCHEDULER_ENABLED: bool = True
    # Comma-separated subset of "fixtures,live,results,recover,forecasts,settle"; empty
    # disables every task. One line in .env disables a single one.
    SYNC_SCHEDULER_TASKS: str = "fixtures,live,results,recover,forecasts,settle"
    # How often the loop wakes up and asks each task whether it is due. Costs nothing by itself.
    SYNC_SCHEDULER_TICK_SECONDS: int = 60
    # Grace period after startup before the first tick. Development restarts the backend constantly;
    # without this every restart would pay for a full pass. Task due-times also survive a restart
    # (they live in Redis), so the delay is a second line of defence, not the only one.
    SYNC_SCHEDULER_STARTUP_DELAY_SECONDS: int = 120
    # Requests held back from the scheduler so interactive page loads always have allowance left.
    # Capped at a tenth of the plan, so it can never freeze out a very small allowance.
    SYNC_SCHEDULER_BUDGET_RESERVE: int = 50

    # Fixture calendar: hours, not minutes. 6 club competitions x 3 days = 18 Live Score requests a
    # pass, 72/day at this interval against a 1,200/day budget. The national-team competitions are
    # asked for on top of that only on the days their coverage calendar says they play, bounded by
    # SYNC_FIXTURES_MAX_NATIONAL_REQUESTS_PER_PASS below.
    SYNC_FIXTURES_INTERVAL_SECONDS: int = 6 * 3600
    SYNC_FIXTURES_DAYS_AHEAD: int = 3  # today and the next two days
    # Live scores: one request a poll (matches/live.json), and only while a covered match is actually
    # in its live window. Matches the 60 s live cache TTL closely enough not to re-serve the same copy.
    SYNC_LIVE_INTERVAL_SECONDS: int = 120
    # Results: only the competitions that still have an unsettled match on a day cost anything, so
    # this is free on a quiet day and bounded by SYNC_RESULTS_MAX_REQUESTS_PER_PASS on a busy one.
    SYNC_RESULTS_INTERVAL_SECONDS: int = 1800
    SYNC_RESULTS_LOOKBACK_DAYS: int = 1  # today and yesterday

    # ---------------------------------------------- what national-team coverage may cost a pass
    # Three caps, one per task that can grow with the covered set. Each is a hard per-pass or
    # per-day bound rather than an average, so the day's worst case can be written down:
    #
    #   club fixtures      6 x 3 days x 4 passes                           =  72
    #   national fixtures  24 a pass x 4 passes                            =  96
    #   results            8 a pass x 48 passes                            = 384
    #   live               capped below                                    = 420
    #                      (the recovery pass's live poll spends out of this same ceiling)
    #   recovery           SYNC_RECOVERY_MAX_REQUESTS_PER_DAY              =  40
    #   calendars          the existing CALENDAR_HEAD_DAILY_REQUEST_CEILING = 120
    #                      (the coverage rotation spends out of this same share, not beside it)
    #                                                                       -----
    #                                                                       1,132
    #   + SYNC_SCHEDULER_BUDGET_RESERVE held back for page loads               50
    #                                                                       =====
    #                                                                       1,182  of 1,200
    #
    # These are SIMULTANEOUS worst cases, which is deliberately pessimistic: the live ceiling is
    # only reached on a day whose live windows run for fourteen hours, and the results cap is only
    # reached while sixteen competitions all hold an unsettled match at once, and a day is
    # unlikely to be both. A pass that does hit a cap defers national-team work to the next one -
    # half an hour for results, six hours for fixtures - and never defers a club competition.
    #
    # `tests/services/test_coverage_budget.py` asserts that sum against the plan, so a cap raised
    # here without the arithmetic being redone fails a test rather than quietly overrunning.

    # National-team competitions asked about per fixtures pass, across every day in the window.
    # An international break runs perhaps eight competitions at once - the confederations'
    # qualifiers, the two Nations Leagues, and National Teams Friendlies, which is one competition
    # holding the whole world's friendlies - so 24 covers eight of them across the whole 3-day
    # window with nothing deferred. Club competitions are never counted against this cap and never
    # deferred by it.
    SYNC_FIXTURES_MAX_NATIONAL_REQUESTS_PER_PASS: int = 24
    # Competitions asked for results per pass, over every day in the lookback. Clubs are served
    # first, then the national set rotated by pass number so none is always the one cut.
    SYNC_RESULTS_MAX_REQUESTS_PER_PASS: int = 8
    # Live polls per UTC day. 420 at a 120 s interval is 14 hours of continuously open live
    # windows, which no club matchday comes near; it binds only on a day when national fixtures
    # spread live windows across most of the clock. One poll covers every competition at once, so
    # this cannot starve one competition in favour of another - it bounds hours, not coverage.
    SYNC_LIVE_MAX_REQUESTS_PER_DAY: int = 420
    # Coverage calendars refreshed per fixtures pass, stalest first. 8 x 4 passes = 32/day covers
    # all 29 national-team competitions daily in the worst case where every one is due at once.
    SYNC_COVERAGE_CALENDAR_REFRESH_PER_PASS: int = 8
    # Allowance a provider must still have before a pass spends anything on national-team work.
    # Below it the pass serves the club six and nothing else: coverage degrades to what this
    # installation has always had rather than the club competitions going unfetched.
    SYNC_NATIONAL_TEAM_BUDGET_FLOOR: int = 250
    # ------------------------------------------------ getting back what an outage left stranded
    # A match whose final score never arrived falls out of every refresh: the live poll stops
    # considering it 150 minutes after kickoff (this application's polling window, not anything
    # measured about a provider), and the results task only looks back SYNC_RESULTS_LOOKBACK_DAYS
    # days. The recovery task goes and gets them unattended.
    #
    # WHAT IT ASKS, AND HOW OFTEN. Every competition is treated the same way. The archive has
    # answered for national-team competitions (World Cup, AFCON, Copa America, Women's World Cup),
    # and when asked on 2026-09-22 and 2026-09-25 it returned nothing dated 2026-09-18 or later for
    # club and national competitions alike, for reasons not yet known
    # (docs/evidence/livescore-archive-observations.json).
    # So a result may appear days late, and each unsettled fixture is asked about on RETRY_SCHEDULE
    # in match_registry.py: every pass for six hours, then every 2 h, 6 h, 12 h and 24 h as it ages,
    # stopping at 14 days. That is 39 requests per competition-day over a fortnight against an
    # archive that stays empty, and at most 4 a day once the day is behind the results lookback.
    # Stopping is a budget decision and is written on the row as one. Nothing asks about a stopped
    # match again on its own account; it is reopened only if a results request made later for
    # another unsettled match in the same competition returns results dated on or after its date.
    # A stop recorded by a rule since removed carries no `stopped_by`, and the recovery pass undoes
    # it and puts the match back on this schedule.
    #
    # Half an hour is how long a reader can be shown "LIVE, HT" after connectivity comes back. It
    # is a REPAIR rather than a refresh, so a pass that reaches no provider is reported as a
    # failure but does not back off - a six-hour backoff taken during an outage is how a fixture
    # stays wrong all night after the provider came back. See `_run_recovery`.
    SYNC_RECOVERY_INTERVAL_SECONDS: int = 1800
    # Results requests one recovery pass may make. One per competition holding a stranded fixture
    # on a reopened day; the day's ceiling below is the real bound and this stops a single pass
    # taking all of it. The pass's live poll is not counted here - it is charged to
    # SYNC_LIVE_MAX_REQUESTS_PER_DAY above, so recovery adds nothing to the day's live worst case.
    SYNC_RECOVERY_MAX_REQUESTS_PER_PASS: int = 4
    # Results requests the recovery task may spend in a UTC day, and the figure the plan above
    # adds up. 48 passes could otherwise spend 192. Every request that goes out is charged to it,
    # answered or not: a request that failed was still sent and still costs the provider's plan. Under the retry schedule a competition-day
    # behind the results lookback costs at most 4 a day, so 40 covers ten of them at once; a
    # competition-day the allowance cannot reach is deferred and stays due for a later pass. It
    # resets at UTC midnight with the provider's own allowance.
    SYNC_RECOVERY_MAX_REQUESTS_PER_DAY: int = 40

    #: Scoring reads stored data only, so it costs nothing and can run often. Ten minutes means a
    #: match that finished is scored within ten minutes of its result being ingested.
    SYNC_SETTLE_INTERVAL_SECONDS: int = 600
    #: How far back to look for matches that finished but were never scored (a restart, an outage).
    SYNC_SETTLE_LOOKBACK_DAYS: int = 3
    # Forecasts: ForecastService already enforces its own per-competition interval (24 h) and its own
    # daily allowance, so this only controls how often it is offered the chance to rotate.
    SYNC_FORECASTS_INTERVAL_SECONDS: int = 6 * 3600

    # Cache TTLs (seconds) for provider data
    MATCH_CACHE_TTL_FIXTURES: int = 1800
    MATCH_CACHE_TTL_LIVE: int = 60
    MATCH_CACHE_TTL_RESULTS: int = 1800
    MATCH_CACHE_TTL_STANDINGS: int = 3600
    MATCH_CACHE_TTL_COMPETITIONS: int = 86400
    
    # ML/AI Configuration
    ML_MODEL_PATH: str = "/app/ml/models"
    ML_ENABLED: bool = True
    
    # Feature Flags
    EXPERT_TOOLS_ENABLED: bool = True
    # Phase 1 product decision: expert predictions go live immediately (no mandatory admin approval).
    # Set to False to restore the review-queue workflow (predictions created as PENDING).
    EXPERT_DIRECT_PUBLISH: bool = True
    ADMIN_FEATURES_ENABLED: bool = True

    # May a record be classified as test data (and so excluded from measured performance)?
    #
    # OFF by default, and it must stay off anywhere real records are published: with it on, the
    # author of a prediction can ask for their own record to be left out of the leaderboard, which
    # is exactly the hole this setting exists to keep shut. It is turned on only where the records
    # genuinely are test data - a developer machine running the end-to-end suite - and it is a
    # deliberate opt-in rather than something inferred from ENVIRONMENT, so no deployment can
    # satisfy it by accident.
    #
    # The classification itself is always written server-side onto a column
    # (predictions.is_test_data). Nothing is ever inferred from the reasoning text.
    ALLOW_TEST_DATA_CLASSIFICATION: bool = False
    
    # Pagination
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100
    
    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # json or text
    
    # First Superuser (for initialization)
    FIRST_SUPERUSER_EMAIL: str = "admin@soccerpredictions.com"
    FIRST_SUPERUSER_PASSWORD: str = "changeme123"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


# Create settings instance
settings = Settings()

