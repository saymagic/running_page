import argparse
import json
import os
import plistlib
import xml.etree.ElementTree as ET
import zipfile
from collections import namedtuple
from datetime import datetime, timedelta, timezone

from config import (
    BASE_TIMEZONE,
    JSON_FILE,
    OUTPUT_DIR,
    SQL_FILE,
    run_map,
    start_point,
)
from generator import Generator
from utils import adjust_time, make_activities_file

APPLE_HEALTH_EXPORT_ZIP = "apple_health_export"
APPLE_HEALTH_EXPORT_XML = "export.xml"
APPLE_HEALTH_CDA_XML = "export_cda.xml"


def _find_export_xml(directory):
    """Find the main Apple Health export XML in a directory.

    Apple Health exports use localized filenames (e.g. '导出.xml' in Chinese)
    instead of 'export.xml'. This function finds the main export XML regardless
    of locale by looking for any .xml file that isn't export_cda.xml.
    """
    candidate = os.path.join(directory, APPLE_HEALTH_EXPORT_XML)
    if os.path.exists(candidate):
        return candidate
    for fname in os.listdir(directory):
        if fname.endswith(".xml") and fname != APPLE_HEALTH_CDA_XML:
            return os.path.join(directory, fname)
    return None

WORKOUT_TYPE_MAP = {
    "HKWorkoutActivityTypeRunning": ("Run", "Run"),
    "HKWorkoutActivityTypeWalking": ("Walk", "Walk"),
    "HKWorkoutActivityTypeCycling": ("Ride", "Ride"),
    "HKWorkoutActivityTypeSwimming": ("Swim", "Swim"),
    "HKWorkoutActivityTypeHiking": ("Hiking", "Hiking"),
    "HKWorkoutActivityTypeDownhillSkiing": ("Skiing", "Skiing"),
    "HKWorkoutActivityTypeSnowboarding": ("Skiing", "Skiing"),
    "HKWorkoutActivityTypeCrossCountrySkiing": ("Skiing", "Skiing"),
    "HKWorkoutActivityTypeTreadmill": ("Run", "treadmill"),
    "HKWorkoutActivityTypeIndoorRunning": ("Run", "indoor"),
    "HKWorkoutActivityTypeIndoorCycling": ("Ride", "indoor"),
    "HKWorkoutActivityTypeIndoorWalking": ("Walk", "indoor"),
    "HKWorkoutActivityTypeYoga": ("Yoga", "indoor"),
    "HKWorkoutActivityTypeFunctionalStrengthTraining": ("StrengthTraining", "indoor"),
    "HKWorkoutActivityTypeTraditionalStrengthTraining": ("StrengthTraining", "indoor"),
    "HKWorkoutActivityTypeElliptical": ("Elliptical", "indoor"),
    "HKWorkoutActivityTypeRowing": ("Rowing", "indoor"),
    "HKWorkoutActivityTypeStairClimbing": ("StairClimbing", "indoor"),
    "HKWorkoutActivityTypeMindAndBody": ("MindAndBody", "indoor"),
    "HKWorkoutActivityTypeFlexibility": ("Flexibility", "indoor"),
    "HKWorkoutActivityTypeCoreTraining": ("CoreTraining", "indoor"),
    "HKWorkoutActivityTypeHighIntensityIntervalTraining": ("HIIT", "indoor"),
    "HKWorkoutActivityTypeJumpRope": ("JumpRope", "indoor"),
    "HKWorkoutActivityTypeDance": ("Dance", "indoor"),
    "HKWorkoutActivityTypeBarre": ("Barre", "indoor"),
    "HKWorkoutActivityTypePilates": ("Pilates", "indoor"),
    "HKWorkoutActivityTypeTaiChi": ("TaiChi", "indoor"),
    "HKWorkoutActivityTypeMixedCardio": ("Cardio", "indoor"),
    "HKWorkoutActivityTypeKickboxing": ("Kickboxing", "indoor"),
    "HKWorkoutActivityTypeWaterPolo": ("WaterPolo", "indoor"),
    "HKWorkoutActivityTypeSurfingSports": ("Surfing", "indoor"),
    "HKWorkoutActivityTypeOther": ("Other", "Other"),
}

DEFAULT_WORKOUT_TYPE = ("Other", "Other")

# Offset added to Apple Health IDs to avoid collision with Strava/Garmin IDs
# (which are typically < 10 digits). This ensures unique run_id values.
APPLE_HEALTH_ID_OFFSET = 9_000_000_000_000

HEALTH_KG_TO_M = 1.0
HEALTH_KM_TO_M = 1000.0
HEALTH_MI_TO_M = 1609.344


