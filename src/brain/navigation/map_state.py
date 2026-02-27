import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MapMarker:
    """Represents a map marker/POI"""

    id: str
    position: dict[str, float]  # {lat, lng}
    title: str
    type: str  # restaurant, hotel, attraction, custom, origin, destination
    data: dict[str, Any] = field(default_factory=dict)  # Additional place data
    icon: str | None = None
    color: str | None = None


@dataclass
class MapRoute:
    """Represents a navigation route"""

    id: str
    origin: dict[str, float]  # {lat, lng}
    destination: dict[str, float]  # {lat, lng}
    polyline: str  # Encoded polyline
    distance: str
    duration: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    mode: str = "driving"  # driving, walking, transit, bicycle


@dataclass
class MapState:
    """Global map state"""

    markers: list[MapMarker] = field(default_factory=list)
    routes: list[MapRoute] = field(default_factory=list)
    active_place: dict[str, Any] | None = None
    center: dict[str, float] = field(default_factory=lambda: {"lat": 50.4501, "lng": 30.5234})
    zoom: int = 12
    map_type: str = "roadmap"  # roadmap, satellite, hybrid, terrain
    layers: list[str] = field(default_factory=list)  # traffic, transit, bicycle
    agent_view: dict[str, Any] | None = None  # {image_path, heading, pitch, fov}
    distance_info: dict[str, Any] | None = None  # {distance, duration, origin, destination}
    show_map: bool = False  # Flag to trigger map display in frontend


class MapStateManager:
    """Singleton manager for map state"""

    def __init__(self):
        self.state = MapState()
        self._marker_counter = 0
        self._route_counter = 0

    def add_marker(
        self,
        position: dict[str, float],
        title: str,
        marker_type: str = "custom",
        data: dict[str, Any] | None = None,
        icon: str | None = None,
        color: str | None = None,
    ) -> MapMarker:
        """Add a new marker to the map"""
        self._marker_counter += 1
        marker = MapMarker(
            id=f"marker-{self._marker_counter}",
            position=position,
            title=title,
            type=marker_type,
            data=data or {},
            icon=icon,
            color=color,
        )
        self.state.markers.append(marker)
        return marker

    def add_route(
        self,
        origin: dict[str, float],
        destination: dict[str, float],
        polyline: str,
        distance: str,
        duration: str,
        steps: list[dict[str, Any]] | None = None,
        mode: str = "driving",
    ) -> MapRoute:
        """Add a navigation route"""
        self._route_counter += 1
        route = MapRoute(
            id=f"route-{self._route_counter}",
            origin=origin,
            destination=destination,
            polyline=polyline,
            distance=distance,
            duration=duration,
            steps=steps or [],
            mode=mode,
        )
        self.state.routes.append(route)
        return route

    def clear_markers(self):
        """Remove all markers"""
        self.state.markers = []

    def clear_routes(self):
        """Remove all routes"""
        self.state.routes = []

    def clear_all(self):
        """Reset entire map state"""
        self.state = MapState()
        self._marker_counter = 0
        self._route_counter = 0

    def set_center(self, lat: float, lng: float, zoom: int | None = None):
        """Update map center and optional zoom"""
        self.state.center = {"lat": lat, "lng": lng}
        if zoom is not None:
            self.state.zoom = zoom

    def set_active_place(self, place_data: dict[str, Any] | None):
        """Set the currently active/selected place"""
        self.state.active_place = place_data

    def set_agent_view(
        self,
        image_path: str,
        heading: int,
        pitch: int,
        fov: int,
        lat: float | None = None,
        lng: float | None = None,
    ):
        """Update the agent's current visual perspective"""
        self.state.agent_view = {

            "image_path": image_path,
            "heading": heading,
            "pitch": pitch,
            "fov": fov,
            "timestamp": time.time(),
            "lat": lat,
            "lng": lng,
        }
        self.state.show_map = True


    def set_distance_info(
        self,
        distance: str | None = None,
        duration: str | None = None,
        origin: str | None = None,
        destination: str | None = None,
        trigger_display: bool = True,
    ):
        """Set distance/duration info for overlay display"""
        self.state.distance_info = {

            "distance": distance,
            "duration": duration,
            "origin": origin,
            "destination": destination,
            "timestamp": time.time(),
        }

        if trigger_display:
            self.state.show_map = True

    def clear_distance_info(self):
        """Clear distance overlay"""
        self.state.distance_info = None

    def trigger_map_display(self):
        """Signal frontend to show map view"""
        self.state.show_map = True

    def reset_map_trigger(self):
        """Reset the show_map flag after frontend has processed it"""
        self.state.show_map = False

    def to_dict(self) -> dict[str, Any]:
        """Convert state to dictionary for JSON serialization"""
        return {
            "markers": [
                {
                    "id": m.id,
                    "position": m.position,
                    "title": m.title,
                    "type": m.type,
                    "data": m.data,
                    "icon": m.icon,
                    "color": m.color,
                }
                for m in self.state.markers
            ],
            "routes": [
                {
                    "id": r.id,
                    "origin": r.origin,
                    "destination": r.destination,
                    "polyline": r.polyline,
                    "distance": r.distance,
                    "duration": r.duration,
                    "steps": r.steps,
                    "mode": r.mode,
                }
                for r in self.state.routes
            ],
            "active_place": self.state.active_place,
            "center": self.state.center,
            "zoom": self.state.zoom,
            "map_type": self.state.map_type,
            "layers": self.state.layers,
            "agent_view": self.state.agent_view,
            "distance_info": self.state.distance_info,
            "show_map": self.state.show_map,
        }


# Global singleton instance
map_state_manager = MapStateManager()
