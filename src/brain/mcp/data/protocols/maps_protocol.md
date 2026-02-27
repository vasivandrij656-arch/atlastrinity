# GOOGLE MAPS & LOCATION PROTOCOL

## 1. CORE PHILOSOPHY

- **Visual Intelligence**: Maps are not just data; they are the "Spatial Eyes" of the system.
- **Cyberpunk Aesthetic**: All visual outputs (Static Maps, Street View) should default to `cyberpunk: true`.
- **User-Centric**: Always localize results to the user's focus area unless specified otherwise.

## 2. ADVANCED SEARCH DOCTRINE

- **Precision Filtering**: Do NOT just search for "restaurants". Use parameters:
  - `open_now: true` (Don't send user to closed places)
  - `min_price/max_price` (Respect budget if known)Test typing
  - `rankby: distance` (If proximity is key)

- **Radius**: Default is 5000m (5km). Adjust based on mode (Walking: 1000m, Driving: 10000m).
- **Type Safety**: Use the `type` parameter (e.g., `cafe`, `gym`) for cleaner results than keyword matching.

## 3. ROUTING & NAVIGATION

- **Multi-Stop**: If the user mentions "via" or multiple stops, use `waypoints`.
  - Format: `stop1|stop2`. The system optimizes the order automatically.
- **Alternatives**: ALWAYS set `alternatives: true` when planning a route to give the user choice (Fastest vs Shortest).
- **Traffic**: Route requests imply `departure_time: "now"` for live traffic data.
- **Avoidance**: Respect user preferences (e.g., "scenic route" -> probably avoid highways).

## 4. PLACE INTELLIGENCE

- **Deep Dive**: Use `maps_place_details` when the user asks specifically about _one_ place.
- **Field Optimization**: If you only need hours, request `fields: "opening_hours"`.
- **Language**: Default to Ukrainian (`language: "uk"`) for local description.

## 5. VISUALIZATION

- **Street View**: Use for confirmation ("Is this the right building?").
- **Static Map**: Use for high-level context ("Show me where these 3 places are").

## 6. INTERACTIVE UI

- **Hand-off**: If the user wants to _explore_, use `maps_open_interactive_search` to launch the frontend UI. Don't try to describe 50 pins verbally.

## 7. REAL-TIME VISUALIZATION DOCTRINE

- **Automatic Feedback**: Calculating routes or distances MUST trigger a visual response.
- **Overlay Information**: Display distance and duration data prominently on the map view using the established overlay components.
- **Seamless Transition**: The system should automatically switch to the Map View when new spatial data is computed to provide immediate context.
- **Cyberpunk Integration**: All overlays must match the established design language (JetBrains Mono, Neon Blue/Red).
