"""Google Calendar OAuth token management."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from dgmt.utils.logging import get_logger

SCOPES = ["https://www.googleapis.com/auth/calendar"]

DEFAULT_TOKEN_DIR = Path.home() / ".dgmt" / "tokens"
DEFAULT_TOKEN_FILE = DEFAULT_TOKEN_DIR / "google_calendar_token.json"
DEFAULT_CREDENTIALS_FILE = Path.home() / ".dgmt" / "google_credentials.json"


class TokenManager:
    """Manages Google OAuth tokens for Calendar API access."""

    def __init__(
        self,
        token_path: Optional[Path] = None,
        credentials_path: Optional[Path] = None,
    ) -> None:
        self._token_path = token_path or DEFAULT_TOKEN_FILE
        self._credentials_path = credentials_path or DEFAULT_CREDENTIALS_FILE
        self._logger = get_logger("dgmt.calendar.auth")

    @property
    def token_path(self) -> Path:
        return self._token_path

    @property
    def credentials_path(self) -> Path:
        return self._credentials_path

    def get_credentials(self) -> Optional[Credentials]:
        """Get valid credentials, refreshing if needed."""
        creds = None

        if self._token_path.exists():
            creds = Credentials.from_authorized_user_file(str(self._token_path), SCOPES)

        if creds and creds.valid:
            return creds

        if creds and creds.expired and creds.refresh_token:
            self._logger.info("Refreshing expired token")
            creds.refresh(Request())
            self._save_token(creds)
            return creds

        return None

    def authorize(self) -> Credentials:
        """Run the OAuth flow to get new credentials."""
        if not self._credentials_path.exists():
            raise FileNotFoundError(
                f"Google OAuth credentials not found at {self._credentials_path}\n"
                "Download your OAuth client credentials from the Google Cloud Console\n"
                "and save them to this path."
            )

        flow = InstalledAppFlow.from_client_secrets_file(
            str(self._credentials_path), SCOPES
        )
        creds = flow.run_local_server(port=0)
        self._save_token(creds)
        self._logger.info("Authorization successful, token saved")
        return creds

    def revoke(self) -> bool:
        """Revoke and delete the stored token."""
        if self._token_path.exists():
            self._token_path.unlink()
            self._logger.info("Token revoked and deleted")
            return True
        self._logger.info("No token to revoke")
        return False

    def _save_token(self, creds: Credentials) -> None:
        """Save credentials to token file."""
        self._token_path.parent.mkdir(parents=True, exist_ok=True)
        self._token_path.write_text(creds.to_json())

    def get_or_authorize(self) -> Credentials:
        """Get existing credentials or run auth flow."""
        creds = self.get_credentials()
        if creds:
            return creds
        return self.authorize()