def _parse_apple_date(date_str):
    if not date_str:
        return None
    date_str = date_str.strip()
    for fmt in [
        "%Y-%m-%d %H:%M:%S %z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
    ]:
        try:
            dt = datetime.strptime(date_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _distance_to_meters(value_str, unit_str):
    if not value_str:
        return 0.0
    try:
        value = float(value_str)
    except (ValueError, TypeError):
        return 0.0
    unit_lower = (unit_str or "").lower()
    if "km" in unit_lower:
        return value * HEALTH_KM_TO_M
    elif "mi" in unit_lower:
        return value * HEALTH_MI_TO_M
    elif "m" in unit_lower and "km" not in unit_lower:
        return value
    return value


def _extract_route_from_plist(route_data):
    try:
        if isinstance(route_data, bytes):
            plist = plistlib.loads(route_data)
        elif isinstance(route_data, str):
            plist = plistlib.loads(route_data.encode("utf-8"))
        else:
            return []

        coordinates = []
        if isinstance(plist, dict):
            locations = plist.get("HKPrivateMetadataKeyWorkoutRouteLocations", [])
            if isinstance(locations, list):
                for loc in locations:
                    lat = loc.get(" latitude") or loc.get("latitude")
                    lon = loc.get(" longitude") or loc.get("longitude")
                    timestamp = loc.get(" timestamp") or loc.get("timestamp")
                    if lat is not None and lon is not None:
                        coordinates.append(
                            {
                                "lat": float(lat),
                                "lon": float(lon),
                                "timestamp": timestamp,
                            }
                        )

        if not coordinates:
            for key in plist:
                val = plist[key]
                if isinstance(val, list):
                    for item in val:
                        if isinstance(item, dict):
                            lat = item.get(" latitude") or item.get("latitude")
                            lon = item.get(" longitude") or item.get("longitude")
                            if lat is not None and lon is not None:
                                coordinates.append(
                                    {
                                        "lat": float(lat),
                                        "lon": float(lon),
                                        "timestamp": item.get(" timestamp")
                                        or item.get("timestamp"),
                                    }
                                )
                    if coordinates:
                        break
        return coordinates
    except Exception as e:
        print(f"  Warning: Failed to parse route plist: {e}")
        return []


def _build_polyline_from_route(route_coords):
    try:
        import polyline as polyline_codec
    except ImportError:
        print("  Error: 'polyline' package is required for route encoding.")
        print("  Install it with: pip install polyline")
        return ""

    if not route_coords or len(route_coords) < 2:
        return ""
    coords_list = [(c["lat"], c["lon"]) for c in route_coords]
    try:
        return polyline_codec.encode(coords_list)
    except Exception as e:
        print(f"  Warning: Failed to encode polyline: {e}")
        return ""


def _find_route_for_workout(workout_start, workout_end, route_map):
    if not route_map:
        return []

    w_start = workout_start.timestamp() if workout_start else 0
    w_end = workout_end.timestamp() if workout_end else float("inf")

    best_route = []
    best_overlap = 0

    for route_timestamp, route_coords in route_map.items():
        if not route_coords:
            continue
        first_ts = route_timestamp
        last_coord = route_coords[-1]
        last_ts_str = last_coord.get("timestamp", "")
        try:
            if isinstance(last_ts_str, str):
                last_ts_dt = _parse_apple_date(last_ts_str)
                last_ts = last_ts_dt.timestamp() if last_ts_dt else first_ts + 3600
            else:
                last_ts = first_ts + 3600
        except Exception:
            last_ts = first_ts + 3600

        overlap_start = max(w_start, first_ts)
        overlap_end = min(w_end, last_ts)
        overlap = max(0, overlap_end - overlap_start)

        if overlap > best_overlap:
            best_overlap = overlap
            best_route = route_coords

    return best_route


def parse_workout_route_xml(route_xml_path):
    routes = {}
    try:
        tree = ET.parse(route_xml_path)
        root = tree.getroot()
    except Exception as e:
        print(f"  Warning: Failed to parse workout route XML: {e}")
        return routes

    for record in root.iter("WorkoutRoute"):
        start_str = record.get("startDate", "")
        start_dt = _parse_apple_date(start_str)
        if not start_dt:
            continue

        coords = []
        for point in record.iter("Location"):
            lat = point.get("latitudeValue")
            lon = point.get("longitudeValue")
            if lat and lon:
                coords.append(
                    {
                        "lat": float(lat),
                        "lon": float(lon),
                        "timestamp": point.get("timestamp", ""),
                    }
                )

        if coords:
            routes[start_dt.timestamp()] = coords

    return routes


def parse_export_xml(export_path, output_dir, only_run=False):
    xml_path = export_path
    if os.path.isdir(export_path):
        found = _find_export_xml(export_path)
        if found:
            xml_path = found
        else:
            xml_path = os.path.join(export_path, APPLE_HEALTH_EXPORT_XML)
    if not os.path.exists(xml_path):
        raise FileNotFoundError(f"Apple Health export XML not found: {xml_path}")

    route_xml_path = os.path.join(os.path.dirname(xml_path), "workout-routes.xml")
    route_map = {}
    if os.path.exists(route_xml_path):
        print("Found workout-routes.xml, parsing routes...")
        route_map = parse_workout_route_xml(route_xml_path)
        print(f"  Loaded {len(route_map)} route entries")

    route_dir = os.path.join(os.path.dirname(xml_path), "workout-routes")
    if os.path.isdir(route_dir) and not route_map:
        print("Found workout-routes directory, parsing route files...")
        for fname in sorted(os.listdir(route_dir)):
            if fname.endswith(".gpx"):
                fpath = os.path.join(route_dir, fname)
                try:
                    import gpxpy
                except ImportError:
                    print("  Error: 'gpxpy' package is required for GPX route parsing.")
                    print("  Install it with: pip install gpxpy")
                    break
                try:
                    with open(fpath, "r") as f:
                        gpx = gpxpy.parse(f)
                    for track in gpx.tracks:
                        coords = []
                        for segment in track.segments:
                            for point in segment.points:
                                coords.append(
                                    {
                                        "lat": point.latitude,
                                        "lon": point.longitude,
                                        "timestamp": str(point.time),
                                    }
                                )
                        if coords and track.get_time_bounds().start_time:
                            route_map[
                                track.get_time_bounds().start_time.timestamp()
                            ] = coords
                except Exception as e:
                    print(f"  Warning: Failed to parse GPX route {fname}: {e}")

    print(f"Parsing Apple Health export: {xml_path}")
    tree = ET.parse(xml_path)
    root = tree.getroot()

    tracks = []
    workouts = root.iter("Workout")
    total = 0
    skipped = 0

    AppleHealthTrack = namedtuple(
        "AppleHealthTrack",
        [
            "id",
            "name",
            "type",
            "subtype",
            "start_date",
            "start_date_local",
            "distance",
            "moving_time",
            "elapsed_time",
            "average_heartrate",
            "average_speed",
            "map",
            "start_latlng",
            "elevation_gain",
            "location_country",
        ],
    )

    for workout in workouts:
        workout_type = workout.get("workoutActivityType", "")
        type_info = WORKOUT_TYPE_MAP.get(workout_type, DEFAULT_WORKOUT_TYPE)
        activity_type, subtype = type_info

        if only_run and activity_type != "Run":
            skipped += 1
            continue

        start_date_str = workout.get("startDate", "")
        end_date_str = workout.get("endDate", "")
        start_date = _parse_apple_date(start_date_str)
        end_date = _parse_apple_date(end_date_str)

        if not start_date:
            continue

        duration = 0.0
        duration_unit = workout.get("durationUnit", "min")
        workout_duration = workout.get("duration")
        if workout_duration:
            try:
                duration = float(workout_duration)
                if duration_unit == "min":
                    duration *= 60
                elif duration_unit == "hr":
                    duration *= 3600
            except ValueError:
                pass

        distance = 0.0
        avg_hr = None
        elevation_gain = 0.0
        source_name = ""

        for stat in workout.iter("WorkoutStatistics"):
            stat_type = stat.get("type", "")
            if "Distance" in stat_type:
                unit = stat.get("unit", "km")
                val = stat.get("sum") or stat.get("value", "0")
                distance = _distance_to_meters(val, unit)
            elif "HeartRate" in stat_type:
                avg_hr_val = stat.get("average") or stat.get("averageValue")
                if avg_hr_val:
                    try:
                        avg_hr = float(avg_hr_val)
                    except ValueError:
                        pass
            elif "Elevation" in stat_type or "FlightsClimbed" in stat_type:
                val = stat.get("sum") or stat.get("value", "0")
                unit = stat.get("unit", "m")
                try:
                    elevation_gain = _distance_to_meters(val, unit)
                except ValueError:
                    elevation_gain = 0.0

        pause_duration = 0.0
        for event in workout.iter("WorkoutEvent"):
            if event.get("type") == "HKWorkoutEventTypePause":
                event_start = _parse_apple_date(event.get("startDate", ""))
                event_end = _parse_apple_date(event.get("endDate", ""))
                if event_start and event_end:
                    pause_duration += (event_end - event_start).total_seconds()

        source = workout.find("Source")
        if source is not None:
            source_name = source.get("name", "")

        if distance < 1 and duration < 60:
            skipped += 1
            continue

        if duration == 0 and end_date and start_date:
            duration = (end_date - start_date).total_seconds()

        moving_duration = max(0.0, duration - pause_duration)
        moving_time = timedelta(seconds=int(moving_duration)) if moving_duration else timedelta(0)
        elapsed_time = (
            (end_date - start_date) if end_date and start_date else moving_time
        )

        # Convert to UTC for storage (consistent with other sync scripts)
        start_date_utc = start_date.astimezone(timezone.utc)
        end_date_utc = end_date.astimezone(timezone.utc) if end_date else None

        start_date_local = adjust_time(start_date_utc, BASE_TIMEZONE)
        end_date_local = adjust_time(end_date_utc, BASE_TIMEZONE) if end_date_utc else None

        route_coords = _find_route_for_workout(start_date, end_date, route_map)
        summary_polyline = _build_polyline_from_route(route_coords)

        start_latlng = None
        if route_coords:
            first = route_coords[0]
            start_latlng = start_point(lat=first["lat"], lon=first["lon"])

        activity_name = source_name or "Apple Watch"
        if "Watch" in source_name:
            activity_name = "run from Apple Watch"

        avg_speed = distance / moving_duration if moving_duration > 0 else 0.0

        run_id = int(start_date_utc.timestamp() * 1000) + APPLE_HEALTH_ID_OFFSET

        track = AppleHealthTrack(
            id=run_id,
            name=activity_name,
            type=activity_type,
            subtype=subtype,
            start_date=datetime.strftime(start_date_utc, "%Y-%m-%d %H:%M:%S"),
            start_date_local=datetime.strftime(
                start_date_local, "%Y-%m-%d %H:%M:%S"
            ),
            distance=distance,
            moving_time=moving_time,
            elapsed_time=elapsed_time,
            average_heartrate=avg_hr,
            average_speed=avg_speed,
            map=run_map(summary_polyline),
            start_latlng=start_latlng,
            elevation_gain=elevation_gain,
            location_country="",
        )
        tracks.append(track)
        total += 1

    print(f"Parsed {total} workouts from Apple Health export (skipped {skipped})")
    return tracks


def extract_zip(zip_path, extract_to=None):
    if extract_to is None:
        extract_to = os.path.dirname(zip_path)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_to)
    for root, _dirs, files in os.walk(extract_to):
        if _find_export_xml(root):
            return root
    return extract_to


