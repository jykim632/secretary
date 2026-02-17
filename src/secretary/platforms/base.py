"""Base platform adapter interface."""

from abc import ABC, abstractmethod


class PlatformAdapter(ABC):
    """Interface that all platform bots must implement."""

    @abstractmethod
    async def start(self) -> None:
        """Start the bot (blocking)."""

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully stop the bot."""

    @abstractmethod
    async def send_message(self, platform_user_id: str, text: str) -> None:
        """Send a message to a specific user on this platform."""
