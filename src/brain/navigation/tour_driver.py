"""Tour Driver for Automated Virtual Navigation
Manages the "physical" movement of the agent through the virtual world (Street View).
Optimized with image prefetching for smooth tour experience.
"""

import asyncio
import math
import re
from dataclasses import dataclass

from src.brain.mcp.mcp_manager import mcp_manager  # pyre-ignore
from src.brain.monitoring.logger import logger  # pyre-ignore
from src.brain.navigation.map_state import map_state_manager  # pyre-ignore


@dataclass
class PrefetchedImage:
    """Represents a prefetched Street View image."""

    index: int
    lat: float
    lng: float
    heading: int
    image_path: str


class TourDriver:
    """Controls the automated navigation loop with image prefetching."""

    # Configuration
    PREFETCH_AHEAD = 3  # Number of images to prefetch ahead
    MAX_PREFETCH_CONCURRENT = 2  # Max concurrent prefetch requests

    def __init__(self) -> None:
        self.is_active = False
        self.is_paused = False
        self.current_route_points: list[tuple[float, float]] = []  # [(lat, lng)]
        self.current_step_index = 0
        self.speed_modifier = 1.0  # 0.5 = slow, 2.0 = fast
        self.base_step_duration = 2.0  # seconds between frames
        self.heading_offset = 0  # relative look direction (0 = forward, 90 = right)
        self._task: asyncio.Task | None = None
        self._prefetch_task: asyncio.Task | None = None

        # Prefetch buffer: stores ready-to-display images
        self._prefetch_buffer: dict[int, PrefetchedImage] = {}
        self._prefetch_lock = asyncio.Lock()
        self._prefetch_in_progress: set[int] = set()

    @property
    def progress(self) -> tuple[int, int]:
        """Returns (current_step, total_steps) for progress tracking."""
        return (self.current_step_index, len(self.current_route_points))

    @property
    def progress_percent(self) -> float:
        """Returns tour progress as percentage (0-100)."""
        if not self.current_route_points:
            return 0.0
        return (self.current_step_index / len(self.current_route_points)) * 100

    async def start_tour(self, route_polyline: str) -> None:
        """Start a tour along a polyline."""
        if self.is_active:
            await self.stop_tour()

        logger.info("[TourDriver] Starting tour...")
        map_state_manager.trigger_map_display()
        self.current_route_points = self._decode_polyline(route_polyline)

        if not self.current_route_points:
            logger.error("[TourDriver] Failed to decode polyline or empty route.")
            return

        logger.info(f"[TourDriver] Route decoded: {len(self.current_route_points)} points")

        self.is_active = True
        self.is_paused = False
        self.current_step_index = 0
        self.heading_offset = 0
        self._prefetch_buffer.clear()
        self._prefetch_in_progress.clear()

        # Start prefetching first images before drive loop
        await self._prefetch_initial_images()

        # Start the async drive loop and continuous prefetching
        self._task = asyncio.create_task(self._drive_loop())
        self._prefetch_task = asyncio.create_task(self._prefetch_loop())

    async def stop_tour(self) -> None:
        """Stop the tour completely."""
        self.is_active = False

        # Cancel prefetch task first
        if self._prefetch_task:
            self._prefetch_task.cancel()  # pyre-ignore
            try:
                await self._prefetch_task  # pyre-ignore
            except asyncio.CancelledError:
                pass
            self._prefetch_task = None

        if self._task:
            self._task.cancel()  # pyre-ignore
            try:
                await self._task  # pyre-ignore
            except asyncio.CancelledError:
                pass
            self._task = None

        # Clear prefetch buffer
        self._prefetch_buffer.clear()
        self._prefetch_in_progress.clear()

        logger.info("[TourDriver] Tour stopped.")

    def pause_tour(self) -> None:
        self.is_paused = True
        logger.info("[TourDriver] Tour paused.")

    def resume_tour(self) -> None:
        self.is_paused = False
        logger.info("[TourDriver] Tour resumed.")

    def look_around(self, angle: int) -> None:
        """Change relative viewing angle (e.g., -90 for left).
        Note: This invalidates prefetch buffer as heading changes.
        """
        old_offset = self.heading_offset
        self.heading_offset = angle

        # If heading changed significantly, clear prefetch buffer
        if abs(old_offset - angle) > 10:
            self._prefetch_buffer.clear()
            self._prefetch_in_progress.clear()
            logger.debug("[TourDriver] Cleared prefetch buffer due to heading change")

        # Trigger immediate update if paused
        if self.is_paused:
            asyncio.create_task(self._update_view_at_current_location())

    def set_speed(self, modifier: float) -> None:
        """Set speed modifier (0.5 to 3.0)."""
        self.speed_modifier = max(0.5, min(modifier, 3.0))
        logger.info(f"[TourDriver] Speed set to {self.speed_modifier}x")

    async def _prefetch_initial_images(self) -> None:
        """Prefetch first few images before starting the drive loop."""
        logger.info("[TourDriver] Prefetching initial images...")
        tasks = []
        for i in range(min(self.PREFETCH_AHEAD, len(self.current_route_points))):
            tasks.append(self._prefetch_single_image(i))
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info(f"[TourDriver] Prefetched {len(self._prefetch_buffer)} initial images")

    async def _prefetch_loop(self) -> None:
        """Continuous background prefetching loop."""
        try:
            while self.is_active:
                if self.is_paused:
                    await asyncio.sleep(0.5)
                    continue

                # Determine which indices need prefetching
                current = self.current_step_index
                needed_indices = []

                for offset in range(1, self.PREFETCH_AHEAD + 1):
                    idx = current + offset
                    if idx < len(self.current_route_points):
                        if (
                            idx not in self._prefetch_buffer
                            and idx not in self._prefetch_in_progress
                        ):
                            needed_indices.append(idx)

                # Limit concurrent prefetches
                needed_indices = needed_indices[: self.MAX_PREFETCH_CONCURRENT]  # pyre-ignore

                if needed_indices:
                    tasks = [self._prefetch_single_image(idx) for idx in needed_indices]
                    await asyncio.gather(*tasks, return_exceptions=True)

                # Clean up old buffer entries (behind current position)
                async with self._prefetch_lock:
                    old_keys = [k for k in self._prefetch_buffer if k < current - 1]
                    for k in old_keys:
                        del self._prefetch_buffer[k]  # pyre-ignore

                await asyncio.sleep(0.3)  # Small delay between prefetch checks

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[TourDriver] Prefetch loop error: {e}")

    async def _prefetch_single_image(self, index: int) -> None:
        """Prefetch a single image for the given route index."""
        if index in self._prefetch_buffer or index in self._prefetch_in_progress:
            return

        if index >= len(self.current_route_points):
            return

        self._prefetch_in_progress.add(index)

        try:
            lat, lng = self.current_route_points[index]

            # Calculate heading to next point
            next_lat, next_lng = lat, lng
            if index + 1 < len(self.current_route_points):
                next_lat, next_lng = self.current_route_points[index + 1]

            base_heading = self._calculate_bearing(lat, lng, next_lat, next_lng)
            final_heading = int((base_heading + self.heading_offset) % 360)

            location_str = f"{lat},{lng}"

            result = await mcp_manager.call_tool(
                "xcodebuild",
                "maps_street_view",
                {
                    "location": location_str,
                    "heading": final_heading,
                    "pitch": 0,
                    "fov": 90,
                    "cyberpunk": True,
                },
            )

            output_text = result.content[0].text if result.content else ""
            match = re.search(r"Saved to: (.+)", output_text)

            if match:
                image_path = match.group(1).strip()
                async with self._prefetch_lock:
                    self._prefetch_buffer[index] = PrefetchedImage(
                        index=index,
                        lat=lat,
                        lng=lng,
                        heading=final_heading,
                        image_path=image_path,
                    )
                logger.debug(f"[TourDriver] Prefetched image for step {index}")

        except Exception as e:
            logger.warning(f"[TourDriver] Prefetch failed for step {index}: {e}")
        finally:
            self._prefetch_in_progress.discard(index)

    async def _drive_loop(self) -> None:
        """Main navigation loop with prefetch utilization."""
        try:
            while self.is_active and self.current_step_index < len(self.current_route_points):
                if self.is_paused:
                    await asyncio.sleep(0.5)
                    continue

                # Try to use prefetched image first
                prefetched = self._prefetch_buffer.get(self.current_step_index)

                if prefetched:
                    # Use prefetched image - instant display!
                    map_state_manager.set_center(prefetched.lat, prefetched.lng)
                    map_state_manager.set_agent_view(
                        image_path=prefetched.image_path,
                        heading=prefetched.heading,
                        pitch=0,
                        fov=90,
                        lat=prefetched.lat,
                        lng=prefetched.lng,
                    )
                    logger.debug(
                        f"[TourDriver] Used prefetched image for step {self.current_step_index}"
                    )
                else:
                    # Fallback: fetch synchronously (slower path)
                    logger.debug(
                        f"[TourDriver] No prefetch for step {self.current_step_index}, fetching..."
                    )
                    await self._update_view_at_current_location()

                # Calculate variable sleep based on speed
                sleep_time = self.base_step_duration / self.speed_modifier
                await asyncio.sleep(sleep_time)

                self.current_step_index += 1

            logger.info("[TourDriver] Reached destination.")
            self.is_active = False

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception(f"[TourDriver] Error in drive loop: {e}")
            self.is_active = False

    async def _update_view_at_current_location(self) -> None:
        """Fetch and update the view for the current location (fallback path)."""
        if self.current_step_index >= len(self.current_route_points):
            return

        lat, lng = self.current_route_points[self.current_step_index]

        # Calculate heading to next point (if available)
        next_lat, next_lng = lat, lng
        if self.current_step_index + 1 < len(self.current_route_points):
            next_lat, next_lng = self.current_route_points[self.current_step_index + 1]

        # Determine base navigation heading
        base_heading = self._calculate_bearing(lat, lng, next_lat, next_lng)

        # Apply user look offset
        final_heading = (base_heading + self.heading_offset) % 360

        try:
            location_str = f"{lat},{lng}"

            result = await mcp_manager.call_tool(
                "xcodebuild",
                "maps_street_view",
                {
                    "location": location_str,
                    "heading": int(final_heading),
                    "pitch": 0,
                    "fov": 90,
                    "cyberpunk": True,
                },
            )

            output_text = result.content[0].text if result.content else ""
            match = re.search(r"Saved to: (.+)", output_text)
            if match:
                image_path = match.group(1).strip()
                map_state_manager.set_center(lat, lng)
                map_state_manager.set_agent_view(
                    image_path=image_path,
                    heading=int(final_heading),
                    pitch=0,
                    fov=90,
                    lat=lat,
                    lng=lng,
                )

        except Exception as e:
            logger.error(f"[TourDriver] Failed to fetch Street View: {e}")

    def _decode_polyline(self, polyline_str: str) -> list[tuple[float, float]]:
        """Decodes a Google Maps encoded polyline string."""
        points = []
        index = 0
        lat = 0
        lng = 0
        length = len(polyline_str)

        while index < length:
            b = 0
            shift = 0
            result = 0

            while True:
                if index >= length:
                    return points
                b = ord(polyline_str[index]) - 63  # pyre-ignore
                index += 1  # pyre-ignore
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break

            dlat = ~(result >> 1) if (result & 1) else (result >> 1)
            lat += dlat  # pyre-ignore

            shift = 0
            result = 0

            while True:
                if index >= length:
                    return points
                b = ord(polyline_str[index]) - 63  # pyre-ignore
                index += 1  # pyre-ignore
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break

            dlng = ~(result >> 1) if (result & 1) else (result >> 1)
            lng += dlng  # pyre-ignore

            points.append((lat * 1e-5, lng * 1e-5))

        return points

    def _calculate_bearing(self, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """Calculate bearing between two GPS points."""
        # If points are identical, keep previous heading or default to 0
        if lat1 == lat2 and lng1 == lng2:
            return 0.0

        y = math.sin(math.radians(lng2 - lng1)) * math.cos(math.radians(lat2))
        x = math.cos(math.radians(lat1)) * math.sin(math.radians(lat2)) - math.sin(
            math.radians(lat1)
        ) * math.cos(math.radians(lat2)) * math.cos(math.radians(lng2 - lng1))

        bearing = math.atan2(y, x)
        return (math.degrees(bearing) + 360) % 360


# Global instance
tour_driver = TourDriver()