def find_export_path(base_path):
    if os.path.isfile(base_path):
        if base_path.endswith(".zip"):
            print(f"Extracting zip archive: {base_path}")
            return extract_zip(base_path, os.path.dirname(base_path))
        elif base_path.endswith(".xml"):
            return base_path
        else:
            raise ValueError(f"Unsupported file format: {base_path}")

    if os.path.isdir(base_path):
        if _find_export_xml(base_path):
            return base_path

        inner_dir = os.path.join(base_path, "apple_health_export")
        if os.path.isdir(inner_dir) and _find_export_xml(inner_dir):
            return inner_dir

        for item in os.listdir(base_path):
            if item.endswith(".zip"):
                zip_path = os.path.join(base_path, item)
                print(f"Found zip archive: {zip_path}")
                return extract_zip(zip_path, base_path)

    raise FileNotFoundError(
        f"Could not find Apple Health export data at: {base_path}\n"
        "Please ensure you have exported your health data from:\n"
        "  iPhone > Health app > Profile (top right) > Export All Health Data\n"
        "Then place the export.zip or export.xml in the specified path."
    )


def run(export_path, only_run=False):
    resolved_path = find_export_path(export_path)

    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    tracks = parse_export_xml(resolved_path, OUTPUT_DIR, only_run=only_run)

    if not tracks:
        print("No workouts found in Apple Health export.")
        return

    generator = Generator(SQL_FILE)
    generator.sync_from_app(tracks)

    activities_list = generator.load()
    with open(JSON_FILE, "w") as f:
        json.dump(activities_list, f)

    print(f"Successfully synced {len(tracks)} Apple Health workouts")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Sync Apple Health (Apple Watch) workout data to running_page"
    )
    parser.add_argument(
        "export_path",
        help="Path to Apple Health export (zip file, xml file, or directory containing export.xml)",
    )
    parser.add_argument(
        "--only-run",
        dest="only_run",
        action="store_true",
        help="Only sync running activities",
    )
    options = parser.parse_args()
    run(options.export_path, options.only_run)
